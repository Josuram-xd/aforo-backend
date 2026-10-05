import base64
import json

import pytest

from db import dynamo_client
from handlers.post_events import SECRET_HEADER, handler
from tests.helpers import PERSON_ID, add_person, get_person

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


SECRET = "secreto-de-prueba-123"


@pytest.fixture(autouse=True)
def shared_secret(monkeypatch):
    monkeypatch.setenv("EVENTS_SHARED_SECRET", SECRET)


def post(payload):
    return handler({"headers": {SECRET_HEADER: SECRET}, "body": json.dumps(payload)}, None)


def body_of(response):
    return json.loads(response["body"])


def test_valid_entry_returns_201_and_increments_occupancy(table):
    response = post(VALID_PAYLOAD)

    assert response["statusCode"] == 201
    assert body_of(response) == {"eventId": VALID_PAYLOAD["eventId"]}
    assert dynamo_client.get_occupancy() == 1
    assert (
        len(
            table.query(
                KeyConditionExpression="PK = :pk",
                ExpressionAttributeValues={":pk": "EVENT#2026-09-30"},
            )["Items"]
        )
        == 1
    )


def test_valid_exit_decrements_occupancy(table):
    dynamo_client.change_occupancy(2)

    response = post({**VALID_PAYLOAD, "direction": "EXIT"})

    assert response["statusCode"] == 201
    assert dynamo_client.get_occupancy() == 1


def test_exit_with_empty_room_keeps_occupancy_at_zero(table):
    response = post({**VALID_PAYLOAD, "direction": "EXIT"})

    assert response["statusCode"] == 201
    assert dynamo_client.get_occupancy() == 0


def test_event_with_person_updates_person_status(table):
    add_person(table, status="OUT")

    post({**VALID_PAYLOAD, "personId": PERSON_ID, "personName": "Ana"})

    assert get_person(table)["status"] == "IN"


def test_base64_body_is_decoded(table):
    encoded = base64.b64encode(json.dumps(VALID_PAYLOAD).encode()).decode()

    response = handler(
        {"headers": {SECRET_HEADER: SECRET}, "body": encoded, "isBase64Encoded": True}, None
    )

    assert response["statusCode"] == 201


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"direction": "SIDEWAYS"}, "direction"),
        ({"confidence": 1.5}, "confidence"),
        ({"timestamp": "2026-09-30T14:32:00"}, "timestamp"),
        ({"eventId": "not-a-uuid"}, "eventId"),
        ({"cameraOutsideId": "camera-inside"}, "cameraOutsideId"),
        ({"unexpected": 1}, "unexpected"),
    ],
)
def test_invalid_event_returns_400_and_writes_nothing(table, overrides, field):
    response = post({**VALID_PAYLOAD, **overrides})

    assert response["statusCode"] == 400
    assert field in body_of(response)["invalidFields"]
    assert table.scan()["Items"] == []


def test_missing_field_returns_400(table):
    payload = {k: v for k, v in VALID_PAYLOAD.items() if k != "method"}

    response = post(payload)

    assert response["statusCode"] == 400
    assert body_of(response)["invalidFields"] == ["method"]


@pytest.mark.parametrize("event", [{}, {"body": None}, {"body": "{not json"}, {"body": "[]"}])
def test_unusable_body_returns_400(table, event):
    response = handler({"headers": {SECRET_HEADER: SECRET}, **event}, None)

    assert response["statusCode"] == 400
    assert table.scan()["Items"] == []


def test_duplicate_event_does_not_change_occupancy(table):
    first = post(VALID_PAYLOAD)
    second = post(VALID_PAYLOAD)

    assert first["statusCode"] == 201
    assert second["statusCode"] == 200
    assert body_of(second) == {"eventId": VALID_PAYLOAD["eventId"], "duplicate": True}
    assert dynamo_client.get_occupancy() == 1


def test_duplicate_event_does_not_overwrite_person_status(table):
    add_person(table, status="OUT")
    entry = {**VALID_PAYLOAD, "personId": PERSON_ID}
    post(entry)
    # Newer exit, then the late retry of the original entry.
    post(
        {
            **entry,
            "eventId": "11111111-1111-4111-8111-111111111111",
            "direction": "EXIT",
            "timestamp": "2026-09-30T15:00:00Z",
        }
    )

    post(entry)

    assert get_person(table)["status"] == "OUT"
    assert dynamo_client.get_occupancy() == 0


@pytest.mark.parametrize(
    "headers",
    [None, {}, {SECRET_HEADER: ""}, {SECRET_HEADER: "otro-secreto"}, {SECRET_HEADER: SECRET + "x"}],
)
def test_missing_or_wrong_secret_returns_401_and_writes_nothing(table, headers):
    response = handler({"headers": headers, "body": json.dumps(VALID_PAYLOAD)}, None)

    assert response["statusCode"] == 401
    assert table.scan()["Items"] == []
    assert dynamo_client.get_occupancy() == 0


def test_secret_is_checked_before_the_body(table):
    response = handler({"headers": {}, "body": "{not json"}, None)

    assert response["statusCode"] == 401


def test_unconfigured_secret_fails_closed(table, monkeypatch):
    monkeypatch.delenv("EVENTS_SHARED_SECRET")

    # Even an empty header must not match an empty (missing) secret.
    response = handler({"headers": {SECRET_HEADER: ""}, "body": json.dumps(VALID_PAYLOAD)}, None)

    assert response["statusCode"] == 500
    assert table.scan()["Items"] == []
