# aforo-backend

API en la nube del piloto de aforo (API Gateway HTTP API + Lambda + DynamoDB). Recibe los eventos
de `aforo-vision`, mantiene el aforo actual y sirve los datos al dashboard `aforo-frontend`.
La tabla de DynamoDB vive en el repo `aforo-db`. Más detalle en `PRD.md` y `ARCHITECTURE.md`.

## URL base

```
<API_URL>
```

> Pendiente: se completa con el output `ApiUrl` después del primer `sam deploy` (task 7.3).
> `aforo-vision` y `aforo-frontend` necesitan este valor. Sin barra final.

## Endpoints

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

> Autenticación: por ahora las rutas están abiertas. El secreto compartido de `POST /events`
> (task 8.1) y el login con Cognito en las rutas `GET` (task 11) aún no están implementados.
> No conviene desplegar para uso real antes de esas tareas.

## Ejemplos con curl

```bash
API_URL="<API_URL>"

# Estado del API
curl "$API_URL/health"

# Registrar una entrada
curl -X POST "$API_URL/events" \
  -H "Content-Type: application/json" \
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

## Probar sin cámaras

`scripts/send_fake_events.py` manda eventos de prueba al API desplegado (solo biblioteca estándar):

```bash
python scripts/send_fake_events.py "$API_URL" --count 20 --interval 2
python scripts/send_fake_events.py "$API_URL" --person-id <uuid-del-roster> --person-name "Ana"
python scripts/send_fake_events.py "$API_URL" --dry-run
```

## Desarrollo

Requiere Python 3.14 (el runtime de Lambda). Desde la raíz del repo:

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r src/requirements.txt --group dev
python -m pytest                  # tests con moto, no tocan AWS
ruff check . && ruff format --check .
```

## Despliegue

Antes hay que desplegar la tabla desde `aforo-db` (este stack importa `AforoPilotTableName`).

```bash
sam validate --lint
sam build
sam deploy                        # muestra el changeset y pide confirmación
```

Parámetro `AmplifyOrigin`: dominio del dashboard permitido por CORS, por ejemplo
`sam deploy --parameter-overrides AmplifyOrigin=https://main.xxxx.amplifyapp.com` (sin barra final).
`http://localhost:5173` y `http://localhost:3000` ya están permitidos.
