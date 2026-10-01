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
| D — Ensayo y ajustes | 5 | 8-9 | 8-11 | 7-8 |
| E — Extras | 6 | 10 | 12-13 | 9-10 |

**Hito fin de septiembre:** fase A completa → aquí, el `GET /health` desplegado en AWS (task 2).

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
- [ ] **3.2** `feat(models): add aforo event schema with validation` — Modelo Pydantic `AforoEvent` idéntico al contrato de `ARCHITECTURE.md`. Si cambia, avisar a `aforo-vision` (task 7.1) y `aforo-frontend` (task 4.1).
- [ ] **3.3** `test(models): validate accepted and rejected payloads` — Casos válidos, campos faltantes y enums inválidos.

### Task 4 — Cliente de DynamoDB
> Depende de: Seguir con las task 1-3 del repo: `aforo-db`

- [ ] **4.1** `feat(infra): import table name from aforo-db stack` — En `template.yaml`, `!ImportValue AforoPilotTableName` como variable de entorno `TABLE_NAME` + política `DynamoDBCrudPolicy` para las Lambdas.
- [ ] **4.2** `feat(db): add put event and query by time range` — `src/db/dynamo_client.py`: funciones `put_event(event)` y `query_events(from_ts, to_ts)`.
- [ ] **4.3** `feat(db): add update person status` — Función `update_person_status(person_id, direction, ts)` sobre `PERSON#<id>` / `PROFILE`.
- [ ] **4.4** `feat(db): add atomic occupancy counter` — Funciones `change_occupancy(delta)` y `get_occupancy()` sobre `AFORO` / `CURRENT`; nunca baja de 0.
- [ ] **4.5** `test(db): cover dynamo client with moto` — Tests con `moto` (DynamoDB simulado, sin tocar AWS).

### Task 5 — Endpoint `POST /events`
- [ ] **5.1** `feat(api): add post events handler` — `src/handlers/post_events.py`: valida con `AforoEvent`, guarda el evento, suma/resta el contador y, si hay `personId`, actualiza su estado.
- [ ] **5.2** `feat(api): make post events idempotent by event id` — `ConditionExpression attribute_not_exists` para que un reintento de la cola de `aforo-vision` no cuente dos veces.
- [ ] **5.3** `feat(infra): wire post events route` — Ruta `POST /events` en `template.yaml`.
- [ ] **5.4** `test(api): cover post events happy path and duplicates` — Evento válido, inválido (400) y duplicado (no altera el aforo).

### Task 6 — Endpoints de lectura
- [ ] **6.1** `feat(api): add get aforo handler` — Devuelve `{ currentOccupancy, lastUpdated }`.
- [ ] **6.2** `feat(api): add get events handler with range filter` — Query params `from` y `to` opcionales (por defecto: hoy).
- [ ] **6.3** `feat(api): add get people handler` — Lista de `{ personId, name, status, lastEventAt }`.
- [ ] **6.4** `feat(infra): wire read routes and enable cors` — Rutas GET + CORS para el dominio de Amplify y `localhost`.
- [ ] **6.5** `test(api): cover read handlers` — Respuestas con tabla vacía y con datos.

### Task 7 — Despliegue completo
- [ ] **7.1** `feat(scripts): add fake event sender for manual testing` — `scripts/send_fake_events.py`: manda eventos de prueba al API desplegado. Lo usan `aforo-frontend` (task 6) y este mismo repo para probar sin cámaras.
- [ ] **7.2** `docs: add api url and endpoints to readme` — URL base del API, endpoints y ejemplos `curl`. Esta URL la necesitan `aforo-vision` y `aforo-frontend`.
- [ ] **7.3** (sin commit) `sam deploy` y probar los 4 endpoints con el script de 7.1.

---

## Prioridad 2 — Importante

### Task 8 — Seguridad mínima
- [ ] **8.1** `feat(api): validate shared secret header on post events` — Rechazar con 401 cualquier `POST /events` sin el header correcto (secreto como parámetro `NoEcho` de SAM). Después sigue con la task 9 del repo: `aforo-vision`.
- [ ] **8.2** `feat(infra): add throttling limits to api stage` — Límite de peticiones por segundo para que nadie dispare costos.

### Task 9 — Observabilidad y retención
- [ ] **9.1** `feat(logging): add structured logs per request` — Log JSON con ruta, estado y `eventId`.
- [ ] **9.2** `chore(infra): set log retention to 7 days` — Evita acumular logs (y costo) en CloudWatch.
- [ ] **9.3** `feat(db): set expires at on event items` — Escribir `expiresAt` en cada evento para el borrado automático. Depende de: Seguir con la task 5 del repo: `aforo-db`.

---

## Prioridad 3 — Extras

### Task 10 — Exportar resultados
- [ ] **10.1** `feat(api): add csv export of events` — `GET /events/export` devuelve los eventos del día en CSV para adjuntarlos al informe.
