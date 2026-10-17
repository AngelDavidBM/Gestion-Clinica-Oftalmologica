"""Entidades del dominio de gestión de citas."""

from abc import ABC
from dataclasses import dataclass, field
from datetime import date, datetime, time
from hashlib import sha256
from uuid import uuid4

from config import DURACION_BLOQUE_MINUTOS, HORA_FIN_MANANA, HORA_FIN_TARDE, HORA_INICIO_MANANA, HORA_INICIO_TARDE, MAX_CITAS_POR_DIA
from enums import EstadoCita, EstadoPago, EstadoUsuario, MetodoPago, Rol, TipoConsulta, TipoDocumento
from excepciones import FormatoInvalidoError, TransicionEstadoInvalidaError


def generar_identificador() -> str:
    """Genera un identificador único.

    Retorna:
        Identificador UUID como texto.
    """
    return str(uuid4())


def hashear_contrasena(contrasena: str) -> str:
    """Obtiene el hash SHA-256 de una contraseña.

    Parámetros:
        contrasena: Contraseña en texto plano.
    Retorna:
        Hash hexadecimal de la contraseña.
    """
    return sha256(contrasena.encode("utf-8")).hexdigest()


@dataclass
class Usuario(ABC):
    """Entidad abstracta base para las personas que acceden al sistema."""
    tipo_documento: TipoDocumento
    numero_documento: str
    nombres: str
    apellidos: str
    telefono: str
    correo: str
    contrasena: str
    rol: Rol
    id: str = field(default_factory=generar_identificador)
    estado: EstadoUsuario = EstadoUsuario.ACTIVO
    fecha_ultima_actualizacion: datetime = field(default_factory=datetime.now)

    def autenticar(self, correo: str, contrasena: str) -> bool:
        """Comprueba las credenciales ingresadas.

        Parámetros:
            correo: Correo a verificar.
            contrasena: Contraseña en texto plano.
        Retorna:
            Verdadero cuando ambas credenciales coinciden.
        """
        return self.correo.lower() == correo.lower() and self.contrasena == hashear_contrasena(contrasena)

    def cambiar_estado(self, nuevo_estado: EstadoUsuario) -> None:
        """Cambia el estado de la cuenta.

        Parámetros:
            nuevo_estado: Nuevo estado de la cuenta.
        Retorna:
            Ninguno.
        """
        self.estado = nuevo_estado
        self._registrar_actualizacion()

    def _registrar_actualizacion(self) -> None:
        """Registra el instante de la última modificación.

        Retorna:
            Ninguno.
        """
        self.fecha_ultima_actualizacion = datetime.now()


@dataclass
class Paciente(Usuario):
    """Representa a un paciente de la clínica."""
    fecha_nacimiento: date = field(default_factory=date.today)
    nombre_acudiente: str = ""
    telefono_acudiente: str = ""

    def calcular_edad(self) -> int:
        """Calcula la edad actual del paciente.

        Retorna:
            Edad completa en años.
        """
        hoy = date.today()
        return hoy.year - self.fecha_nacimiento.year - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day))

    def actualizar_datos_personales(self, telefono: str, correo: str, nombre_acudiente: str, telefono_acudiente: str) -> None:
        """Actualiza los datos de contacto y de acudiente del paciente.

        Parámetros:
            telefono: Teléfono de contacto nuevo.
            correo: Correo electrónico nuevo.
            nombre_acudiente: Nombre del acudiente registrado.
            telefono_acudiente: Teléfono del acudiente registrado.
        Retorna:
            Ninguno.
        """
        self.telefono, self.correo = telefono, correo
        self.nombre_acudiente, self.telefono_acudiente = nombre_acudiente, telefono_acudiente
        self._registrar_actualizacion()

    def es_menor_de_edad(self) -> bool:
        """Determina si el paciente es menor de edad.

        Retorna:
            Verdadero cuando la edad es menor que dieciocho años.
        """
        return self.calcular_edad() < 18


@dataclass
class Medico(Usuario):
    """Representa a un médico especialista."""
    especialidad: TipoConsulta = TipoConsulta.OFTALMOLOGIA_GENERAL
    id_sede: str = ""
    hora_inicio_manana: time = HORA_INICIO_MANANA
    hora_fin_manana: time = HORA_FIN_MANANA
    hora_inicio_tarde: time = HORA_INICIO_TARDE
    hora_fin_tarde: time = HORA_FIN_TARDE
    max_citas_dia: int = MAX_CITAS_POR_DIA

    def configurar_limite_diario(self, maximo: int) -> None:
        """Define el número máximo de citas que acepta el especialista en un día.

        Parámetros:
            maximo: Cantidad máxima de citas diarias permitidas.
        Retorna:
            Ninguno.
        """
        if maximo < 1:
            raise FormatoInvalidoError("El límite diario de citas debe ser de al menos una cita")
        if maximo > MAX_CITAS_POR_DIA:
            raise FormatoInvalidoError(f"El límite diario no puede superar los {MAX_CITAS_POR_DIA} bloques de la jornada")
        self.max_citas_dia = maximo
        self._registrar_actualizacion()

    def asignar_sede(self, id_sede: str) -> None:
        """Asigna el médico a una sede.

        Parámetros:
            id_sede: Identificador de la sede de destino.
        Retorna:
            Ninguno.
        """
        self.id_sede = id_sede
        self._registrar_actualizacion()

    def actualizar_contacto(self, telefono: str, correo: str) -> None:
        """Actualiza los datos de contacto del médico.

        Parámetros:
            telefono: Número telefónico nuevo.
            correo: Correo electrónico nuevo.
        Retorna:
            Ninguno.
        """
        self.telefono = telefono
        self.correo = correo
        self._registrar_actualizacion()

    def actualizar_jornada(self, hora_inicio_manana: time, hora_fin_manana: time, hora_inicio_tarde: time, hora_fin_tarde: time) -> None:
        """Actualiza los dos bloques de atención configurados para el especialista."""
        self.hora_inicio_manana, self.hora_fin_manana = hora_inicio_manana, hora_fin_manana
        self.hora_inicio_tarde, self.hora_fin_tarde = hora_inicio_tarde, hora_fin_tarde
        self._registrar_actualizacion()


@dataclass
class Administrador(Usuario):
    """Representa un administrador asignado inmutablemente a una sede."""
    id_sede: str = ""

    def __post_init__(self) -> None:
        """Fija el rol administrativo al crear la entidad.

        Retorna:
            Ninguno.
        """
        self.rol = Rol.ADMINISTRADOR
        self._registrar_actualizacion()

    def __setattr__(self, nombre: str, valor: object) -> None:
        """Impide cambiar la sede después de asignarla en la creación.

        Parámetros:
            nombre: Nombre del atributo a asignar.
            valor: Valor nuevo propuesto.
        Retorna:
            Ninguno.
        """
        if nombre == "id_sede" and "id_sede" in self.__dict__ and self.__dict__["id_sede"] != valor:
            raise AttributeError("El id de sede del administrador es inmutable")
        super().__setattr__(nombre, valor)


@dataclass
class Sede:
    """Representa una sede física de la clínica."""
    nombre: str
    direccion: str
    numero_consultorios: int
    id: str = field(default_factory=generar_identificador)
    fecha_ultima_actualizacion: datetime = field(default_factory=datetime.now)

    def actualizar_datos(self, nombre: str, direccion: str, numero_consultorios: int) -> None:
        """Actualiza la información y los recursos físicos de la sede.

        Parámetros:
            nombre: Nombre comercial de la sede.
            direccion: Dirección física de la sede.
            numero_consultorios: Cantidad de consultorios disponibles.
        Retorna:
            Ninguno.
        """
        if not nombre.strip() or not direccion.strip():
            raise FormatoInvalidoError("El nombre y la dirección de la sede son obligatorios")
        if numero_consultorios < 1:
            raise FormatoInvalidoError("La sede debe tener al menos un consultorio")
        self.nombre, self.direccion, self.numero_consultorios = nombre.strip(), direccion.strip(), numero_consultorios
        self.fecha_ultima_actualizacion = datetime.now()


@dataclass
class CitaMedica:
    """Representa una cita médica y su ciclo de vida."""
    id_paciente: str
    id_medico: str
    id_sede: str
    fecha_hora: datetime
    tipo_consulta: TipoConsulta
    metodo_pago: MetodoPago | None = None
    id: str = field(default_factory=generar_identificador)
    duracion_minutos: int = field(default=DURACION_BLOQUE_MINUTOS, init=False)
    estado_cita: EstadoCita = EstadoCita.PROGRAMADA
    motivo_cancelacion: str = ""
    observaciones_atencion: str = ""
    valor_base: float = 0.0
    porcentaje_descuento: float = 0.0
    descuento_fijo: float = 0.0
    monto_descuento: float = 0.0
    valor_neto: float = 0.0
    estado_pago: EstadoPago = EstadoPago.PENDIENTE

    def calcular_valor_neto(self) -> float:
        """Calcula el valor de la cita después del descuento.

        Retorna:
            Valor neto redondeado a dos decimales.
        """
        if self.valor_base < 0:
            raise ValueError("El valor base de la consulta no puede ser negativo")
        if self.porcentaje_descuento < 0:
            raise ValueError("El porcentaje de descuento no puede ser negativo")
        if self.porcentaje_descuento > 100:
            raise ValueError("El porcentaje de descuento no puede superar el 100%")
        if self.valor_base == 0 and self.porcentaje_descuento > 0:
            raise ValueError("No se puede aplicar descuento a una consulta sin valor")
        if self.descuento_fijo < 0:
            raise ValueError("El descuento fijo no puede ser negativo")
        if self.porcentaje_descuento > 0 and self.descuento_fijo > 0:
            raise ValueError("Debe aplicar descuento porcentual o fijo, no ambos")
        monto_porcentaje = self.valor_base * self.porcentaje_descuento / 100
        self.monto_descuento = monto_porcentaje if self.porcentaje_descuento > 0 else self.descuento_fijo
        if self.monto_descuento > self.valor_base:
            raise ValueError("El descuento no puede superar el valor base de la consulta")
        self.valor_neto = self.valor_base - self.monto_descuento
        return round(self.valor_neto, 2)

    def cancelar(self, motivo: str) -> None:
        """Cancela una cita programada o confirmada.

        Parámetros:
            motivo: Razón de la cancelación.
        Retorna:
            Ninguno.
        """
        if self.estado_cita not in (EstadoCita.PROGRAMADA, EstadoCita.CONFIRMADA):
            raise TransicionEstadoInvalidaError(f"No es posible pasar de {self.estado_cita.value} a CANCELADA")
        self.estado_cita = EstadoCita.CANCELADA
        self.motivo_cancelacion = motivo

    def reagendar(self, nueva_fecha_hora: datetime) -> None:
        """Actualiza la fecha y hora de la cita.

        Parámetros:
            nueva_fecha_hora: Fecha y hora de destino.
        Retorna:
            Ninguno.
        """
        self.fecha_hora = nueva_fecha_hora

    def registrar_atencion(self, observaciones: str) -> None:
        """Registra la atención de una cita confirmada.

        Parámetros:
            observaciones: Notas de la atención.
        Retorna:
            Ninguno.
        """
        if self.estado_cita == EstadoCita.PROGRAMADA:
            raise TransicionEstadoInvalidaError("La cita debe estar CONFIRMADA antes de registrar la atención")
        if self.estado_cita in (EstadoCita.ATENDIDA, EstadoCita.CANCELADA):
            raise TransicionEstadoInvalidaError("La cita ya se encuentra en estado terminal y no puede modificarse")
        self.observaciones_atencion = observaciones
        self.estado_cita = EstadoCita.ATENDIDA


@dataclass
class RegistroListaEspera:
    """Representa una solicitud en lista de espera."""
    id_paciente: str
    id_sede: str
    tipo_consulta: TipoConsulta
    fecha_solicitud: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=generar_identificador)


@dataclass
class RegistroAuditoria:
    """Representa un evento registrado en la bitácora de auditoría."""
    accion: str
    id_usuario: str
    rol: str
    id_sede: str
    resultado: int
    fecha_hora: datetime = field(default_factory=datetime.now)
    id: str = field(default_factory=generar_identificador)

    def fue_exitoso(self) -> bool:
        """Indica si la acción auditada terminó sin error.

        Retorna:
            Verdadero cuando el código de respuesta es inferior a cuatrocientos.
        """
        return self.resultado < 400
