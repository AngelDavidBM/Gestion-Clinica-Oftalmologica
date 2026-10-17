"""Implementaciones de los repositorios respaldadas por SQLite.

Cada clase implementa exactamente la misma interfaz abstracta que su
contraparte en memoria (`repositorios.py`), así que `servicios.py` no necesita
ningún cambio para trabajar con una base de datos real: solo cambia qué
repositorio le inyecta `main.py`. Esto es el principio de inversión de
dependencias aplicado al proyecto: la capa de negocio depende de una
abstracción (`IUsuarioRepository`, `ICitaRepository`, ...), no de SQLite.
"""

import sqlite3
from datetime import date, datetime, time

from enums import EstadoCita, EstadoPago, EstadoUsuario, MetodoPago, Rol, TipoConsulta, TipoDocumento
from modelos import Administrador, CitaMedica, Medico, Paciente, RegistroAuditoria, RegistroListaEspera, Sede, Usuario
from repositorios import IAuditoriaRepository, ICitaRepository, IListaEsperaRepository, ISedeRepository, IUsuarioRepository


def _fila_a_usuario(conexion: sqlite3.Connection, fila: sqlite3.Row) -> Usuario:
    """Reconstruye la subclase correcta de Usuario a partir de una fila de la tabla base.

    Parámetros:
        conexion: Conexión abierta a la base de datos, usada para consultar la tabla de extensión.
        fila: Fila de la tabla `usuarios`.
    Retorna:
        Instancia de Paciente, Medico o Administrador según `tipo_usuario`.
    """
    comunes = dict(
        tipo_documento=TipoDocumento(fila["tipo_documento"]), numero_documento=fila["numero_documento"],
        nombres=fila["nombres"], apellidos=fila["apellidos"], telefono=fila["telefono"], correo=fila["correo"],
        contrasena=fila["contrasena"], rol=Rol(fila["rol"]), id=fila["id"], estado=EstadoUsuario(fila["estado"]),
        fecha_ultima_actualizacion=datetime.fromisoformat(fila["fecha_ultima_actualizacion"]),
    )
    if fila["tipo_usuario"] == "PACIENTE":
        extension = conexion.execute("SELECT * FROM pacientes WHERE id_usuario = ?", (fila["id"],)).fetchone()
        return Paciente(**comunes, fecha_nacimiento=date.fromisoformat(extension["fecha_nacimiento"]),
                         nombre_acudiente=extension["nombre_acudiente"], telefono_acudiente=extension["telefono_acudiente"])
    if fila["tipo_usuario"] == "MEDICO":
        extension = conexion.execute("SELECT * FROM medicos WHERE id_usuario = ?", (fila["id"],)).fetchone()
        return Medico(**comunes, especialidad=TipoConsulta(extension["especialidad"]), id_sede=extension["id_sede"],
                       hora_inicio_manana=time.fromisoformat(extension["hora_inicio_manana"]), hora_fin_manana=time.fromisoformat(extension["hora_fin_manana"]),
                       hora_inicio_tarde=time.fromisoformat(extension["hora_inicio_tarde"]), hora_fin_tarde=time.fromisoformat(extension["hora_fin_tarde"]),
                       max_citas_dia=extension["max_citas_dia"])
    extension = conexion.execute("SELECT * FROM administradores WHERE id_usuario = ?", (fila["id"],)).fetchone()
    administrador = Administrador(**comunes, id_sede=extension["id_sede"])
    administrador.fecha_ultima_actualizacion = comunes["fecha_ultima_actualizacion"]  # __post_init__ la sobrescribe con datetime.now()
    return administrador


class UsuarioRepositorySQLite(IUsuarioRepository):
    """Persiste los usuarios (pacientes, médicos y administradores) en SQLite."""
    def __init__(self, conexion: sqlite3.Connection) -> None:
        """Recibe la conexión abierta a la base de datos."""
        self.conexion = conexion

    def guardar(self, usuario: Usuario) -> bool:
        """Guarda o actualiza un usuario y su tabla de extensión según su tipo."""
        tipo = "PACIENTE" if isinstance(usuario, Paciente) else "MEDICO" if isinstance(usuario, Medico) else "ADMINISTRADOR"
        self.conexion.execute(
            """INSERT INTO usuarios (id, tipo_usuario, tipo_documento, numero_documento, nombres, apellidos, telefono, correo, contrasena, rol, estado, fecha_ultima_actualizacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET tipo_documento=excluded.tipo_documento, numero_documento=excluded.numero_documento,
                   nombres=excluded.nombres, apellidos=excluded.apellidos, telefono=excluded.telefono, correo=excluded.correo,
                   contrasena=excluded.contrasena, rol=excluded.rol, estado=excluded.estado, fecha_ultima_actualizacion=excluded.fecha_ultima_actualizacion""",
            (usuario.id, tipo, usuario.tipo_documento.value, usuario.numero_documento, usuario.nombres, usuario.apellidos,
             usuario.telefono, usuario.correo, usuario.contrasena, usuario.rol.value, usuario.estado.value, usuario.fecha_ultima_actualizacion.isoformat()))
        if tipo == "PACIENTE":
            self.conexion.execute(
                """INSERT INTO pacientes (id_usuario, fecha_nacimiento, nombre_acudiente, telefono_acudiente) VALUES (?, ?, ?, ?)
                   ON CONFLICT(id_usuario) DO UPDATE SET fecha_nacimiento=excluded.fecha_nacimiento, nombre_acudiente=excluded.nombre_acudiente, telefono_acudiente=excluded.telefono_acudiente""",
                (usuario.id, usuario.fecha_nacimiento.isoformat(), usuario.nombre_acudiente, usuario.telefono_acudiente))
        elif tipo == "MEDICO":
            self.conexion.execute(
                """INSERT INTO medicos (id_usuario, especialidad, id_sede, hora_inicio_manana, hora_fin_manana, hora_inicio_tarde, hora_fin_tarde, max_citas_dia) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(id_usuario) DO UPDATE SET especialidad=excluded.especialidad, id_sede=excluded.id_sede, hora_inicio_manana=excluded.hora_inicio_manana,
                       hora_fin_manana=excluded.hora_fin_manana, hora_inicio_tarde=excluded.hora_inicio_tarde, hora_fin_tarde=excluded.hora_fin_tarde, max_citas_dia=excluded.max_citas_dia""",
                (usuario.id, usuario.especialidad.value, usuario.id_sede, usuario.hora_inicio_manana.isoformat(), usuario.hora_fin_manana.isoformat(),
                 usuario.hora_inicio_tarde.isoformat(), usuario.hora_fin_tarde.isoformat(), usuario.max_citas_dia))
        else:
            self.conexion.execute(
                """INSERT INTO administradores (id_usuario, id_sede) VALUES (?, ?) ON CONFLICT(id_usuario) DO UPDATE SET id_sede=excluded.id_sede""",
                (usuario.id, usuario.id_sede))
        self.conexion.commit()
        return True

    def buscar_por_id(self, identificador: str) -> Usuario | None:
        """Busca un usuario por identificador."""
        fila = self.conexion.execute("SELECT * FROM usuarios WHERE id = ?", (identificador,)).fetchone()
        return _fila_a_usuario(self.conexion, fila) if fila else None

    def buscar_por_correo(self, correo: str) -> Usuario | None:
        """Busca un usuario ignorando mayúsculas en el correo."""
        fila = self.conexion.execute("SELECT * FROM usuarios WHERE LOWER(correo) = LOWER(?)", (correo,)).fetchone()
        return _fila_a_usuario(self.conexion, fila) if fila else None

    def buscar_por_documento(self, numero_documento: str) -> Usuario | None:
        """Busca un usuario por número de documento."""
        fila = self.conexion.execute("SELECT * FROM usuarios WHERE numero_documento = ?", (numero_documento,)).fetchone()
        return _fila_a_usuario(self.conexion, fila) if fila else None

    def buscar_por_documento_o_nombre(self, termino: str) -> list[Usuario]:
        """Busca coincidencias insensibles a mayúsculas en documento o nombres."""
        patron = f"%{termino.lower()}%"
        filas = self.conexion.execute("SELECT * FROM usuarios WHERE LOWER(numero_documento) LIKE ? OR LOWER(nombres) LIKE ?", (patron, patron)).fetchall()
        return [_fila_a_usuario(self.conexion, fila) for fila in filas]

    def obtener_activos(self) -> list[Usuario]:
        """Retorna todos los usuarios en estado ACTIVO."""
        filas = self.conexion.execute("SELECT * FROM usuarios WHERE estado = ?", (EstadoUsuario.ACTIVO.value,)).fetchall()
        return [_fila_a_usuario(self.conexion, fila) for fila in filas]

    def obtener_todos(self) -> list[Usuario]:
        """Retorna todos los usuarios registrados, sin filtrar por estado."""
        filas = self.conexion.execute("SELECT * FROM usuarios").fetchall()
        return [_fila_a_usuario(self.conexion, fila) for fila in filas]

    def existe_documento_o_correo(self, documento: str, correo: str) -> bool:
        """Indica si el documento o el correo ya están registrados."""
        fila = self.conexion.execute("SELECT 1 FROM usuarios WHERE numero_documento = ? OR LOWER(correo) = LOWER(?)", (documento, correo)).fetchone()
        return fila is not None


def _fila_a_cita(fila: sqlite3.Row) -> CitaMedica:
    """Reconstruye una CitaMedica a partir de una fila de la tabla `citas`.

    Parámetros:
        fila: Fila leída de la tabla `citas`.
    Retorna:
        Instancia de CitaMedica equivalente a la fila.
    """
    cita = CitaMedica(
        id_paciente=fila["id_paciente"], id_medico=fila["id_medico"], id_sede=fila["id_sede"],
        fecha_hora=datetime.fromisoformat(fila["fecha_hora"]), tipo_consulta=TipoConsulta(fila["tipo_consulta"]),
        metodo_pago=MetodoPago(fila["metodo_pago"]) if fila["metodo_pago"] else None, id=fila["id"])
    cita.estado_cita = EstadoCita(fila["estado_cita"])
    cita.motivo_cancelacion = fila["motivo_cancelacion"]
    cita.observaciones_atencion = fila["observaciones_atencion"]
    cita.valor_base = fila["valor_base"]
    cita.porcentaje_descuento = fila["porcentaje_descuento"]
    cita.descuento_fijo = fila["descuento_fijo"]
    cita.monto_descuento = fila["monto_descuento"]
    cita.valor_neto = fila["valor_neto"]
    cita.estado_pago = EstadoPago(fila["estado_pago"])
    return cita


class CitaRepositorySQLite(ICitaRepository):
    """Persiste las citas médicas en SQLite."""
    def __init__(self, conexion: sqlite3.Connection) -> None:
        """Recibe la conexión abierta a la base de datos."""
        self.conexion = conexion

    def guardar(self, cita: CitaMedica) -> bool:
        """Guarda o actualiza una cita."""
        self.conexion.execute(
            """INSERT INTO citas (id, id_paciente, id_medico, id_sede, fecha_hora, tipo_consulta, metodo_pago, duracion_minutos, estado_cita,
                   motivo_cancelacion, observaciones_atencion, valor_base, porcentaje_descuento, descuento_fijo, monto_descuento, valor_neto, estado_pago)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET fecha_hora=excluded.fecha_hora, estado_cita=excluded.estado_cita, motivo_cancelacion=excluded.motivo_cancelacion,
                   observaciones_atencion=excluded.observaciones_atencion, metodo_pago=excluded.metodo_pago, valor_base=excluded.valor_base,
                   porcentaje_descuento=excluded.porcentaje_descuento, descuento_fijo=excluded.descuento_fijo, monto_descuento=excluded.monto_descuento,
                   valor_neto=excluded.valor_neto, estado_pago=excluded.estado_pago""",
            (cita.id, cita.id_paciente, cita.id_medico, cita.id_sede, cita.fecha_hora.isoformat(), cita.tipo_consulta.value,
             cita.metodo_pago.value if cita.metodo_pago else None, cita.duracion_minutos, cita.estado_cita.value, cita.motivo_cancelacion,
             cita.observaciones_atencion, cita.valor_base, cita.porcentaje_descuento, cita.descuento_fijo, cita.monto_descuento, cita.valor_neto, cita.estado_pago.value))
        self.conexion.commit()
        return True

    def buscar_por_id(self, identificador: str) -> CitaMedica | None:
        """Busca una cita por identificador."""
        fila = self.conexion.execute("SELECT * FROM citas WHERE id = ?", (identificador,)).fetchone()
        return _fila_a_cita(fila) if fila else None

    def obtener_por_paciente(self, id_paciente: str) -> list[CitaMedica]:
        """Obtiene las citas de un paciente."""
        filas = self.conexion.execute("SELECT * FROM citas WHERE id_paciente = ?", (id_paciente,)).fetchall()
        return [_fila_a_cita(fila) for fila in filas]

    def obtener_por_medico_y_fecha(self, id_medico: str, fecha: date) -> list[CitaMedica]:
        """Obtiene citas de un médico en una fecha, comparando solo la parte de fecha del campo `fecha_hora`."""
        filas = self.conexion.execute("SELECT * FROM citas WHERE id_medico = ? AND substr(fecha_hora, 1, 10) = ?", (id_medico, fecha.isoformat())).fetchall()
        return [_fila_a_cita(fila) for fila in filas]

    def obtener_por_sede_medico_fecha(self, id_sede: str, id_medico: str, fecha: date) -> list[CitaMedica]:
        """Obtiene citas filtradas por sede, médico y fecha."""
        filas = self.conexion.execute("SELECT * FROM citas WHERE id_sede = ? AND id_medico = ? AND substr(fecha_hora, 1, 10) = ?", (id_sede, id_medico, fecha.isoformat())).fetchall()
        return [_fila_a_cita(fila) for fila in filas]

    def existe_cita_en_horario(self, id_medico: str, fecha_hora: datetime) -> bool:
        """Indica si un médico tiene una cita no cancelada a esa hora exacta."""
        fila = self.conexion.execute("SELECT 1 FROM citas WHERE id_medico = ? AND fecha_hora = ? AND estado_cita != ?",
                                      (id_medico, fecha_hora.isoformat(), EstadoCita.CANCELADA.value)).fetchone()
        return fila is not None

    def existe_cita_paciente_en_horario(self, id_paciente: str, fecha_hora: datetime) -> bool:
        """Indica si un paciente tiene una cita no cancelada a esa hora exacta."""
        fila = self.conexion.execute("SELECT 1 FROM citas WHERE id_paciente = ? AND fecha_hora = ? AND estado_cita != ?",
                                      (id_paciente, fecha_hora.isoformat(), EstadoCita.CANCELADA.value)).fetchone()
        return fila is not None

    def contar_citas_medico_en_fecha(self, id_medico: str, fecha: date) -> int:
        """Cuenta las citas no canceladas de un médico durante una fecha."""
        fila = self.conexion.execute("SELECT COUNT(*) AS total FROM citas WHERE id_medico = ? AND substr(fecha_hora, 1, 10) = ? AND estado_cita != ?",
                                      (id_medico, fecha.isoformat(), EstadoCita.CANCELADA.value)).fetchone()
        return fila["total"]

    def obtener_todas(self) -> list[CitaMedica]:
        """Obtiene todas las citas almacenadas."""
        filas = self.conexion.execute("SELECT * FROM citas").fetchall()
        return [_fila_a_cita(fila) for fila in filas]

    def obtener_futuras_por_medico(self, id_medico: str) -> list[CitaMedica]:
        """Obtiene las citas futuras programadas o confirmadas de un médico."""
        ahora = datetime.now().isoformat()
        filas = self.conexion.execute(
            "SELECT * FROM citas WHERE id_medico = ? AND fecha_hora > ? AND estado_cita IN (?, ?)",
            (id_medico, ahora, EstadoCita.PROGRAMADA.value, EstadoCita.CONFIRMADA.value)).fetchall()
        return [_fila_a_cita(fila) for fila in filas]


class SedeRepositorySQLite(ISedeRepository):
    """Persiste las sedes en SQLite."""
    def __init__(self, conexion: sqlite3.Connection) -> None:
        """Recibe la conexión abierta a la base de datos."""
        self.conexion = conexion

    def guardar(self, sede: Sede) -> bool:
        """Guarda o actualiza una sede."""
        self.conexion.execute(
            """INSERT INTO sedes (id, nombre, direccion, numero_consultorios, fecha_ultima_actualizacion) VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, direccion=excluded.direccion,
                   numero_consultorios=excluded.numero_consultorios, fecha_ultima_actualizacion=excluded.fecha_ultima_actualizacion""",
            (sede.id, sede.nombre, sede.direccion, sede.numero_consultorios, sede.fecha_ultima_actualizacion.isoformat()))
        self.conexion.commit()
        return True

    def buscar_por_id(self, identificador: str) -> Sede | None:
        """Busca una sede por identificador."""
        fila = self.conexion.execute("SELECT * FROM sedes WHERE id = ?", (identificador,)).fetchone()
        return self._fila_a_sede(fila) if fila else None

    def buscar_por_nombre(self, nombre: str) -> Sede | None:
        """Busca una sede por nombre ignorando mayúsculas."""
        fila = self.conexion.execute("SELECT * FROM sedes WHERE LOWER(nombre) = LOWER(?)", (nombre.strip(),)).fetchone()
        return self._fila_a_sede(fila) if fila else None

    def obtener_todas(self) -> list[Sede]:
        """Obtiene todas las sedes registradas."""
        filas = self.conexion.execute("SELECT * FROM sedes").fetchall()
        return [self._fila_a_sede(fila) for fila in filas]

    @staticmethod
    def _fila_a_sede(fila: sqlite3.Row) -> Sede:
        """Reconstruye una Sede a partir de una fila de la tabla `sedes`."""
        return Sede(nombre=fila["nombre"], direccion=fila["direccion"], numero_consultorios=fila["numero_consultorios"],
                     id=fila["id"], fecha_ultima_actualizacion=datetime.fromisoformat(fila["fecha_ultima_actualizacion"]))


class ListaEsperaRepositorySQLite(IListaEsperaRepository):
    """Persiste la lista de espera en SQLite."""
    def __init__(self, conexion: sqlite3.Connection) -> None:
        """Recibe la conexión abierta a la base de datos."""
        self.conexion = conexion

    def guardar(self, registro: RegistroListaEspera) -> bool:
        """Guarda una solicitud en espera."""
        self.conexion.execute(
            "INSERT INTO lista_espera (id, id_paciente, id_sede, tipo_consulta, fecha_solicitud) VALUES (?, ?, ?, ?, ?)",
            (registro.id, registro.id_paciente, registro.id_sede, registro.tipo_consulta.value, registro.fecha_solicitud.isoformat()))
        self.conexion.commit()
        return True

    def buscar_por_id(self, identificador: str) -> RegistroListaEspera | None:
        """Busca una solicitud por identificador."""
        fila = self.conexion.execute("SELECT * FROM lista_espera WHERE id = ?", (identificador,)).fetchone()
        return self._fila_a_registro(fila) if fila else None

    def eliminar(self, identificador: str) -> bool:
        """Elimina una solicitud de la lista de espera."""
        cursor = self.conexion.execute("DELETE FROM lista_espera WHERE id = ?", (identificador,))
        self.conexion.commit()
        return cursor.rowcount > 0

    def obtener_todas(self) -> list[RegistroListaEspera]:
        """Obtiene todas las solicitudes vigentes, ordenadas por fecha de solicitud."""
        filas = self.conexion.execute("SELECT * FROM lista_espera ORDER BY fecha_solicitud").fetchall()
        return [self._fila_a_registro(fila) for fila in filas]

    @staticmethod
    def _fila_a_registro(fila: sqlite3.Row) -> RegistroListaEspera:
        """Reconstruye un RegistroListaEspera a partir de una fila de la tabla `lista_espera`."""
        return RegistroListaEspera(id_paciente=fila["id_paciente"], id_sede=fila["id_sede"], tipo_consulta=TipoConsulta(fila["tipo_consulta"]),
                                    fecha_solicitud=datetime.fromisoformat(fila["fecha_solicitud"]), id=fila["id"])


class AuditoriaRepositorySQLite(IAuditoriaRepository):
    """Persiste la bitácora de auditoría en SQLite."""
    def __init__(self, conexion: sqlite3.Connection) -> None:
        """Recibe la conexión abierta a la base de datos."""
        self.conexion = conexion

    def registrar(self, registro: RegistroAuditoria) -> bool:
        """Agrega un evento a la bitácora."""
        self.conexion.execute(
            "INSERT INTO auditoria (id, accion, id_usuario, rol, id_sede, resultado, fecha_hora) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (registro.id, registro.accion, registro.id_usuario, registro.rol, registro.id_sede, registro.resultado, registro.fecha_hora.isoformat()))
        self.conexion.commit()
        return True

    def obtener_por_rango(self, fecha_inicio: date, fecha_fin: date, id_sede: str = "") -> list[RegistroAuditoria]:
        """Obtiene los eventos de un rango, opcionalmente filtrados por sede, del más reciente al más antiguo."""
        parametros = [f"{fecha_inicio.isoformat()}T00:00:00", f"{fecha_fin.isoformat()}T23:59:59.999999"]
        condicion_sede = ""
        if id_sede:
            condicion_sede = "AND id_sede = ?"
            parametros.append(id_sede)
        filas = self.conexion.execute(
            f"SELECT * FROM auditoria WHERE fecha_hora BETWEEN ? AND ? {condicion_sede} ORDER BY fecha_hora DESC", parametros).fetchall()
        return [RegistroAuditoria(accion=fila["accion"], id_usuario=fila["id_usuario"], rol=fila["rol"], id_sede=fila["id_sede"],
                                  resultado=fila["resultado"], fecha_hora=datetime.fromisoformat(fila["fecha_hora"]), id=fila["id"]) for fila in filas]
