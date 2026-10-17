"""Capa de acceso a la base de datos SQLite del sistema de citas oftalmológicas.

Este módulo NO contiene reglas de negocio: solo abre la conexión y crea las
tablas. Las clases de `repositorios.py` son las únicas que ejecutan sentencias
SQL sobre esta base de datos; `servicios.py` sigue sin saber que existe SQLite.
"""

import sqlite3
from pathlib import Path

RUTA_BASE_DATOS_POR_DEFECTO = str(Path(__file__).parent / "clinica.db")

ESQUEMA_SQL = """
CREATE TABLE IF NOT EXISTS sedes (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL UNIQUE,
    direccion TEXT NOT NULL,
    numero_consultorios INTEGER NOT NULL,
    fecha_ultima_actualizacion TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS usuarios (
    id TEXT PRIMARY KEY,
    tipo_usuario TEXT NOT NULL CHECK (tipo_usuario IN ('PACIENTE', 'MEDICO', 'ADMINISTRADOR')),
    tipo_documento TEXT NOT NULL,
    numero_documento TEXT NOT NULL UNIQUE,
    nombres TEXT NOT NULL,
    apellidos TEXT NOT NULL,
    telefono TEXT NOT NULL,
    correo TEXT NOT NULL UNIQUE,
    contrasena TEXT NOT NULL,
    rol TEXT NOT NULL,
    estado TEXT NOT NULL,
    fecha_ultima_actualizacion TEXT NOT NULL
);

-- Extiende a "usuarios" cuando tipo_usuario = 'PACIENTE' (incluye las cuentas de secretaría,
-- que en el modelo de dominio son instancias de Paciente con rol SECRETARIA).
CREATE TABLE IF NOT EXISTS pacientes (
    id_usuario TEXT PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    fecha_nacimiento TEXT NOT NULL,
    nombre_acudiente TEXT NOT NULL DEFAULT '',
    telefono_acudiente TEXT NOT NULL DEFAULT ''
);

-- Extiende a "usuarios" cuando tipo_usuario = 'MEDICO'.
CREATE TABLE IF NOT EXISTS medicos (
    id_usuario TEXT PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    especialidad TEXT NOT NULL,
    id_sede TEXT NOT NULL REFERENCES sedes(id),
    hora_inicio_manana TEXT NOT NULL,
    hora_fin_manana TEXT NOT NULL,
    hora_inicio_tarde TEXT NOT NULL,
    hora_fin_tarde TEXT NOT NULL,
    max_citas_dia INTEGER NOT NULL
);

-- Extiende a "usuarios" cuando tipo_usuario = 'ADMINISTRADOR'.
CREATE TABLE IF NOT EXISTS administradores (
    id_usuario TEXT PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    id_sede TEXT NOT NULL REFERENCES sedes(id)
);

CREATE TABLE IF NOT EXISTS citas (
    id TEXT PRIMARY KEY,
    id_paciente TEXT NOT NULL REFERENCES usuarios(id),
    id_medico TEXT NOT NULL REFERENCES usuarios(id),
    id_sede TEXT NOT NULL REFERENCES sedes(id),
    fecha_hora TEXT NOT NULL,
    tipo_consulta TEXT NOT NULL,
    metodo_pago TEXT,
    duracion_minutos INTEGER NOT NULL,
    estado_cita TEXT NOT NULL,
    motivo_cancelacion TEXT NOT NULL DEFAULT '',
    observaciones_atencion TEXT NOT NULL DEFAULT '',
    valor_base REAL NOT NULL DEFAULT 0,
    porcentaje_descuento REAL NOT NULL DEFAULT 0,
    descuento_fijo REAL NOT NULL DEFAULT 0,
    monto_descuento REAL NOT NULL DEFAULT 0,
    valor_neto REAL NOT NULL DEFAULT 0,
    estado_pago TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_citas_medico_fecha ON citas(id_medico, fecha_hora);
CREATE INDEX IF NOT EXISTS idx_citas_paciente ON citas(id_paciente);

CREATE TABLE IF NOT EXISTS lista_espera (
    id TEXT PRIMARY KEY,
    id_paciente TEXT NOT NULL REFERENCES usuarios(id),
    id_sede TEXT NOT NULL REFERENCES sedes(id),
    tipo_consulta TEXT NOT NULL,
    fecha_solicitud TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auditoria (
    id TEXT PRIMARY KEY,
    accion TEXT NOT NULL,
    id_usuario TEXT NOT NULL,
    rol TEXT NOT NULL,
    id_sede TEXT NOT NULL DEFAULT '',
    resultado INTEGER NOT NULL,
    fecha_hora TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria(fecha_hora);
"""


def conectar(ruta_base_datos: str = RUTA_BASE_DATOS_POR_DEFECTO) -> sqlite3.Connection:
    """Abre una conexión a la base de datos SQLite del sistema.

    Parámetros:
        ruta_base_datos: Ruta del archivo `.db`, o `:memory:` para una base
            de datos temporal en memoria (usada por las pruebas automáticas).
    Retorna:
        Conexión abierta, con claves foráneas activas y filas accesibles por nombre de columna.
    """
    conexion = sqlite3.connect(ruta_base_datos, check_same_thread=False)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


def crear_esquema(conexion: sqlite3.Connection) -> None:
    """Crea las tablas del sistema si todavía no existen.

    Parámetros:
        conexion: Conexión abierta a la base de datos.
    Retorna:
        Ninguno.
    """
    conexion.executescript(ESQUEMA_SQL)
    conexion.commit()


def base_de_datos_vacia(conexion: sqlite3.Connection) -> bool:
    """Indica si la base de datos todavía no tiene sedes registradas.

    Se usa para decidir si hay que precargar los datos de ejemplo: así el
    servidor puede reiniciarse sin duplicar la información semilla.

    Parámetros:
        conexion: Conexión abierta a la base de datos.
    Retorna:
        Verdadero cuando la tabla de sedes está vacía.
    """
    fila = conexion.execute("SELECT COUNT(*) AS total FROM sedes").fetchone()
    return fila["total"] == 0
