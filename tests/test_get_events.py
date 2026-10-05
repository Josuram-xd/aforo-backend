import json
from datetime import UTC, datetime, timedelta

import pytest

from db import dynamo_client
from handlers.get_events import _COLOMBIA_TZ, handler
from tests.test_dynamo_client import make_event


def get(**params):
    return handler({"queryStringParameters": params or None}, None)


def ids(response):
    return [e["eventId"] for e in json.loads(response["body"])]


def test_empty_table_returns_empty_list(table):
    response = get()

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == []


def test_range_filters_and_orders_events(table):
    early = make_event(timestamp="2026-09-30T14:00:00Z")
    late = make_event(timestamp="2026-09-30T15:00:00Z")
    outside = make_event(timestamp="2026-09-30T16:00:00Z")
    for event in (late, outside, early):
        dynamo_client.put_event(event)

    response = get(**{"from": "2026-09-30T14:00:00Z", "to": "2026-09-30T15:00:00Z"})

    assert response["statusCode"] == 200
    assert ids(response) == [str(early.event_id), str(late.event_id)]


def test_returns_event_contract_fields(table):
    dynamo_client.put_event(make_event(timestamp="2026-09-30T14:00:00Z"))

    (item,) = json.loads(
        get(**{"from": "2026-09-30T00:00:00Z", "to": "2026-09-30T23:59:59Z"})["body"]
    )

    assert item["timestamp"] == "2026-09-30T14:00:00Z"
    assert item["direction"] == "ENTRY"
    assert item["confidence"] == 0.91
    assert "PK" not in item


def test_offset_with_plus_sign_decoded_as_space(table):
    event = make_event(timestamp="2026-09-30T14:00:00Z")
    dynamo_client.put_event(event)

    # "+00:00" arrives from API Gateway as " 00:00".
    response = get(**{"from": "2026-09-30T13:00:00 00:00", "to": "2026-09-30T15:00:00 00:00"})

    assert ids(response) == [str(event.event_id)]


def test_defaults_to_today_in_colombia(table):
    now = datetime.now(_COLOMBIA_TZ)
    today = make_event(timestamp=now.astimezone(UTC).isoformat())
    yesterday = make_event(timestamp=(now - timedelta(days=1)).astimezone(UTC).isoformat())
    dynamo_client.put_event(today)
    dynamo_client.put_event(yesterday)

    assert ids(get()) == [str(today.event_id)]


def test_only_from_runs_until_end_of_today(table):
    now = datetime.now(_COLOMBIA_TZ)
    recent = make_event(timestamp=now.astimezone(UTC).isoformat())
    dynamo_client.put_event(recent)

    response = get(**{"from": (now - timedelta(days=2)).astimezone(UTC).isoformat()})

    assert ids(response) == [str(recent.event_id)]


@pytest.mark.parametrize(
    "params",
    [
        {"from": "ayer"},
        {"to": "2026-09-30"},
        {"from": "2026-09-30T14:00:00"},
        {"from": "2026-01-01T00:00:00Z", "to": "2026-09-30T00:00:00Z"},
    ],
)
def test_invalid_params_return_400(table, params):
    response = get(**params)

    assert response["statusCode"] == 400
    assert json.loads(response["body"])["message"]
