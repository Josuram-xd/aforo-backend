# aforo-backend

Backend 100 % Python del sistema de aforo. Control de **entrada y salida de los estudiantes de un curso** (curso de prueba: código `TEST`) y ocupación del salón. Corre como **una sola Lambda de AWS** detrás de un API Gateway HTTP API y consulta Supabase (PostgreSQL + Auth) por REST con la biblioteca estándar (sin dependencias de terceros).

El frontend y `aforo-vision` siguen hablando con Supabase para el login y los datos en vivo; este repo agrega lo que necesita lógica de servidor: el roster ordenado, el reporte de una sesión, la exportación a CSV y la invitación de usuarios. Detalle en `ARCHITECTURE.md` (ADR-007), `PRD.md` y `AGENTS.md`.

## Rutas

Todas menos `/health` exigen `Authorization: Bearer <access token de Supabase>`. El token se valida con Supabase Auth y los datos se leen con ese mismo token, así que aplica RLS. Los errores son `{"error": "<mensaje en español>"}`.

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| `GET` | `/health` | público | `{"status": "ok"}` |
| `GET` | `/courses/{courseId}/roster?q=` | admin, teacher, viewer | Roster del curso ordenado por nombre (árbol binario de búsqueda); `q` filtra por prefijo del nombre |
| `GET` | `/sessions/{sessionId}/report?cursor=&dir=next\|prev&limit=10` | admin, teacher, viewer | Reporte de la sesión: orden de llegada, quién está dentro, anomalías, últimas entradas, pico y línea de tiempo paginada |
| `GET`/`POST` | `/export-events` | admin, teacher | CSV de eventos de un salón (`from`, `to`, `classroomId`; máximo 31 días). Registra `EXPORT` en la auditoría |
| `POST` | `/invite-user` | admin | Invita por correo con un rol inicial (`{"email", "role"}`). Usa la `service_role` key; responde `503` si no está configurada |

## Estructuras de datos

Implementaciones propias en `src/structures/` (sin `collections.deque` ni `heapq`).

| Estructura | Archivo | Endpoint que la usa | Qué hace | Complejidad |
|---|---|---|---|---|
| Lista enlazada simple | `src/structures/singly_linked_list.py` | `/sessions/{id}/report` (base de la cola) | Almacén con puntero a cabeza y cola | `append`, `prepend`, `remove_first`: O(1); recorrido O(n) |
| Cola (FIFO) | `src/structures/queue.py` | `/sessions/{id}/report` | Orden de llegada: cada estudiante entra a la cola con su primera ENTRADA | `enqueue`, `dequeue`, `peek`: O(1) |
| Pila (LIFO) | `src/structures/stack.py` | `/sessions/{id}/report` | Una pila por estudiante (push en ENTRADA, pop en SALIDA) para saber quién está dentro y detectar anomalías; una pila global con las últimas 5 entradas | `push`, `pop`, `peek`: O(1) |
| Lista doblemente enlazada | `src/structures/doubly_linked_list.py` | `/sessions/{id}/report` | Línea de tiempo de eventos; navega hacia adelante y atrás desde un cursor (id de evento) | `append`, `prepend`, `remove(nodo)`: O(1); `window`: O(n) para ubicar el cursor + O(limit) |
| Árbol binario de búsqueda | `src/structures/binary_search_tree.py` | `/courses/{id}/roster` | Roster ordenado por nombre (sin mayúsculas ni tildes) y búsqueda por prefijo | `insert`/`search`: O(h); `in_order`: O(n); `prefix_range`: O(h + k) |

Límite conocido del árbol: no se auto-balancea; con datos ya ordenados la altura llega a O(n). Para un curso (decenas de estudiantes, leídos en orden arbitrario) es suficiente. La respuesta del roster incluye `height` y `size` para verlo.

## Estructura del repo

```
aforo-backend/
├── src/
│   ├── app.py                  # entrada de la Lambda: handler(event, context), router y CORS
│   ├── auth.py                 # valida el token y los roles contra Supabase
│   ├── http_utils.py           # Request/Response, errores JSON, CORS
│   ├── routes/                 # health, roster, session_report, export_events, invite_user
│   ├── services/supabase_client.py   # cliente REST/Auth con urllib (transporte inyectable)
│   ├── structures/             # estructuras de datos propias
│   └── requirements.txt        # vacío: solo biblioteca estándar
├── tests/                      # pytest, sin red (transporte falso)
├── template.yaml · samconfig.toml    # AWS SAM, stack aforo-backend-py
└── PRD.md · ARCHITECTURE.md · AGENTS.md · TASKS.md
```

## Desarrollo

Requiere Python 3.13 (runtime de Lambda). Desde la raíz del repo:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install pytest ruff           # o: pip install --group dev
python -m pytest
ruff check .
```

## Despliegue

No se despliega solo: el usuario debe confirmar cada `sam deploy`.

```bash
sam validate --lint
sam build
sam deploy --parameter-overrides \
  SupabaseUrl=https://<ref>.supabase.co \
  SupabasePublishableKey=<publishable key> \
  SupabaseServiceRoleKey=<service role key, opcional> \
  AllowedOrigins="https://main.d2o7lrrjmkkq29.amplifyapp.com,http://localhost:5173"
```

| Parámetro | Para qué |
|---|---|
| `SupabaseUrl` | URL del proyecto Supabase |
| `SupabasePublishableKey` | llave pública; RLS protege los datos |
| `SupabaseServiceRoleKey` | solo `POST /invite-user`; `NoEcho`, vacía = esa ruta responde 503. Nunca va a git ni al navegador |
| `AllowedOrigins` | orígenes del frontend permitidos por CORS (separados por coma) |
| `InviteRedirectTo` | opcional: URL fija del enlace de invitación (debe estar en Auth > Redirect URLs de Supabase) |

El stack se llama `aforo-backend-py`; el stack anterior `aforo-pilot-backend` (DynamoDB) no se toca. La URL base sale en el output `ApiUrl`.

## Ejemplos

```bash
API_URL="<ApiUrl>"
TOKEN="<access token de Supabase>"
curl "$API_URL/health"
curl -H "Authorization: Bearer $TOKEN" "$API_URL/courses/<courseId>/roster?q=an"
curl -H "Authorization: Bearer $TOKEN" "$API_URL/sessions/<sessionId>/report?limit=10"
curl -H "Authorization: Bearer $TOKEN" \
  "$API_URL/export-events?from=2026-11-19T00:00:00Z&to=2026-11-20T00:00:00Z&classroomId=<uuid>"
```
