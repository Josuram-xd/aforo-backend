# TASKS — aforo-backend

API en la nube (API Gateway + Lambda en Python) que recibe eventos de `aforo-vision` y sirve datos a `aforo-frontend`.

## Cómo usar este archivo

- Cada subtarea es **un commit**. Formato: `tipo(alcance): descripción [x.y]`
  Ejemplo: `git commit -m "feat(api): add post events handler [5.1]"`
- En ese mismo commit cambia `[ ]` por `[x]` en este archivo.
- Las subtareas marcadas **(sin commit)** son verificaciones manuales: márcalas en el siguiente commit que hagas.
- Tipos: `feat`, `fix`, `test`, `docs`, `chore`, `perf`, `refactor`.
- **Prioridad 1** = sin esto no hay piloto. **Prioridad 2** = importante para que el piloto salga bien. **Prioridad 3** = extra si sobra tiempo.
- `> Depende de:` indica que antes tienes que avanzar tareas de otro repo.

## Orden global entre los 4 repos

| Fase | aforo-db | aforo-backend | aforo-vision | aforo-frontend |
|---|---|---|---|---|
| A — Arranque (en paralelo) | 1-3 | 1-2 | 1-3 | 1-2 |
| B — Núcleo | 4 | 3-7 | 4-6 | 3-5 (con datos mock) |
| C — Integración | — | — | 7 | 6 |
| D — Ensayo y ajustes | 5 | 8-9, 11 (login) | 8-11 | 7-8, 11 (login) |
| E — Extras | 6 | 10 | 12-13 | 9-10 |

**Hito fin de septiembre:** fase A completa → aquí, el `GET /health` desplegado en AWS (task 2).

### Versión 2 (después de la primera entrega, octubre 2026)

Retroalimentación del profe: pocas tablas, sin registro ni login, endpoints públicos, AWS sin protección contra abuso y un frontend muy básico. La v2 pasa los datos y el login a **Supabase** (PostgreSQL + Auth con Google + RLS + Realtime). Detalle en la sección "Version 2" de cada `ARCHITECTURE.md`.

| Fase | aforo-db | aforo-backend | aforo-vision | aforo-frontend |
|---|---|---|---|---|
| F — Base v2 | 7 | 12.1-12.2 | — | 12 |
| G — Login, seguridad e integración | 8 | 13 | 14 | 13 |
| H — Producto | 9 | — | 15 (evaluar visión en la nube) | 14-15 |
| I — Cierre | 10 | 12.3-12.4 | 15.3-15.6, 16 | 16 |

Las tareas v1 que la v2 reemplaza quedan marcadas con ~~tachado~~ y una nota; no se borran para conservar el historial.

---

## Prioridad 1 — Crítico

### Task 1 — Inicializar el proyecto
- [x] **1.1** `chore: init sam project structure` — `template.yaml`, `src/handlers/`, `src/models/`, `src/db/`, `tests/`, `requirements.txt`, `.gitignore` (excluir `.aws-sam/`).
- [x] **1.2** `chore: add pytest and ruff config` — `pyproject.toml` con pytest y ruff.
- [x] **1.3** `docs: add PRD, ARCHITECTURE and AGENTS` — Subir los documentos a la raíz.

### Task 2 — "Hola mundo" desplegado **[HITO SEPT]**
- [x] **2.1** `feat(api): add health handler` — `src/handlers/health.py`: función `handler(event, context)` que responde `{"status": "ok"}`.
- [x] **2.2** `feat(infra): wire get health route` — Ruta `GET /health` en `template.yaml` (HTTP API + Lambda Python 3.14).
- [x] **2.3** `chore(infra): add samconfig for pilot stack` — `samconfig.toml` con nombre del stack y región.
- [x] **2.4** (sin commit) `sam deploy` y probar `curl <url>/health`.

### Task 3 — Contrato compartido
- [x] **3.1** `feat(models): add direction, method and camera enums` — `src/models/event.py`: `Direction` (`ENTRY`/`EXIT`), `EventMethod` (`FACE`/`BODY_ONLY`), `CameraId` (`camera-outside`/`camera-inside`).
- [x] **3.2** `feat(models): add aforo event schema with validation` — Modelo Pydantic `AforoEvent` idéntico al contrato de `ARCHITECTURE.md`. Si cambia, avisar a `aforo-vision` (task 7.1) y `aforo-frontend` (task 4.1).
- [x] **3.3** `test(models): validate accepted and rejected payloads` — Casos válidos, campos faltantes y enums inválidos.

### Task 4 — Cliente de DynamoDB
> Depende de: Seguir con las task 1-3 del repo: `aforo-db`

- [x] **4.1** `feat(infra): import table name from aforo-db stack` — En `template.yaml`, `!ImportValue AforoPilotTableName` como variable de entorno `TABLE_NAME` + política `DynamoDBCrudPolicy` para las Lambdas.
- [x] **4.2** `feat(db): add put event and query by time range` — `src/db/dynamo_client.py`: funciones `put_event(event)` y `query_events(from_ts, to_ts)`.
- [x] **4.3** `feat(db): add update person status` — Función `update_person_status(person_id, direction, ts)` sobre `PERSON#<id>` / `PROFILE`.
- [x] **4.4** `feat(db): add atomic occupancy counter` — Funciones `change_occupancy(delta)` y `get_occupancy()` sobre `AFORO` / `CURRENT`; nunca baja de 0.
- [x] **4.5** `test(db): cover dynamo client with moto` — Tests con `moto` (DynamoDB simulado, sin tocar AWS).

### Task 5 — Endpoint `POST /events`
- [x] **5.1** `feat(api): add post events handler` — `src/handlers/post_events.py`: valida con `AforoEvent`, guarda el evento, suma/resta el contador y, si hay `personId`, actualiza su estado.
- [x] **5.2** `feat(api): make post events idempotent by event id` — `ConditionExpression attribute_not_exists` para que un reintento de la cola de `aforo-vision` no cuente dos veces.
- [x] **5.3** `feat(infra): wire post events route` — Ruta `POST /events` en `template.yaml`.
- [x] **5.4** `test(api): cover post events happy path and duplicates` — Evento válido, inválido (400) y duplicado (no altera el aforo).

### Task 6 — Endpoints de lectura
- [x] **6.1** `feat(api): add get aforo handler` — Devuelve `{ currentOccupancy, lastUpdated }`.
- [x] **6.2** `feat(api): add get events handler with range filter` — Query params `from` y `to` opcionales (por defecto: hoy).
- [x] **6.3** `feat(api): add get people handler` — Lista de `{ personId, name, status, lastEventAt }`.
- [x] **6.4** `feat(infra): wire read routes and enable cors` — Rutas GET + CORS para el dominio de Amplify y `localhost`.
- [x] **6.5** `test(api): cover read handlers` — Respuestas con tabla vacía y con datos.

### Task 7 — Despliegue completo
- [x] **7.1** `feat(scripts): add fake event sender for manual testing` — `scripts/send_fake_events.py`: manda eventos de prueba al API desplegado. Lo usan `aforo-frontend` (task 6) y este mismo repo para probar sin cámaras.
- [x] **7.2** `docs: add api url and endpoints to readme` — URL base del API, endpoints y ejemplos `curl`. Esta URL la necesitan `aforo-vision` y `aforo-frontend`.
- [x] **7.3** (sin commit) `sam deploy` y probar los 4 endpoints con el script de 7.1.

---

## Prioridad 2 — Importante

### Task 8 — Seguridad mínima
- [x] **8.1** `feat(api): validate shared secret header on post events` — Rechazar con 401 cualquier `POST /events` sin el header correcto (secreto como parámetro `NoEcho` de SAM). Después sigue con la task 9 del repo: `aforo-vision`.
- [ ] ~~**8.2** `feat(infra): add throttling limits to api stage` — Límite de peticiones por segundo para que nadie dispare costos.~~ → se adelanta como task 12.2 (mitigación urgente mientras v1 siga en línea).

### Task 9 — Observabilidad y retención
- [ ] ~~**9.1** `feat(logging): add structured logs per request` — Log JSON con ruta, estado y `eventId`.~~ → v1 se retira; en v2 los logs los da Supabase (task 13.3).
- [ ] ~~**9.2** `chore(infra): set log retention to 7 days` — Evita acumular logs (y costo) en CloudWatch.~~ → v1 se retira (task 12.3).
- [ ] ~~**9.3** `feat(db): set expires at on event items` — Escribir `expiresAt` en cada evento para el borrado automático. Depende de: Seguir con la task 5 del repo: `aforo-db`.~~ → reemplazada por `aforo-db` task 9.1 (pg_cron).

### Task 11 — Login de usuarios (Cognito)
> Depende de: task 6 de este repo (rutas GET ya creadas).

- [ ] ~~**11.1** `feat(infra): add cognito user pool with viewer and dev groups` — En `template.yaml`: User Pool sin auto-registro (solo el admin crea cuentas), App Client público con PKCE (sin secreto), dominio de login administrado, grupos `viewer` y `dev`. Outputs `UserPoolId`, `UserPoolClientId`, `UserPoolDomain` (los usan `aforo-frontend` task 11 y `aforo-vision` task 12). Verificar antes los límites vigentes del nivel gratuito de Cognito.~~ → reemplazada por Supabase Auth (v2, `aforo-db` tasks 7.5 y 7.7, `aforo-frontend` task 13).
- [ ] ~~**11.2** `feat(infra): protect read routes with jwt authorizer` — Authorizer JWT del HTTP API sobre `GET /events`, `GET /aforo`, `GET /people` (y `GET /events/export` si existe). `GET /health` queda pública y `POST /events` sigue con el secreto de 8.1. CORS: permitir el header `Authorization`.~~ → reemplazada por Supabase Auth (v2, `aforo-db` tasks 7.5 y 7.7, `aforo-frontend` task 13).
- [ ] ~~**11.3** `feat(scripts): add create user script` — `scripts/create_user.py <correo> <viewer|dev>`: crea la cuenta con `admin_create_user` (contraseña temporal por correo) y la agrega al grupo.~~ → reemplazada por Supabase Auth (v2, `aforo-db` tasks 7.5 y 7.7, `aforo-frontend` task 13).
- [ ] ~~**11.4** `test(api): reject read routes without token` — Verificar que el template declara el authorizer en las rutas GET y no en `/health` ni `POST /events`.~~ → reemplazada por Supabase Auth (v2, `aforo-db` tasks 7.5 y 7.7, `aforo-frontend` task 13).
- [ ] ~~**11.5** (sin commit) `sam deploy`, crear un usuario `viewer` y uno `dev`, y probar con `curl` que sin token responde 401 y con token 200.~~ → reemplazada por Supabase Auth (v2, `aforo-db` tasks 7.5 y 7.7, `aforo-frontend` task 13).

---

## Prioridad 3 — Extras

### Task 10 — Exportar resultados
- [ ] ~~**10.1** `feat(api): add csv export of events` — `GET /events/export` devuelve los eventos del día en CSV para adjuntarlos al informe.~~ → reemplazada por la task 13.1 (Edge Function).

---

## Versión 2 — Supabase reemplaza el API de AWS

> Ver `ARCHITECTURE.md` sección 9. En v2 los datos, el login y la seguridad viven en Supabase (`aforo-db`): el frontend y `aforo-vision` hablan directo con Supabase. Este repo pasa a contener las **Edge Functions** (lógica de servidor que no cabe en SQL) y se encarga de apagar el API de AWS.

### Task 12 — Mitigar y retirar el API de AWS **(Prioridad 1)**
- [x] **12.1** `docs: document v2 migration and deprecate aws api` — README y `ARCHITECTURE.md`: el API v1 queda en modo legado hasta la task 12.3.
- [x] **12.2** `feat(infra): add throttling limits to api stage` — **Urgente mientras v1 siga en línea:** límite de peticiones (por ejemplo 10 req/s, ráfaga 20) en el stage del HTTP API para que nadie dispare costos. Junto con esto, la alerta de presupuesto de `aforo-db` task 3.1 debe estar activa.
- [ ] **12.3** (sin commit) Cuando `aforo-vision` task 14 y `aforo-frontend` task 16 funcionen contra Supabase: `sam delete` del stack `aforo-pilot-backend` (confirmar antes) y quitar las variables de Amplify que apuntan al API viejo.
- [ ] **12.4** `chore: remove lambda handlers and sam template` — Quitar `src/handlers`, `src/db`, `template.yaml` y los tests de v1; dejar solo lo de la task 13.

### Task 13 — Edge Functions **(Prioridad 2)**
> Depende de: `aforo-db` task 7 (proyecto y esquema).

- [x] **13.1** `feat(functions): add events csv export function` — `supabase/functions/export-events`: valida el JWT del usuario y su rol (`teacher` o `admin`), recibe `from`/`to` y `classroomId`, devuelve CSV con nombre del estudiante, dirección, método y confianza. Registra `EXPORT` en `audit_log`.
- [x] **13.2** `feat(functions): add admin invite user function` — `supabase/functions/invite-user`: un `admin` invita por correo con un rol inicial (usa la `service_role` key solo dentro de la función, nunca en el navegador).
- [x] **13.3** `docs: add functions deploy and logs guide` — Cómo desplegar (`supabase functions deploy`), configurar secretos (`supabase secrets set`) y ver logs en el dashboard de Supabase.
- [x] **13.4** `test(functions): cover auth and role checks` — Sin token → 401, `viewer` → 403, `teacher` → 200 con CSV válido.
