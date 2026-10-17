"""Pruebas manuales de los requerimientos agregados en el segundo momento.

Ejecución:
    python pruebas_momento2.py
"""

import os
os.environ.setdefault("CLINICA_DB_PATH", ":memory:")

from datetime import date, datetime, timedelta

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
    """Autentica un usuario en el cliente de pruebas.

    Parámetros:
        cliente: Cliente HTTP de pruebas.
        correo: Correo de acceso.
        contrasena: Contraseña en texto plano.
    Retorna:
        Ninguno.
    """
    respuesta = cliente.post("/login", json={"correo": correo, "contrasena": contrasena}, headers=JSON)
    assert respuesta.status_code == 200, respuesta.text


def ejecutar() -> None:
    """Ejecuta las verificaciones de los requerimientos nuevos.

    Retorna:
        Ninguno.
    """
    resultados = []
    sede_norte, sede_sur = main.app.state.sede_repo.obtener_todas()
    medico_norte = next(u for u in main.app.state.usuario_repo.obtener_todos() if getattr(u, "id_sede", "") == sede_norte.id and hasattr(u, "especialidad"))
    paciente = next(u for u in main.app.state.usuario_repo.obtener_todos() if u.correo == "paciente@clinica.com")
    menor = next(u for u in main.app.state.usuario_repo.obtener_todos() if u.correo == "menor@clinica.com")

    admin = TestClient(main.app)
    iniciar_sesion(admin, "admin.norte@clinica.com", "AdminNorte2026")
    secretaria = TestClient(main.app)
    iniciar_sesion(secretaria, "secretaria@clinica.com", "Secretaria2026")
    cliente_paciente = TestClient(main.app)
    iniciar_sesion(cliente_paciente, "paciente@clinica.com", "Paciente2026")

    # RF10: administración de sedes
    respuesta = admin.put(f"/sedes/{sede_norte.id}?id_sede={sede_norte.id}", json={"nombre": "Sede Norte", "direccion": "Calle 41 # 12-05", "numero_consultorios": 6}, headers=JSON)
    assert respuesta.status_code == 200, respuesta.text
    assert main.app.state.sede_repo.buscar_por_id(sede_norte.id).numero_consultorios == 6
    ajena = admin.put(f"/sedes/{sede_sur.id}?id_sede={sede_norte.id}", json={"nombre": "Sede Sur", "direccion": "x", "numero_consultorios": 2}, headers=JSON)
    assert ajena.status_code == 403, ajena.text
    creada = admin.post(f"/sedes?id_sede={sede_norte.id}", json={"nombre": "Sede Centro", "direccion": "Calle 27 # 3-40", "numero_consultorios": 2}, headers=JSON)
    assert creada.status_code == 201, creada.text
    duplicada = admin.post(f"/sedes?id_sede={sede_norte.id}", json={"nombre": "Sede Centro", "direccion": "otra", "numero_consultorios": 2}, headers=JSON)
    assert duplicada.status_code == 409, duplicada.text
    resultados.append("RF10 sedes administrables: OK")

    # RF50: límite diario configurable
    respuesta = admin.post(f"/medicos/{medico_norte.id}/limite-diario?id_sede={sede_norte.id}", json={"max_citas_dia": 1}, headers=JSON)
    assert respuesta.status_code == 200, respuesta.text
    fecha = proximo_dia_laboral()
    primera = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha}T08:00:00", "tipo_consulta": "OFTALMOLOGIA_GENERAL"}, headers=JSON)
    assert primera.status_code == 201, primera.text
    segunda = secretaria.post("/agendar", json={"id_paciente": menor.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha}T08:30:00", "tipo_consulta": "OFTALMOLOGIA_GENERAL", "nombre_acudiente": "Laura Menor", "telefono_acudiente": "3000000008"}, headers=JSON)
    assert segunda.status_code == 409 and "límite" in segunda.json()["detail"], segunda.text
    admin.post(f"/medicos/{medico_norte.id}/limite-diario?id_sede={sede_norte.id}", json={"max_citas_dia": 8}, headers=JSON)
    resultados.append("RF50 límite diario por médico: OK")

    # RF16: historial completo del paciente consultado por secretaría
    id_cita = primera.json()["id"]
    secretaria.post("/confirmar", json={"id_cita": id_cita}, headers=JSON)
    secretaria.post("/atender", json={"id_cita": id_cita, "observaciones": "Control de agudeza visual"}, headers=JSON)
    secretaria.post("/cobrar", json={"id_cita": id_cita, "valor_base": 90000, "porcentaje_descuento": 10, "metodo_pago": "EFECTIVO"}, headers=JSON)
    historial = secretaria.get(f"/pacientes/{paciente.numero_documento}/historial?solo_atendidas=true&orden=asc", headers=JSON)
    assert historial.status_code == 200, historial.text
    cuerpo = historial.json()
    assert cuerpo["total_citas"] == 1 and cuerpo["citas"][0]["valor_neto"] == 81000, cuerpo
    assert cuerpo["citas"][0]["observaciones"] == "Control de agudeza visual"
    resultados.append("RF16 historial por paciente: OK")

    # RF05 y RF30: actualización de datos con sello de modificación
    sello_anterior = paciente.fecha_ultima_actualizacion
    respuesta = cliente_paciente.post("/mis-datos", json={"telefono": "3019998877", "correo": "paciente@clinica.com"}, headers=JSON)
    assert respuesta.status_code == 200, respuesta.text
    paciente = main.app.state.usuario_repo.buscar_por_id(paciente.id)
    assert paciente.telefono == "3019998877" and paciente.fecha_ultima_actualizacion > sello_anterior
    invalido = cliente_paciente.post("/mis-datos", json={"telefono": "abc", "correo": "paciente@clinica.com"}, headers=JSON)
    assert invalido.status_code == 400, invalido.text
    sin_acudiente = secretaria.post(f"/pacientes/{menor.numero_documento}/actualizar", json={"telefono": "3005556677", "correo": "menor@clinica.com"}, headers=JSON)
    assert sin_acudiente.status_code == 400, sin_acudiente.text
    resultados.append("RF05/RF30 datos del paciente editables: OK")

    # RF27: lista de espera gestionable
    espera = secretaria.post("/lista-espera", json={"id_paciente": menor.numero_documento, "id_sede": sede_norte.id, "tipo_consulta": "OFTALMOLOGIA_GENERAL"}, headers=JSON)
    assert espera.status_code == 201, espera.text
    id_registro = espera.json()["id"]
    sin_confirmar = secretaria.post(f"/lista-espera/{id_registro}/retirar", json={"confirmado": False}, headers=JSON)
    assert sin_confirmar.status_code == 400, sin_confirmar.text
    promovida = secretaria.post(f"/lista-espera/{id_registro}/promover", json={"id_medico": medico_norte.id, "fecha_hora": f"{fecha}T09:00:00"}, headers=JSON)
    assert promovida.status_code == 201, promovida.text
    assert not main.app.state.agendamiento.obtener_lista_espera()
    repetida = secretaria.post(f"/lista-espera/{id_registro}/promover", json={"id_medico": medico_norte.id, "fecha_hora": f"{fecha}T09:30:00"}, headers=JSON)
    assert repetida.status_code == 400, repetida.text
    resultados.append("RF27 lista de espera operativa: OK")

    # RF12, RF43 y RF48: filtros, orden y citas canceladas en secretaría
    tablero = secretaria.get(f"/dashboard/secretaria?estado=CANCELADA&orden=asc&id_sede={sede_norte.id}")
    assert tablero.status_code == 200 and "Panel de secretaría" in tablero.text
    resultados.append("RF12/RF43/RF48 filtros de secretaría: OK")

    # RF24 y RF29: estados de cuenta
    bloqueo = admin.post(f"/usuarios/{menor.id}/estado?id_sede={sede_norte.id}", json={"nuevo_estado": "BLOQUEADO", "confirmado": True}, headers=JSON)
    assert bloqueo.status_code == 200, bloqueo.text
    menor = main.app.state.usuario_repo.buscar_por_id(menor.id)
    assert menor.estado.value == "BLOQUEADO"
    acceso = TestClient(main.app).post("/login", json={"correo": "menor@clinica.com", "contrasena": "Menor2026"}, headers=JSON)
    assert acceso.status_code == 401, acceso.text
    reactivacion = admin.post(f"/usuarios/{menor.id}/estado?id_sede={sede_norte.id}", json={"nuevo_estado": "ACTIVO", "confirmado": True}, headers=JSON)
    assert reactivacion.status_code == 200, reactivacion.text
    propia = admin.post(f"/usuarios/{main.app.state.usuario_repo.buscar_por_correo('admin.norte@clinica.com').id}/estado?id_sede={sede_norte.id}", json={"nuevo_estado": "INACTIVO", "confirmado": True}, headers=JSON)
    assert propia.status_code == 403, propia.text
    medico_ocupado = admin.post(f"/usuarios/{medico_norte.id}/estado?id_sede={sede_norte.id}", json={"nuevo_estado": "INACTIVO", "confirmado": True}, headers=JSON)
    assert medico_ocupado.status_code == 409, medico_ocupado.text
    resultados.append("RF24/RF29 estados de cuenta: OK")

    # HU-03: bitácora de auditoría
    hoy = date.today().isoformat()
    bitacora = admin.get(f"/auditoria?id_sede={sede_norte.id}&fecha_inicio={hoy}&fecha_fin={hoy}", headers=JSON)
    assert bitacora.status_code == 200, bitacora.text
    eventos = bitacora.json()
    assert any(evento["accion"].endswith("/limite-diario") for evento in eventos), eventos[:3]
    assert any(not evento["exitoso"] for evento in eventos)
    csv = admin.get(f"/auditoria/exportar?id_sede={sede_norte.id}&fecha_inicio={hoy}&fecha_fin={hoy}")
    assert csv.status_code == 200 and "Accion" in csv.text
    resultados.append(f"HU-03 auditoría ({len(eventos)} eventos de la sede): OK")

    # Regresión: tableros y reporte siguen respondiendo
    assert cliente_paciente.get("/dashboard/paciente").status_code == 200
    reporte = admin.get(f"/reportes?id_sede={sede_norte.id}&fecha_inicio={fecha}&fecha_fin={fecha}", headers=JSON)
    assert reporte.status_code == 200 and reporte.json()["total_ingresos"] == 81000, reporte.text
    assert admin.get(f"/dashboard/administrador/{sede_norte.id}?fecha_inicio={fecha}&fecha_fin={fecha}").status_code == 200
    resultados.append("Regresión de tableros y reportes: OK")

    print("\n".join(resultados))
    print(f"\n{len(resultados)} bloques verificados sin errores.")


if __name__ == "__main__":
    ejecutar()
