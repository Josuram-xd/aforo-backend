# PRD — aforo-backend

**Repositorio:** `aforo-backend`
**Última actualización:** 26 de septiembre de 2026

## 1. Problema

`aforo-vision` (el pipeline local de visión) produce eventos de entrada/salida resueltos, pero necesita un lugar en la nube donde guardarlos y desde donde `aforo-frontend` (el dashboard) pueda consultarlos en tiempo real durante la prueba piloto.

`aforo-backend` es esa pieza intermedia: recibe eventos, los guarda, y expone los datos que el dashboard necesita mostrar.

## 2. Objetivo

1. Recibir eventos resueltos desde `aforo-vision` (JSON, sin video) y guardarlos.
2. Calcular y exponer el aforo actual del salón (personas dentro = entradas - salidas).
3. Exponer el historial de eventos para el día del piloto.
4. Exponer la lista de personas enroladas (roster del curso) y su estado.
5. Servir estos datos al dashboard (`aforo-frontend`) de forma simple y rápida.

## 3. No-objetivos

- No procesa video ni imágenes — solo recibe JSON ya resuelto por `aforo-vision`.
- No hace reconocimiento facial ni tracking — eso vive en `aforo-vision`.
- No guarda usuarios ni contraseñas propias — el login lo maneja Amazon Cognito (ver ADR-005 en `ARCHITECTURE.md`).
- No necesita alta disponibilidad ni escalar a múltiples salones/cámaras — es un solo curso, un solo día.
- No usa colas de mensajería (Kafka/MQTT) ni contenedores — un solo productor de eventos de baja frecuencia no las justifica (ver ADR en `ARCHITECTURE.md`).

## 4. Usuarios

- `aforo-vision`, como cliente que escribe eventos (`POST /events`).
- `aforo-frontend`, como cliente que lee datos para mostrarlos (`GET /aforo`, `GET /events`, `GET /people`).
- Josuram, para revisar logs y depurar durante el piloto.
- Usuarios con login (grupo `viewer`: ven el dashboard y las cámaras; grupo `dev`: además ven el video anotado del análisis).

## 5. Requisitos funcionales

| Endpoint | Método | Descripción | Consumido por |
|---|---|---|---|
| `/events` | `POST` | Recibe un evento resuelto (entrada/salida) | `aforo-vision` |
| `/events` | `GET` | Lista de eventos, con filtro opcional `from`/`to` | `aforo-frontend` |
| `/aforo` | `GET` | Aforo actual (personas dentro en este momento) | `aforo-frontend` |
| `/people` | `GET` | Lista de personas enroladas y su estado (dentro/fuera) | `aforo-frontend` |

Las rutas `GET` exigen un usuario con sesión iniciada (token de Cognito de los grupos `viewer` o `dev`). `POST /events` exige el secreto compartido de `aforo-vision`.

## 6. Requisitos no funcionales

- Debe funcionar dentro del nivel gratuito de AWS (créditos de cuenta nueva + niveles "Always Free" de Lambda/DynamoDB).
- Latencia baja para que el dashboard se sienta "en vivo" (polling corto o, si el tiempo alcanza, WebSocket/SSE — no es un requisito duro para el piloto).
- Sin servidores que mantener corriendo 24/7 — arquitectura serverless (ver `ARCHITECTURE.md`).
- Debe poder desplegarse y probarse antes de fin de septiembre de 2026.

## 7. Restricciones

- Python para el backend.
- Debe usar la cuenta gratuita/nueva de AWS del usuario.
- Presupuesto total del proyecto: ~500.000 COP (compartido con hardware de cámaras) — el backend en sí debe mantenerse dentro del nivel gratuito de AWS, sin costo adicional.

## 8. Métricas de éxito del piloto

- Cada evento enviado por `aforo-vision` aparece en `GET /events` en menos de un par de segundos.
- El aforo mostrado en `GET /aforo` siempre coincide con (entradas - salidas) reales del día.
- Cero eventos perdidos durante la sesión de prueba.
