# AGENTS.md — aforo-backend

Este archivo le dice a los asistentes de IA cómo comportarse dentro de este repositorio.

## Qué es este repositorio

`aforo-backend` es la API en la nube del piloto de aforo. Recibe eventos resueltos desde `aforo-vision` (`POST /events`), los guarda en DynamoDB (definida en `aforo-db`), y expone datos para el dashboard `aforo-frontend`. **No** contiene código de visión por computador ni maneja video — eso vive en `aforo-vision`.

Antes de proponer cambios, lee `PRD.md` y `ARCHITECTURE.md` (en inglés).

> **Versión 2 en curso (oct 2026):** el API de AWS se retira; los datos, el login y la seguridad pasan a Supabase (`ARCHITECTURE.md` sección 9, `aforo-db` sección 7). En v2 este repo contiene las **Edge Functions** de Supabase (`supabase/functions/`). Las reglas marcadas **(v2)** aplican a ese trabajo; el resto aplica al API v1 mientras siga desplegado.

## Reglas de git (obligatorias, sin excepciones)

1. **Ninguna IA puede hacer commit ni push.** Ningún asistente (Claude Code, Cursor, Copilot, Codex, Gemini, etc.) ejecuta `git commit`, `git push`, `git merge`, `git rebase`, `git tag` ni `git reset`, ni crea o fusiona PRs, ni por terminal ni por herramientas MCP/API de GitHub. El agente deja los cambios en el árbol de trabajo y, si ayuda, **propone** el mensaje de commit (formato de `TASKS.md`); el commit y el push los hace siempre una persona.
2. **Nadie puede tener `Co-Authored-By` de una IA.** Ningún commit ni PR puede incluir líneas `Co-Authored-By: Claude ...` (ni de ninguna otra IA), `noreply@anthropic.com` ni "Generated with Claude Code". Esto aplica también a las personas: si el mensaje propuesto trae esa línea, se borra antes de commitear.
3. **Cómo se hace cumplir:**
   - `.githooks/commit-msg` rechaza localmente esos mensajes. Actívalo una vez por clon: `git config core.hooksPath .githooks`.
   - `.github/workflows/no-ai-coauthor.yml` falla en GitHub si algún commit del historial los tiene.
   - `.claude/settings.json` desactiva la coautoría automática de Claude Code y le bloquea `git commit`/`git push`.
   No desactives ni modifiques estos tres archivos sin que el usuario lo pida explícitamente.

## Reglas para el agente

1. **No agregues Kafka, MQTT, ni ningún broker de mensajería.** Ya se decidió explícitamente (ver ADR-002 en `ARCHITECTURE.md`) que este backend no los necesita — un solo productor de eventos de baja frecuencia no lo justifica. Si el agente cree que hace falta, debe preguntar primero.
2. **No agregues Docker ni contenedores.** La arquitectura es serverless (API Gateway + Lambda). No propongas mover esto a ECS/Fargate/EC2 sin que el usuario lo pida explícitamente. **(v2)** Lo nuevo va como Edge Functions de Supabase, no como Lambdas nuevas.
3. **Mantén el contrato de evento sincronizado.** El esquema del evento JSON y los enums (`Direction`, `EventMethod`, `CameraId`) están definidos en `ARCHITECTURE.md` de este repo. Si cambias algo ahí, dilo explícitamente: `aforo-vision` (quien produce eventos) y `aforo-frontend` (quien los consume) también deben actualizarse. No cambies el contrato de forma aislada.
4. **No proceses video ni imágenes aquí.** Si una tarea pide algo relacionado con visión por computador, redirige esa lógica a `aforo-vision` — este repo solo recibe JSON ya resuelto.
5. **Prioriza el nivel gratuito de AWS.** Cualquier recurso nuevo (Lambda, DynamoDB, API Gateway, Amplify) debe mantenerse dentro de los niveles "Always Free" o del crédito de cuenta nueva. Si una sugerencia va a generar costo, dilo de inmediato y de forma clara — no lo menciones solo al final de una propuesta grande. Recuerda: el presupuesto total del proyecto es de ~500.000 COP, y ya está mayormente asignado a las cámaras, no a la nube. **(v2)** Lo mismo con Supabase: plan Free (cuota de invocaciones de Edge Functions incluida).
6. **(v2) La autenticación de usuarios es Supabase Auth** (correo, Google), con roles `admin`, `teacher` y `viewer` en la base de datos (`aforo-db`). Cognito (ADR-005) queda descartado. Cada Edge Function valida el JWT y el rol del usuario por sí misma; la `service_role` key solo existe como secreto de la función, nunca en el frontend ni en git. `aforo-vision` se autentica con su llave de dispositivo, no con una cuenta de usuario.
7. **Verifica versiones antes de fijar una dependencia.** Antes de agregar algo a `requirements.txt`, confirma que soporta Python 3.14 y que es la versión estable más reciente.
8. **Textos para humanos (mensajes de error visibles, documentación) van en español**; nombres de variables, funciones, clases, commits y comentarios de código van en inglés.

## Herramientas que el agente puede usar libremente

- Lectura/escritura de archivos dentro de este repositorio.
- Ejecución de tests locales.
- Búsqueda web para verificar versiones de AWS SDKs, runtimes de Lambda, o precios/límites del nivel gratuito.

## Herramientas que requieren confirmación explícita del usuario

- Cualquier despliegue real a AWS (`sam deploy`, `terraform apply`, o equivalente) — el usuario debe confirmar antes de crear recursos en su cuenta.
- Crear o modificar recursos de AWS fuera de los definidos en `template.yaml`.
- Cambios al esquema del evento JSON o a los enums compartidos, sin avisar explícitamente que `aforo-vision` y `aforo-frontend` también deben actualizarse.
