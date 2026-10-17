"""Rutas exclusivas del paciente."""

import base64
import hashlib
import hmac
import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from config import CLAVE_SESION, NOMBRE_COOKIE_SESION
from enums import EstadoCita, EstadoUsuario, Rol
from excepciones import AccesoFueraDeSedError, CredencialesInvalidasError, TransicionEstadoInvalidaError, UsuarioInactivoError
from modelos import CitaMedica
from routers.auth_router import leer_datos
from schemas import ActualizarPacienteSchema, CancelarCitaSchema, CitaCreateSchema, ReagendarCitaSchema

router = APIRouter()


def obtener_sesion(request: Request) -> dict:
    """Valida y decodifica la cookie firmada.

    Parámetros:
        request: Solicitud HTTP.
    Retorna:
        Datos de sesión validados.
    """
    valor = request.cookies.get(NOMBRE_COOKIE_SESION, "")
    try:
        datos, firma = valor.rsplit(".", 1)
        esperada = hmac.new(CLAVE_SESION.encode(), datos.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(firma, esperada): raise ValueError
        sesion = json.loads(base64.urlsafe_b64decode(datos.encode()))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        raise CredencialesInvalidasError("La sesión no es válida")
    usuario = request.app.state.usuario_repo.buscar_por_id(sesion.get("id_usuario", ""))
    if usuario is None:
        raise CredencialesInvalidasError("La sesión no corresponde a un usuario registrado")
    if usuario.estado != EstadoUsuario.ACTIVO:
        raise UsuarioInactivoError("Su cuenta se encuentra inactiva o bloqueada")
    return sesion


def requerir_paciente(sesion: dict = Depends(obtener_sesion)) -> dict:
    """Exige que la sesión corresponda a un paciente.

    Parámetros:
        sesion: Sesión validada.
    Retorna:
        Sesión del paciente.
    """
    if sesion["rol"] != Rol.PACIENTE.value: raise AccesoFueraDeSedError("No tiene permisos de paciente")
    return sesion


@router.get("/dashboard/paciente", response_class=HTMLResponse)
async def tablero_paciente(request: Request, sesion: dict = Depends(requerir_paciente)) -> HTMLResponse:
    """Muestra historial ordenable, filtrable y opciones de disponibilidad.

    Parámetros:
        request: Solicitud HTTP con filtros opcionales.
        sesion: Sesión autenticada del paciente.
    Retorna:
        Tablero HTML del paciente.
    """
    citas = request.app.state.cita_repo.obtener_por_paciente(sesion["id_usuario"])
    estado = request.query_params.get("estado", "")
    orden = request.query_params.get("orden", "desc")
    if estado in {valor.value for valor in EstadoCita}:
        citas = [cita for cita in citas if cita.estado_cita.value == estado]
    citas.sort(key=lambda cita: cita.fecha_hora, reverse=orden != "asc")
    medicos = [u for u in request.app.state.usuario_repo.obtener_activos() if hasattr(u, "especialidad")]
    medicos_por_id = {medico.id: medico for medico in medicos}
    sedes = request.app.state.sedes_servicio.obtener_sedes()
    sedes_por_id = {sede.id: sede for sede in sedes}
    detalles_citas = [{"cita": cita, "medico": medicos_por_id.get(cita.id_medico), "sede": sedes_por_id.get(cita.id_sede)} for cita in citas]
    registros_espera = [registro for registro in request.app.state.agendamiento.obtener_lista_espera() if registro.id_paciente == sesion["id_usuario"]]
    paciente = request.app.state.usuario_repo.buscar_por_id(sesion["id_usuario"])
    etiquetas_cita = {"PROGRAMADA": "Pendiente", "CONFIRMADA": "Confirmada", "ATENDIDA": "Completada", "CANCELADA": "Cancelada"}
    return request.app.state.plantillas.TemplateResponse(request=request, name="dashboard_paciente.html", context={"detalles_citas": detalles_citas, "medicos": medicos, "sedes": sedes, "registros_espera": registros_espera, "paciente": paciente, "etiquetas_cita": etiquetas_cita, "hoy": date.today().isoformat(), "estado_seleccionado": estado, "orden_seleccionado": orden})


@router.post("/agendar", response_model=None)
async def agendar(request: Request, sesion: dict = Depends(obtener_sesion)) -> RedirectResponse | JSONResponse:
    """Agenda una cita para el paciente autenticado o para un paciente seleccionado por secretaría.

    La ruta es compartida por ambos formularios. Cuando agenda un paciente, el
    identificador enviado por el navegador se ignora para conservar la cita en
    su propia cuenta; cuando agenda secretaría, el paciente se resuelve por
    documento, nombre único o identificador.
    """
    datos = await leer_datos(request)
    if sesion["rol"] == Rol.PACIENTE.value:
        datos["id_paciente"] = sesion["id_usuario"]
        paciente = request.app.state.usuario_repo.buscar_por_id(sesion["id_usuario"])
        destino = "/dashboard/paciente"
    elif sesion["rol"] == Rol.SECRETARIA.value:
        paciente = request.app.state.secretaria.resolver_paciente(datos.get("id_paciente", ""))
        datos["id_paciente"] = paciente.id
        destino = "/dashboard/secretaria"
    else:
        raise AccesoFueraDeSedError("No tiene permisos para agendar citas")
    request.app.state.secretaria.actualizar_acudiente_menor(paciente, datos.get("nombre_acudiente", ""), datos.get("telefono_acudiente", ""))
    entrada = CitaCreateSchema(**datos)
    cita = CitaMedica(entrada.id_paciente, entrada.id_medico, entrada.id_sede, entrada.fecha_hora, entrada.tipo_consulta)
    request.app.state.agendamiento.agendar_cita(cita)
    if "application/json" in request.headers.get("accept", ""): return JSONResponse({"id": cita.id}, status_code=201)
    return RedirectResponse(destino, status_code=303)


@router.post("/cancelar", response_model=None)
async def cancelar(request: Request, sesion: dict = Depends(requerir_paciente)) -> RedirectResponse | JSONResponse:
    """Cancela una cita propia tras doble confirmación."""
    datos = await leer_datos(request)
    cita = request.app.state.cita_repo.buscar_por_id(datos.get("id_cita", ""))
    if cita is None or cita.id_paciente != sesion["id_usuario"]: raise AccesoFueraDeSedError("No puede cancelar una cita ajena")
    if cita.fecha_hora <= datetime.now():
        raise TransicionEstadoInvalidaError("Solo puede cancelar una cita antes de la fecha y hora programadas")
    entrada = CancelarCitaSchema(**datos)
    request.app.state.agendamiento.cancelar_cita(cita.id, entrada.motivo, entrada.confirmado)
    if "application/json" in request.headers.get("accept", ""): return JSONResponse({"mensaje": "Cita cancelada"})
    return RedirectResponse("/dashboard/paciente", status_code=303)


@router.post("/reagendar", response_model=None)
async def reagendar(request: Request, sesion: dict = Depends(requerir_paciente)) -> RedirectResponse | JSONResponse:
    """Reagenda una cita propia."""
    datos = await leer_datos(request)
    cita = request.app.state.cita_repo.buscar_por_id(datos.get("id_cita", ""))
    if cita is None or cita.id_paciente != sesion["id_usuario"]: raise AccesoFueraDeSedError("No puede reagendar una cita ajena")
    if cita.fecha_hora <= datetime.now():
        raise TransicionEstadoInvalidaError("Solo puede reagendar una cita antes de la fecha y hora programadas")
    entrada = ReagendarCitaSchema(**datos)
    request.app.state.agendamiento.reagendar_cita(cita.id, entrada.nueva_fecha_hora)
    if "application/json" in request.headers.get("accept", ""): return JSONResponse({"mensaje": "Cita reagendada"})
    return RedirectResponse("/dashboard/paciente", status_code=303)


@router.post("/mis-datos", response_model=None)
async def actualizar_mis_datos(request: Request, sesion: dict = Depends(requerir_paciente)) -> RedirectResponse | JSONResponse:
    """Permite al paciente actualizar sus propios datos de contacto.

    Parámetros:
        request: Solicitud con los datos nuevos.
        sesion: Sesión autenticada del paciente.
    Retorna:
        Confirmación JSON o redirección al tablero del paciente.
    """
    entrada = ActualizarPacienteSchema(**(await leer_datos(request)))
    request.app.state.secretaria.actualizar_datos_paciente(sesion["id_usuario"], entrada.telefono, str(entrada.correo), entrada.nombre_acudiente, entrada.telefono_acudiente)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Datos actualizados"})
    return RedirectResponse("/dashboard/paciente", status_code=303)
