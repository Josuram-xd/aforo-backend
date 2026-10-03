# Architecture — aforo-backend

**Repository:** `aforo-backend`
**Last updated:** September 26, 2026
**Scope:** One-day pilot, single classroom door.

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

### ADR-005: User login with Amazon Cognito (groups `viewer` and `dev`)
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
