# AGENTS.md — aforo-backend

Este archivo le dice a los asistentes de IA cómo comportarse dentro de este repositorio.

## Qué es este repositorio

`aforo-backend` es el backend **100 % Python** del sistema de aforo: una sola Lambda de AWS (HTTP API) que consulta Supabase y cubre el control de entrada y salida de los estudiantes de un curso. Rutas: `/health`, `/courses/{id}/roster`, `/sessions/{id}/report`, `/export-events`, `/invite-user`. **No** contiene código de visión por computador ni maneja video — eso vive en `aforo-vision`.

Antes de proponer cambios, lee `README.md`, `PRD.md` y `ARCHITECTURE.md` (en inglés; ADR-007 explica el cambio de Edge Functions a Python). No debe haber TypeScript, Deno ni Edge Functions en este repo.

## Reglas de git (obligatorias, sin excepciones)

1. **Una rama por task.** Los asistentes de IA pueden hacer commit y push, pero **solo en ramas de trabajo**, nunca en `main`. Nombre de la rama: `task-<n>-<descripcion-corta>` (ej. `task-7-supabase-schema`). Si la task depende de otra que aún no está en `main`, la rama sale de la rama de esa task (PRs encadenados).
2. **Un commit por subtarea**, con el mensaje exacto de `TASKS.md` y el sufijo `[x.y]`; en ese mismo commit se marca `[x]` en `TASKS.md`.
3. **Prohibido para la IA:** `git merge`, `git rebase`, `git reset --hard`, `git tag`, `push --force` y push a `main`; tampoco fusionar PRs. Puede **abrir** el PR de la rama hacia `main` (o hacia la rama de la que depende); la revisión y el merge los hace siempre una persona.
4. **Nadie puede tener `Co-Authored-By` de una IA.** Ningún commit ni PR puede incluir líneas `Co-Authored-By: Claude ...` (ni de ninguna otra IA), `noreply@anthropic.com` ni "Generated with Claude Code". El autor es el usuario configurado en git.
5. **Cómo se hace cumplir:**
   - `.githooks/commit-msg` rechaza localmente esos mensajes. Actívalo una vez por clon: `git config core.hooksPath .githooks`. No se usa `--no-verify`.
   - `.github/workflows/no-ai-coauthor.yml` falla en GitHub si algún commit del historial los tiene.
   - `.claude/settings.json` desactiva la coautoría automática de Claude Code y bloquea merge, rebase, force push y push a `main`.
   No desactives ni modifiques estos tres archivos sin que el usuario lo pida explícitamente.

## Reglas para el agente

1. **No agregues Kafka, MQTT, ni ningún broker de mensajería.** Ya se decidió explícitamente (ver ADR-002 en `ARCHITECTURE.md`) que este backend no los necesita — un solo productor de eventos de baja frecuencia no lo justifica. Si el agente cree que hace falta, debe preguntar primero.
2. **No agregues Docker ni contenedores.** La arquitectura es serverless (API Gateway + Lambda). No propongas mover esto a ECS/Fargate/EC2 sin que el usuario lo pida explícitamente. Todo el backend es Python en una sola Lambda; no agregues Edge Functions ni código TypeScript.
3. **Mantén el contrato de evento y de las rutas sincronizado.** El esquema del evento JSON y los enums (`Direction`, `EventMethod`, `CameraId`) están definidos en `ARCHITECTURE.md` de este repo. Si cambias algo ahí, dilo explícitamente: `aforo-vision` (quien produce eventos) y `aforo-frontend` (quien los consume) también deben actualizarse. No cambies el contrato de forma aislada.
4. **No proceses video ni imágenes aquí.** Si una tarea pide algo relacionado con visión por computador, redirige esa lógica a `aforo-vision` — este repo solo recibe JSON ya resuelto.
5. **Prioriza el nivel gratuito de AWS.** Cualquier recurso nuevo (Lambda, DynamoDB, API Gateway, Amplify) debe mantenerse dentro de los niveles "Always Free" o del crédito de cuenta nueva. Si una sugerencia va a generar costo, dilo de inmediato y de forma clara — no lo menciones solo al final de una propuesta grande. Recuerda: el presupuesto total del proyecto es de ~500.000 COP, y ya está mayormente asignado a las cámaras, no a la nube. Lo mismo con Supabase: plan Free.
6. **La autenticación de usuarios es Supabase Auth** (correo, Google), con roles `admin`, `teacher` y `viewer` en la base de datos (`aforo-db`). Cognito (ADR-005) queda descartado. El backend valida el token y el rol del usuario en cada ruta (salvo `/health`); la `service_role` key solo se usa en `/invite-user`, llega como parámetro `NoEcho` de SAM y nunca va al frontend ni a git. `aforo-vision` se autentica con su llave de dispositivo, no con una cuenta de usuario.
7. **Verifica versiones antes de fijar una dependencia.** El runtime es Python 3.13 y el código usa solo la biblioteca estándar: no agregues dependencias de terceros al Lambda salvo que sea inevitable (y confirma antes que soportan 3.13 y son la versión estable más reciente).
8. **Textos para humanos (mensajes de error visibles, documentación) van en español**; nombres de variables, funciones, clases, commits y comentarios de código van en inglés.

## Herramientas que el agente puede usar libremente

- Lectura/escritura de archivos dentro de este repositorio.
- Ejecución de tests locales.
- Búsqueda web para verificar versiones de AWS SDKs, runtimes de Lambda, o precios/límites del nivel gratuito.

## Herramientas que requieren confirmación explícita del usuario

- Cualquier despliegue real a AWS (`sam deploy`, `terraform apply`, o equivalente) — el usuario debe confirmar antes de crear recursos en su cuenta.
- Crear o modificar recursos de AWS fuera de los definidos en `template.yaml`.
- Cambios al esquema del evento JSON o a los enums compartidos, sin avisar explícitamente que `aforo-vision` y `aforo-frontend` también deben actualizarse.
