# Requerimientos y ajustes agregados — Ronda 3

A diferencia de la ronda anterior (sedes, estados de cuenta, límite diario, historial,
datos del paciente, lista de espera, filtros y auditoría), esta vez el sistema ya cubría
prácticamente los 50 requisitos. Los 5 puntos siguientes no eran funcionalidades ausentes
por completo, sino **validaciones que existían a medias**: el formulario web las exigía con
`required`, pero la API las aceptaba igual si se le enviaban vacías o con datos absurdos.
Cada uno se comprobó con una petición directa (sin pasar por el formulario) antes y después
del cambio, para confirmar que era un hueco real y no una suposición.

## 1. RF.11 — La jornada de un médico no puede salirse de la franja de la clínica

**El hueco:** `config.py` define la franja oficial (8:00-12:00 y 14:00-18:00), pero al
configurar la jornada de un médico (`actualizar_jornada_medico` en `servicios.py`) solo se
validaba que los cuatro bloques estuvieran ordenados y no se superpusieran — nada impedía
ponerle a un médico una jornada de 6:00 a 19:00, saltándose la franja de la clínica.

**El arreglo:** se agregó la comparación contra `HORA_INICIO_MANANA`, `HORA_FIN_MANANA`,
`HORA_INICIO_TARDE` y `HORA_FIN_TARDE` de `config.py`.

**Cómo demostrarlo:** en "Jornada de especialistas", intenta poner la hora de inicio de la
mañana en 06:00 — el sistema lo rechaza explicando la franja permitida.

## 2. RF.35 — Nombres y apellidos vacíos en el registro

**El hueco:** `PacienteCreateSchema` y `MedicoCreateSchema` no tenían `min_length=1` en
`nombres` y `apellidos` (a diferencia de otros formularios del sistema, que sí lo tenían).
Enviando la petición directamente a `/registro-paciente` con esos campos vacíos, el sistema
los aceptaba.

**El arreglo:** se agregó `Field(min_length=1)` a los cuatro campos.

**Cómo demostrarlo:** es difícil de ver desde el navegador porque el HTML ya bloqueaba el
envío; lo comprobé mandando la petición sin pasar por el formulario. Se documenta para que
quede constancia de la validación reforzada en el lado del servidor.

## 3. RF.37 / HU-02 — Reasignar un médico a otra sede sin revisar sus citas futuras

**El hueco:** HU-02 exige bloquear la eliminación de un médico con citas futuras, y esa
regla ya estaba aplicada al *desactivar* un médico. Pero **reasignarlo de sede** (RF.37) es
una acción distinta que no tenía la misma protección: se podía mover a un médico de la sede
norte a la sede sur aunque tuviera pacientes con cita agendada en la sede norte, dejando esas
citas con un médico que ya no pertenece a esa sede.

**El arreglo:** `asignar_sede_medico` ahora reutiliza la misma verificación de citas futuras
que ya usaba la desactivación.

**Cómo demostrarlo:** agenda una cita con un médico, y luego intenta reasignarlo a otra sede
desde el panel del administrador de la sede destino — el sistema lo bloquea hasta que esas
citas se cancelen o se atiendan.

## 4. RF.07 / RF.22 (HU-08) — Valores de cobro sin límites

**El hueco:** `RegistrarCobroSchema` aceptaba `valor_base` negativo y
`porcentaje_descuento` mayor a 100%, aunque HU-08 dice explícitamente: *"Dado que se
ingresa un valor inválido o negativo, entonces el sistema solicita corregir la
información."* El campo numérico del formulario no tenía `min="0"` ni tope en el
porcentaje.

**El arreglo:** `valor_base` ahora exige ser mayor que cero, `porcentaje_descuento` queda
entre 0 y 100, y `descuento_fijo` no puede ser negativo.

**Cómo demostrarlo:** en "Registrar cobro", intenta guardar un valor negativo o un
descuento de 150% — el sistema lo rechaza.

## 5. RF.44 — Motivo de cancelación vacío

**El hueco:** igual que el punto 2, el campo `motivo` del formulario de cancelación tenía
`required` en el HTML, pero el esquema `CancelarCitaSchema` no exigía que tuviera contenido,
así que una petición directa con `motivo: ""` pasaba.

**El arreglo:** se agregó `Field(min_length=1)`.

## Además: horarios ocupados en rojo (ajuste visual solicitado)

Antes, `/bloques-disponibles` devolvía solo los bloques libres — los ocupados
simplemente no aparecían en la lista, así que no había forma de ver "esto ya está tomado".
Se agregó `AgendamientoService.consultar_bloques_del_dia()`, que arma **todos** los bloques
de la jornada del médico marcando cada uno con `ocupado: true/false`, y se actualizó el
mismo endpoint para devolver esa información. En el panel de paciente y en el de secretaría,
los bloques ocupados ahora se muestran en rojo, tachados y deshabilitados; los libres se ven
como antes y siguen siendo seleccionables.

## Cómo verificar todo

```bash
source .venv/bin/activate
pip install httpx
python pruebas_momento3.py   # los 5 puntos de esta ronda + el ajuste visual
python pruebas_momento2.py   # confirma que nada de la ronda anterior se rompió
uvicorn main:app --reload
```
