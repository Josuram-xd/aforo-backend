# aforo-backend

Lógica de servidor del sistema de aforo que no cabe en SQL.

- **v2 (actual): Edge Functions de Supabase** (Deno/TypeScript) en `supabase/functions/`. En v2 el frontend y `aforo-vision` hablan directo con Supabase (`aforo-db`); este repo solo agrega lo que necesita una llave privada o generar archivos:
  - `export-events`: descarga los eventos de un salón en CSV (`teacher` y `admin`).
  - `invite-user`: un `admin` invita a una persona por correo con un rol inicial.
- **v1 (legado, deprecado): API de AWS** (API Gateway HTTP API + Lambda + DynamoDB) en `src/` y `template.yaml`. Sigue en línea, con límite de 10 req/s (ráfaga 20), hasta la task 12.3; no se le agregan funciones nuevas y se borra en la task 12.4.

Más detalle en `PRD.md`, `ARCHITECTURE.md` (sección 9 = v2) y `AGENTS.md`. El trabajo pendiente está en `TASKS.md`.

## Estructura

```
aforo-backend/
├── supabase/functions/           # v2
│   ├── export-events/index.ts    # CSV de eventos (registra EXPORT en la auditoría)
│   ├── invite-user/index.ts      # invitación por correo con rol inicial
│   ├── _shared/                  # auth.ts (JWT + rol), cors.ts, csv.ts
│   ├── functions_test.ts         # pruebas con Deno
│   └── README.md                 # contrato, despliegue, secretos y logs de las funciones
├── src/                          # v1 (legado): Lambdas
│   ├── handlers/                 # health, post_events, get_events, get_aforo, get_people
│   ├── models/event.py           # contrato del evento y validación
│   └── db/dynamo_client.py       # acceso a la tabla AforoPilot
├── tests/                        # v1: pytest con moto (no tocan AWS)
├── scripts/send_fake_events.py   # v1: manda eventos de prueba al API de AWS
├── template.yaml · samconfig.toml  # v1: infraestructura con AWS SAM
└── PRD.md · ARCHITECTURE.md · AGENTS.md · TASKS.md
```

## v2 — Edge Functions

Todo el detalle (contrato para el frontend, códigos de respuesta, despliegue, secretos y logs) está en [`supabase/functions/README.md`](supabase/functions/README.md). Resumen:

```bash
supabase login
supabase link --project-ref <ref>
supabase functions deploy export-events
supabase functions deploy invite-user

cd supabase/functions && deno test --allow-env     # pruebas
```

Ambas exigen el JWT del usuario y además revisan su rol. La `service_role` key solo existe dentro de las funciones; nunca en git ni en el navegador.

---

## Estructuras de datos, GRASP y SOLID

Dónde y cómo se aplican en v2 (`supabase/functions/`) los conceptos del curso de estructuras de datos, GRASP y SOLID. El código v1 (`src/`, DynamoDB) está en retiro y no se analiza aquí.

### Estructuras de datos

**Aplicada: tabla hash (`Map`) en el limitador de tasa.** [`_shared/ratelimit.ts`](supabase/functions/_shared/ratelimit.ts) guarda un `Map<string, { start, count }>` con clave = id del usuario. `authenticate()` en [`_shared/auth.ts`](supabase/functions/_shared/auth.ts) llama a `allowRequest(userId)` después de validar el JWT, así que el límite aplica a ambas funciones. Es una ventana fija de 60 s con `MAX_PER_WINDOW = 30`. Cuando el mapa tiene más de 1000 entradas, al abrir una ventana nueva se borran las entradas vencidas. El comentario `shortcut:` del archivo documenta el límite: el contador vive en memoria de cada instancia, no se comparte entre instancias y un cliente decidido puede superarlo; la mejora sería un contador en la base de datos.

**Recorrido de arreglos en `csvRow`.** [`_shared/csv.ts`](supabase/functions/_shared/csv.ts) serializa cada fila con `values.map(csvCell)`; [`export-events/index.ts`](supabase/functions/export-events/index.ts) la usa para cada página de eventos. Es un arreglo, no una estructura propia.

**Del curso que no se aplican.** No se forzaron a propósito; no hay un uso natural en este repo, porque las funciones son casi sin estado (el único estado en memoria es el `Map` del limitador) y los datos viven en Postgres.

- **Pila:** no hay procesos que deban deshacerse en orden inverso.
- **Cola:** el orden de las peticiones lo decide la plataforma, y el orden de los eventos lo da Postgres con `ORDER BY`.
- **Listas enlazadas:** los resultados son páginas de la base (`range`), no nodos que se recorran en memoria.
- **Árbol:** los índices de búsqueda los mantiene Postgres, no el código de las funciones.
- **Cola de prioridad:** el repo no tiene trabajos con prioridad.

### GRASP

- **Bajo acoplamiento (inyección de dependencias).** [`export-events/index.ts`](supabase/functions/export-events/index.ts) e [`invite-user/index.ts`](supabase/functions/invite-user/index.ts) declaran `interface Deps`, un `defaultDeps` con los clientes reales de Supabase y `handle(req, deps)`. [`functions_test.ts`](supabase/functions/functions_test.ts) pasa mocks (por ejemplo `createUserClient: () => client`), así que las pruebas no hacen llamadas de red.
- **Alta cohesión.** `_shared/` tiene módulos con propósitos acotados: `cors.ts` (CORS y respuestas JSON), `auth.ts` (JWT, límite de tasa, roles y cuenta activa), `ratelimit.ts` (límite por usuario) y `csv.ts` (CSV y formato de fecha). Las funciones usan esos módulos y se limitan a su lógica de endpoint: validación, consulta y respuesta.
- **Fabricación pura.** `csvCell`, `csvRow` (en `csv.ts`) y `allowRequest` (en `ratelimit.ts`) son piezas artificiales que no representan un concepto del dominio (estudiante, aula, evento): reciben valores y claves genéricas. Pero `allowRequest` guarda estado en el `Map`, y `formatBogota` fija la zona `America/Bogota`, así que `csv.ts` mezcla utilidades genéricas con una específica del proyecto.

### SOLID

- **S (responsabilidad única).** Cada módulo de `_shared/` tiene un propósito acotado. `auth.ts` es el más amplio (JWT, límite de tasa, roles y cuenta activa) y es el candidato a dividirse si crece. Cada función hace una tarea: `export-events` exporta y `invite-user` invita.
- **O (abierto/cerrado).** Visible en parte: `authenticate(req, createUserClient, allowedRoles)` recibe los roles permitidos como parámetro, así que una función nueva reutiliza la autenticación sin modificar `auth.ts`.
- **L (sustitución de Liskov).** No se ve de forma verificable: `DbClient` es `any`, así que el compilador no comprueba que un mock cumpla el contrato del cliente real.
- **I (segregación de interfaces).** Visible en parte: cada función declara solo lo que usa. `export-events` tiene solo `createUserClient`; `invite-user` agrega `createAdminClient`, que `export-events` no recibe.
- **D (inversión de dependencias).** `handle` depende de la interfaz `Deps`, no de `createClient`. `createClient` solo se llama en `defaultDeps`, en el punto de entrada.

El material del curso está en la carpeta «Estructura de datos» del curso.

---

## Legado v1 — API de AWS

> Se apaga en la task 12.3, cuando `aforo-vision` y `aforo-frontend` funcionen contra Supabase.

### URL base

```
https://y2bd1cj4s3.execute-api.us-east-1.amazonaws.com
```

> Es el output `ApiUrl` del stack `aforo-pilot-backend` (us-east-1). `aforo-vision` y
> `aforo-frontend` necesitan este valor. Sin barra final.

### Endpoints

| Ruta | Método | Descripción | Respuesta |
|---|---|---|---|
| `/health` | `GET` | Comprobación de que el API está viva | `200` `{"status": "ok"}` |
| `/events` | `POST` | Registra un evento de `aforo-vision` | `201` `{"eventId": ...}`; `200` con `"duplicate": true` si el `eventId` ya existía; `400` si el evento no es válido |
| `/events` | `GET` | Eventos en un rango. Params opcionales `from` y `to` (ISO 8601 con zona horaria); por defecto, hoy (hora de Colombia) | `200` lista de eventos, del más antiguo al más reciente |
| `/aforo` | `GET` | Aforo actual | `200` `{"currentOccupancy": n, "lastUpdated": timestamp \| null}` |
| `/people` | `GET` | Personas del roster y su estado | `200` lista de `{personId, name, status: "IN" \| "OUT", lastEventAt: timestamp \| null}` |

El formato del evento y los enums (`Direction`, `EventMethod`, `CameraId`) están en la sección 4
de `ARCHITECTURE.md`. Los errores `400` traen `message` en español y, si el fallo es de
validación, `invalidFields`.

> Autenticación: `POST /events` exige el header `X-Aforo-Secret` con el secreto compartido
> (`401` si falta o es incorrecto). Las rutas `GET` siguen abiertas: el login con Cognito (task 11)
> se descartó porque en v2 el login es Supabase Auth, y este API se retira en vez de protegerlo.

### Ejemplos con curl

```bash
API_URL="https://y2bd1cj4s3.execute-api.us-east-1.amazonaws.com"
SHARED_SECRET="<el secreto con el que desplegaste>"

# Estado del API
curl "$API_URL/health"

# Registrar una entrada
curl -X POST "$API_URL/events" \
  -H "Content-Type: application/json" \
  -H "X-Aforo-Secret: $SHARED_SECRET" \
  -d '{
    "eventId": "0b6f1c9e-8a2e-4c55-9d0e-1f2a3b4c5d6e",
    "personId": null,
    "personName": null,
    "direction": "ENTRY",
    "cameraOutsideId": "camera-outside",
    "cameraInsideId": "camera-inside",
    "confidence": 0.91,
    "method": "BODY_ONLY",
    "timestamp": "2026-09-30T14:32:00Z"
  }'

# Aforo actual
curl "$API_URL/aforo"

# Eventos de hoy, o de un rango (usa Z o %2B para el + de la zona horaria)
curl "$API_URL/events"
curl "$API_URL/events?from=2026-09-30T00:00:00Z&to=2026-09-30T23:59:59Z"

# Personas y su estado
curl "$API_URL/people"
```

### Probar sin cámaras

`scripts/send_fake_events.py` manda eventos de prueba al API desplegado (solo biblioteca estándar):

```bash
python scripts/send_fake_events.py "$API_URL" --count 20 --interval 2 --header "X-Aforo-Secret: $SHARED_SECRET"
python scripts/send_fake_events.py "$API_URL" --person-id <uuid-del-roster> --person-name "Ana"
python scripts/send_fake_events.py "$API_URL" --dry-run
```

### Desarrollo

Requiere Python 3.14 (el runtime de Lambda). Desde la raíz del repo:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r src/requirements.txt --group dev
python -m pytest                  # tests con moto, no tocan AWS
ruff check . && ruff format --check .
```

### Despliegue

Antes hay que desplegar la tabla desde `aforo-db` (este stack importa `AforoPilotTableName`).

```bash
sam validate --lint
sam build
sam deploy --parameter-overrides SharedSecret=<secreto-de-al-menos-16-caracteres>
                                  # muestra el changeset y pide confirmación
```

`SharedSecret` es obligatorio (mínimo 16 caracteres, no se muestra en la consola de
CloudFormation). Guárdalo: `aforo-vision` debe enviarlo en el header `X-Aforo-Secret`.

Parámetro `AmplifyOrigin`: dominio del dashboard permitido por CORS; se pasa en el mismo
`--parameter-overrides`, por ejemplo `AmplifyOrigin=https://main.xxxx.amplifyapp.com` (sin barra final).
`http://localhost:5173` y `http://localhost:3000` ya están permitidos.
