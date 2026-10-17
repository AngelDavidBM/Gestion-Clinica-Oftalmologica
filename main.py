"""Punto de entrada de la aplicación de citas oftalmológicas.
source .venv/bin/activate
uvicorn main:app --reload

Los datos se guardan en la base de datos SQLite `clinica.db` (se crea sola la
primera vez que se corre la aplicación). Para usar otra ruta o una base de
datos en memoria (usada por las pruebas automáticas), defina la variable de
entorno CLINICA_DB_PATH antes de iniciar el servidor.

Credenciales semilla:
- Administrador Norte:  admin.norte@clinica.com/ AdminNorte2026
- Administrador Sur: admin.sur@clinica.com / AdminSur2026
- Secretaria: secretaria@clinica.com / Secretaria2026
- Paciente: paciente@clinica.com / Paciente2026

"""

import os 
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from enums import Rol, TipoConsulta, TipoDocumento
from excepciones import AccesoFueraDeSedError, CampoObligatorioError, ConfirmacionRequeridaError, CredencialesInvalidasError, DuplicidadRegistroError, FormatoInvalidoError, HorarioFueraDeJornadaError, LimiteDiarioAlcanzadoError, MedicoConCitasFuturaError, MenorDeEdadSinAcudienteError, SobreasignacionMedicoError, TransicionEstadoInvalidaError, UsuarioInactivoError
from modelos import Administrador, Medico, Paciente, Sede, hashear_contrasena
import basededatos
from repositorios_sqlite import AuditoriaRepositorySQLite, CitaRepositorySQLite, ListaEsperaRepositorySQLite, SedeRepositorySQLite, UsuarioRepositorySQLite
from routers import admin_router, auth_router, paciente_router, secretaria_router
from routers.auth_router import leer_sesion_opcional
from servicios import AdministradorService, AgendamientoService, AuditoriaService, AutenticacionService, ReporteFinancieroService, SecretariaService, SedeService

app = FastAPI(title="Gestión de Citas Oftalmológicas Multi-Sede")
app.state.plantillas = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
RUTA_BASE_DATOS = os.environ.get("CLINICA_DB_PATH", basededatos.RUTA_BASE_DATOS_POR_DEFECTO)
app.state.conexion_bd = basededatos.conectar(RUTA_BASE_DATOS)
basededatos.crear_esquema(app.state.conexion_bd)
app.state.usuario_repo = UsuarioRepositorySQLite(app.state.conexion_bd)
app.state.cita_repo = CitaRepositorySQLite(app.state.conexion_bd)
app.state.sede_repo = SedeRepositorySQLite(app.state.conexion_bd)
app.state.auditoria_repo = AuditoriaRepositorySQLite(app.state.conexion_bd)
app.state.lista_espera_repo = ListaEsperaRepositorySQLite(app.state.conexion_bd)
app.state.autenticacion = AutenticacionService(app.state.usuario_repo)
app.state.agendamiento = AgendamientoService(app.state.cita_repo, app.state.usuario_repo, app.state.lista_espera_repo)
app.state.secretaria = SecretariaService(app.state.usuario_repo, app.state.cita_repo)
app.state.administrador = AdministradorService(app.state.usuario_repo, app.state.cita_repo)
app.state.reportes = ReporteFinancieroService(app.state.cita_repo)
app.state.sedes_servicio = SedeService(app.state.sede_repo, app.state.usuario_repo)
app.state.auditoria = AuditoriaService(app.state.auditoria_repo)


@app.middleware("http")
async def auditar_operaciones(request: Request, call_next: object) -> object:
    """Registra en la bitácora toda operación que modifica información del sistema.

    Parámetros:
        request: Solicitud HTTP recibida.
        call_next: Siguiente manejador de la cadena.
    Retorna:
        Respuesta generada por la aplicación.
    """
    respuesta = await call_next(request)
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        sesion = leer_sesion_opcional(request)
        app.state.auditoria.registrar_evento(f"{request.method} {request.url.path}", sesion.get("id_usuario", "anonimo"), sesion.get("rol", "ANONIMO"), sesion.get("id_sede", ""), respuesta.status_code)
    return respuesta


@app.get("/", include_in_schema=False)
async def inicio() -> RedirectResponse:
    """Redirige la ruta inicial a la pantalla de acceso.

    Retorna:
        Redirección temporal a la ruta de login.
    """
    return RedirectResponse("/login", status_code=303)


def es_solicitud_json(request: Request) -> bool:
    """Determina si el cliente espera una respuesta JSON.

    Parámetros:
        request: Solicitud HTTP recibida.
    Retorna:
        Verdadero si se solicitó JSON.
    """
    return "application/json" in request.headers.get("accept", "")


def ruta_retorno_segura(request: Request) -> str:
    """Obtiene una ruta local segura para regresar tras un error de formulario."""
    referencia = request.headers.get("referer", "")
    ruta = urlparse(referencia).path
    return ruta if ruta.startswith("/") and not ruta.startswith("//") else "/login"


def registrar_manejador(tipo: type[Exception], codigo: int) -> None:
    """Registra un manejador global para una excepción del dominio.

    Parámetros:
        tipo: Clase de excepción a manejar.
        codigo: Código HTTP de respuesta.
    Retorna:
        Ninguno.
    """
    async def manejar(request: Request, excepcion: Exception) -> HTMLResponse | JSONResponse:
        """Traduce una excepción de negocio a una respuesta HTTP."""
        if es_solicitud_json(request):
            return JSONResponse({"detail": str(excepcion)}, status_code=codigo)
        return app.state.plantillas.TemplateResponse(request=request, name="error.html", context={"alerta": str(excepcion), "volver_a": ruta_retorno_segura(request)}, status_code=codigo)
    app.add_exception_handler(tipo, manejar)


for _tipo, _codigo in {
    CredencialesInvalidasError: 401, UsuarioInactivoError: 401,
    AccesoFueraDeSedError: 403,
    ConfirmacionRequeridaError: 400, CampoObligatorioError: 400, FormatoInvalidoError: 400,
    MenorDeEdadSinAcudienteError: 400, TransicionEstadoInvalidaError: 400,
    SobreasignacionMedicoError: 409, LimiteDiarioAlcanzadoError: 409,
    DuplicidadRegistroError: 409, MedicoConCitasFuturaError: 409,
    HorarioFueraDeJornadaError: 409,
}.items():
    registrar_manejador(_tipo, _codigo)


async def manejar_error_validacion(request: Request, excepcion: Exception) -> HTMLResponse | JSONResponse:
    """Convierte errores de formato de Pydantic en mensajes comprensibles.

    Parámetros:
        request: Solicitud HTTP que produjo el error.
        excepcion: Error de validación recibido.
    Retorna:
        Respuesta JSON o plantilla HTML con el detalle del error.
    """
    errores = excepcion.errors()
    detalle = "; ".join(error.get("msg", "Formato inválido") for error in errores)
    if es_solicitud_json(request):
        return JSONResponse({"detail": detalle}, status_code=400)
    return app.state.plantillas.TemplateResponse(request=request, name="error.html", context={"alerta": detalle, "volver_a": ruta_retorno_segura(request)}, status_code=400)


app.add_exception_handler(ValidationError, manejar_error_validacion)
app.add_exception_handler(RequestValidationError, manejar_error_validacion)


def cargar_datos_semilla() -> None:
    """Precarga las sedes y usuarios requeridos para pruebas manuales.

    Retorna:
        Ninguno.
    """
    sede_norte = Sede("Sede Norte", "Calle 10 # 20-30", 4)
    sede_sur = Sede("Sede Sur", "Carrera 30 # 40-50", 3)
    for sede in (sede_norte, sede_sur):
        app.state.sede_repo.guardar(sede)
    usuarios = [
        Administrador(TipoDocumento.CC, "1000000001", "Ana", "Norte", "3000000001", "admin.norte@clinica.com", hashear_contrasena("AdminNorte2026"), Rol.ADMINISTRADOR, id_sede=sede_norte.id),
        Administrador(TipoDocumento.CC, "1000000002", "Bruno", "Sur", "3000000002", "admin.sur@clinica.com", hashear_contrasena("AdminSur2026"), Rol.ADMINISTRADOR, id_sede=sede_sur.id),
        Paciente(TipoDocumento.CC, "1000000003", "Sofía", "Secretaria", "3000000003", "secretaria@clinica.com", hashear_contrasena("Secretaria2026"), Rol.SECRETARIA, fecha_nacimiento=date(1990, 1, 1)),
        Medico(TipoDocumento.CC, "1000000004", "Carlos", "Oftalmólogo", "3000000004", "medico.norte@clinica.com", hashear_contrasena("MedicoNorte2026"), Rol.SECRETARIA, especialidad=TipoConsulta.OFTALMOLOGIA_GENERAL, id_sede=sede_norte.id),
        Medico(TipoDocumento.CC, "1000000005", "Diana", "Optómetra", "3000000005", "medico.sur@clinica.com", hashear_contrasena("MedicoSur2026"), Rol.SECRETARIA, especialidad=TipoConsulta.OPTOMETRIA, id_sede=sede_sur.id),
        Paciente(TipoDocumento.CC, "1000000006", "Elena", "Mayor", "3000000006", "paciente@clinica.com", hashear_contrasena("Paciente2026"), Rol.PACIENTE, fecha_nacimiento=date(1990, 5, 10)),
        Paciente(TipoDocumento.TI, "1000000007", "Felipe", "Menor", "3000000007", "menor@clinica.com", hashear_contrasena("Menor2026"), Rol.PACIENTE, fecha_nacimiento=date(2012, 5, 10), nombre_acudiente="Laura Menor", telefono_acudiente="3000000008"),
    ]
    for usuario in usuarios:
        app.state.usuario_repo.guardar(usuario)


if basededatos.base_de_datos_vacia(app.state.conexion_bd):
    cargar_datos_semilla()
app.include_router(auth_router.router)
app.include_router(paciente_router.router)
app.include_router(secretaria_router.router)
app.include_router(admin_router.router)
