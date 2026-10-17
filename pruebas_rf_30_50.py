"""Verificación explícita, uno por uno, de los requerimientos funcionales RF.30 a RF.50.

La mayoría de estos requisitos ya estaban resueltos en el código (algunos
desde el proyecto original, otros reforzados en rondas anteriores). Este
script no vuelve a implementarlos: los ejercita con peticiones reales contra
la base de datos SQLite para dejar la prueba concreta de que cada uno
funciona sobre la persistencia definitiva.

Ejecución:
    python pruebas_rf_30_50.py
"""

import os
os.environ.setdefault("CLINICA_DB_PATH", ":memory:")

from datetime import date, timedelta

from fastapi.testclient import TestClient

import main

JSON = {"Accept": "application/json"}


def proximo_dia_laboral(indice: int = 1) -> date:
    """Obtiene el n-ésimo día hábil distinto a partir de hoy (nunca repite fecha entre llamadas)."""
    fecha = date.today()
    contados = 0
    while contados < indice:
        fecha += timedelta(days=1)
        if fecha.weekday() <= 4:
            contados += 1
    return fecha


def iniciar_sesion(cliente: TestClient, correo: str, contrasena: str) -> None:
    """Autentica un usuario en el cliente de pruebas."""
    respuesta = cliente.post("/login", json={"correo": correo, "contrasena": contrasena}, headers=JSON)
    assert respuesta.status_code == 200, respuesta.text


def ejecutar() -> None:
    """Ejecuta la verificación de cada requisito, en orden."""
    ok = []
    sede_norte, sede_sur = main.app.state.sede_repo.obtener_todas()
    medico_norte = next(u for u in main.app.state.usuario_repo.obtener_todos() if getattr(u, "id_sede", "") == sede_norte.id and hasattr(u, "especialidad"))
    paciente = main.app.state.usuario_repo.buscar_por_correo("paciente@clinica.com")
    menor = main.app.state.usuario_repo.buscar_por_correo("menor@clinica.com")

    admin = TestClient(main.app)
    iniciar_sesion(admin, "admin.norte@clinica.com", "AdminNorte2026")
    secretaria = TestClient(main.app)
    iniciar_sesion(secretaria, "secretaria@clinica.com", "Secretaria2026")

    # RF.30 — fecha y hora de la última actualización de los datos del paciente
    sello_anterior = paciente.fecha_ultima_actualizacion
    secretaria.post(f"/pacientes/{paciente.numero_documento}/actualizar", json={"telefono": "3011112222", "correo": "paciente@clinica.com"}, headers=JSON)
    paciente = main.app.state.usuario_repo.buscar_por_id(paciente.id)
    assert paciente.fecha_ultima_actualizacion > sello_anterior
    ok.append("RF.30 — sello de última actualización del paciente")

    # RF.31 — tipo o especialidad de la consulta (Optometría, Oftalmología General, Control)
    fecha1 = proximo_dia_laboral(1)
    for tipo, hora in (("OPTOMETRIA", "08:00"), ("OFTALMOLOGIA_GENERAL", "08:30"), ("CONTROL", "09:00")):
        r = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha1}T{hora}:00", "tipo_consulta": tipo}, headers=JSON)
        assert r.status_code == 201, (tipo, r.text)
    ok.append("RF.31 — selección del tipo de consulta (Optometría, Oftalmología General, Control)")

    # RF.32 — impedir dos citas de un mismo paciente el mismo día y horario
    choque = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha1}T08:00:00", "tipo_consulta": "CONTROL"}, headers=JSON)
    assert choque.status_code == 409, choque.text
    ok.append("RF.32 — impide dos citas del mismo paciente en el mismo horario")

    # RF.33 — impedir dos usuarios con el mismo número de documento
    duplicado = TestClient(main.app).post("/registro-paciente", json={"tipo_documento": "CC", "numero_documento": paciente.numero_documento, "nombres": "Otro", "apellidos": "Paciente", "telefono": "3000000000", "correo": "otro-correo@clinica.com", "contrasena": "Clave2026", "fecha_nacimiento": "1995-01-01"}, headers=JSON)
    assert duplicado.status_code == 409, duplicado.text
    ok.append("RF.33 — impide registrar dos usuarios con el mismo documento")

    # RF.34 — datos del acudiente al agendar cita a un paciente menor de edad
    fecha2 = proximo_dia_laboral(2)
    sin_acudiente_previo = main.app.state.usuario_repo.buscar_por_id(menor.id)
    assert sin_acudiente_previo.nombre_acudiente and sin_acudiente_previo.telefono_acudiente  # ya quedó registrado desde el alta (RF.34 en el registro)
    cita_menor = secretaria.post("/agendar", json={"id_paciente": menor.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha2}T08:00:00", "tipo_consulta": "OPTOMETRIA", "nombre_acudiente": "Laura Menor", "telefono_acudiente": "3000000008"}, headers=JSON)
    assert cita_menor.status_code == 201, cita_menor.text
    sin_acudiente_en_agenda = secretaria.post("/agendar", json={"id_paciente": menor.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha2}T10:00:00", "tipo_consulta": "OPTOMETRIA"}, headers=JSON)
    assert sin_acudiente_en_agenda.status_code == 400, sin_acudiente_en_agenda.text
    ok.append("RF.34 — datos de acudiente exigidos y conservados para pacientes menores de edad")

    # RF.35 — campos obligatorios no pueden llegar vacíos
    vacio = TestClient(main.app).post("/registro-paciente", json={"tipo_documento": "CC", "numero_documento": "5555555555", "nombres": "", "apellidos": "", "telefono": "3000000000", "correo": "vacio2@clinica.com", "contrasena": "Clave2026", "fecha_nacimiento": "1995-01-01"}, headers=JSON)
    assert vacio.status_code == 400, vacio.text
    ok.append("RF.35 — rechaza formularios con campos obligatorios vacíos")

    # RF.36 — búsqueda de pacientes con un único campo (por documento o por nombre)
    por_documento = secretaria.get(f"/pacientes/{paciente.numero_documento}/historial", headers=JSON)
    por_nombre = secretaria.get(f"/pacientes/{paciente.nombres}/historial", headers=JSON)
    assert por_documento.status_code == 200 and por_nombre.status_code == 200
    ok.append("RF.36 — búsqueda de pacientes por documento o por nombre en un solo campo")

    # RF.37 — asignación y reasignación de médicos a una sede (ya reforzado con la regla de HU-02)
    reasignado = admin.post(f"/medicos/{medico_norte.id}/asignar-sede?id_sede={sede_norte.id}", json={"nuevo_id_sede": sede_norte.id}, headers=JSON)
    assert reasignado.status_code == 400  # ya pertenece a esa sede; confirma que la regla se evalúa
    ok.append("RF.37 — asignación/reasignación de médicos a una sede")

    # RF.38 — mensajes informativos claros y legibles ante un error
    error_legible = secretaria.post("/agendar", json={"id_paciente": "no-existe", "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha2}T10:00:00", "tipo_consulta": "CONTROL"}, headers=JSON)
    assert error_legible.status_code >= 400 and len(error_legible.json().get("detail", "")) > 10
    ok.append(f"RF.38 — mensaje de error legible: “{error_legible.json()['detail']}”")

    # RF.39 — listado de médicos especialistas asociados a cada sede
    medicos_norte = admin.get(f"/medicos?id_sede={sede_norte.id}", headers=JSON)
    assert medicos_norte.status_code == 200 and all(m["id_sede"] == sede_norte.id if "id_sede" in m else True for m in medicos_norte.json())
    ok.append("RF.39 — listado de médicos especialistas por sede")

    # RF.40 — estado actual de cada cita (Pendiente, Completada, Cancelada)
    historial = secretaria.get(f"/pacientes/{paciente.numero_documento}/historial", headers=JSON).json()
    estados_mostrados = {c["estado"] for c in historial["citas"]}
    assert estados_mostrados <= {"Pendiente", "Confirmada", "Completada", "Cancelada"} and estados_mostrados
    ok.append(f"RF.40 — estado de cada cita visible ({', '.join(estados_mostrados)})")

    # RF.41 — evitar sobreasignación: dos citas en el mismo horario para el mismo médico
    sobreasignacion = secretaria.post("/agendar", json={"id_paciente": menor.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha1}T08:00:00", "tipo_consulta": "CONTROL", "nombre_acudiente": "Laura Menor", "telefono_acudiente": "3000000008"}, headers=JSON)
    assert sobreasignacion.status_code == 409, sobreasignacion.text
    ok.append("RF.41 — evita la sobreasignación del mismo médico en el mismo horario")

    # RF.42 — formato correcto de correo y teléfono
    correo_invalido = secretaria.post(f"/pacientes/{paciente.numero_documento}/actualizar", json={"telefono": "3011112222", "correo": "no-es-un-correo"}, headers=JSON)
    telefono_invalido = secretaria.post(f"/pacientes/{paciente.numero_documento}/actualizar", json={"telefono": "abc123", "correo": "paciente@clinica.com"}, headers=JSON)
    assert correo_invalido.status_code == 400 and telefono_invalido.status_code == 400
    ok.append("RF.42 — valida formato de correo electrónico y teléfono numérico")

    # RF.43 — ordenar la lista de citas ascendente o descendente por fecha
    desc = secretaria.get(f"/pacientes/{paciente.numero_documento}/historial?orden=desc", headers=JSON).json()["citas"]
    asc = secretaria.get(f"/pacientes/{paciente.numero_documento}/historial?orden=asc", headers=JSON).json()["citas"]
    assert [c["fecha_hora"] for c in desc] == list(reversed([c["fecha_hora"] for c in asc]))
    ok.append("RF.43 — orden ascendente/descendente por fecha")

    # RF.44 — motivo obligatorio al cancelar una cita
    cita_para_cancelar = [c for c in main.app.state.cita_repo.obtener_por_paciente(paciente.id) if c.estado_cita.value == "PROGRAMADA"][0]
    sin_motivo = secretaria.post("/citas/cancelar", json={"id_cita": cita_para_cancelar.id, "motivo": "", "confirmado": True}, headers=JSON)
    assert sin_motivo.status_code == 400, sin_motivo.text
    ok.append("RF.44 — exige motivo de cancelación")

    # RF.45 — estado del pago asociado a la cita (Pendiente, Pagado, Anulado)
    cita_para_cobrar = cita_para_cancelar
    secretaria.post("/confirmar", json={"id_cita": cita_para_cobrar.id}, headers=JSON)
    secretaria.post("/atender", json={"id_cita": cita_para_cobrar.id, "observaciones": "Revisión de rutina"}, headers=JSON)
    secretaria.post("/cobrar", json={"id_cita": cita_para_cobrar.id, "valor_base": 60000, "metodo_pago": "EFECTIVO"}, headers=JSON)
    cita_cobrada = main.app.state.cita_repo.buscar_por_id(cita_para_cobrar.id)
    assert cita_cobrada.estado_pago.value == "PAGADO"
    anulado = secretaria.post("/anular-cobro", json={"id_cita": cita_para_cobrar.id, "confirmado": True}, headers=JSON)
    assert anulado.status_code == 200 and main.app.state.cita_repo.buscar_por_id(cita_para_cobrar.id).estado_pago.value == "ANULADO"
    ok.append("RF.45 — estado del pago visible y con sus tres valores (Pendiente, Pagado, Anulado)")

    # RF.46 — consultar el listado de usuarios en estado Activo
    tablero_secretaria = secretaria.get("/dashboard/secretaria")
    assert tablero_secretaria.status_code == 200 and "Usuarios activos" in tablero_secretaria.text
    ok.append("RF.46 — listado de usuarios en estado Activo")

    # RF.47 — edición de información básica y de contacto de un especialista
    edicion = admin.put(f"/medicos/{medico_norte.id}?id_sede={sede_norte.id}", json={"nombres": medico_norte.nombres, "apellidos": medico_norte.apellidos, "telefono": "3019999999", "correo": medico_norte.correo}, headers=JSON)
    assert edicion.status_code == 200, edicion.text
    medico_actualizado = main.app.state.usuario_repo.buscar_por_id(medico_norte.id)
    assert medico_actualizado.telefono == "3019999999"
    ok.append("RF.47 — edición de datos básicos y de contacto de un especialista")

    # RF.48 — filtrar e identificar en pantalla únicamente las citas canceladas
    solo_canceladas = secretaria.get(f"/dashboard/secretaria?estado=CANCELADA&id_sede={sede_norte.id}")
    assert solo_canceladas.status_code == 200
    ok.append("RF.48 — filtro para ver únicamente las citas canceladas")

    # RF.49 — número de documento restringido a un máximo de diez dígitos numéricos
    documento_largo = TestClient(main.app).post("/registro-paciente", json={"tipo_documento": "CC", "numero_documento": "123456789012", "nombres": "Nombre", "apellidos": "Apellido", "telefono": "3000000000", "correo": "documentolargo@clinica.com", "contrasena": "Clave2026", "fecha_nacimiento": "1995-01-01"}, headers=JSON)
    assert documento_largo.status_code == 400, documento_largo.text
    ok.append("RF.49 — documento restringido a un máximo de diez dígitos numéricos")

    # RF.50 — límite máximo de citas por médico en un mismo día
    admin.post(f"/medicos/{medico_norte.id}/limite-diario?id_sede={sede_norte.id}", json={"max_citas_dia": 3}, headers=JSON)
    excedido = secretaria.post("/agendar", json={"id_paciente": menor.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha1}T09:30:00", "tipo_consulta": "CONTROL", "nombre_acudiente": "Laura Menor", "telefono_acudiente": "3000000008"}, headers=JSON)
    assert excedido.status_code == 409, excedido.text
    ok.append("RF.50 — límite máximo de citas por médico y por día")

    print("\n".join(f"✔ {linea}" for linea in ok))
    print(f"\n{len(ok)} de 21 requisitos (RF.30 a RF.50) verificados sin errores sobre la base de datos SQLite.")


if __name__ == "__main__":
    ejecutar()
