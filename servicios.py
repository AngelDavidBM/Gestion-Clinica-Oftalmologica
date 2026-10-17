"""Servicios que implementan las reglas de negocio."""

from datetime import date, datetime, time, timedelta
import re

from config import DIAS_LABORALES, DURACION_BLOQUE_MINUTOS, HORA_FIN_MANANA, HORA_FIN_TARDE, HORA_INICIO_MANANA, HORA_INICIO_TARDE, MAX_CITAS_POR_DIA
from enums import EstadoCita, EstadoPago, EstadoUsuario, Rol
from excepciones import AccesoFueraDeSedError, CampoObligatorioError, ConfirmacionRequeridaError, CredencialesInvalidasError, DuplicidadRegistroError, FormatoInvalidoError, HorarioFueraDeJornadaError, LimiteDiarioAlcanzadoError, MedicoConCitasFuturaError, MenorDeEdadSinAcudienteError, SobreasignacionMedicoError, TransicionEstadoInvalidaError, UsuarioInactivoError
from modelos import CitaMedica, Medico, Paciente, RegistroAuditoria, RegistroListaEspera, Sede, Usuario
from repositorios import IAuditoriaRepository, ICitaRepository, IListaEsperaRepository, ISedeRepository, IUsuarioRepository


class AutenticacionService:
    """Gestiona el acceso y registro de pacientes."""
    def __init__(self, usuario_repo: IUsuarioRepository) -> None:
        """Recibe el repositorio de usuarios."""
        self.usuario_repo = usuario_repo

    def login(self, correo: str, contrasena: str) -> Usuario:
        """Autentica un usuario y valida su estado."""
        usuario = self.usuario_repo.buscar_por_correo(correo)
        if usuario is None:
            raise CredencialesInvalidasError("Usuario no encontrado")
        if not usuario.autenticar(correo, contrasena):
            raise CredencialesInvalidasError("Credenciales inválidas")
        if usuario.estado in (EstadoUsuario.INACTIVO, EstadoUsuario.BLOQUEADO):
            raise UsuarioInactivoError("Su cuenta se encuentra inactiva o bloqueada")
        return usuario

    def obtener_ruta_redireccion(self, usuario: Usuario) -> str:
        """Obtiene el tablero correspondiente al rol del usuario."""
        if usuario.rol == Rol.PACIENTE:
            return "/dashboard/paciente"
        if usuario.rol == Rol.SECRETARIA:
            return "/dashboard/secretaria"
        return f"/dashboard/administrador/{usuario.id_sede}"

    def registrar_paciente(self, paciente: Paciente) -> bool:
        """Registra un paciente aplicando las validaciones ordenadas."""
        if not all([paciente.numero_documento.strip(), paciente.nombres.strip(), paciente.apellidos.strip(), paciente.telefono.strip(), paciente.correo.strip(), paciente.contrasena.strip()]):
            raise CampoObligatorioError("Todos los campos obligatorios deben estar diligenciados")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", paciente.correo):
            raise FormatoInvalidoError("El formato del correo es inválido")
        if not paciente.numero_documento.isdigit() or len(paciente.numero_documento) > 10:
            raise FormatoInvalidoError("El documento debe ser numérico y tener máximo 10 dígitos")
        if not paciente.telefono.isdigit():
            raise FormatoInvalidoError("El teléfono debe contener únicamente dígitos")
        if paciente.fecha_nacimiento > date.today():
            raise FormatoInvalidoError("La fecha de nacimiento no puede ser posterior a la fecha actual")
        if self.usuario_repo.existe_documento_o_correo(paciente.numero_documento, paciente.correo):
            raise DuplicidadRegistroError("El documento o correo ya está registrado")
        if paciente.es_menor_de_edad() and (not paciente.nombre_acudiente.strip() or not paciente.telefono_acudiente.strip()):
            raise MenorDeEdadSinAcudienteError("Los menores de edad requieren nombre y teléfono de acudiente")
        paciente.estado = EstadoUsuario.ACTIVO
        paciente._registrar_actualizacion()
        return self.usuario_repo.guardar(paciente)


class AgendamientoService:
    """Gestiona disponibilidad, agenda y lista de espera."""
    def __init__(self, cita_repo: ICitaRepository, usuario_repo: IUsuarioRepository, lista_espera_repo: IListaEsperaRepository) -> None:
        """Recibe repositorios de citas y usuarios."""
        self.cita_repo, self.usuario_repo, self.lista_espera_repo = cita_repo, usuario_repo, lista_espera_repo

    def consultar_bloques_disponibles(self, id_sede: str, id_medico: str, fecha: date) -> list[datetime]:
        """Genera los bloques libres de un médico de la sede indicada.

        Parámetros:
            id_sede: Identificador de la sede consultada.
            id_medico: Identificador del especialista.
            fecha: Fecha a consultar.
        Retorna:
            Bloques de horario no reservados.
        """
        medico = self._validar_medico_en_sede(id_medico, id_sede)
        if fecha.weekday() not in DIAS_LABORALES:
            return []
        bloques = []
        for inicio, fin in ((medico.hora_inicio_manana, medico.hora_fin_manana), (medico.hora_inicio_tarde, medico.hora_fin_tarde)):
            instante = datetime.combine(fecha, inicio)
            limite = datetime.combine(fecha, fin)
            while instante < limite:
                if not self.cita_repo.existe_cita_en_horario(id_medico, instante):
                    bloques.append(instante)
                instante += timedelta(minutes=DURACION_BLOQUE_MINUTOS)
        return bloques

    def consultar_bloques_del_dia(self, id_sede: str, id_medico: str, fecha: date) -> list[dict]:
        """Genera todos los bloques de la jornada de un médico, marcando los ya ocupados.

        Parámetros:
            id_sede: Identificador de la sede consultada.
            id_medico: Identificador del especialista.
            fecha: Fecha a consultar.
        Retorna:
            Bloques de horario del día con su hora y si están ocupados.
        """
        medico = self._validar_medico_en_sede(id_medico, id_sede)
        if fecha.weekday() not in DIAS_LABORALES:
            return []
        bloques = []
        for inicio, fin in ((medico.hora_inicio_manana, medico.hora_fin_manana), (medico.hora_inicio_tarde, medico.hora_fin_tarde)):
            instante = datetime.combine(fecha, inicio)
            limite = datetime.combine(fecha, fin)
            while instante < limite:
                bloques.append({"hora": instante, "ocupado": self.cita_repo.existe_cita_en_horario(id_medico, instante)})
                instante += timedelta(minutes=DURACION_BLOQUE_MINUTOS)
        return bloques

    def _validar_medico_en_sede(self, id_medico: str, id_sede: str) -> Medico:
        """Verifica que un especialista activo pertenezca a la sede indicada.

        Parámetros:
            id_medico: Identificador del médico.
            id_sede: Identificador de la sede.
        Retorna:
            Médico validado.
        """
        medico = self.usuario_repo.buscar_por_id(id_medico)
        if not isinstance(medico, Medico):
            raise CampoObligatorioError("El especialista seleccionado no existe")
        if medico.estado != EstadoUsuario.ACTIVO:
            raise UsuarioInactivoError("El especialista seleccionado se encuentra inactivo")
        if medico.id_sede != id_sede:
            raise AccesoFueraDeSedError("El especialista seleccionado no pertenece a la sede indicada")
        return medico

    def solicitar_confirmacion_cancelacion(self, id_cita: str) -> dict:
        """Devuelve los datos de una cita sin modificarla."""
        cita = self.cita_repo.buscar_por_id(id_cita)
        if cita is None:
            raise CampoObligatorioError("La cita solicitada no existe")
        paciente, medico = self.usuario_repo.buscar_por_id(cita.id_paciente), self.usuario_repo.buscar_por_id(cita.id_medico)
        return {"id_cita": cita.id, "id_paciente": cita.id_paciente, "nombre_paciente": f"{paciente.nombres} {paciente.apellidos}", "id_medico": cita.id_medico, "nombre_medico": f"{medico.nombres} {medico.apellidos}", "fecha_hora": cita.fecha_hora, "tipo_consulta": cita.tipo_consulta, "estado_cita": cita.estado_cita}

    def cancelar_cita(self, id_cita: str, motivo: str, confirmado: bool) -> bool:
        """Cancela una cita solo tras confirmación expresa."""
        if not confirmado:
            raise ConfirmacionRequeridaError("Debe confirmar la cancelación de la cita")
        if not motivo.strip():
            raise CampoObligatorioError("El motivo de cancelación es obligatorio")
        cita = self.cita_repo.buscar_por_id(id_cita)
        if cita is None:
            raise CampoObligatorioError("La cita solicitada no existe")
        cita.cancelar(motivo)
        return self.cita_repo.guardar(cita)

    def confirmar_cita(self, id_cita: str) -> bool:
        """Confirma una cita que se encuentra programada.

        Parámetros:
            id_cita: Identificador de la cita.
        Retorna:
            Verdadero cuando se confirma la cita.
        """
        cita = self.cita_repo.buscar_por_id(id_cita)
        if cita is None:
            raise CampoObligatorioError("La cita solicitada no existe")
        if cita.estado_cita != EstadoCita.PROGRAMADA:
            raise TransicionEstadoInvalidaError(f"No es posible pasar de {cita.estado_cita.value} a CONFIRMADA")
        cita.estado_cita = EstadoCita.CONFIRMADA
        return self.cita_repo.guardar(cita)

    def registrar_atencion(self, id_cita: str, observaciones: str) -> bool:
        """Registra la atención clínica de una cita confirmada.

        Parámetros:
            id_cita: Identificador de la cita.
            observaciones: Notas de atención.
        Retorna:
            Verdadero cuando se registra la atención.
        """
        cita = self.cita_repo.buscar_por_id(id_cita)
        if cita is None:
            raise CampoObligatorioError("La cita solicitada no existe")
        cita.registrar_atencion(observaciones)
        return self.cita_repo.guardar(cita)

    def _validar_horario(self, cita: CitaMedica, excluir_id: str | None = None) -> None:
        """Valida un horario de cita conforme a las reglas de agenda."""
        fecha_hora = cita.fecha_hora
        medico = self._validar_medico_en_sede(cita.id_medico, cita.id_sede)
        en_jornada = fecha_hora.weekday() in DIAS_LABORALES and ((medico.hora_inicio_manana <= fecha_hora.time() < medico.hora_fin_manana) or (medico.hora_inicio_tarde <= fecha_hora.time() < medico.hora_fin_tarde)) and fecha_hora.minute in (0, 30) and fecha_hora.second == 0
        if not en_jornada:
            raise HorarioFueraDeJornadaError("El horario está fuera de la jornada laboral")
        conflictos_medico = self.cita_repo.existe_cita_en_horario(cita.id_medico, fecha_hora)
        conflictos_paciente = self.cita_repo.existe_cita_paciente_en_horario(cita.id_paciente, fecha_hora)
        if excluir_id:
            anterior = self.cita_repo.buscar_por_id(excluir_id)
            if anterior and anterior.fecha_hora == fecha_hora:
                conflictos_medico = conflictos_paciente = False
        if conflictos_medico:
            raise SobreasignacionMedicoError("El médico ya tiene una cita en ese horario")
        limite_medico = getattr(medico, "max_citas_dia", MAX_CITAS_POR_DIA)
        cantidad = self.cita_repo.contar_citas_medico_en_fecha(cita.id_medico, fecha_hora.date())
        if excluir_id:
            anterior = self.cita_repo.buscar_por_id(excluir_id)
            if anterior and anterior.id_medico == cita.id_medico and anterior.fecha_hora.date() == fecha_hora.date():
                cantidad -= 1
        if cantidad >= limite_medico:
            raise LimiteDiarioAlcanzadoError(f"El médico alcanzó su límite de {limite_medico} citas para el día seleccionado")
        if conflictos_paciente:
            raise SobreasignacionMedicoError("El paciente ya tiene una cita en ese horario")
        paciente = self.usuario_repo.buscar_por_id(cita.id_paciente)
        if isinstance(paciente, Paciente) and paciente.es_menor_de_edad() and (not paciente.nombre_acudiente.strip() or not paciente.telefono_acudiente.strip()):
            raise MenorDeEdadSinAcudienteError("El paciente menor de edad requiere acudiente")

    def agendar_cita(self, cita: CitaMedica) -> bool:
        """Agenda una nueva cita tras validar el horario."""
        self._validar_medico_en_sede(cita.id_medico, cita.id_sede)
        self._validar_horario(cita)
        cita.estado_cita, cita.estado_pago = EstadoCita.PROGRAMADA, EstadoPago.PENDIENTE
        return self.cita_repo.guardar(cita)

    def reagendar_cita(self, id_cita: str, nueva_fecha_hora: datetime) -> bool:
        """Reagenda una cita aplicando las validaciones al nuevo horario."""
        cita = self.cita_repo.buscar_por_id(id_cita)
        if cita is None:
            raise CampoObligatorioError("La cita solicitada no existe")
        if cita.estado_cita in (EstadoCita.ATENDIDA, EstadoCita.CANCELADA):
            raise TransicionEstadoInvalidaError(f"No es posible pasar de {cita.estado_cita.value} a PROGRAMADA")
        copia = CitaMedica(cita.id_paciente, cita.id_medico, cita.id_sede, nueva_fecha_hora, cita.tipo_consulta)
        self._validar_horario(copia, cita.id)
        cita.reagendar(nueva_fecha_hora)
        return self.cita_repo.guardar(cita)

    def agregar_a_lista_espera(self, registro: RegistroListaEspera) -> None:
        """Añade una solicitud de paciente a la lista de espera.

        Parámetros:
            registro: Solicitud de espera que se va a conservar.
        Retorna:
            Ninguno.
        """
        paciente = self.usuario_repo.buscar_por_id(registro.id_paciente)
        if not isinstance(paciente, Paciente):
            raise CampoObligatorioError("El paciente seleccionado no existe")
        self.lista_espera_repo.guardar(registro)

    def buscar_registro_espera(self, id_registro: str) -> RegistroListaEspera:
        """Busca una solicitud vigente en la lista de espera.

        Parámetros:
            id_registro: Identificador de la solicitud.
        Retorna:
            Solicitud encontrada.
        """
        registro = self.lista_espera_repo.buscar_por_id(id_registro)
        if registro is None:
            raise CampoObligatorioError("La solicitud de lista de espera no existe o ya fue gestionada")
        return registro

    def retirar_de_lista_espera(self, id_registro: str, confirmado: bool) -> bool:
        """Retira una solicitud de la lista de espera tras confirmación expresa.

        Parámetros:
            id_registro: Identificador de la solicitud.
            confirmado: Confirmación explícita de la eliminación.
        Retorna:
            Verdadero cuando la solicitud se retira.
        """
        if not confirmado:
            raise ConfirmacionRequeridaError("Debe confirmar el retiro de la solicitud de la lista de espera")
        registro = self.buscar_registro_espera(id_registro)
        self.lista_espera_repo.eliminar(registro.id)
        return True

    def promover_lista_espera(self, id_registro: str, id_medico: str, fecha_hora: datetime) -> CitaMedica:
        """Convierte una solicitud en espera en una cita agendada.

        Parámetros:
            id_registro: Identificador de la solicitud en espera.
            id_medico: Especialista que atenderá la cita.
            fecha_hora: Bloque liberado que se asigna a la solicitud.
        Retorna:
            Cita creada a partir de la solicitud.
        """
        registro = self.buscar_registro_espera(id_registro)
        cita = CitaMedica(registro.id_paciente, id_medico, registro.id_sede, fecha_hora, registro.tipo_consulta)
        self.agendar_cita(cita)
        self.lista_espera_repo.eliminar(registro.id)
        return cita

    def obtener_lista_espera(self) -> list[RegistroListaEspera]:
        """Obtiene las solicitudes de lista de espera registradas.

        Retorna:
            Copia de las solicitudes en espera.
        """
        return self.lista_espera_repo.obtener_todas()


class SecretariaService:
    """Provee operaciones globales para secretaría."""
    def __init__(self, usuario_repo: IUsuarioRepository, cita_repo: ICitaRepository) -> None:
        """Recibe los repositorios necesarios."""
        self.usuario_repo, self.cita_repo = usuario_repo, cita_repo
    def obtener_usuarios_activos(self) -> list[Usuario]:
        """Retorna todos los usuarios activos sin filtro de sede."""
        return self.usuario_repo.obtener_activos()
    def buscar_paciente(self, termino: str) -> list[Usuario]:
        """Busca pacientes por documento o nombres."""
        return [u for u in self.usuario_repo.buscar_por_documento_o_nombre(termino) if u.rol == Rol.PACIENTE]

    def resolver_paciente(self, identificador: str) -> Usuario:
        """Resuelve un paciente por UUID, documento o nombre único.

        Parámetros:
            identificador: UUID, documento o nombre ingresado por secretaría.
        Retorna:
            Paciente encontrado.
        """
        termino = identificador.strip()
        if not termino:
            raise CampoObligatorioError("Debe ingresar el documento, nombre o identificador del paciente")
        usuario = self.usuario_repo.buscar_por_id(termino) or self.usuario_repo.buscar_por_documento(termino)
        if usuario is not None and usuario.rol == Rol.PACIENTE:
            return usuario
        coincidencias = self.buscar_paciente(termino)
        if not coincidencias:
            raise CampoObligatorioError("No se encontró un paciente con el dato ingresado")
        if len(coincidencias) > 1:
            raise CampoObligatorioError("Se encontraron varios pacientes; use el número de documento o seleccione uno de la búsqueda")
        return coincidencias[0]

    def actualizar_acudiente_menor(self, paciente: Usuario, nombre_acudiente: str, telefono_acudiente: str) -> None:
        """Registra los datos del acudiente requeridos antes de agendar un menor."""
        if not isinstance(paciente, Paciente) or not paciente.es_menor_de_edad():
            return
        if not nombre_acudiente.strip() or not telefono_acudiente.strip():
            raise MenorDeEdadSinAcudienteError("Debe registrar nombre y teléfono del acudiente para agendar a un menor de edad")
        if not telefono_acudiente.isdigit():
            raise FormatoInvalidoError("El teléfono del acudiente debe contener únicamente dígitos")
        paciente.nombre_acudiente, paciente.telefono_acudiente = nombre_acudiente.strip(), telefono_acudiente.strip()
        paciente._registrar_actualizacion()
        self.usuario_repo.guardar(paciente)

    def obtener_historial_paciente(self, id_paciente: str, solo_atendidas: bool = False, orden: str = "desc") -> list[CitaMedica]:
        """Obtiene el historial de citas de un paciente con orden configurable.

        Parámetros:
            id_paciente: Identificador del paciente consultado.
            solo_atendidas: Cuando es verdadero limita el historial a citas atendidas.
            orden: Texto "asc" para orden ascendente por fecha; cualquier otro valor ordena de forma descendente.
        Retorna:
            Citas del paciente ordenadas por fecha.
        """
        paciente = self.usuario_repo.buscar_por_id(id_paciente)
        if not isinstance(paciente, Paciente):
            raise CampoObligatorioError("El paciente consultado no existe")
        citas = self.cita_repo.obtener_por_paciente(id_paciente)
        if solo_atendidas:
            citas = [cita for cita in citas if cita.estado_cita == EstadoCita.ATENDIDA]
        return sorted(citas, key=lambda cita: cita.fecha_hora, reverse=orden != "asc")

    def actualizar_datos_paciente(self, id_paciente: str, telefono: str, correo: str, nombre_acudiente: str, telefono_acudiente: str) -> bool:
        """Actualiza los datos de contacto de un paciente y registra el sello de modificación.

        Parámetros:
            id_paciente: Identificador del paciente.
            telefono: Teléfono de contacto nuevo.
            correo: Correo electrónico nuevo.
            nombre_acudiente: Nombre del acudiente.
            telefono_acudiente: Teléfono del acudiente.
        Retorna:
            Verdadero cuando los datos quedan actualizados.
        """
        paciente = self.usuario_repo.buscar_por_id(id_paciente)
        if not isinstance(paciente, Paciente):
            raise CampoObligatorioError("El paciente consultado no existe")
        if not telefono.strip() or not correo.strip():
            raise CampoObligatorioError("El teléfono y el correo son obligatorios")
        if not telefono.isdigit():
            raise FormatoInvalidoError("El teléfono debe contener únicamente dígitos")
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", correo):
            raise FormatoInvalidoError("El formato del correo es inválido")
        if telefono_acudiente.strip() and not telefono_acudiente.isdigit():
            raise FormatoInvalidoError("El teléfono del acudiente debe contener únicamente dígitos")
        if paciente.es_menor_de_edad() and (not nombre_acudiente.strip() or not telefono_acudiente.strip()):
            raise MenorDeEdadSinAcudienteError("Los menores de edad requieren nombre y teléfono de acudiente")
        existente = self.usuario_repo.buscar_por_correo(correo)
        if existente is not None and existente.id != paciente.id:
            raise DuplicidadRegistroError("El correo ya está registrado por otro usuario")
        paciente.actualizar_datos_personales(telefono.strip(), correo.strip(), nombre_acudiente.strip(), telefono_acudiente.strip())
        return self.usuario_repo.guardar(paciente)

    def anular_cobro(self, id_cita: str, confirmado: bool) -> bool:
        """Anula un pago registrado, preservando la cita y su trazabilidad."""
        if not confirmado:
            raise ConfirmacionRequeridaError("Debe confirmar la anulación del pago")
        cita = self.cita_repo.buscar_por_id(id_cita)
        if cita is None:
            raise CampoObligatorioError("La cita solicitada no existe")
        if cita.estado_pago != EstadoPago.PAGADO:
            raise TransicionEstadoInvalidaError("Solo es posible anular un pago en estado PAGADO")
        cita.estado_pago = EstadoPago.ANULADO
        return self.cita_repo.guardar(cita)


class AdministradorService:
    """Gestiona los recursos restringidos a la sede administrativa."""
    def __init__(self, usuario_repo: IUsuarioRepository, cita_repo: ICitaRepository) -> None:
        """Recibe los repositorios necesarios."""
        self.usuario_repo, self.cita_repo = usuario_repo, cita_repo
    def _verificar_sede(self, usuario: Usuario | None, id_sede_sesion: str) -> None:
        """Verifica que un recurso pertenezca a la sede de sesión."""
        if usuario is None or getattr(usuario, "id_sede", None) != id_sede_sesion:
            raise AccesoFueraDeSedError("No tiene acceso a recursos de otra sede")
    def registrar_medico(self, medico: Medico, id_sede_sesion: str) -> bool:
        """Registra un médico únicamente en la sede de sesión."""
        self._verificar_sede(medico, id_sede_sesion)
        if not medico.numero_documento.isdigit() or len(medico.numero_documento) > 10:
            raise FormatoInvalidoError("El documento debe ser numérico y tener máximo 10 dígitos")
        if not medico.telefono.isdigit():
            raise FormatoInvalidoError("El teléfono debe contener únicamente dígitos")
        if self.usuario_repo.existe_documento_o_correo(medico.numero_documento, medico.correo):
            raise DuplicidadRegistroError("El documento o correo ya está registrado")
        return self.usuario_repo.guardar(medico)
    def registrar_usuario_interno(self, usuario: Usuario, id_sede_sesion: str) -> bool:
        """Registra una secretaria global o un administrador para la sede administrada."""
        if usuario.rol == Rol.ADMINISTRADOR:
            self._verificar_sede(usuario, id_sede_sesion)
        elif usuario.rol != Rol.SECRETARIA:
            raise CampoObligatorioError("Solo es posible registrar usuarios de secretaría o administración")
        if self.usuario_repo.existe_documento_o_correo(usuario.numero_documento, usuario.correo):
            raise DuplicidadRegistroError("El documento o correo ya está registrado")
        return self.usuario_repo.guardar(usuario)
    def actualizar_jornada_medico(self, id_medico: str, hora_inicio_manana: time, hora_fin_manana: time, hora_inicio_tarde: time, hora_fin_tarde: time, id_sede_sesion: str) -> bool:
        """Configura la jornada de un médico de la sede, en bloques de media hora."""
        medico = self.usuario_repo.buscar_por_id(id_medico)
        self._verificar_sede(medico, id_sede_sesion)
        horas = (hora_inicio_manana, hora_fin_manana, hora_inicio_tarde, hora_fin_tarde)
        if not all(hora.minute in (0, 30) and hora.second == 0 for hora in horas):
            raise FormatoInvalidoError("La jornada debe usar bloques de 30 minutos exactos")
        if not hora_inicio_manana < hora_fin_manana <= hora_inicio_tarde < hora_fin_tarde:
            raise FormatoInvalidoError("Los bloques de la jornada deben estar ordenados y no superponerse")
        if hora_inicio_manana < HORA_INICIO_MANANA or hora_fin_manana > HORA_FIN_MANANA or hora_inicio_tarde < HORA_INICIO_TARDE or hora_fin_tarde > HORA_FIN_TARDE:
            raise FormatoInvalidoError(f"La jornada del especialista debe estar dentro de la franja de la clínica ({HORA_INICIO_MANANA.strftime('%H:%M')}-{HORA_FIN_MANANA.strftime('%H:%M')} y {HORA_INICIO_TARDE.strftime('%H:%M')}-{HORA_FIN_TARDE.strftime('%H:%M')})")
        medico.actualizar_jornada(hora_inicio_manana, hora_fin_manana, hora_inicio_tarde, hora_fin_tarde)
        return self.usuario_repo.guardar(medico)
    def actualizar_datos_especialista(self, id_medico: str, nombres: str, apellidos: str, telefono: str, correo: str, id_sede_sesion: str) -> bool:
        """Actualiza los cuatro datos editables de un médico."""
        medico = self.usuario_repo.buscar_por_id(id_medico)
        self._verificar_sede(medico, id_sede_sesion)
        if correo.lower() != medico.correo.lower():
            existente = self.usuario_repo.buscar_por_correo(correo)
            if existente and existente.id != medico.id:
                raise DuplicidadRegistroError("El correo ya está registrado")
        medico.nombres, medico.apellidos, medico.telefono, medico.correo = nombres, apellidos, telefono, correo
        medico._registrar_actualizacion()
        return self.usuario_repo.guardar(medico)
    def asignar_sede_medico(self, id_medico: str, nuevo_id_sede: str, id_sede_sesion: str) -> bool:
        """Asigna un médico desde la administración de la sede destino."""
        if nuevo_id_sede != id_sede_sesion:
            raise AccesoFueraDeSedError("Solo el administrador de la sede destino puede asignar el médico")
        medico = self.usuario_repo.buscar_por_id(id_medico)
        if not isinstance(medico, Medico):
            raise CampoObligatorioError("El usuario no es un médico")
        if medico.id_sede == nuevo_id_sede:
            raise FormatoInvalidoError("El especialista ya pertenece a esta sede")
        if self.cita_repo.obtener_futuras_por_medico(id_medico):
            raise MedicoConCitasFuturaError("El médico tiene citas futuras en su sede actual; reasigne los pacientes antes de moverlo de sede")
        medico.asignar_sede(nuevo_id_sede)
        return self.usuario_repo.guardar(medico)
    def desactivar_medico(self, id_medico: str, id_sede_sesion: str, confirmado: bool) -> bool:
        """Desactiva un médico sin citas futuras, tras confirmar."""
        if not confirmado: raise ConfirmacionRequeridaError("Debe confirmar la desactivación del médico")
        medico = self.usuario_repo.buscar_por_id(id_medico)
        self._verificar_sede(medico, id_sede_sesion)
        futuras = self.cita_repo.obtener_futuras_por_medico(id_medico)
        if futuras: raise MedicoConCitasFuturaError("El médico tiene citas futuras programadas o confirmadas")
        medico.cambiar_estado(EstadoUsuario.INACTIVO)
        return self.usuario_repo.guardar(medico)
    def inactivar_usuario(self, id_usuario: str, confirmado: bool) -> bool:
        """Inactiva un usuario preservando su historial."""
        if not confirmado: raise ConfirmacionRequeridaError("Debe confirmar la inactivación del usuario")
        usuario = self.usuario_repo.buscar_por_id(id_usuario)
        if usuario is None: raise CampoObligatorioError("El usuario no existe")
        usuario.cambiar_estado(EstadoUsuario.INACTIVO)
        return self.usuario_repo.guardar(usuario)
    def cambiar_estado_usuario(self, id_usuario: str, nuevo_estado: EstadoUsuario, confirmado: bool, id_usuario_sesion: str) -> bool:
        """Cambia el estado de una cuenta entre activa, inactiva y bloqueada.

        Parámetros:
            id_usuario: Identificador de la cuenta afectada.
            nuevo_estado: Estado destino de la cuenta.
            confirmado: Confirmación explícita del cambio.
            id_usuario_sesion: Identificador del administrador que ejecuta la acción.
        Retorna:
            Verdadero cuando el estado queda actualizado.
        """
        if not confirmado:
            raise ConfirmacionRequeridaError("Debe confirmar el cambio de estado de la cuenta")
        if id_usuario == id_usuario_sesion:
            raise AccesoFueraDeSedError("No puede modificar el estado de su propia cuenta")
        usuario = self.usuario_repo.buscar_por_id(id_usuario)
        if usuario is None:
            raise CampoObligatorioError("El usuario no existe")
        if usuario.estado == nuevo_estado:
            raise TransicionEstadoInvalidaError(f"La cuenta ya se encuentra en estado {nuevo_estado.value}")
        if nuevo_estado != EstadoUsuario.ACTIVO and isinstance(usuario, Medico) and self.cita_repo.obtener_futuras_por_medico(usuario.id):
            raise MedicoConCitasFuturaError("El médico tiene citas futuras; reasigne los pacientes antes de restringir su cuenta")
        usuario.cambiar_estado(nuevo_estado)
        return self.usuario_repo.guardar(usuario)

    def configurar_limite_diario_medico(self, id_medico: str, maximo: int, id_sede_sesion: str) -> bool:
        """Configura el número máximo de citas diarias de un especialista de la sede.

        Parámetros:
            id_medico: Identificador del especialista.
            maximo: Cantidad máxima de citas por día.
            id_sede_sesion: Sede administrada en la sesión.
        Retorna:
            Verdadero cuando el límite queda configurado.
        """
        medico = self.usuario_repo.buscar_por_id(id_medico)
        self._verificar_sede(medico, id_sede_sesion)
        if not isinstance(medico, Medico):
            raise CampoObligatorioError("El usuario no es un médico")
        medico.configurar_limite_diario(maximo)
        return self.usuario_repo.guardar(medico)

    def obtener_usuarios_gestionables(self, id_sede_sesion: str, id_usuario_sesion: str) -> list[Usuario]:
        """Obtiene las cuentas cuyo estado puede administrar la sede, sin importar su estado actual.

        Parámetros:
            id_sede_sesion: Sede administrada en la sesión.
            id_usuario_sesion: Administrador autenticado, que se excluye del listado.
        Retorna:
            Cuentas de pacientes, secretaría y personal de la sede.
        """
        gestionables = []
        for usuario in self.usuario_repo.obtener_todos():
            if usuario.id == id_usuario_sesion:
                continue
            if usuario.rol in (Rol.PACIENTE, Rol.SECRETARIA) and not getattr(usuario, "id_sede", ""):
                gestionables.append(usuario)
            elif getattr(usuario, "id_sede", "") == id_sede_sesion:
                gestionables.append(usuario)
        return sorted(gestionables, key=lambda cuenta: (cuenta.rol.value, cuenta.apellidos))

    def obtener_medicos_por_sede(self, id_sede_sesion: str) -> list[Medico]:
        """Obtiene médicos de la sede de sesión."""
        return [u for u in self.usuario_repo.obtener_activos() if isinstance(u, Medico) and u.id_sede == id_sede_sesion]
    def buscar_usuario_en_sede(self, termino: str, id_sede_sesion: str) -> list[Usuario]:
        """Busca usuarios pertenecientes a una sede."""
        return [u for u in self.usuario_repo.buscar_por_documento_o_nombre(termino) if getattr(u, "id_sede", None) == id_sede_sesion]


class ReporteFinancieroService:
    """Calcula informes financieros de una sede."""
    def __init__(self, cita_repo: ICitaRepository) -> None:
        """Recibe el repositorio de citas."""
        self.cita_repo = cita_repo
    def _citas_sede(self, inicio: date, fin: date, sede: str) -> list[CitaMedica]:
        """Filtra citas de una sede dentro de un rango."""
        return [c for c in self.cita_repo.obtener_todas() if c.id_sede == sede and inicio <= c.fecha_hora.date() <= fin]
    def calcular_ingresos_generados(self, fecha_inicio: date, fecha_fin: date, id_sede: str) -> float:
        """Suma ingresos pagados de citas atendidas."""
        return round(sum(c.valor_neto for c in self._citas_sede(fecha_inicio, fecha_fin, id_sede) if c.estado_pago == EstadoPago.PAGADO and c.estado_cita == EstadoCita.ATENDIDA), 2)
    def generar_reporte_consolidado(self, fecha_inicio: date, fecha_fin: date, id_sede: str) -> dict:
        """Genera el consolidado financiero y asistencial de una sede."""
        citas = self._citas_sede(fecha_inicio, fecha_fin, id_sede)
        atendidas = [c for c in citas if c.estado_cita == EstadoCita.ATENDIDA]
        desglose = {}
        for cita in atendidas: desglose[cita.tipo_consulta] = desglose.get(cita.tipo_consulta, 0) + 1
        return {"total_citas_atendidas": len(atendidas), "desglose_por_especialidad": desglose, "total_ingresos": self.calcular_ingresos_generados(fecha_inicio, fecha_fin, id_sede), "citas_canceladas": sum(c.estado_cita == EstadoCita.CANCELADA for c in citas)}


class SedeService:
    """Gestiona la información y los recursos físicos de las sedes."""
    def __init__(self, sede_repo: ISedeRepository, usuario_repo: IUsuarioRepository) -> None:
        """Recibe los repositorios de sedes y usuarios."""
        self.sede_repo, self.usuario_repo = sede_repo, usuario_repo

    def obtener_sedes(self) -> list[Sede]:
        """Obtiene todas las sedes registradas.

        Retorna:
            Sedes disponibles en el sistema.
        """
        return self.sede_repo.obtener_todas()

    def obtener_sede(self, id_sede: str) -> Sede:
        """Obtiene una sede por identificador.

        Parámetros:
            id_sede: Identificador de la sede.
        Retorna:
            Sede encontrada.
        """
        sede = self.sede_repo.buscar_por_id(id_sede)
        if sede is None:
            raise CampoObligatorioError("La sede solicitada no existe")
        return sede

    def crear_sede(self, nombre: str, direccion: str, numero_consultorios: int) -> Sede:
        """Registra una sede nueva validando que su nombre sea único.

        Parámetros:
            nombre: Nombre comercial de la sede.
            direccion: Dirección física de la sede.
            numero_consultorios: Cantidad de consultorios disponibles.
        Retorna:
            Sede creada.
        """
        if not nombre.strip() or not direccion.strip():
            raise CampoObligatorioError("El nombre y la dirección de la sede son obligatorios")
        if numero_consultorios < 1:
            raise FormatoInvalidoError("La sede debe tener al menos un consultorio")
        if self.sede_repo.buscar_por_nombre(nombre) is not None:
            raise DuplicidadRegistroError("Ya existe una sede registrada con ese nombre")
        sede = Sede(nombre.strip(), direccion.strip(), numero_consultorios)
        self.sede_repo.guardar(sede)
        return sede

    def actualizar_sede(self, id_sede: str, nombre: str, direccion: str, numero_consultorios: int, id_sede_sesion: str) -> Sede:
        """Actualiza los datos de la sede administrada en la sesión.

        Parámetros:
            id_sede: Sede que se desea modificar.
            nombre: Nombre comercial nuevo.
            direccion: Dirección física nueva.
            numero_consultorios: Cantidad de consultorios disponibles.
            id_sede_sesion: Sede autorizada por la sesión administrativa.
        Retorna:
            Sede actualizada.
        """
        if id_sede != id_sede_sesion:
            raise AccesoFueraDeSedError("Solo puede modificar la información de la sede que administra")
        sede = self.obtener_sede(id_sede)
        duplicada = self.sede_repo.buscar_por_nombre(nombre)
        if duplicada is not None and duplicada.id != sede.id:
            raise DuplicidadRegistroError("Ya existe otra sede registrada con ese nombre")
        sede.actualizar_datos(nombre, direccion, numero_consultorios)
        self.sede_repo.guardar(sede)
        return sede

    def contar_medicos_por_sede(self) -> dict[str, int]:
        """Cuenta los especialistas activos asignados a cada sede.

        Retorna:
            Diccionario con el identificador de sede y su cantidad de especialistas.
        """
        conteo = {sede.id: 0 for sede in self.sede_repo.obtener_todas()}
        for usuario in self.usuario_repo.obtener_activos():
            if isinstance(usuario, Medico) and usuario.id_sede in conteo:
                conteo[usuario.id_sede] += 1
        return conteo


class AuditoriaService:
    """Registra y consulta la bitácora de acciones del sistema."""
    def __init__(self, auditoria_repo: IAuditoriaRepository) -> None:
        """Recibe el repositorio de auditoría."""
        self.auditoria_repo = auditoria_repo

    def registrar_evento(self, accion: str, id_usuario: str, rol: str, id_sede: str, resultado: int) -> bool:
        """Registra un evento de auditoría con su autor y resultado.

        Parámetros:
            accion: Operación ejecutada, con método y ruta.
            id_usuario: Identificador del autor de la acción.
            rol: Rol con el que actuó el autor.
            id_sede: Sede asociada a la sesión, cuando aplica.
            resultado: Código de respuesta HTTP obtenido.
        Retorna:
            Verdadero cuando el evento queda registrado.
        """
        return self.auditoria_repo.registrar(RegistroAuditoria(accion, id_usuario, rol, id_sede, resultado))

    def consultar_bitacora(self, fecha_inicio: date, fecha_fin: date, id_sede: str = "") -> list[RegistroAuditoria]:
        """Consulta los eventos auditados en un rango de fechas.

        Parámetros:
            fecha_inicio: Inicio inclusivo del rango.
            fecha_fin: Fin inclusivo del rango.
            id_sede: Sede a filtrar; vacío consulta todas.
        Retorna:
            Eventos del rango, del más reciente al más antiguo.
        """
        if fecha_inicio > fecha_fin:
            raise FormatoInvalidoError("La fecha inicial no puede ser posterior a la fecha final")
        return self.auditoria_repo.obtener_por_rango(fecha_inicio, fecha_fin, id_sede)
