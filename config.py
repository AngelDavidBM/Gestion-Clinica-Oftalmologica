"""Constantes de configuración del sistema de citas."""

from datetime import time

MAX_CITAS_POR_DIA = 16
HORA_INICIO_MANANA = time(8, 0)
HORA_FIN_MANANA = time(12, 0)
HORA_INICIO_TARDE = time(14, 0)
HORA_FIN_TARDE = time(18, 0)
DURACION_BLOQUE_MINUTOS = 30
DIAS_LABORALES = [0, 1, 2, 3, 4]
CLAVE_SESION = "clave-desarrollo-citas-oftalmologicas"
NOMBRE_COOKIE_SESION = "sesion_citas"
