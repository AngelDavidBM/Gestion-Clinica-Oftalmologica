"""Rutas de autenticación y registro de pacientes."""

import base64
import hashlib
import hmac
import json
from datetime import date
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import CLAVE_SESION, NOMBRE_COOKIE_SESION
from enums import Rol
from modelos import Paciente, hashear_contrasena
from schemas import LoginSchema, PacienteCreateSchema

router = APIRouter()


async def leer_datos(request: Request) -> dict:
    """Lee datos JSON o de formulario sin dependencias adicionales.

    Parámetros:
        request: Solicitud HTTP con cuerpo.
    Retorna:
        Diccionario con los valores enviados.
    """
    if "application/json" in request.headers.get("content-type", ""):
        return await request.json()
    contenido = (await request.body()).decode("utf-8")
    return {clave: valores[-1] for clave, valores in parse_qs(contenido, keep_blank_values=True).items()}


def crear_sesion(usuario: object) -> str:
    """Crea una cookie firmada con identidad y rol.

    Parámetros:
        usuario: Usuario autenticado.
    Retorna:
        Valor firmado de sesión.
    """
    contenido = json.dumps({"id_usuario": usuario.id, "rol": usuario.rol.value, "id_sede": getattr(usuario, "id_sede", "")}).encode()
    datos = base64.urlsafe_b64encode(contenido).decode()
    firma = hmac.new(CLAVE_SESION.encode(), datos.encode(), hashlib.sha256).hexdigest()
    return f"{datos}.{firma}"


def leer_sesion_opcional(request: Request) -> dict:
    """Decodifica la cookie de sesión sin interrumpir la solicitud cuando falta o es inválida.

    Parámetros:
        request: Solicitud HTTP recibida.
    Retorna:
        Datos de sesión o un diccionario vacío.
    """
    valor = request.cookies.get(NOMBRE_COOKIE_SESION, "")
    try:
        datos, firma = valor.rsplit(".", 1)
        esperada = hmac.new(CLAVE_SESION.encode(), datos.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(firma, esperada):
            return {}
        return json.loads(base64.urlsafe_b64decode(datos.encode()))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return {}


@router.get("/login", response_class=HTMLResponse)
async def ver_login(request: Request) -> HTMLResponse:
    """Renderiza la pantalla de acceso.

    Parámetros:
        request: Solicitud HTTP.
    Retorna:
        Plantilla de inicio de sesión.
    """
    return request.app.state.plantillas.TemplateResponse(request=request, name="login.html", context={"hoy": date.today().isoformat()})


@router.post("/login", response_model=None)
async def login(request: Request) -> RedirectResponse | JSONResponse:
    """Autentica al usuario y crea una sesión HTTP-only.

    Parámetros:
        request: Solicitud HTTP con credenciales.
    Retorna:
        Redirección HTML o respuesta JSON.
    """
    datos = await leer_datos(request)
    entrada = LoginSchema(**datos)
    usuario = request.app.state.autenticacion.login(str(entrada.correo), entrada.contrasena)
    ruta = request.app.state.autenticacion.obtener_ruta_redireccion(usuario)
    if "application/json" in request.headers.get("accept", ""):
        respuesta = JSONResponse({"ruta": ruta})
    else:
        respuesta = RedirectResponse(ruta, status_code=303)
    respuesta.set_cookie(NOMBRE_COOKIE_SESION, crear_sesion(usuario), httponly=True, samesite="lax")
    return respuesta


@router.post("/logout", response_model=None)
async def logout(request: Request) -> RedirectResponse | JSONResponse:
    """Elimina la cookie de sesión actual.

    Parámetros:
        request: Solicitud HTTP.
    Retorna:
        Redirección a login o confirmación JSON.
    """
    respuesta = JSONResponse({"mensaje": "Sesión cerrada"}) if "application/json" in request.headers.get("accept", "") else RedirectResponse("/login", status_code=303)
    respuesta.delete_cookie(NOMBRE_COOKIE_SESION)
    return respuesta


@router.post("/registro-paciente", response_model=None)
async def registro_paciente(request: Request) -> RedirectResponse | JSONResponse:
    """Registra un paciente con contraseña hasheada.

    Parámetros:
        request: Solicitud HTTP con datos del paciente.
    Retorna:
        Resultado JSON o redirección al inicio.
    """
    datos = await leer_datos(request)
    entrada = PacienteCreateSchema(**datos)
    paciente = Paciente(tipo_documento=entrada.tipo_documento, numero_documento=entrada.numero_documento, nombres=entrada.nombres, apellidos=entrada.apellidos, telefono=entrada.telefono, correo=str(entrada.correo), contrasena=hashear_contrasena(entrada.contrasena), rol=Rol.PACIENTE, fecha_nacimiento=entrada.fecha_nacimiento, nombre_acudiente=entrada.nombre_acudiente, telefono_acudiente=entrada.telefono_acudiente)
    request.app.state.autenticacion.registrar_paciente(paciente)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Paciente registrado", "id": paciente.id}, status_code=201)
    return RedirectResponse("/login", status_code=303)
