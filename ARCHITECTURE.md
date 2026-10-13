# Architecture — aforo-backend

**Repository:** `aforo-backend`
**Last updated:** October 8, 2026
**Scope:** One-day pilot, single classroom door.

> **Version 2 planned (section 9).** Sections 1-8 describe the AWS API deployed today (v1). In v2, data,
> login and authorization move to Supabase (`aforo-db` section 7) and this AWS API is retired.

## 1. Purpose

`aforo-backend` is the cloud API layer. It receives resolved events from `aforo-vision` (running locally on Josuram's laptop), persists them, computes the current occupancy, and serves everything `aforo-frontend` needs to render the live dashboard.

It contains **no** computer-vision code and **no** video handling — that all lives in `aforo-vision`. This repo is API-only.

## 2. High-level architecture

```
┌───────────────┐      HTTPS       ┌──────────────────┐
│  aforo-vision  │ ───────────────▶│   API Gateway     │
│ (laptop, local)│   POST /events   └────────┬──────────┘
└───────────────┘                            ▼
                                     ┌──────────────────┐
                                     │  Lambda (Python)  │
                                     │  - handlers per    │
                                     │    endpoint         │
                                     └────────┬──────────┘
                                              ▼
                                     ┌──────────────────┐
                                     │    DynamoDB        │
                                     │  (aforo-db repo)   │
                                     └────────▲──────────┘
                                              │
┌───────────────┐      HTTPS                 │
│ aforo-frontend │ ◀──────────────────────────┘
│ (AWS Amplify)  │   GET /events, /aforo, /people
└───────────────┘
```

- **API Gateway**: single HTTP API with 4 routes (`POST /events`, `GET /events`, `GET /aforo`, `GET /people`).
- **Lambda (Python)**: one function per route (or a single function with internal routing — implementation detail, either is fine at this scale).
- **DynamoDB**: single table, defined and provisioned in the sibling `aforo-db` repository (this repo only reads/writes to it via the AWS SDK; it does not define the table).

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

| Route | Method | Request | Response |
|---|---|---|---|
| `/events` | `POST` | Event JSON (above) | `201 Created` |
| `/events` | `GET` | Query params: `from`, `to` (ISO timestamps, optional) | List of events |
| `/aforo` | `GET` | — | `{ "currentOccupancy": number, "lastUpdated": timestamp }` |
| `/people` | `GET` | — | List of `{ personId, name, status: "IN" \| "OUT", lastEventAt }` |

**Auth**: every `GET` route requires `Authorization: Bearer <Cognito access token>` from a user in group `viewer` or `dev` (otherwise `401`). `POST /events` requires the shared-secret header instead. `GET /health` stays public.

## 6. Tech stack

| Layer | Choice | Version (verified Sept 2026) |
|---|---|---|
| Language | Python | 3.14.7 |
| Compute | AWS Lambda | Python 3.14 runtime |
| API | AWS API Gateway (HTTP API) | — |
| Database | AWS DynamoDB | — (see `aforo-db`) |
| IaC / deploy | AWS SAM or Terraform (implementation choice) | latest |

## 7. Repository structure

```
aforo-backend/
├── ARCHITECTURE.md
├── AGENTS.md
├── PRD.md
├── README.md
├── requirements.txt
├── template.yaml              # AWS SAM template (API Gateway + Lambda)
├── src/
│   ├── handlers/
│   │   ├── post_events.py
│   │   ├── get_events.py
│   │   ├── get_aforo.py
│   │   └── get_people.py
│   ├── models/
│   │   └── event.py           # shared enums + event schema (Pydantic)
│   └── db/
│       └── dynamo_client.py
└── tests/
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

### 9.4 Edge Functions

| Function | Who | What |
|---|---|---|
| `export-events` | `teacher`, `admin` | CSV of events in a date range for one classroom; logs `EXPORT` in `audit_log` |
| `invite-user` | `admin` | Invites a user by email with an initial role; the service-role key is only available inside the function |

Each function verifies the caller's JWT and role itself; secrets are set with `supabase secrets set` and never committed.
