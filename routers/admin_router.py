"""Rutas administrativas restringidas por sede."""

from datetime import date
from csv import writer
from io import StringIO
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from enums import EstadoUsuario, Rol
from excepciones import AccesoFueraDeSedError
from modelos import Administrador, Medico, Paciente, hashear_contrasena
from routers.paciente_router import obtener_sesion
from routers.auth_router import leer_datos
from schemas import ActualizarEspecialistaSchema, CambiarEstadoUsuarioSchema, JornadaMedicoSchema, LimiteDiarioSchema, MedicoCreateSchema, ReporteRequestSchema, SedeCreateSchema, SedeUpdateSchema, UsuarioInternoCreateSchema

router = APIRouter()


def requerir_administrador(id_sede: str, sesion: dict = Depends(obtener_sesion)) -> dict:
    """Exige un administrador de la misma sede solicitada.

    Parámetros:
        id_sede: Sede del recurso solicitado.
        sesion: Sesión validada.
    Retorna:
        Sesión administrativa válida.
    """
    if sesion["rol"] != Rol.ADMINISTRADOR.value or sesion.get("id_sede") != id_sede:
        raise AccesoFueraDeSedError("No tiene acceso a esta sede")
    return sesion


@router.get("/dashboard/administrador/{id_sede}", response_class=HTMLResponse)
async def tablero_administrador(id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> HTMLResponse:
    """Muestra el tablero administrativo y el reporte de una sede.

    Parámetros:
        id_sede: Identificador de la sede administrada.
        request: Solicitud con rango de fechas opcional.
        sesion: Sesión administrativa autorizada.
    Retorna:
        Tablero administrativo HTML.
    """
    medicos = request.app.state.administrador.obtener_medicos_por_sede(id_sede)
    medicos_reasignables = [usuario for usuario in request.app.state.usuario_repo.obtener_activos() if isinstance(usuario, Medico) and usuario.id_sede != id_sede]
    usuarios_activos = request.app.state.administrador.buscar_usuario_en_sede("", id_sede)
    hoy = date.today()
    fecha_inicio = date.fromisoformat(request.query_params.get("fecha_inicio", hoy.isoformat()))
    fecha_fin = date.fromisoformat(request.query_params.get("fecha_fin", hoy.isoformat()))
    reporte = request.app.state.reportes.generar_reporte_consolidado(fecha_inicio, fecha_fin, id_sede)
    sede_actual = request.app.state.sedes_servicio.obtener_sede(id_sede)
    sedes = request.app.state.sedes_servicio.obtener_sedes()
    conteo_medicos = request.app.state.sedes_servicio.contar_medicos_por_sede()
    usuarios_gestionables = request.app.state.administrador.obtener_usuarios_gestionables(id_sede, sesion["id_usuario"])
    bitacora = request.app.state.auditoria.consultar_bitacora(fecha_inicio, fecha_fin, id_sede)[:50]
    return request.app.state.plantillas.TemplateResponse(request=request, name="dashboard_admin.html", context={"medicos": medicos, "medicos_reasignables": medicos_reasignables, "usuarios_activos": usuarios_activos, "id_sede": id_sede, "fecha_inicio": fecha_inicio.isoformat(), "fecha_fin": fecha_fin.isoformat(), "reporte": reporte, "sede_actual": sede_actual, "sedes": sedes, "conteo_medicos": conteo_medicos, "usuarios_gestionables": usuarios_gestionables, "estados_usuario": [estado.value for estado in EstadoUsuario], "bitacora": bitacora})


@router.get("/medicos")
async def obtener_medicos(id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> JSONResponse:
    """Obtiene médicos activos de la sede de sesión."""
    medicos = request.app.state.administrador.obtener_medicos_por_sede(id_sede)
    return JSONResponse([{"id": m.id, "nombres": m.nombres, "apellidos": m.apellidos, "especialidad": m.especialidad.value, "correo": m.correo} for m in medicos])


@router.post("/medicos", response_model=None)
async def registrar_medico(id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Registra un médico en la sede del administrador."""
    datos = await leer_datos(request)
    datos["id_sede"] = id_sede
    entrada = MedicoCreateSchema(**datos)
    medico = Medico(tipo_documento=entrada.tipo_documento, numero_documento=entrada.numero_documento, nombres=entrada.nombres, apellidos=entrada.apellidos, telefono=entrada.telefono, correo=str(entrada.correo), contrasena=hashear_contrasena(entrada.contrasena), rol=Rol.SECRETARIA, especialidad=entrada.especialidad, id_sede=entrada.id_sede)
    request.app.state.administrador.registrar_medico(medico, id_sede)
    if "application/json" in request.headers.get("accept", ""): return JSONResponse({"id": medico.id}, status_code=201)
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.put("/medicos/{id_medico}")
async def actualizar_medico(id_medico: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> JSONResponse:
    """Actualiza los datos permitidos de un especialista."""
    entrada = ActualizarEspecialistaSchema(**(await leer_datos(request)))
    request.app.state.administrador.actualizar_datos_especialista(id_medico, entrada.nombres, entrada.apellidos, entrada.telefono, str(entrada.correo), id_sede)
    return JSONResponse({"mensaje": "Especialista actualizado"})


@router.api_route("/medicos/{id_medico}/jornada", methods=["POST", "PUT"])
async def actualizar_jornada_medico(id_medico: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> JSONResponse:
    """Actualiza la jornada configurable de un especialista de la sede."""
    entrada = JornadaMedicoSchema(**(await leer_datos(request)))
    request.app.state.administrador.actualizar_jornada_medico(id_medico, entrada.hora_inicio_manana, entrada.hora_fin_manana, entrada.hora_inicio_tarde, entrada.hora_fin_tarde, id_sede)
    return JSONResponse({"mensaje": "Jornada del especialista actualizada"})


@router.post("/usuarios", response_model=None)
async def registrar_usuario_interno(id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Registra credenciales nuevas para secretaría o administración."""
    entrada = UsuarioInternoCreateSchema(**(await leer_datos(request)))
    if entrada.rol == Rol.ADMINISTRADOR:
        usuario = Administrador(entrada.tipo_documento, entrada.numero_documento, entrada.nombres, entrada.apellidos, entrada.telefono, str(entrada.correo), hashear_contrasena(entrada.contrasena), entrada.rol, id_sede=id_sede)
    else:
        # Las cuentas de secretaría se representan como Paciente (igual que en los datos semilla):
        # comparten los mismos campos básicos y el rol es lo que realmente determina sus permisos.
        usuario = Paciente(entrada.tipo_documento, entrada.numero_documento, entrada.nombres, entrada.apellidos, entrada.telefono, str(entrada.correo), hashear_contrasena(entrada.contrasena), entrada.rol)
    request.app.state.administrador.registrar_usuario_interno(usuario, id_sede)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"id": usuario.id}, status_code=201)
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.post("/medicos/{id_medico}/asignar-sede", response_model=None)
async def asignar_sede(id_medico: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Asigna un médico a la sede de destino administrada."""
    datos = await leer_datos(request)
    request.app.state.administrador.asignar_sede_medico(id_medico, datos.get("nuevo_id_sede", ""), id_sede)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Sede asignada"})
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.post("/medicos/{id_medico}/desactivar", response_model=None)
async def desactivar_medico(id_medico: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Desactiva un médico de la sede, tras confirmación."""
    datos = await leer_datos(request)
    request.app.state.administrador.desactivar_medico(id_medico, id_sede, str(datos.get("confirmado", "")).lower() in ("true", "1", "on"))
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Médico desactivado"})
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.post("/usuarios/{id_usuario}/inactivar", response_model=None)
async def inactivar_usuario(id_usuario: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Inactiva un usuario preservando su historial."""
    datos = await leer_datos(request)
    request.app.state.administrador.inactivar_usuario(id_usuario, str(datos.get("confirmado", "")).lower() in ("true", "1", "on"))
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Usuario inactivado"})
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.get("/reportes")
async def reportes(id_sede: str, fecha_inicio: date, fecha_fin: date, request: Request, sesion: dict = Depends(requerir_administrador)) -> JSONResponse:
    """Genera el reporte consolidado de la sede administrativa."""
    reporte = request.app.state.reportes.generar_reporte_consolidado(fecha_inicio, fecha_fin, id_sede)
    return JSONResponse({"total_citas_atendidas": reporte["total_citas_atendidas"], "desglose_por_especialidad": {clave.value: valor for clave, valor in reporte["desglose_por_especialidad"].items()}, "total_ingresos": reporte["total_ingresos"], "citas_canceladas": reporte["citas_canceladas"]})


@router.get("/reportes/exportar")
async def exportar_reporte(id_sede: str, fecha_inicio: date, fecha_fin: date, request: Request, sesion: dict = Depends(requerir_administrador)) -> Response:
    """Exporta el reporte consolidado de la sede como archivo CSV.

    Parámetros:
        id_sede: Sede administrativa autorizada.
        fecha_inicio: Inicio del rango inclusivo.
        fecha_fin: Fin del rango inclusivo.
        request: Solicitud HTTP.
        sesion: Sesión administrativa válida.
    Retorna:
        Archivo CSV de descarga segura.
    """
    reporte = request.app.state.reportes.generar_reporte_consolidado(fecha_inicio, fecha_fin, id_sede)
    salida = StringIO()
    csv = writer(salida)
    csv.writerow(["Indicador", "Valor"])
    csv.writerow(["Fecha inicial", fecha_inicio.isoformat()])
    csv.writerow(["Fecha final", fecha_fin.isoformat()])
    csv.writerow(["Citas atendidas", reporte["total_citas_atendidas"]])
    csv.writerow(["Ingresos generados", reporte["total_ingresos"]])
    csv.writerow(["Citas canceladas", reporte["citas_canceladas"]])
    for especialidad, cantidad in reporte["desglose_por_especialidad"].items():
        csv.writerow([f"Citas {especialidad.value}", cantidad])
    nombre = f"reporte_sede_{id_sede}_{fecha_inicio}_{fecha_fin}.csv"
    return Response(salida.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})


@router.get("/sedes")
async def obtener_sedes(id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> JSONResponse:
    """Obtiene las sedes registradas con su cantidad de especialistas activos.

    Parámetros:
        id_sede: Sede administrada en la sesión.
        request: Solicitud HTTP.
        sesion: Sesión administrativa válida.
    Retorna:
        Listado de sedes en JSON.
    """
    conteo = request.app.state.sedes_servicio.contar_medicos_por_sede()
    sedes = request.app.state.sedes_servicio.obtener_sedes()
    return JSONResponse([{"id": s.id, "nombre": s.nombre, "direccion": s.direccion, "numero_consultorios": s.numero_consultorios, "medicos_activos": conteo.get(s.id, 0), "administrada_por_usted": s.id == id_sede} for s in sedes])


@router.post("/sedes", response_model=None)
async def crear_sede(id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Registra una sede nueva de la clínica.

    Parámetros:
        id_sede: Sede administrada en la sesión.
        request: Solicitud con los datos de la sede.
        sesion: Sesión administrativa válida.
    Retorna:
        Confirmación JSON o redirección al tablero.
    """
    entrada = SedeCreateSchema(**(await leer_datos(request)))
    sede = request.app.state.sedes_servicio.crear_sede(entrada.nombre, entrada.direccion, entrada.numero_consultorios)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"id": sede.id, "nombre": sede.nombre}, status_code=201)
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.api_route("/sedes/{id_sede_destino}", methods=["POST", "PUT"], response_model=None)
async def actualizar_sede(id_sede_destino: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Actualiza la información y los recursos de la sede administrada.

    Parámetros:
        id_sede_destino: Sede que se desea modificar.
        id_sede: Sede autorizada por la sesión.
        request: Solicitud con los datos nuevos.
        sesion: Sesión administrativa válida.
    Retorna:
        Confirmación JSON o redirección al tablero.
    """
    entrada = SedeUpdateSchema(**(await leer_datos(request)))
    request.app.state.sedes_servicio.actualizar_sede(id_sede_destino, entrada.nombre, entrada.direccion, entrada.numero_consultorios, id_sede)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Sede actualizada"})
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.post("/medicos/{id_medico}/limite-diario", response_model=None)
async def configurar_limite_diario(id_medico: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Configura el máximo de citas diarias que acepta un especialista.

    Parámetros:
        id_medico: Especialista configurado.
        id_sede: Sede autorizada por la sesión.
        request: Solicitud con el límite diario.
        sesion: Sesión administrativa válida.
    Retorna:
        Confirmación JSON o redirección al tablero.
    """
    entrada = LimiteDiarioSchema(**(await leer_datos(request)))
    request.app.state.administrador.configurar_limite_diario_medico(id_medico, entrada.max_citas_dia, id_sede)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Límite diario configurado", "max_citas_dia": entrada.max_citas_dia})
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.post("/usuarios/{id_usuario}/estado", response_model=None)
async def cambiar_estado_usuario(id_usuario: str, id_sede: str, request: Request, sesion: dict = Depends(requerir_administrador)) -> RedirectResponse | JSONResponse:
    """Cambia el estado de una cuenta entre activa, inactiva y bloqueada.

    Parámetros:
        id_usuario: Cuenta afectada.
        id_sede: Sede autorizada por la sesión.
        request: Solicitud con el estado destino y la confirmación.
        sesion: Sesión administrativa válida.
    Retorna:
        Confirmación JSON o redirección al tablero.
    """
    datos = await leer_datos(request)
    datos["confirmado"] = str(datos.get("confirmado", "")).lower() in ("true", "1", "on")
    entrada = CambiarEstadoUsuarioSchema(**datos)
    request.app.state.administrador.cambiar_estado_usuario(id_usuario, entrada.nuevo_estado, entrada.confirmado, sesion["id_usuario"])
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": f"Cuenta en estado {entrada.nuevo_estado.value}"})
    return RedirectResponse(f"/dashboard/administrador/{id_sede}", status_code=303)


@router.get("/auditoria")
async def consultar_auditoria(id_sede: str, fecha_inicio: date, fecha_fin: date, request: Request, sesion: dict = Depends(requerir_administrador)) -> JSONResponse:
    """Consulta la bitácora de auditoría de la sede administrada.

    Parámetros:
        id_sede: Sede autorizada por la sesión.
        fecha_inicio: Inicio inclusivo del rango.
        fecha_fin: Fin inclusivo del rango.
        request: Solicitud HTTP.
        sesion: Sesión administrativa válida.
    Retorna:
        Eventos auditados en JSON.
    """
    registros = request.app.state.auditoria.consultar_bitacora(fecha_inicio, fecha_fin, id_sede)
    return JSONResponse([{"fecha_hora": r.fecha_hora.isoformat(timespec="seconds"), "accion": r.accion, "id_usuario": r.id_usuario, "rol": r.rol, "resultado": r.resultado, "exitoso": r.fue_exitoso()} for r in registros])


@router.get("/auditoria/exportar")
async def exportar_auditoria(id_sede: str, fecha_inicio: date, fecha_fin: date, request: Request, sesion: dict = Depends(requerir_administrador)) -> Response:
    """Exporta la bitácora de auditoría de la sede como archivo CSV.

    Parámetros:
        id_sede: Sede autorizada por la sesión.
        fecha_inicio: Inicio inclusivo del rango.
        fecha_fin: Fin inclusivo del rango.
        request: Solicitud HTTP.
        sesion: Sesión administrativa válida.
    Retorna:
        Archivo CSV de descarga segura.
    """
    registros = request.app.state.auditoria.consultar_bitacora(fecha_inicio, fecha_fin, id_sede)
    salida = StringIO()
    csv = writer(salida)
    csv.writerow(["Fecha y hora", "Accion", "Usuario", "Rol", "Codigo", "Exitoso"])
    for registro in registros:
        csv.writerow([registro.fecha_hora.isoformat(timespec="seconds"), registro.accion, registro.id_usuario, registro.rol, registro.resultado, "SI" if registro.fue_exitoso() else "NO"])
    nombre = f"auditoria_sede_{id_sede}_{fecha_inicio}_{fecha_fin}.csv"
    return Response(salida.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{nombre}"'})
