import json
from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from models.event import AforoEvent, CameraId, Direction, EventMethod

# Example payload from ARCHITECTURE.md section 4.
VALID_PAYLOAD = {
    "eventId": "0b6f1c9e-8a2e-4c55-9d0e-1f2a3b4c5d6e",
    "personId": None,
    "personName": None,
    "direction": "ENTRY",
    "cameraOutsideId": "camera-outside",
    "cameraInsideId": "camera-inside",
    "confidence": 0.91,
    "method": "FACE",
    "timestamp": "2026-09-30T14:32:00Z",
}

REQUIRED_FIELDS = [
    "eventId",
    "direction",
    "cameraOutsideId",
    "cameraInsideId",
    "confidence",
    "method",
    "timestamp",
]


def payload(**overrides):
    return {**VALID_PAYLOAD, **overrides}


def error_fields(exc_info):
    return {err["loc"][0] for err in exc_info.value.errors()}


# --- Accepted payloads ---


def test_accepts_contract_example():
    event = AforoEvent.model_validate(VALID_PAYLOAD)

    assert event.event_id == UUID("0b6f1c9e-8a2e-4c55-9d0e-1f2a3b4c5d6e")
    assert event.person_id is None
    assert event.direction is Direction.ENTRY
    assert event.camera_outside_id is CameraId.OUTSIDE
    assert event.camera_inside_id is CameraId.INSIDE
    assert event.method is EventMethod.FACE
    assert event.timestamp == datetime(2026, 9, 30, 14, 32, tzinfo=UTC)


def test_accepts_identified_person_exit():
    event = AforoEvent.model_validate(
        payload(
            personId="7d1e2f3a-4b5c-4d6e-8f90-a1b2c3d4e5f6",
            personName="Ana",
            direction="EXIT",
            method="BODY_ONLY",
        )
    )

    assert event.person_id == UUID("7d1e2f3a-4b5c-4d6e-8f90-a1b2c3d4e5f6")
    assert event.person_name == "Ana"
    assert event.direction is Direction.EXIT
    assert event.method is EventMethod.BODY_ONLY


def test_person_fields_are_optional():
    raw = {k: v for k, v in VALID_PAYLOAD.items() if k not in ("personId", "personName")}

    event = AforoEvent.model_validate(raw)

    assert event.person_id is None
    assert event.person_name is None


@pytest.mark.parametrize("confidence", [0, 1])
def test_accepts_confidence_bounds(confidence):
    assert AforoEvent.model_validate(payload(confidence=confidence)).confidence == confidence


def test_accepts_timestamp_with_offset():
    event = AforoEvent.model_validate(payload(timestamp="2026-09-30T09:32:00-05:00"))

    assert event.timestamp == datetime(2026, 9, 30, 14, 32, tzinfo=UTC)


def test_json_round_trip_keeps_contract_shape():
    event = AforoEvent.model_validate_json(json.dumps(VALID_PAYLOAD))

    assert json.loads(event.model_dump_json()) == VALID_PAYLOAD


# --- Rejected payloads ---


@pytest.mark.parametrize("field", REQUIRED_FIELDS)
def test_rejects_missing_required_field(field):
    raw = {k: v for k, v in VALID_PAYLOAD.items() if k != field}

    with pytest.raises(ValidationError) as exc_info:
        AforoEvent.model_validate(raw)

    assert error_fields(exc_info) == {field}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("direction", "IN"),
        ("direction", "entry"),
        ("method", "FACE_ONLY"),
        ("cameraOutsideId", "camera-low"),
        ("cameraInsideId", "camera-high"),
        # Cameras swapped between fields.
        ("cameraOutsideId", "camera-inside"),
        ("cameraInsideId", "camera-outside"),
    ],
)
def test_rejects_invalid_enum_value(field, value):
    with pytest.raises(ValidationError) as exc_info:
        AforoEvent.model_validate(payload(**{field: value}))

    assert error_fields(exc_info) == {field}


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_rejects_confidence_out_of_range(confidence):
    with pytest.raises(ValidationError) as exc_info:
        AforoEvent.model_validate(payload(confidence=confidence))

    assert error_fields(exc_info) == {"confidence"}


@pytest.mark.parametrize("timestamp", ["2026-09-30T14:32:00", "not-a-date"])
def test_rejects_timestamp_without_timezone_or_invalid(timestamp):
    with pytest.raises(ValidationError) as exc_info:
        AforoEvent.model_validate(payload(timestamp=timestamp))

    assert error_fields(exc_info) == {"timestamp"}


@pytest.mark.parametrize("field", ["eventId", "personId"])
def test_rejects_invalid_uuid(field):
    with pytest.raises(ValidationError) as exc_info:
        AforoEvent.model_validate(payload(**{field: "not-a-uuid"}))

    assert error_fields(exc_info) == {field}


def test_rejects_unknown_field():
    with pytest.raises(ValidationError) as exc_info:
        AforoEvent.model_validate(payload(cameraId="camera-outside"))

    assert error_fields(exc_info) == {"cameraId"}


def test_event_is_immutable():
    event = AforoEvent.model_validate(VALID_PAYLOAD)

    with pytest.raises(ValidationError):
        event.direction = Direction.EXIT
