# RF.30 a RF.50 y migración a base de datos — Ronda 4

## Parte 1: los requisitos RF.30 a RF.50

Antes de escribir una sola línea revisé, requisito por requisito, si de
verdad faltaba algo entre el RF.30 y el RF.50. Con el trabajo de las tres
rondas anteriores (sedes, estados de cuenta, límite diario, historial, datos
del paciente, lista de espera, filtros, auditoría, jornada acotada a la
franja de la clínica, reasignación segura de médicos, validaciones de
formularios) **los 21 ya estaban resueltos en el código**. En vez de tocar
algo que ya funcionaba, hice dos cosas:

1. Encontré y corregí **un acceso indebido que se me había pasado en la
   ronda 1**: `routers/secretaria_router.py` leía
   `usuario_repo._usuarios.values()` directamente, es decir, entraba a la
   libreta de direcciones interna del repositorio en memoria en vez de
   usar `obtener_todos()`. Esto habría roto el panel de secretaría en cuanto
   cambiara el motor de almacenamiento — que es exactamente lo que pasó al
   migrar a SQLite en la Parte 2 de este trabajo, y fue así como lo detecté.
   Ya quedó corregido y probado.
2. Escribí `pruebas_rf_30_50.py`, que ejercita **cada uno de los 21
   requisitos por separado**, contra la base de datos real, para que tengas
   la prueba concreta y puedas mostrarle al profesor exactamente qué
   petición corresponde a cada número. Al correrlo verás 21 líneas con un
   check (✔), una por cada RF.

Un detalle que vale la pena explicar en la sustentación: al probar el
RF.34 descubrí que el sistema pide los datos del acudiente **en cada cita
que se agenda para un menor**, no solo la primera vez que se registra el
paciente (aunque esos datos ya queden guardados). No es un error — es una
lectura más estricta del requisito ("solicitar los datos del acudiente
**al agendar** una cita a un menor"), y así estaba diseñado desde el
código original del equipo. Lo dejé como está porque es una postura
razonable, pero es un punto que conviene que sepas explicar si el profesor
pregunta por qué hay que volver a escribir el nombre del acudiente cada vez.

## Parte 2: la base de datos

El sistema ya no guarda nada en memoria. Ahora usa **SQLite** (viene incluido
en Python, no hay que instalar nada nuevo) a través del módulo estándar
`sqlite3`, con SQL escrito a mano en vez de un ORM — así se ve exactamente
qué sentencia se ejecuta en cada operación, que es más fácil de explicar en
una materia de bases de datos.

### Diseño de las tablas

El diagrama de clases del Momento 1 ya mostraba `Usuario` como clase base
con `Paciente` y las demás heredando de ella. Ese mismo diseño se tradujo
directamente a tablas:

- **`sedes`** — las dos sedes de la clínica.
- **`usuarios`** — la tabla base: documento, nombres, correo, contraseña
  (con su hash), rol, estado y la fecha de última actualización. Todo
  usuario (paciente, secretaria, médico o administrador) tiene una fila
  aquí.
- **`pacientes`**, **`medicos`**, **`administradores`** — cada una extiende
  `usuarios` con los campos específicos de ese tipo (fecha de nacimiento y
  acudiente para pacientes; especialidad, sede y jornada para médicos; sede
  fija para administradores). Es el mismo patrón "tabla base + tablas de
  extensión" que se usa para modelar herencia en una base de datos
  relacional.
- **`citas`** — cada cita, con referencia a paciente, médico y sede.
- **`lista_espera`** — antes vivía en una simple lista de Python dentro del
  servicio (por eso se perdía al reiniciar el servidor); ahora es una tabla
  con su propio repositorio.
- **`auditoria`** — la bitácora de acciones administrativas.

Los archivos nuevos son:

- **`basededatos.py`** — abre la conexión y crea las tablas (`CREATE TABLE
  IF NOT EXISTS`, así que correr el servidor mil veces no rompe nada).
- **`repositorios_sqlite.py`** — la implementación real con SQL: un
  `UsuarioRepositorySQLite`, `CitaRepositorySQLite`, `SedeRepositorySQLite`,
  `AuditoriaRepositorySQLite` y `ListaEsperaRepositorySQLite`.

### Por qué el cambio fue casi indoloro

El proyecto ya estaba organizado con **repositorios detrás de una interfaz**
(`IUsuarioRepository`, `ICitaRepository`, etc., en `repositorios.py`) desde
antes de que yo empezara a ayudarte. `servicios.py` —donde vive toda la
lógica de negocio— nunca habla con SQLite directamente: solo conoce esas
interfaces. Por eso, migrar de memoria a una base de datos real fue
**cambiar qué clase le entrega `main.py` a cada servicio**, no reescribir
las reglas de negocio. Ese es el valor práctico del patrón Repository que
ya traía el diseño original: aísla la lógica de negocio de cómo se guardan
los datos. La única lógica que sí tuve que tocar fue la lista de espera,
porque antes no tenía repositorio (era una lista de Python suelta dentro de
`AgendamientoService`) — le creé su propia interfaz `IListaEsperaRepository`
para que también quedara guardada de verdad.

`repositorios.py` conserva las versiones en memoria (`UsuarioRepositoryMemory`,
etc.) sin usarlas — las dejé ahí como referencia, por si en la sustentación
quieres mostrar la comparación entre las dos implementaciones de la misma
interfaz.

### Cómo se prueba

```bash
source .venv/bin/activate
uvicorn main:app --reload
```

La primera vez que corras el servidor se crea el archivo `clinica.db` en la
misma carpeta, con las sedes y usuarios semilla. Las siguientes veces que lo
reinicies, **la información ya guardada sigue ahí** — la siembra solo se
ejecuta si la base de datos está vacía. Compruébalo tú mismo: crea una cita,
apaga el servidor con Ctrl+C, vuelve a correr `uvicorn main:app --reload`, y
la cita seguirá existiendo.

Para las pruebas automáticas, los tres scripts (`pruebas_momento2.py`,
`pruebas_momento3.py` y `pruebas_rf_30_50.py`) usan una base de datos SQLite
**en memoria** (`:memory:`), para que cada corrida empiece limpia y no toque
tu `clinica.db` real:

```bash
pip install httpx
python pruebas_rf_30_50.py   # los 21 requisitos de esta ronda, uno por uno
python pruebas_momento2.py   # ronda 2, contra SQLite
python pruebas_momento3.py   # ronda 3, contra SQLite
```

Si en algún momento quieres empezar de cero con datos limpios, simplemente
borra el archivo `clinica.db` y el servidor lo vuelve a crear con la siembra
inicial la próxima vez que arranque.
