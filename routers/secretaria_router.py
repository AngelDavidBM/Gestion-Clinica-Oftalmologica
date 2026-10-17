"""Rutas globales de secretaría."""

from datetime import date
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from enums import EstadoCita, EstadoPago, Rol
from excepciones import AccesoFueraDeSedError, CampoObligatorioError, TransicionEstadoInvalidaError
from modelos import CitaMedica, RegistroListaEspera
from routers.paciente_router import obtener_sesion
from routers.auth_router import leer_datos
from schemas import ActualizarPacienteSchema, AnularCobroSchema, CancelarCitaSchema, CitaCreateSchema, ListaEsperaSchema, PromoverEsperaSchema, ReagendarCitaSchema, RegistrarCobroSchema, RetirarEsperaSchema

router = APIRouter()


def requerir_secretaria(sesion: dict = Depends(obtener_sesion)) -> dict:
    """Exige una sesión de secretaria.

    Parámetros:
        sesion: Sesión validada.
    Retorna:
        Sesión de secretaria.
    """
    if sesion["rol"] != Rol.SECRETARIA.value: raise AccesoFueraDeSedError("No tiene permisos de secretaría")
    return sesion


@router.get("/dashboard/secretaria", response_class=HTMLResponse)
async def tablero_secretaria(request: Request, sesion: dict = Depends(requerir_secretaria)) -> HTMLResponse:
    """Muestra agenda, búsqueda, cobro y lista de espera.

    Parámetros:
        request: Solicitud HTTP.
        sesion: Sesión autenticada de secretaría.
    Retorna:
        Tablero HTML de secretaría.
    """
    medicos = [u for u in request.app.state.usuario_repo.obtener_activos() if hasattr(u, "especialidad")]
    citas = request.app.state.cita_repo.obtener_todas()
    filtro_sede = request.query_params.get("id_sede", "")
    filtro_medico = request.query_params.get("id_medico", "")
    filtro_fecha = request.query_params.get("fecha", "")
    filtro_estado = request.query_params.get("estado", "")
    orden = request.query_params.get("orden", "desc")
    if filtro_sede:
        citas = [cita for cita in citas if cita.id_sede == filtro_sede]
    if filtro_medico:
        citas = [cita for cita in citas if cita.id_medico == filtro_medico]
    if filtro_fecha:
        try:
            citas = [cita for cita in citas if cita.fecha_hora.date() == date.fromisoformat(filtro_fecha)]
        except ValueError:
            raise CampoObligatorioError("La fecha del filtro no es válida")
    if filtro_estado in {valor.value for valor in EstadoCita}:
        citas = [cita for cita in citas if cita.estado_cita.value == filtro_estado]
    citas.sort(key=lambda cita: cita.fecha_hora, reverse=orden != "asc")
    sedes = request.app.state.sedes_servicio.obtener_sedes()
    pacientes_por_id = {usuario.id: usuario for usuario in request.app.state.usuario_repo.obtener_todos() if usuario.rol == Rol.PACIENTE}
    sedes_por_id = {sede.id: sede for sede in sedes}
    medicos_por_id = {medico.id: medico for medico in medicos}
    detalles_citas = [{"cita": cita, "paciente": pacientes_por_id.get(cita.id_paciente), "medico": medicos_por_id.get(cita.id_medico), "sede": sedes_por_id.get(cita.id_sede)} for cita in citas]
    espera_detallada = [{"registro": registro, "paciente": pacientes_por_id.get(registro.id_paciente), "sede": sedes_por_id.get(registro.id_sede)} for registro in request.app.state.agendamiento.obtener_lista_espera()]
    usuarios_activos = request.app.state.secretaria.obtener_usuarios_activos()
    etiquetas_cita = {"PROGRAMADA": "Pendiente", "CONFIRMADA": "Confirmada", "ATENDIDA": "Completada", "CANCELADA": "Cancelada"}
    return request.app.state.plantillas.TemplateResponse(request=request, name="dashboard_secretaria.html", context={"medicos": medicos, "detalles_citas": detalles_citas, "sedes": sedes, "espera_detallada": espera_detallada, "usuarios_activos": usuarios_activos, "etiquetas_cita": etiquetas_cita, "filtro_sede": filtro_sede, "filtro_medico": filtro_medico, "filtro_fecha": filtro_fecha, "filtro_estado": filtro_estado, "orden_seleccionado": orden, "estados_cita": [valor.value for valor in EstadoCita], "hoy": date.today().isoformat()})


@router.get("/buscar")
async def buscar(termino: str, request: Request, sesion: dict = Depends(requerir_secretaria)) -> JSONResponse:
    """Busca pacientes globalmente por documento o nombres."""
    pacientes = request.app.state.secretaria.buscar_paciente(termino)
    return JSONResponse([{"id": p.id, "documento": p.numero_documento, "nombres": p.nombres, "apellidos": p.apellidos, "edad": p.calcular_edad(), "estado": p.estado.value, "requiere_acudiente": p.es_menor_de_edad()} for p in pacientes])


@router.get("/bloques-disponibles")
async def bloques_disponibles(id_sede: str, id_medico: str, fecha: date, request: Request, sesion: dict = Depends(obtener_sesion)) -> JSONResponse:
    """Obtiene bloques libres para pacientes o secretaría.

    Parámetros:
        id_sede: Identificador de sede.
        id_medico: Identificador de médico.
        fecha: Fecha de consulta.
        request: Solicitud HTTP.
        sesion: Sesión autenticada.
    Retorna:
        Bloques de horario disponibles en JSON.
    """
    if sesion["rol"] not in (Rol.PACIENTE.value, Rol.SECRETARIA.value):
        raise AccesoFueraDeSedError("No tiene permisos para consultar disponibilidad")
    bloques = request.app.state.agendamiento.consultar_bloques_del_dia(id_sede, id_medico, fecha)
    return JSONResponse([{"hora": bloque["hora"].isoformat(), "ocupado": bloque["ocupado"]} for bloque in bloques])


@router.post("/agendar", response_model=None)
async def agendar(request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Agenda una cita desde secretaría."""
    datos = await leer_datos(request)
    paciente = request.app.state.secretaria.resolver_paciente(datos.get("id_paciente", ""))
    datos["id_paciente"] = paciente.id
    request.app.state.secretaria.actualizar_acudiente_menor(paciente, datos.get("nombre_acudiente", ""), datos.get("telefono_acudiente", ""))
    entrada = CitaCreateSchema(**datos)
    cita = CitaMedica(entrada.id_paciente, entrada.id_medico, entrada.id_sede, entrada.fecha_hora, entrada.tipo_consulta)
    request.app.state.agendamiento.agendar_cita(cita)
    if "application/json" in request.headers.get("accept", ""): return JSONResponse({"id": cita.id}, status_code=201)
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/cobrar", response_model=None)
async def cobrar(request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Registra el cobro de una cita atendida."""
    datos = await leer_datos(request)
    cita = request.app.state.cita_repo.buscar_por_id(datos.get("id_cita", ""))
    if cita is None: raise CampoObligatorioError("La cita solicitada no existe")
    if cita.estado_cita != EstadoCita.ATENDIDA:
        raise TransicionEstadoInvalidaError("Solo es posible cobrar una cita que se encuentra ATENDIDA")
    if cita.estado_pago != EstadoPago.PENDIENTE:
        raise TransicionEstadoInvalidaError("Solo es posible cobrar una cita con pago PENDIENTE")
    entrada = RegistrarCobroSchema(**datos)
    cita.valor_base, cita.porcentaje_descuento, cita.descuento_fijo, cita.metodo_pago = entrada.valor_base, entrada.porcentaje_descuento, entrada.descuento_fijo, entrada.metodo_pago
    cita.calcular_valor_neto()
    cita.estado_pago = EstadoPago.PAGADO
    request.app.state.cita_repo.guardar(cita)
    if "application/json" in request.headers.get("accept", ""): return JSONResponse({"valor_neto": cita.valor_neto})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/anular-cobro", response_model=None)
async def anular_cobro(request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Anula un pago cobrado tras confirmación expresa de secretaría."""
    entrada = AnularCobroSchema(**(await leer_datos(request)))
    request.app.state.secretaria.anular_cobro(entrada.id_cita, entrada.confirmado)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Pago anulado"})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/citas/cancelar", response_model=None)
async def cancelar_cita_secretaria(request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Permite a secretaría cancelar una cita con motivo y confirmación."""
    datos = await leer_datos(request)
    entrada = CancelarCitaSchema(**datos)
    request.app.state.agendamiento.cancelar_cita(datos.get("id_cita", ""), entrada.motivo, entrada.confirmado)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Cita cancelada"})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/citas/reagendar", response_model=None)
async def reagendar_cita_secretaria(request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Permite a secretaría reagendar una cita no terminal."""
    datos = await leer_datos(request)
    entrada = ReagendarCitaSchema(**datos)
    request.app.state.agendamiento.reagendar_cita(datos.get("id_cita", ""), entrada.nueva_fecha_hora)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Cita reagendada"})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/lista-espera", response_model=None)
async def agregar_lista_espera(request: Request, sesion: dict = Depends(obtener_sesion)) -> RedirectResponse | JSONResponse:
    """Registra una solicitud de lista de espera para paciente o secretaría.

    Parámetros:
        request: Solicitud con la sede y tipo de consulta.
        sesion: Sesión autenticada.
    Retorna:
        Confirmación JSON o redirección al tablero correspondiente.
    """
    if sesion["rol"] not in (Rol.PACIENTE.value, Rol.SECRETARIA.value):
        raise AccesoFueraDeSedError("No tiene permisos para registrar lista de espera")
    datos = await leer_datos(request)
    if sesion["rol"] == Rol.PACIENTE.value:
        datos["id_paciente"] = sesion["id_usuario"]
    else:
        datos["id_paciente"] = request.app.state.secretaria.resolver_paciente(datos.get("id_paciente", "")).id
    entrada = ListaEsperaSchema(**datos)
    if not entrada.id_paciente:
        raise CampoObligatorioError("Debe seleccionar un paciente para la lista de espera")
    registro = RegistroListaEspera(entrada.id_paciente, entrada.id_sede, entrada.tipo_consulta)
    request.app.state.agendamiento.agregar_a_lista_espera(registro)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Paciente agregado a lista de espera", "id": registro.id}, status_code=201)
    destino = "/dashboard/paciente" if sesion["rol"] == Rol.PACIENTE.value else "/dashboard/secretaria"
    return RedirectResponse(destino, status_code=303)


@router.post("/confirmar", response_model=None)
async def confirmar(request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Confirma una cita programada para iniciar su ciclo clínico."""
    datos = await leer_datos(request)
    request.app.state.agendamiento.confirmar_cita(datos.get("id_cita", ""))
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Cita confirmada"})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/atender", response_model=None)
async def atender(request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Registra la atención de una cita confirmada."""
    datos = await leer_datos(request)
    request.app.state.agendamiento.registrar_atencion(datos.get("id_cita", ""), datos.get("observaciones", ""))
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Atención registrada"})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.get("/pacientes/{id_paciente}/historial")
async def historial_paciente(id_paciente: str, request: Request, sesion: dict = Depends(requerir_secretaria)) -> JSONResponse:
    """Consulta el historial completo de citas de un paciente.

    Parámetros:
        id_paciente: Documento, nombre único o identificador del paciente.
        request: Solicitud con los parámetros de filtro y orden.
        sesion: Sesión de secretaría autenticada.
    Retorna:
        Historial del paciente en JSON.
    """
    paciente = request.app.state.secretaria.resolver_paciente(id_paciente)
    solo_atendidas = request.query_params.get("solo_atendidas", "").lower() in ("true", "1", "on")
    orden = request.query_params.get("orden", "desc")
    citas = request.app.state.secretaria.obtener_historial_paciente(paciente.id, solo_atendidas, orden)
    medicos = {usuario.id: usuario for usuario in request.app.state.usuario_repo.obtener_todos() if hasattr(usuario, "especialidad")}
    sedes = {sede.id: sede for sede in request.app.state.sedes_servicio.obtener_sedes()}
    etiquetas = {"PROGRAMADA": "Pendiente", "CONFIRMADA": "Confirmada", "ATENDIDA": "Completada", "CANCELADA": "Cancelada"}
    detalle = [{
        "id": cita.id,
        "fecha_hora": cita.fecha_hora.isoformat(timespec="minutes"),
        "tipo_consulta": cita.tipo_consulta.value,
        "especialista": f"{medicos[cita.id_medico].nombres} {medicos[cita.id_medico].apellidos}" if cita.id_medico in medicos else "No disponible",
        "sede": sedes[cita.id_sede].nombre if cita.id_sede in sedes else "No disponible",
        "estado": etiquetas[cita.estado_cita.value],
        "estado_pago": cita.estado_pago.value,
        "valor_neto": cita.valor_neto,
        "observaciones": cita.observaciones_atencion,
        "motivo_cancelacion": cita.motivo_cancelacion,
    } for cita in citas]
    return JSONResponse({"paciente": f"{paciente.nombres} {paciente.apellidos}", "documento": paciente.numero_documento, "edad": paciente.calcular_edad(), "estado": paciente.estado.value, "total_citas": len(detalle), "citas": detalle})


@router.post("/pacientes/{id_paciente}/actualizar", response_model=None)
async def actualizar_paciente(id_paciente: str, request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Actualiza los datos de contacto de un paciente desde secretaría.

    Parámetros:
        id_paciente: Documento, nombre único o identificador del paciente.
        request: Solicitud con los datos nuevos.
        sesion: Sesión de secretaría autenticada.
    Retorna:
        Confirmación JSON o redirección al tablero.
    """
    paciente = request.app.state.secretaria.resolver_paciente(id_paciente)
    entrada = ActualizarPacienteSchema(**(await leer_datos(request)))
    request.app.state.secretaria.actualizar_datos_paciente(paciente.id, entrada.telefono, str(entrada.correo), entrada.nombre_acudiente, entrada.telefono_acudiente)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Datos del paciente actualizados"})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/lista-espera/{id_registro}/retirar", response_model=None)
async def retirar_lista_espera(id_registro: str, request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Retira una solicitud de la lista de espera tras confirmación.

    Parámetros:
        id_registro: Identificador de la solicitud en espera.
        request: Solicitud con la confirmación.
        sesion: Sesión de secretaría autenticada.
    Retorna:
        Confirmación JSON o redirección al tablero.
    """
    datos = await leer_datos(request)
    datos["confirmado"] = str(datos.get("confirmado", "")).lower() in ("true", "1", "on")
    entrada = RetirarEsperaSchema(**datos)
    request.app.state.agendamiento.retirar_de_lista_espera(id_registro, entrada.confirmado)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Solicitud retirada de la lista de espera"})
    return RedirectResponse("/dashboard/secretaria", status_code=303)


@router.post("/lista-espera/{id_registro}/promover", response_model=None)
async def promover_lista_espera(id_registro: str, request: Request, sesion: dict = Depends(requerir_secretaria)) -> RedirectResponse | JSONResponse:
    """Asigna un bloque liberado a una solicitud de la lista de espera.

    Parámetros:
        id_registro: Identificador de la solicitud en espera.
        request: Solicitud con el especialista y el bloque asignado.
        sesion: Sesión de secretaría autenticada.
    Retorna:
        Identificador de la cita creada o redirección al tablero.
    """
    entrada = PromoverEsperaSchema(**(await leer_datos(request)))
    cita = request.app.state.agendamiento.promover_lista_espera(id_registro, entrada.id_medico, entrada.fecha_hora)
    if "application/json" in request.headers.get("accept", ""):
        return JSONResponse({"mensaje": "Cita agendada desde la lista de espera", "id": cita.id}, status_code=201)
    return RedirectResponse("/dashboard/secretaria", status_code=303)
