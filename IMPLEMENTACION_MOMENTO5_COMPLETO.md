# Los 50 requerimientos funcionales — estado final y cómo probarlos

Este documento es el cierre de todo el trabajo: confirma que los **50
requisitos funcionales** del documento de Momento 1 están resueltos, dice en
qué parte del código vive cada uno, y explica cómo comprobarlo tú mismo.

## Lo que se hizo en esta última ronda

Antes de escribir código revisé, línea por línea, los cuatro archivos de
rutas (`auth_router.py`, `paciente_router.py`, `secretaria_router.py`,
`admin_router.py`) que no había auditado por completo en las rondas
anteriores. De ahí salió **un bug real**, no una omisión de requisito:

**El bug:** cuando un administrador registraba una secretaría nueva desde el
panel (botón "Registrar usuario interno"), el código creaba un objeto
`Usuario` genérico —la clase abstracta base— en vez de usar `Paciente`, que
es la clase que sí usan las cuentas de secretaría de los datos semilla. Con
los repositorios en memoria esto nunca se notaba, porque un diccionario de
Python guarda cualquier objeto sin preguntar su tipo. Pero el repositorio de
SQLite sí necesita saber qué tabla de extensión usar para cada usuario, y al
toparse con ese objeto "huérfano" (ni paciente, ni médico, ni administrador)
fallaba con un error de atributo faltante. Lo encontré probando exactamente
ese flujo con `pruebas_rf_01_29.py`, y la corrección fue una línea: ahora
`registrar_usuario_interno` crea una `Paciente` para las cuentas de
secretaría, igual que ya lo hacía la siembra inicial en `main.py`.

También until ahora los scripts de prueba generaban las fechas de cita con
una función que podía repetir la misma fecha dos veces si hoy es viernes o
sábado (`hoy + 1, 2 o 3 días` caían todos el mismo lunes). La corregí en los
cuatro scripts de prueba para que cada llamada devuelva un día hábil
distinto, sin importar qué día de la semana sea hoy.

Aparte de esas dos correcciones, **confirmé que los 50 requisitos ya estaban
resueltos** — la mayoría desde el proyecto original de tu equipo, y el resto
en las rondas 1 a 4 de este trabajo. No inventé funcionalidad donde no hacía
falta: donde algo ya funcionaba, lo dejé igual y simplemente lo probé.

## Cómo queda organizada la prueba de los 50 requisitos

Hay dos scripts, cada uno imprime una línea `✔ RF.XX — ...` por cada
requisito que verifica, contra la base de datos SQLite real (no simulada):

- **`pruebas_rf_01_29.py`** → verifica el RF.01 al RF.29 (27 líneas de
  verificación; dos pares de requisitos comparten una sola prueba de extremo
  a extremo porque se ejercitan con la misma petición: RF.02/03/04 al
  agendar-cancelar-reagendar, y RF.07 junto con el flujo de cobro).
- **`pruebas_rf_30_50.py`** → verifica el RF.30 al RF.50 (21 líneas).

Y hay dos scripts más, de rondas anteriores, que verifican flujos completos
de extremo a extremo (sedes, estados de cuenta, auditoría, lista de espera,
jornada del médico, validaciones reforzadas):

- **`pruebas_momento2.py`** (9 verificaciones)
- **`pruebas_momento3.py`** (6 verificaciones)

### Cómo correrlas

```bash
source .venv/bin/activate
pip install httpx
python pruebas_rf_01_29.py
python pruebas_rf_30_50.py
python pruebas_momento2.py
python pruebas_momento3.py
```

Los cuatro deben terminar sin ningún `Traceback` y con su resumen final
("X requisitos verificados sin errores"). Si alguno falla, el mensaje de
`assert` te dice exactamente qué línea y qué requisito no cumplió.

## Mapa completo: requisito → dónde está → cómo verlo en el navegador

| RF | Qué hace | Cómo verlo en el navegador |
|---|---|---|
| 01 | Registrar paciente, secretaría o administrador | Pantalla de registro (`/login` → "Crear cuenta") para pacientes; panel de administrador → "Registrar usuario interno" para secretaría/administración |
| 02 | Agendar una cita | Panel de paciente o de secretaría → "Agendar cita" |
| 03 | Cancelar una cita | Botón "Cancelar" en el historial de citas |
| 04 | Reagendar una cita | Botón "Reagendar" en el historial de citas |
| 05 | Datos demográficos completos | Formulario de registro de paciente |
| 06 | Reportes consolidados | Panel de administrador, sección de reporte por rango de fechas |
| 07 | Digitar manualmente el valor a pagar | Secretaría → "Registrar cobro" en una cita atendida |
| 08 | Bloques de horario disponibles por médico | Selector de disponibilidad al agendar (paciente o secretaría) |
| 09 | Confirmación antes de cancelar/eliminar | Cualquier cancelación o cambio de estado pide marcar una casilla de confirmación |
| 10 | Administrar las dos sedes | Panel de administrador, sección "Información y recursos de la sede" |
| 11 | Franja horaria de la clínica | Intentar poner una jornada de médico fuera de 8-12 y 14-18 |
| 12 | Filtrar citas por sede, médico y fecha | Panel de secretaría, sección "Filtrar citas" |
| 13 | Inicio de sesión con credenciales | Pantalla de login |
| 14 | Hora dentro de la jornada del especialista | Agendar fuera del horario configurado para ese médico |
| 15 | Detalle completo de una cita | "Ver detalle completo" en cualquier fila de cita |
| 16 | Historial completo de citas atendidas | Panel de secretaría, "Historial de citas de un paciente" |
| 17 | Observaciones en la cita atendida | Secretaría → "Atender cita" |
| 18 | Botón de acceso rápido al menú principal | Botón "Menú principal / Salir" en la parte superior de cada pantalla |
| 19 | Bloques fijos de 30 minutos | Se ve en los horarios del selector de disponibilidad |
| 20 | Restringir módulos por rol | Entrar como paciente e intentar abrir `/dashboard/secretaria` da error |
| 21 | Ingresos totales por rango de fechas | Panel de administrador, reporte consolidado |
| 22 | Descuento porcentual o fijo | Secretaría → "Registrar cobro", campos de descuento |
| 23 | Transición ordenada de estados de la cita | No se puede "Atender" una cita que no esté "Confirmada" |
| 24 | Cambiar un usuario a Inactivo | Panel de administrador, "Estado de las cuentas" |
| 25 | Método de pago | Secretaría → "Registrar cobro", selector de método |
| 26 | Monto neto final | Se muestra tras registrar el cobro |
| 27 | Lista de espera | Panel de paciente o secretaría, sección "Lista de espera" |
| 28 | Edad calculada automáticamente | Se muestra en el historial del paciente |
| 29 | Estado del paciente (Activo/Inactivo/Bloqueado) | Panel de administrador, "Estado de las cuentas" |
| 30 | Sello de última actualización | Cambia al editar los datos de un paciente o una sede |
| 31 | Tipo de consulta (Optometría, Oftalmología General, Control) | Selector al agendar una cita |
| 32 | Impedir dos citas del mismo paciente en el mismo horario | Intentar agendar dos veces el mismo bloque para el mismo paciente |
| 33 | Impedir documentos duplicados | Intentar registrar dos pacientes con el mismo número de documento |
| 34 | Datos de acudiente para menores | Agendar una cita para un paciente menor de edad |
| 35 | Campos obligatorios no vacíos | Cualquier formulario rechaza el envío con campos clave vacíos |
| 36 | Búsqueda de pacientes por documento o nombre | Panel de secretaría, campo de búsqueda de pacientes |
| 37 | Reasignar un médico a otra sede | Panel de administrador, "Jornada de especialistas" |
| 38 | Mensajes de error claros | Cualquier error se muestra en una caja roja con texto en español |
| 39 | Listado de médicos por sede | Panel de administrador, lista de especialistas de la sede |
| 40 | Estado de cada cita (Pendiente, Completada, Cancelada) | Se ve en cada fila del historial de citas |
| 41 | Evitar sobreasignación del mismo médico | Intentar agendar dos pacientes distintos en el mismo horario con el mismo médico |
| 42 | Formato válido de correo y teléfono | Intentar guardar un correo o teléfono con formato incorrecto |
| 43 | Orden ascendente/descendente por fecha | Selector de orden en los filtros de citas |
| 44 | Motivo obligatorio al cancelar | Intentar cancelar una cita sin escribir el motivo |
| 45 | Estado del pago (Pendiente, Pagado, Anulado) | Se ve en cada fila de cita cobrada |
| 46 | Listado de usuarios activos | Panel de secretaría o de administrador, sección "Usuarios activos" |
| 47 | Editar datos básicos de un especialista | Panel de administrador, formulario de edición junto a cada médico |
| 48 | Filtrar solo las citas canceladas | Panel de secretaría, filtro de estado = "Cancelada" |
| 49 | Documento máximo 10 dígitos | Intentar registrar un documento más largo |
| 50 | Límite máximo de citas por médico y día | Panel de administrador, "Límite de citas por día" |

## La base de datos

Sigue siendo SQLite (`clinica.db`), como se documentó en la ronda anterior.
No cambió el diseño de las tablas, solo se corrigió el bug de arriba, que
afectaba específicamente a cómo se guardaban las cuentas de secretaría
nuevas.
