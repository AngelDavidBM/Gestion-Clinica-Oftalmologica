"""Pruebas de los 5 requerimientos agregados en esta ronda y del arreglo de disponibilidad.

Ejecución:
    python pruebas_momento3.py
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
    """Ejecuta las verificaciones."""
    resultados = []
    sede_norte, sede_sur = main.app.state.sede_repo.obtener_todas()
    medico_norte = next(u for u in main.app.state.usuario_repo.obtener_todos() if getattr(u, "id_sede", "") == sede_norte.id and hasattr(u, "especialidad"))
    paciente = main.app.state.usuario_repo.buscar_por_correo("paciente@clinica.com")

    admin_norte = TestClient(main.app)
    iniciar_sesion(admin_norte, "admin.norte@clinica.com", "AdminNorte2026")
    admin_sur = TestClient(main.app)
    iniciar_sesion(admin_sur, "admin.sur@clinica.com", "AdminSur2026")
    secretaria = TestClient(main.app)
    iniciar_sesion(secretaria, "secretaria@clinica.com", "Secretaria2026")

    # 1) RF.11 — la jornada del médico no puede salirse de la franja de la clínica
    fuera_de_franja = admin_norte.post(f"/medicos/{medico_norte.id}/jornada?id_sede={sede_norte.id}",
        json={"hora_inicio_manana": "06:00", "hora_fin_manana": "12:00", "hora_inicio_tarde": "14:00", "hora_fin_tarde": "18:00"}, headers=JSON)
    assert fuera_de_franja.status_code == 400, fuera_de_franja.text
    dentro_de_franja = admin_norte.post(f"/medicos/{medico_norte.id}/jornada?id_sede={sede_norte.id}",
        json={"hora_inicio_manana": "08:00", "hora_fin_manana": "12:00", "hora_inicio_tarde": "14:00", "hora_fin_tarde": "18:00"}, headers=JSON)
    assert dentro_de_franja.status_code == 200, dentro_de_franja.text
    resultados.append("RF.11 jornada del médico acotada a la franja de la clínica: OK")

    # 2) RF.35 — nombres/apellidos vacíos rechazados al registrar paciente
    vacio = TestClient(main.app).post("/registro-paciente", json={"tipo_documento": "CC", "numero_documento": "9999999911", "nombres": "", "apellidos": "", "telefono": "3000000099", "correo": "vacio1@clinica.com", "contrasena": "x", "fecha_nacimiento": "2000-01-01"}, headers=JSON)
    assert vacio.status_code == 400, vacio.text
    resultados.append("RF.35 nombres/apellidos obligatorios en registro: OK")

    # 3) RF.37 / HU-02 — no reasignar un médico con citas futuras en su sede actual
    fecha = proximo_dia_laboral()
    cita = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha}T09:00:00", "tipo_consulta": "OFTALMOLOGIA_GENERAL"}, headers=JSON)
    assert cita.status_code == 201, cita.text
    reasignar_bloqueado = admin_sur.post(f"/medicos/{medico_norte.id}/asignar-sede?id_sede={sede_sur.id}", json={"nuevo_id_sede": sede_sur.id}, headers=JSON)
    assert reasignar_bloqueado.status_code == 409, reasignar_bloqueado.text
    secretaria.post("/citas/cancelar", json={"id_cita": cita.json()["id"], "motivo": "Prueba automatizada", "confirmado": True}, headers=JSON)
    reasignar_ok = admin_sur.post(f"/medicos/{medico_norte.id}/asignar-sede?id_sede={sede_sur.id}", json={"nuevo_id_sede": sede_sur.id}, headers=JSON)
    assert reasignar_ok.status_code == 200, reasignar_ok.text
    admin_norte.post(f"/medicos/{medico_norte.id}/asignar-sede?id_sede={sede_norte.id}", json={"nuevo_id_sede": sede_norte.id}, headers=JSON)
    resultados.append("RF.37/HU-02 reasignación segura de sede: OK")

    # 4) RF.07 / RF.22 / HU-08 — valores de cobro inválidos rechazados
    fecha2 = proximo_dia_laboral(2)
    cita2 = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha2}T09:00:00", "tipo_consulta": "CONTROL"}, headers=JSON)
    id_cita2 = cita2.json()["id"]
    secretaria.post("/confirmar", json={"id_cita": id_cita2}, headers=JSON)
    secretaria.post("/atender", json={"id_cita": id_cita2, "observaciones": "Control"}, headers=JSON)
    negativo = secretaria.post("/cobrar", json={"id_cita": id_cita2, "valor_base": -1000, "metodo_pago": "EFECTIVO"}, headers=JSON)
    assert negativo.status_code == 400, negativo.text
    descuento_excesivo = secretaria.post("/cobrar", json={"id_cita": id_cita2, "valor_base": 50000, "porcentaje_descuento": 150, "metodo_pago": "EFECTIVO"}, headers=JSON)
    assert descuento_excesivo.status_code == 400, descuento_excesivo.text
    valido = secretaria.post("/cobrar", json={"id_cita": id_cita2, "valor_base": 50000, "porcentaje_descuento": 10, "metodo_pago": "EFECTIVO"}, headers=JSON)
    assert valido.status_code == 200, valido.text
    resultados.append("RF.07/RF.22 valores de cobro válidos: OK")

    # 5) RF.44 — motivo de cancelación obligatorio
    fecha3 = proximo_dia_laboral(3)
    cita3 = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha3}T11:00:00", "tipo_consulta": "OPTOMETRIA"}, headers=JSON)
    assert cita3.status_code == 201, cita3.text
    sin_motivo = secretaria.post("/citas/cancelar", json={"id_cita": cita3.json()["id"], "motivo": "", "confirmado": True}, headers=JSON)
    assert sin_motivo.status_code == 400, sin_motivo.text
    resultados.append("RF.44 motivo de cancelación obligatorio: OK")

    # 6) UI: bloques ocupados marcados en rojo
    fecha4 = proximo_dia_laboral(4)
    ocupar = secretaria.post("/agendar", json={"id_paciente": paciente.numero_documento, "id_medico": medico_norte.id, "id_sede": sede_norte.id, "fecha_hora": f"{fecha4}T10:00:00", "tipo_consulta": "CONTROL"}, headers=JSON)
    assert ocupar.status_code == 201, ocupar.text
    disponibilidad = secretaria.get(f"/bloques-disponibles?id_sede={sede_norte.id}&id_medico={medico_norte.id}&fecha={fecha4}", headers=JSON)
    assert disponibilidad.status_code == 200, disponibilidad.text
    bloques = disponibilidad.json()
    ocupados = [b for b in bloques if b["ocupado"]]
    libres = [b for b in bloques if not b["ocupado"]]
    assert any(b["hora"].startswith(f"{fecha4}T10:00") for b in ocupados), bloques
    assert len(libres) > 0
    resultados.append(f"UI horarios ocupados en rojo ({len(ocupados)} ocupado(s) de {len(bloques)} bloques): OK")

    print("\n".join(resultados))
    print(f"\n{len(resultados)} bloques verificados sin errores.")


if __name__ == "__main__":
    ejecutar()
