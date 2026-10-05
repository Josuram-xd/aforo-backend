from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import boto3
import pytest
from moto import mock_aws

from db import dynamo_client
from models.event import AforoEvent, Direction

TABLE_NAME = "AforoPilot"
PERSON_ID = "7d1f7a52-3c1e-4a53-8a0e-5b9d2c3e4f10"


@pytest.fixture
def table(monkeypatch):
    """Empty AforoPilot table (PK/SK strings) in moto; no real AWS is touched."""
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        resource = boto3.resource("dynamodb")
        resource.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        dynamo_client._table.cache_clear()
        yield resource.Table(TABLE_NAME)
        dynamo_client._table.cache_clear()


def make_event(timestamp="2026-09-30T14:32:00Z", direction="ENTRY", **overrides):
    return AforoEvent.model_validate(
        {
            "eventId": str(uuid4()),
            "personId": None,
            "personName": None,
            "direction": direction,
            "cameraOutsideId": "camera-outside",
            "cameraInsideId": "camera-inside",
            "confidence": 0.91,
            "method": "FACE",
            "timestamp": timestamp,
            **overrides,
        }
    )


def add_person(table, status="OUT"):
    table.put_item(Item={"PK": f"PERSON#{PERSON_ID}", "SK": "PROFILE", "status": status})


def get_person(table):
    return table.get_item(Key={"PK": f"PERSON#{PERSON_ID}", "SK": "PROFILE"})["Item"]


# --- put_event / query_events ---


def test_put_event_stores_item_in_utc_day_partition(table):
    event = make_event(timestamp="2026-09-30T14:32:00Z")

    dynamo_client.put_event(event)

    items = table.scan()["Items"]
    assert len(items) == 1
    assert items[0]["PK"] == "EVENT#2026-09-30"
    assert items[0]["SK"] == f"2026-09-30T14:32:00.000000Z#{event.event_id}"
    assert items[0]["eventId"] == str(event.event_id)


def test_put_event_normalizes_timezone_to_utc(table):
    # 21:30 in Colombia (UTC-5) is already the next day in UTC.
    colombia = timezone(timedelta(hours=-5))
    event = make_event(timestamp=datetime(2026, 9, 30, 21, 30, tzinfo=colombia).isoformat())

    dynamo_client.put_event(event)

    assert table.scan()["Items"][0]["PK"] == "EVENT#2026-10-01"


def test_query_events_returns_range_oldest_first_and_inclusive(table):
    early = make_event(timestamp="2026-09-30T14:00:00Z")
    middle = make_event(timestamp="2026-09-30T14:30:00Z")
    late = make_event(timestamp="2026-09-30T15:00:00Z")
    outside = make_event(timestamp="2026-09-30T16:00:00Z")
    for event in (late, outside, early, middle):
        dynamo_client.put_event(event)

    result = dynamo_client.query_events(
        datetime(2026, 9, 30, 14, 0, tzinfo=UTC), datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
    )

    assert [e.event_id for e in result] == [early.event_id, middle.event_id, late.event_id]


def test_query_events_spans_midnight_utc(table):
    before = make_event(timestamp="2026-09-30T23:50:00Z")
    after = make_event(timestamp="2026-10-01T00:10:00Z")
    dynamo_client.put_event(after)
    dynamo_client.put_event(before)

    result = dynamo_client.query_events(
        datetime(2026, 9, 30, 23, 0, tzinfo=UTC), datetime(2026, 10, 1, 1, 0, tzinfo=UTC)
    )

    assert [e.event_id for e in result] == [before.event_id, after.event_id]


def test_query_events_roundtrips_event_fields(table):
    event = make_event(personId=PERSON_ID, personName="Ana", method="FACE")
    dynamo_client.put_event(event)

    (result,) = dynamo_client.query_events(
        datetime(2026, 9, 30, 0, 0, tzinfo=UTC), datetime(2026, 9, 30, 23, 59, tzinfo=UTC)
    )

    assert result == event


def test_query_events_empty_and_inverted_range(table):
    start = datetime(2026, 9, 30, 14, 0, tzinfo=UTC)

    assert dynamo_client.query_events(start, start + timedelta(hours=1)) == []
    assert dynamo_client.query_events(start + timedelta(hours=1), start) == []


def test_query_events_rejects_naive_datetimes(table):
    with pytest.raises(ValueError, match="zona horaria"):
        dynamo_client.query_events(datetime(2026, 9, 30), datetime(2026, 10, 1, tzinfo=UTC))


def test_query_events_rejects_ranges_over_max_days(table):
    start = datetime(2026, 9, 1, tzinfo=UTC)

    with pytest.raises(ValueError, match="31"):
        dynamo_client.query_events(start, start + timedelta(days=31))


# --- update_person_status ---


def test_update_person_status_entry_sets_in(table):
    add_person(table, status="OUT")
    ts = datetime(2026, 9, 30, 14, 32, tzinfo=UTC)

    assert dynamo_client.update_person_status(PERSON_ID, Direction.ENTRY, ts) is True

    person = get_person(table)
    assert person["status"] == "IN"
    assert person["lastEventAt"] == "2026-09-30T14:32:00.000000Z"


def test_update_person_status_exit_sets_out(table):
    add_person(table, status="IN")

    dynamo_client.update_person_status(
        PERSON_ID, Direction.EXIT, datetime(2026, 9, 30, 15, 0, tzinfo=UTC)
    )

    assert get_person(table)["status"] == "OUT"


def test_update_person_status_ignores_older_or_equal_timestamp(table):
    add_person(table, status="OUT")
    ts = datetime(2026, 9, 30, 14, 32, tzinfo=UTC)
    dynamo_client.update_person_status(PERSON_ID, Direction.ENTRY, ts)

    # A late retry (older timestamp) and a duplicate (same timestamp) must not overwrite.
    assert (
        dynamo_client.update_person_status(PERSON_ID, Direction.EXIT, ts - timedelta(minutes=1))
        is False
    )
    assert dynamo_client.update_person_status(PERSON_ID, Direction.EXIT, ts) is False

    assert get_person(table)["status"] == "IN"


def test_update_person_status_unknown_person_is_not_created(table):
    result = dynamo_client.update_person_status(
        PERSON_ID, Direction.ENTRY, datetime(2026, 9, 30, 14, 32, tzinfo=UTC)
    )

    assert result is False
    assert table.scan()["Items"] == []


# --- occupancy counter ---


def test_get_occupancy_is_zero_without_counter(table):
    assert dynamo_client.get_occupancy() == 0


def test_change_occupancy_creates_counter_and_accumulates(table):
    assert dynamo_client.change_occupancy(1) == 1
    assert dynamo_client.change_occupancy(1) == 2
    assert dynamo_client.change_occupancy(-1) == 1
    assert dynamo_client.get_occupancy() == 1


def test_change_occupancy_stores_last_updated(table):
    dynamo_client.change_occupancy(1)

    item = table.get_item(Key={"PK": "AFORO", "SK": "CURRENT"})["Item"]
    assert item["currentOccupancy"] == 1
    assert item["lastUpdated"].endswith("Z")


def test_change_occupancy_never_goes_below_zero(table):
    # No counter yet.
    assert dynamo_client.change_occupancy(-1) == 0

    # Decrement larger than the current value clamps to 0.
    dynamo_client.change_occupancy(2)
    assert dynamo_client.change_occupancy(-5) == 0
    assert dynamo_client.get_occupancy() == 0

    # The counter keeps working afterwards.
    assert dynamo_client.change_occupancy(1) == 1


def test_change_occupancy_zero_delta_changes_nothing(table):
    assert dynamo_client.change_occupancy(0) == 0
    assert table.scan()["Items"] == []
