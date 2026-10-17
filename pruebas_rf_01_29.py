"""Verificación explícita, uno por uno, de los requerimientos funcionales RF.01 a RF.29.

Junto con `pruebas_rf_30_50.py` (que cubre RF.30 a RF.50), estos dos scripts
ejercitan los 50 requisitos funcionales del documento de Momento 1, cada uno
por su cuenta, contra la base de datos SQLite real.

Ejecución:
    python pruebas_rf_01_29.py
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

    admin = TestClient(main.app)
    iniciar_sesion(admin, "admin.norte@clinica.com", "AdminNorte2026")
    secretaria = TestClient(main.app)
    iniciar_sesion(secretaria, "secretaria@clinica.com", "Secretaria2026")
    cliente_paciente = TestClient(main.app)
    iniciar_sesion(cliente_paciente, "paciente@clinica.com", "Paciente2026")

    # RF.01 — registrar un nuevo usuario (paciente, secretaria, administrador)
    nuevo_paciente = TestClient(main.app).post("/registro-paciente", json={"tipo_documento": "CC", "numero_documento": "7000000001", "nombres": "Nuevo", "apellidos": "Paciente", "telefono": "3007000001", "correo": "nuevopaciente@clinica.com", "contrasena": "Clave2026", "fecha_nacimiento": "1998-01-01"}, headers=JSON)
    nueva_secretaria = admin.post(f"/usuarios?id_sede={sede_norte.id}", json={"tipo_documento": "CC", "numero_documento": "7000000002", "nombres": "Nueva", "apellidos": "Secretaria", "telefono": "3007000002", "correo": "nuevasecretaria@clinica.com", "contrasena": "Clave2026", "rol": "SECRETARIA"}, headers=JSON)
    assert nuevo_paciente.status_code == 201 and nueva_secretaria.status_code == 201
    ok.append("RF.01 — registro de paciente y de secretaría/administración")

    # RF.02, RF.03, RF.04 — agendar, cancelar y reagendar una cita
    fecha1 = proximo_dia_laboral(1)
    agendada = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha1}T08:00:00", "tipo_consulta": "CONTROL"}, headers=JSON)
    assert agendada.status_code == 201, agendada.text
    id_cita = agendada.json()["id"]
    reagendada = secretaria.post("/citas/reagendar", json={"id_cita": id_cita, "nueva_fecha_hora": f"{fecha1}T08:30:00"}, headers=JSON)
    assert reagendada.status_code == 200, reagendada.text
    cancelada = secretaria.post("/citas/cancelar", json={"id_cita": id_cita, "motivo": "Paciente no puede asistir", "confirmado": True}, headers=JSON)
    assert cancelada.status_code == 200, cancelada.text
    ok.append("RF.02/RF.03/RF.04 — agendar, cancelar y reagendar una cita")

    # RF.05 — datos demográficos completos del paciente
    completo = main.app.state.usuario_repo.buscar_por_correo("nuevopaciente@clinica.com")
    assert all([completo.tipo_documento, completo.numero_documento, completo.nombres, completo.telefono, completo.correo])
    ok.append("RF.05 — datos demográficos completos exigidos al registrar un paciente")

    # RF.06 — reportes consolidados
    reporte = admin.get(f"/reportes?id_sede={sede_norte.id}&fecha_inicio={fecha1}&fecha_fin={fecha1}", headers=JSON)
    assert reporte.status_code == 200 and "total_ingresos" in reporte.json()
    ok.append("RF.06 — reporte financiero consolidado")

    # RF.07 — digitación manual del valor a pagar de una cita
    fecha2 = proximo_dia_laboral(2)
    cita2 = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha2}T08:00:00", "tipo_consulta": "CONTROL"}, headers=JSON).json()["id"]
    secretaria.post("/confirmar", json={"id_cita": cita2}, headers=JSON)
    secretaria.post("/atender", json={"id_cita": cita2, "observaciones": "Consulta de rutina"}, headers=JSON)
    cobro = secretaria.post("/cobrar", json={"id_cita": cita2, "valor_base": 75000, "metodo_pago": "TARJETA"}, headers=JSON)
    assert cobro.status_code == 200 and cobro.json()["valor_neto"] == 75000
    ok.append("RF.07 — digitación manual del valor de una cita")

    # RF.08 — lista de bloques de horarios disponibles por médico
    disponibilidad = secretaria.get(f"/bloques-disponibles?id_sede={sede_norte.id}&id_medico={medico_norte.id}&fecha={fecha2}", headers=JSON)
    assert disponibilidad.status_code == 200 and len(disponibilidad.json()) > 0
    ok.append("RF.08 — bloques de horario disponibles por médico")

    # RF.09 — confirmación antes de cancelar un registro
    fecha3 = proximo_dia_laboral(3)
    cita3 = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha3}T08:00:00", "tipo_consulta": "CONTROL"}, headers=JSON).json()["id"]
    sin_confirmar = secretaria.post("/citas/cancelar", json={"id_cita": cita3, "motivo": "Prueba", "confirmado": False}, headers=JSON)
    assert sin_confirmar.status_code == 400, sin_confirmar.text
    ok.append("RF.09 — exige confirmación antes de cancelar un registro")

    # RF.10 — administrar la información de las dos sedes
    actualizar_sede = admin.put(f"/sedes/{sede_norte.id}?id_sede={sede_norte.id}", json={"nombre": "Sede Norte", "direccion": "Calle 41 # 12-05", "numero_consultorios": 5}, headers=JSON)
    assert actualizar_sede.status_code == 200, actualizar_sede.text
    ok.append("RF.10 — administración de la información de las sedes")

    # RF.11 — agendamiento solo dentro de la franja horaria de la clínica
    fuera_de_franja = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha3}T19:00:00", "tipo_consulta": "CONTROL"}, headers=JSON)
    assert fuera_de_franja.status_code == 409, fuera_de_franja.text
    ok.append("RF.11 — agendamiento restringido a la franja horaria de la clínica")

    # RF.12 — filtrar la información de citas por sede, médico y fecha
    filtradas = secretaria.get(f"/dashboard/secretaria?id_sede={sede_norte.id}&id_medico={medico_norte.id}&fecha={fecha2}")
    assert filtradas.status_code == 200
    ok.append("RF.12 — filtro de citas por sede, médico y fecha")

    # RF.13 — inicio de sesión mediante credenciales asignadas
    credenciales_malas = TestClient(main.app).post("/login", json={"correo": "paciente@clinica.com", "contrasena": "incorrecta"}, headers=JSON)
    assert credenciales_malas.status_code == 401
    ok.append("RF.13 — inicio de sesión con credenciales asignadas")

    # RF.14 — la hora seleccionada debe estar dentro de la jornada activa del especialista
    admin.post(f"/medicos/{medico_norte.id}/jornada?id_sede={sede_norte.id}", json={"hora_inicio_manana": "09:00", "hora_fin_manana": "12:00", "hora_inicio_tarde": "14:00", "hora_fin_tarde": "18:00"}, headers=JSON)
    fuera_de_jornada = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha3}T08:00:00", "tipo_consulta": "CONTROL"}, headers=JSON)
    assert fuera_de_jornada.status_code == 409, fuera_de_jornada.text
    admin.post(f"/medicos/{medico_norte.id}/jornada?id_sede={sede_norte.id}", json={"hora_inicio_manana": "08:00", "hora_fin_manana": "12:00", "hora_inicio_tarde": "14:00", "hora_fin_tarde": "18:00"}, headers=JSON)
    ok.append("RF.14 — hora dentro de la jornada activa del especialista")

    # RF.15 — mostrar el detalle completo de una cita seleccionada
    tablero_html = secretaria.get("/dashboard/secretaria")
    assert tablero_html.status_code == 200 and "Ver detalle completo" in tablero_html.text
    ok.append("RF.15 — detalle completo de una cita en pantalla")

    # RF.16 — historial completo de citas atendidas de un paciente
    historial = secretaria.get(f"/pacientes/{paciente.numero_documento}/historial?solo_atendidas=true", headers=JSON)
    assert historial.status_code == 200 and historial.json()["total_citas"] >= 1
    ok.append("RF.16 — historial completo de citas atendidas")

    # RF.17 — registrar observaciones en la cita atendida
    cita_atendida = main.app.state.cita_repo.buscar_por_id(cita2)
    assert cita_atendida.observaciones_atencion == "Consulta de rutina"
    ok.append("RF.17 — observaciones registradas en la cita atendida")

    # RF.18 — botón de acceso rápido al menú principal desde cualquier pantalla
    assert "Menú principal" in tablero_html.text
    ok.append("RF.18 — botón de acceso rápido al menú principal")

    # RF.19 — bloques fijos de 30 minutos por consulta
    assert cita_atendida.duracion_minutos == 30
    ok.append("RF.19 — bloques fijos de 30 minutos por consulta")

    # RF.20 — restringir el acceso a módulos según el rol autenticado
    paciente_en_secretaria = cliente_paciente.get("/dashboard/secretaria")
    secretaria_en_admin = secretaria.get(f"/dashboard/administrador/{sede_norte.id}")
    assert paciente_en_secretaria.status_code == 403 and secretaria_en_admin.status_code == 403
    ok.append("RF.20 — acceso a módulos restringido según el rol")

    # RF.21 — calcular el total de ingresos en un rango de fechas
    ingresos = admin.get(f"/reportes?id_sede={sede_norte.id}&fecha_inicio={fecha2}&fecha_fin={fecha2}", headers=JSON).json()
    assert ingresos["total_ingresos"] == 75000
    ok.append("RF.21 — total de ingresos calculado en un rango de fechas")

    # RF.22 — aplicar un porcentaje o un monto fijo de descuento
    fecha4 = proximo_dia_laboral(4)
    cita4 = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha4}T09:00:00", "tipo_consulta": "CONTROL"}, headers=JSON).json()["id"]
    secretaria.post("/confirmar", json={"id_cita": cita4}, headers=JSON)
    secretaria.post("/atender", json={"id_cita": cita4, "observaciones": "Control"}, headers=JSON)
    con_descuento = secretaria.post("/cobrar", json={"id_cita": cita4, "valor_base": 100000, "porcentaje_descuento": 20, "metodo_pago": "EFECTIVO"}, headers=JSON)
    assert con_descuento.status_code == 200 and con_descuento.json()["valor_neto"] == 80000
    ok.append("RF.22 — descuento porcentual aplicado correctamente")

    # RF.23 — la cita pasa ordenadamente por sus estados (Programada → Confirmada → Atendida/Cancelada)
    fecha5 = proximo_dia_laboral(5)
    cita5 = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha5}T09:00:00", "tipo_consulta": "CONTROL"}, headers=JSON).json()["id"]
    atender_sin_confirmar = secretaria.post("/atender", json={"id_cita": cita5, "observaciones": "x"}, headers=JSON)
    assert atender_sin_confirmar.status_code == 400, atender_sin_confirmar.text
    ok.append("RF.23 — transición de estados validada (no se puede atender sin confirmar)")

    # RF.24 — cambiar un usuario a Inactivo conservando su historial
    nuevo_id = main.app.state.usuario_repo.buscar_por_correo("nuevopaciente@clinica.com").id
    citas_antes = len(main.app.state.cita_repo.obtener_todas())
    inactivado = admin.post(f"/usuarios/{nuevo_id}/estado?id_sede={sede_norte.id}", json={"nuevo_estado": "INACTIVO", "confirmado": True}, headers=JSON)
    assert inactivado.status_code == 200 and len(main.app.state.cita_repo.obtener_todas()) == citas_antes
    ok.append("RF.24 — cambio a estado Inactivo sin perder historial")

    # RF.25 — registrar el método de pago utilizado
    assert main.app.state.cita_repo.buscar_por_id(cita2).metodo_pago.value == "TARJETA"
    ok.append("RF.25 — método de pago registrado (Efectivo, Tarjeta, Transferencia)")

    # RF.26 — monto neto final tras aplicar el descuento
    assert main.app.state.cita_repo.buscar_por_id(cita4).valor_neto == 80000
    ok.append("RF.26 — monto neto final calculado tras el descuento")

    # RF.27 — lista de espera cuando no hay horarios disponibles
    espera = secretaria.post("/lista-espera", json={"id_paciente": paciente.numero_documento, "id_sede": sede_norte.id, "tipo_consulta": "CONTROL"}, headers=JSON)
    assert espera.status_code == 201, espera.text
    ok.append("RF.27 — registro en lista de espera")

    # RF.28 — calcular y mostrar automáticamente la edad del paciente
    datos_paciente = secretaria.get(f"/pacientes/{paciente.numero_documento}/historial", headers=JSON).json()
    assert isinstance(datos_paciente["edad"], int) and datos_paciente["edad"] > 0
    ok.append(f"RF.28 — edad calculada automáticamente ({datos_paciente['edad']} años)")

    # RF.29 — identificar el estado actual del paciente (Activo, Inactivo o Bloqueado)
    assert datos_paciente["estado"] in ("ACTIVO", "INACTIVO", "BLOQUEADO")
    ok.append(f"RF.29 — estado actual del paciente visible ({datos_paciente['estado']})")

    print("\n".join(f"✔ {linea}" for linea in ok))
    print(f"\n{len(ok)} requisitos (RF.01 a RF.29) verificados sin errores sobre la base de datos SQLite.")


if __name__ == "__main__":
    ejecutar()
