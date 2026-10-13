# Edge Functions de Aforo

Funciones de Supabase (Deno/TypeScript) del proyecto `uezrriyikquncmcgwwzo`. Ambas exigen JWT (`verify_jwt = true`) y además validan el rol por sí mismas.

| Función | Rol | Descripción |
|---|---|---|
| `export-events` | `teacher`, `admin` | CSV de eventos de un salón en un rango de fechas. Registra `EXPORT` en `audit_log` (RPC `log_access`). |
| `invite-user` | `admin` | Invita por correo y asigna el rol inicial. Usa `SUPABASE_SERVICE_ROLE_KEY` solo dentro de la función. |

Código compartido: `_shared/` (`cors.ts`, `auth.ts`, `csv.ts`). CORS solo permite `https://main.d2o7lrrjmkkq29.amplifyapp.com` y `http://localhost:5173`.

## Contrato para el frontend

Usar el JWT de la sesión del usuario (`Authorization: Bearer <access_token>`); con `supabase-js`, `supabase.functions.invoke(...)` lo agrega solo.

### `export-events`

`GET /functions/v1/export-events?from=<ISO>&to=<ISO>&classroomId=<uuid>` (también acepta `POST` con JSON `{from,to,classroomId}`).

- `from`/`to`: ISO 8601 con zona horaria (ej. `2026-10-12T00:00:00-05:00`), `to > from`, rango máximo 31 días.
- 200: `text/csv; charset=utf-8` con `Content-Disposition: attachment`. Columnas: `estudiante,direccion,metodo,confianza,fecha_hora_bogota` (hora de America/Bogota). Celdas que empiezan con `= + - @` se prefijan con `'`.
- 400 parámetros inválidos, 401 sin token o token inválido, 403 rol insuficiente (`viewer`, cuenta inactiva), 500 error interno. Errores: `{"error": "mensaje en español"}`.

### `invite-user`

`POST /functions/v1/invite-user` con JSON `{"email": "persona@dominio.com", "role": "admin|teacher|viewer"}`.

- 200: `{"userId", "email", "role"}`. 400 entrada inválida, 401, 403 (no admin), 409 el correo ya existe, 500 error genérico.

## Desplegar

Con la CLI de Supabase (una vez: `supabase login` y `supabase link --project-ref uezrriyikquncmcgwwzo`), desde la raíz del repo:

```bash
supabase functions deploy export-events --project-ref uezrriyikquncmcgwwzo
supabase functions deploy invite-user --project-ref uezrriyikquncmcgwwzo
```

`verify_jwt` queda activo por defecto; no uses `--no-verify-jwt`.

## Secretos

`SUPABASE_URL`, `SUPABASE_ANON_KEY` y `SUPABASE_SERVICE_ROLE_KEY` ya existen en el entorno de las funciones; no hace falta configurarlos y nunca van en git ni en el frontend. Opcional, para que el enlace del correo de invitación apunte al frontend:

```bash
supabase secrets set INVITE_REDIRECT_TO=https://main.d2o7lrrjmkkq29.amplifyapp.com --project-ref uezrriyikquncmcgwwzo
supabase secrets list --project-ref uezrriyikquncmcgwwzo
```

Esa URL debe estar en Authentication > URL Configuration > Redirect URLs.

## Logs

Dashboard de Supabase > Edge Functions > (función) > Logs / Invocations. También en Logs > Edge Functions (`function_edge_logs`). Las funciones solo registran etiquetas cortas (nunca tokens, llaves ni correos).

## Pruebas

Requiere [Deno](https://deno.com) (o `npx deno`):

```bash
cd supabase/functions
deno test --allow-env
```

Humo contra producción (sin token debe dar 401):

```bash
curl -i https://uezrriyikquncmcgwwzo.supabase.co/functions/v1/export-events
```
