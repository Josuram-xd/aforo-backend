"""POST /events: receives a resolved event from aforo-vision."""

import base64
import hmac
import json
import os
from typing import Any

from pydantic import ValidationError

from db import dynamo_client
from models.event import AforoEvent, Direction

# Header aforo-vision must send with the shared secret (HTTP API lowercases header names).
SECRET_HEADER = "x-aforo-secret"

_OCCUPANCY_DELTA = {Direction.ENTRY: 1, Direction.EXIT: -1}


def _response(status_code: int, body: dict[str, Any]) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _is_authorized(event: dict[str, Any], secret: str) -> bool:
    provided = (event.get("headers") or {}).get(SECRET_HEADER, "")
    return hmac.compare_digest(provided.encode(), secret.encode())


def _parse_body(event: dict[str, Any]) -> Any:
    body = event.get("body")
    if body is None:
        raise ValueError("El cuerpo de la petición está vacío.")
    if event.get("isBase64Encoded"):
        body = base64.b64decode(body)
    return json.loads(body)


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    secret = os.environ.get("EVENTS_SHARED_SECRET", "")
    if not secret:
        # Fail closed: never accept events when the deployment forgot to configure the secret.
        return _response(
            500, {"message": "El servidor no tiene configurado el secreto compartido."}
        )
    if not _is_authorized(event, secret):
        return _response(401, {"message": "Secreto compartido ausente o incorrecto."})

    try:
        aforo_event = AforoEvent.model_validate(_parse_body(event))
    except ValidationError as e:
        fields = sorted({".".join(str(part) for part in err["loc"]) for err in e.errors()})
        return _response(
            400, {"message": "El evento no es válido.", "invalidFields": [f for f in fields if f]}
        )
    except ValueError:  # includes json.JSONDecodeError and UnicodeDecodeError
        return _response(400, {"message": "El cuerpo debe ser un JSON válido."})

    if not dynamo_client.put_event(aforo_event):
        # Retry of an event already processed: acknowledge it without touching the counter.
        return _response(200, {"eventId": str(aforo_event.event_id), "duplicate": True})
    dynamo_client.change_occupancy(_OCCUPANCY_DELTA[aforo_event.direction])
    if aforo_event.person_id is not None:
        dynamo_client.update_person_status(
            aforo_event.person_id, aforo_event.direction, aforo_event.timestamp
        )

    return _response(201, {"eventId": str(aforo_event.event_id)})
