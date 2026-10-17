"""Enumeraciones del dominio."""

from enum import Enum


class Rol(str, Enum):
    """Representa los roles permitidos en el sistema."""
    PACIENTE = "PACIENTE"
    SECRETARIA = "SECRETARIA"
    ADMINISTRADOR = "ADMINISTRADOR"


class EstadoUsuario(str, Enum):
    """Representa el estado de una cuenta."""
    ACTIVO = "ACTIVO"
    INACTIVO = "INACTIVO"
    BLOQUEADO = "BLOQUEADO"


class TipoDocumento(str, Enum):
    """Representa los tipos de documento aceptados."""
    CC = "CC"
    TI = "TI"
    CE = "CE"
    PASAPORTE = "PASAPORTE"


class EstadoCita(str, Enum):
    """Representa los estados del ciclo de vida de una cita."""
    PROGRAMADA = "PROGRAMADA"
    CONFIRMADA = "CONFIRMADA"
    ATENDIDA = "ATENDIDA"
    CANCELADA = "CANCELADA"


class EstadoPago(str, Enum):
    """Representa los estados financieros de una cita."""
    PENDIENTE = "PENDIENTE"
    PAGADO = "PAGADO"
    ANULADO = "ANULADO"


class MetodoPago(str, Enum):
    """Representa los métodos de pago disponibles."""
    EFECTIVO = "EFECTIVO"
    TARJETA = "TARJETA"
    TRANSFERENCIA = "TRANSFERENCIA"


class TipoConsulta(str, Enum):
    """Representa los tipos de consulta oftalmológica."""
    OPTOMETRIA = "OPTOMETRIA"
    OFTALMOLOGIA_GENERAL = "OFTALMOLOGIA_GENERAL"
    CONTROL = "CONTROL"
