# Architecture — aforo-backend

**Repository:** `aforo-backend`
**Last updated:** November 19, 2026
**Scope:** entry/exit control of the students of one course (live test course: code `TEST`) and classroom occupancy.

> **Version 3 (current): Python on Lambda (ADR-007).** The backend is one Python Lambda behind an API Gateway
> HTTP API that reads Supabase over REST. Sections 1, 2, 5, 6 and 7 describe it. Sections 3 (ADR-001 to
> ADR-006) and 9 are kept as history: the v1 DynamoDB Lambdas and the Supabase Edge Functions (Deno/TypeScript)
> were removed from this repo.

## 1. Purpose

`aforo-backend` is the server-side layer that does not fit in SQL or in the browser: the ordered course roster, the entry/exit report of a class session, CSV export and user invitations. Events are still written by `aforo-vision` straight into Supabase (`rpc/ingest_event`); this repo only reads them (and uses the service-role key for invitations).

It contains **no** computer-vision code and **no** video handling. It is Python only (zero TypeScript).

## 2. High-level architecture

```
┌────────────────┐  HTTPS + Supabase access token  ┌───────────────────┐   REST (urllib)   ┌──────────────────┐
│ aforo-frontend │ ───────────────────────────────▶│ API Gateway (HTTP)│ ─────────────────▶│ Supabase          │
│ (AWS Amplify)  │ ◀───────────────────────────────│  └─ Lambda app.py │ ◀─────────────────│  Auth + PostgREST │
└────────────────┘                                  └───────────────────┘   user token (RLS) │  (aforo-db)       │
                                                                                            └──────────────────┘
```

- **One Lambda** (`src/app.py`, Python 3.13, stdlib only) receives every HTTP API v2 event, answers CORS, routes by method and path, authenticates and calls the route function.
- **Auth**: the bearer token is validated with `GET /auth/v1/user`; roles are read from `user_roles` with the same token, so RLS applies. Only `POST /invite-user` uses the service-role key.
- **Data structures** (`src/structures/`): own implementations of a singly and doubly linked list, queue, stack and binary search tree, used by the roster and session report routes (see README).

## 3. Architecture Decision Records

### ADR-001: Serverless (API Gateway + Lambda), not a container or EC2
**Decision**: The backend is a set of Lambda functions behind API Gateway, not a Docker container, not an always-on EC2 instance.
**Why**: this pilot has exactly one event source (`aforo-vision`), producing events at low, sporadic frequency (a person walking through a door), for a single day. There is no workload here that benefits from a persistent server, and a serverless design costs nothing when idle — which matters heavily given the ~500,000 COP total project budget. This mirrors the sibling cuy-monitoring project's reasoning in reverse: that project legitimately uses Kafka/Docker/EC2 because it has 3 independent, continuous producers (camera, audio, Arduino); this project does not have that shape.

### ADR-002: No Kafka, no MQTT, no message broker
**Decision**: `aforo-vision` calls `POST /events` directly over HTTPS. No message queue sits in between.
**Why**: a message broker earns its complexity with multiple producers/consumers or a need for buffering under load. Here there is one producer, one write path, and low event volume — a direct HTTP call to API Gateway is simpler, cheaper, and easier to debug during a one-day pilot. `aforo-vision`'s own local FIFO retry queue (see `aforo-vision/ARCHITECTURE.md`) already covers the one real resilience need: surviving a brief network drop.

### ADR-003: DynamoDB, not a relational database
**Decision**: Data is stored in DynamoDB (defined in `aforo-db`), not PostgreSQL/MySQL.
**Why**: DynamoDB has a permanent "Always Free" tier independent of AWS's time-limited signup credit, fits the simple access patterns here (append events, read by time range, read current state), and requires no server to manage or pay for when idle.

### ADR-004: 4 separate repositories, `aforo-vision` split out from the backend
**Decision**: The local ML pipeline lives in its own repository (`aforo-vision`), fully separate from this cloud API repository (`aforo-backend`).
**Why**: they have different runtimes (local laptop process vs. cloud Lambda), different dependency footprints (heavy CV/ML libraries vs. a thin API layer), and different deployment lifecycles (one is "run once during the pilot," the other is "deployed to AWS ahead of time"). Keeping them separate keeps each repo's `AGENTS.md`/dependencies focused and avoids shipping ML dependencies into the Lambda deployment package.

### ADR-005: User login with Amazon Cognito (groups `viewer` and `dev`) — superseded by ADR-006 (v2), never deployed
**Decision**: Users sign in through an Amazon Cognito User Pool defined in this repo's `template.yaml`. Two groups: `viewer` (dashboard + plain camera view) and `dev` (everything `viewer` has, plus the annotated "how the pipeline is analyzing" stream). The HTTP API uses a JWT authorizer on every `GET` route; `POST /events` keeps the shared-secret header (task 8.1) because `aforo-vision` is a machine client, not a user. Accounts are created by an admin script (no public self sign-up).
**Why**: Cognito is managed (no password storage or hashing code of our own), lives in the same AWS account, issues standard JWTs that API Gateway validates natively and that `aforo-vision` can also validate locally for its LAN stream server, and its free tier covers a pilot's handful of users (verify the current Cognito free-tier limits before deploying, per rule 5 of `AGENTS.md`). User data does not go into DynamoDB, so `aforo-db` is unaffected.
**Video is not served by this backend**: camera streams stay on the laptop's local network (served by `aforo-vision`, see its ADR-006); this API only authenticates users.

## 4. Shared event contract

This is the canonical definition — `aforo-vision` (producer) and `aforo-frontend` (consumer) must stay in sync with it.

```json
{
  "eventId": "uuid",
  "personId": "uuid | null",
  "personName": "string | null",
  "direction": "ENTRY | EXIT",
  "cameraOutsideId": "camera-outside",
  "cameraInsideId": "camera-inside",
  "confidence": 0.91,
  "method": "FACE | BODY_ONLY",
  "timestamp": "2026-09-30T14:32:00Z"
}
```

**Shared enums** (must match across all repos):
- `Direction`: `ENTRY | EXIT`
- `EventMethod`: `FACE | BODY_ONLY`
- `CameraId`: `camera-outside | camera-inside` (renamed from the earlier `camera-low`/`camera-high` scheme now that cameras are defined by checkpoint position, not height)

## 5. REST API

| Route | Method | Roles | Response |
|---|---|---|---|
| `/health` | `GET` | public | `{"status": "ok"}` |
| `/courses/{courseId}/roster?q=` | `GET` | admin, teacher, viewer | `{courseId, structure: "binary_search_tree", height, size, students[]}` sorted by name; `q` = name prefix |
| `/sessions/{sessionId}/report?cursor=&dir=&limit=` | `GET` | admin, teacher, viewer | `{session, arrivalOrder, insideNow, anomalies, lastEntries, peak, timeline}` |
| `/export-events` | `GET`/`POST` | admin, teacher | CSV (`from`, `to`, `classroomId`) |
| `/invite-user` | `POST` | admin | `{userId, email, role}` |

Errors are JSON `{"error": "<Spanish message>"}`. CORS echoes the `Origin` only if it is in `AllowedOrigins`.

## 6. Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 (stdlib only at runtime) |
| Compute | AWS Lambda (arm64) |
| API | API Gateway HTTP API (payload v2), `ANY /{proxy+}` |
| Data / auth | Supabase (PostgREST + Auth), schema in `aforo-db` |
| IaC / deploy | AWS SAM, stack `aforo-backend-py` |
| Dev tools | pytest, ruff |

## 7. Repository structure

```
aforo-backend/
├── src/
│   ├── app.py  auth.py  http_utils.py
│   ├── routes/        # health, roster, session_report, export_events, invite_user
│   ├── services/      # supabase_client.py (urllib, injectable transport)
│   └── structures/    # singly_linked_list, queue, stack, doubly_linked_list, binary_search_tree
├── tests/
└── template.yaml · samconfig.toml
```

## 8. Cost notes

Serverless design targets AWS's permanent "Always Free" Lambda/DynamoDB tiers plus the signup credit (up to $200 for a new account, valid up to 6 months). At pilot-day volumes (one classroom, one day, a few dozen events), this backend should cost effectively $0.

## 9. Version 2 — Supabase replaces the AWS API (planned)

### 9.1 What changes

After the first project review: reads were public (anyone with the URL saw student names), there was no rate limit (the API could be abused to generate AWS cost) and there was no user registration. In v2:

```
┌──────────────────────┐  HTTPS: rpc/ingest_event, rpc/camera_heartbeat  ┌───────────────────────────────┐
│ aforo-vision          │ ──────────────────────────────────────────────▶│ Supabase                       │
│ (on-site box or VM)   │   apikey + X-Device-Key                        │  PostgreSQL (aforo-db schema)  │
└──────────────────────┘                                                 │  Auth (email, Google)          │
                                                                         │  Row Level Security            │
┌──────────────────────┐  supabase-js with the user's JWT (RLS)          │  Realtime                      │
│ aforo-frontend        │ ◀─────────────────────────────────────────────▶│  Edge Functions (this repo)    │
│ (AWS Amplify)         │   queries + Realtime subscriptions              └───────────────────────────────┘
└──────────────────────┘
```

- The Lambda handlers (`POST /events`, `GET /events`, `/aforo`, `/people`) are replaced by direct, RLS-protected access to Supabase and by two database RPCs (`ingest_event`, `camera_heartbeat`) defined in `aforo-db`.
- This repo keeps only **server-side logic that does not fit in SQL**, as Supabase Edge Functions (Deno/TypeScript): CSV export of events and admin user invitations.
- Until the switch, v1 stays online with throttling (task 12.2); after it, the SAM stack is deleted (task 12.3).

### 9.2 Event contract

Unchanged: the JSON event of section 4 is what `aforo-vision` sends inside `{"p_event": {...}}` to `ingest_event`. `personName` is accepted but ignored (the name comes from `students`).

| v1 | v2 |
|---|---|
| `POST /events` + `X-Aforo-Secret` | `POST /rest/v1/rpc/ingest_event` + `apikey` + `X-Device-Key` |
| `201` / `200 duplicate` | `200` with `{"eventId", "duplicate"}` |
| `400` invalid | `400` (PostgREST, `message` in Spanish) |
| `401` bad secret | `403` bad or missing device key |
| no rate limit | `429` above 120 requests/min per device key |
| `GET /health` | `rpc/camera_heartbeat` (also proves the keys work) |

### 9.3 ADR-006: Supabase instead of API Gateway + Lambda + Cognito
**Decision**: Supersedes ADR-001, ADR-003 and ADR-005 for v2. Data access goes through Supabase with RLS; custom server code lives in Edge Functions.
**Why**: the requirements added after the review (registration, Google login, per-role access, audit, live updates, ~13 relational tables) are built into Supabase; building them on AWS would need Cognito + RDS (RDS is not free) + custom authorization in every Lambda + a WebSocket API. Supabase's Free plan covers this project's volume at no cost.
**Trade-off**: the project is no longer AWS-only (Amplify still hosts the frontend). ADR-002 (no broker) still holds.

### 9.4 Edge Functions (removed)

`export-events` and `invite-user` were Supabase Edge Functions (Deno/TypeScript). They were ported to Python routes with the same contract (ADR-007).

### ADR-007: Backend moves from Supabase Edge Functions (Deno/TS) to Python on Lambda
**Decision**: Supersedes the Edge Function part of ADR-006. Server-side logic is a single Python Lambda behind an HTTP API, deployed with SAM as the new stack `aforo-backend-py` (the old `aforo-pilot-backend` stack is untouched). Scope: entry/exit of the students of one course. Supabase stays the database and identity provider.
**Why**: the project is graded on Python data-structure work and the team works in Python; the new endpoints (roster, session report) are naturally written with linked lists, queue, stack and a binary search tree. One language also removes the Deno toolchain. Lambda stays inside the AWS free tier at pilot volume.
**Trade-offs**: the per-user rate limit of the Edge Functions was not ported (API Gateway throttling caps total traffic instead); reads use the caller's token, so RLS remains the authorization layer, and the roster tree is not self-balancing (documented shortcut).
**Fix while porting**: if `invite-user` fails after creating the auth account, it deletes that account so the admin can retry instead of being stuck with a half-created viewer.
