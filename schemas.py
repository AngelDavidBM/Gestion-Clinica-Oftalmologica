"""Esquemas de entrada validados por Pydantic."""

from datetime import date, datetime, time
from pydantic import BaseModel, EmailStr, Field

from enums import EstadoUsuario, MetodoPago, Rol, TipoConsulta, TipoDocumento


class LoginSchema(BaseModel):
    """Valida credenciales de acceso."""
    correo: EmailStr
    contrasena: str = Field(min_length=1)


class PacienteCreateSchema(BaseModel):
    """Valida los datos para crear un paciente."""
    tipo_documento: TipoDocumento
    numero_documento: str = Field(pattern=r"^\d{1,10}$")
    nombres: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    telefono: str = Field(pattern=r"^\d+$")
    correo: EmailStr
    contrasena: str = Field(min_length=1)
    fecha_nacimiento: date
    nombre_acudiente: str = ""
    telefono_acudiente: str = ""


class MedicoCreateSchema(BaseModel):
    """Valida los datos para crear un médico."""
    tipo_documento: TipoDocumento
    numero_documento: str = Field(pattern=r"^\d{1,10}$")
    nombres: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    telefono: str = Field(pattern=r"^\d+$")
    correo: EmailStr
    contrasena: str = Field(min_length=1)
    especialidad: TipoConsulta
    id_sede: str


class ActualizarEspecialistaSchema(BaseModel):
    """Valida los campos editables de un especialista."""
    nombres: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    telefono: str = Field(pattern=r"^\d+$")
    correo: EmailStr


class CitaCreateSchema(BaseModel):
    """Valida los datos requeridos para agendar una cita."""
    id_paciente: str
    id_medico: str
    id_sede: str
    fecha_hora: datetime
    tipo_consulta: TipoConsulta
    nombre_acudiente: str = ""
    telefono_acudiente: str = ""


class ReagendarCitaSchema(BaseModel):
    """Valida una nueva fecha y hora para una cita."""
    nueva_fecha_hora: datetime


class CancelarCitaSchema(BaseModel):
    """Valida la confirmación y motivo de cancelación."""
    motivo: str = Field(min_length=1)
    confirmado: bool = False


class RegistrarCobroSchema(BaseModel):
    """Valida el cobro aplicado a una cita."""
    valor_base: float = Field(gt=0)
    porcentaje_descuento: float = Field(default=0.0, ge=0, le=100)
    descuento_fijo: float = Field(default=0.0, ge=0)
    metodo_pago: MetodoPago


class AnularCobroSchema(BaseModel):
    """Valida la confirmación de una anulación de pago."""
    id_cita: str
    confirmado: bool = False


class JornadaMedicoSchema(BaseModel):
    """Valida los dos bloques diarios de atención del especialista."""
    hora_inicio_manana: time
    hora_fin_manana: time
    hora_inicio_tarde: time
    hora_fin_tarde: time


class UsuarioInternoCreateSchema(BaseModel):
    """Valida el alta administrativa de secretaría o administración."""
    tipo_documento: TipoDocumento
    numero_documento: str = Field(pattern=r"^\d{1,10}$")
    nombres: str = Field(min_length=1)
    apellidos: str = Field(min_length=1)
    telefono: str = Field(pattern=r"^\d+$")
    correo: EmailStr
    contrasena: str = Field(min_length=1)
    rol: Rol


class ListaEsperaSchema(BaseModel):
    """Valida una solicitud para la lista de espera."""
    id_paciente: str = ""
    id_sede: str = Field(min_length=1)
    tipo_consulta: TipoConsulta


class ReporteRequestSchema(BaseModel):
    """Valida un rango de fechas para reporte."""
    fecha_inicio: date
    fecha_fin: date


class SedeCreateSchema(BaseModel):
    """Valida los datos para registrar una sede."""
    nombre: str = Field(min_length=1)
    direccion: str = Field(min_length=1)
    numero_consultorios: int = Field(ge=1, le=100)


class SedeUpdateSchema(BaseModel):
    """Valida los datos editables de una sede."""
    nombre: str = Field(min_length=1)
    direccion: str = Field(min_length=1)
    numero_consultorios: int = Field(ge=1, le=100)


class CambiarEstadoUsuarioSchema(BaseModel):
    """Valida el cambio de estado de una cuenta."""
    nuevo_estado: EstadoUsuario
    confirmado: bool = False


class LimiteDiarioSchema(BaseModel):
    """Valida el límite de citas diarias de un especialista."""
    max_citas_dia: int = Field(ge=1, le=16)


class PromoverEsperaSchema(BaseModel):
    """Valida la asignación de un bloque liberado a una solicitud en espera."""
    id_medico: str = Field(min_length=1)
    fecha_hora: datetime


class RetirarEsperaSchema(BaseModel):
    """Valida la confirmación para retirar una solicitud de la lista de espera."""
    confirmado: bool = False


class ActualizarPacienteSchema(BaseModel):
    """Valida los datos de contacto editables de un paciente."""
    telefono: str = Field(pattern=r"^\d+$")
    correo: EmailStr
    nombre_acudiente: str = ""
    telefono_acudiente: str = ""
