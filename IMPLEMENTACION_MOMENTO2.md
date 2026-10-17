# Requerimientos agregados al sistema de citas oftalmológicas

Este documento resume los requerimientos funcionales que se implementaron sobre la base
existente, con el archivo y la ruta HTTP donde puede verificarse cada uno.

## 1. RF.10 — Administrar la información y los recursos de las dos sedes

Antes las sedes existían solo como datos de precarga y nadie podía modificarlas.

- `repositorios.py`: `ISedeRepository` y `SedeRepositoryMemory`.
- `modelos.py`: `Sede.actualizar_datos()` con validación de nombre, dirección y consultorios.
- `servicios.py`: `SedeService` (crear, actualizar, listar, contar especialistas por sede).
- Rutas: `GET /sedes`, `POST /sedes`, `POST|PUT /sedes/{id_sede_destino}`.
- Interfaz: panel del administrador, sección «Información y recursos de la sede».

Regla de negocio: un administrador solo puede modificar la sede que administra; intentar
editar la otra sede responde 403.

## 2. RF.24 y RF.29 — Estado real de las cuentas (Activo, Inactivo, Bloqueado)

Antes solo existía la inactivación en un sentido y el estado `BLOQUEADO` nunca se usaba.

- `servicios.py`: `AdministradorService.cambiar_estado_usuario()` y `obtener_usuarios_gestionables()`.
- Ruta: `POST /usuarios/{id_usuario}/estado`.
- Interfaz: panel del administrador, sección «Estado de las cuentas».

Reglas de negocio: exige confirmación explícita, no permite cambiar el propio estado, no
permite restringir a un médico con citas futuras y conserva todo el historial. Además,
`obtener_sesion()` revalida el estado en cada petición, de modo que una cuenta bloqueada
pierde el acceso incluso con la sesión ya abierta.

## 3. RF.50 — Límite de citas por médico y por día

Antes era una constante global de 16 citas, igual a la jornada completa, por lo que nunca
se activaba.

- `modelos.py`: `Medico.max_citas_dia` y `configurar_limite_diario()`.
- `servicios.py`: `AdministradorService.configurar_limite_diario_medico()`; `_validar_horario()`
  ahora consulta el límite del especialista.
- Ruta: `POST /medicos/{id_medico}/limite-diario`.
- Interfaz: panel del administrador, sección «Límite de citas por día».

## 4. RF.16 — Historial completo de citas de un paciente desde secretaría

Antes el historial solo lo veía el propio paciente en su panel.

- `servicios.py`: `SecretariaService.obtener_historial_paciente()`.
- Ruta: `GET /pacientes/{id_paciente}/historial?solo_atendidas=&orden=`.
- Interfaz: panel de secretaría, sección «Historial de citas de un paciente».

El paciente se resuelve por documento, nombre único o identificador, igual que en el resto
del módulo de secretaría.

## 5. RF.05, RF.30 y RF.42 — Actualización de datos del paciente

Antes los datos demográficos solo se capturaban en el registro y el sello de última
actualización nunca cambiaba.

- `modelos.py`: `Paciente.actualizar_datos_personales()`.
- `servicios.py`: `SecretariaService.actualizar_datos_paciente()`.
- Rutas: `POST /mis-datos` (paciente) y `POST /pacientes/{id_paciente}/actualizar` (secretaría).
- Interfaz: «Mis datos de contacto» en el panel del paciente y «Actualizar datos del
  paciente» en el de secretaría.

Reglas de negocio: valida teléfono numérico y formato de correo, rechaza correos ya usados
por otro usuario, exige acudiente cuando el paciente es menor de edad y actualiza la fecha
y hora de la última modificación.

## 6. RF.27 — Lista de espera operativa

Antes solo se podía agregar solicitudes; no había forma de retirarlas ni de convertirlas en
cita cuando se liberaba un bloque.

- `servicios.py`: `AgendamientoService.buscar_registro_espera()`, `retirar_de_lista_espera()`
  y `promover_lista_espera()`.
- Rutas: `POST /lista-espera/{id_registro}/retirar` y `POST /lista-espera/{id_registro}/promover`.
- Interfaz: panel de secretaría, sección «Lista de espera».

Al promover, la solicitud pasa por las mismas validaciones de agendamiento (jornada,
sobreasignación, límite diario) y se retira de la lista únicamente si la cita queda creada.

## 7. RF.12, RF.43 y RF.48 — Filtros, orden y citas canceladas en secretaría

Antes el panel de secretaría filtraba por sede, médico y fecha, pero el orden era fijo y no
existía filtro por estado.

- `routers/secretaria_router.py`: parámetros `estado` y `orden` en el tablero.
- Interfaz: sección «Filtrar citas», con accesos directos a citas canceladas y atendidas.

## 8. HU-03 y RF.06 — Bitácora de auditoría

La historia de usuario HU-03 pedía auditoría además del reporte financiero, y no existía
ningún registro de quién ejecutaba cada operación.

- `modelos.py`: `RegistroAuditoria`.
- `repositorios.py`: `IAuditoriaRepository` y `AuditoriaRepositoryMemory`.
- `servicios.py`: `AuditoriaService`.
- `main.py`: middleware `auditar_operaciones()`, que registra toda petición POST, PUT, PATCH
  y DELETE con autor, rol, sede y código de respuesta.
- Rutas: `GET /auditoria` y `GET /auditoria/exportar` (CSV).
- Interfaz: panel del administrador, sección «Bitácora de auditoría».

## Mejoras de diseño aplicadas de paso

- `ICitaRepository` expone `obtener_todas()` y `obtener_futuras_por_medico()`, e
  `IUsuarioRepository` expone `obtener_todos()`. Los servicios y los routers ya no acceden a
  los diccionarios internos `_citas` ni `_usuarios`, con lo que la capa de persistencia queda
  realmente intercambiable.
- Las sedes dejan de vivir en `app.state.sedes` y pasan al repositorio correspondiente.

## Cómo verificar

```bash
source .venv/bin/activate
uvicorn main:app --reload
```

Para ejecutar las pruebas automáticas de los requerimientos nuevos:

```bash
pip install httpx
python pruebas_momento2.py
```

El script `pruebas_momento2.py` valida los ocho puntos anteriores y comprueba que los
tableros y el reporte consolidado sigan funcionando.
