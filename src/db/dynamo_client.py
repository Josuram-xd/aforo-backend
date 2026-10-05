"""DynamoDB access for the AforoPilot table (defined in the aforo-db repo).

Key design (see aforo-db/ARCHITECTURE.md):
- Events: PK = EVENT#<YYYY-MM-DD>, SK = <timestamp>#<eventId>, both in UTC.
- People: PK = PERSON#<personId>, SK = PROFILE (created by aforo-db/scripts/seed_people.py).
- Occupancy: PK = AFORO, SK = CURRENT, with the number in currentOccupancy.
"""

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cache
from uuid import UUID

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

from models.event import AforoEvent, Direction

# Upper bound on how many daily partitions a single query_events call may touch.
MAX_QUERY_DAYS = 31

# Fixed-width UTC format so stored timestamps (event SK, lastEventAt) compare lexicographically
# by time ("...00Z" and "...00.5Z" would sort the wrong way if mixed).
_SORTABLE_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
# Sorts after any eventId (UUID chars), making the upper bound inclusive.
_SK_UPPER_SUFFIX = "#~"

_OCCUPANCY_PK = "AFORO"
_OCCUPANCY_SK = "CURRENT"

_STATUS_BY_DIRECTION = {Direction.ENTRY: "IN", Direction.EXIT: "OUT"}

_EVENT_FIELDS = {field.alias for field in AforoEvent.model_fields.values()}


@cache
def _table():
    """Table resource, created once per Lambda container (tests can call _table.cache_clear())."""
    return boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])


def _to_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("La fecha debe incluir zona horaria (por ejemplo, terminar en Z).")
    return ts.astimezone(UTC)


def _event_pk(day: date) -> str:
    return f"EVENT#{day.isoformat()}"


def _sortable_timestamp(ts: datetime) -> str:
    return ts.strftime(_SORTABLE_TIMESTAMP_FORMAT)


def _item_to_event(item: dict) -> AforoEvent:
    data = {k: v for k, v in item.items() if k in _EVENT_FIELDS}
    data["confidence"] = float(data["confidence"])
    return AforoEvent.model_validate(data)


def put_event(event: AforoEvent) -> None:
    """Store an event in the partition of its UTC date."""
    ts = _to_utc(event.timestamp)
    item = event.model_dump(mode="json")
    item["timestamp"] = ts.isoformat().replace("+00:00", "Z")
    # DynamoDB rejects floats; str() keeps the value as sent (0.91, not 0.9100000000000000310...).
    item["confidence"] = Decimal(str(event.confidence))
    item["PK"] = _event_pk(ts.date())
    item["SK"] = f"{_sortable_timestamp(ts)}#{event.event_id}"
    _table().put_item(Item=item)


def query_events(from_ts: datetime, to_ts: datetime) -> list[AforoEvent]:
    """Return events with from_ts <= timestamp <= to_ts, oldest first.

    Queries one EVENT#<date> partition per UTC day in the range, so a session that
    crosses midnight UTC (7 p.m. in Colombia) is still returned whole.
    """
    start, end = _to_utc(from_ts), _to_utc(to_ts)
    if start > end:
        return []

    days = (end.date() - start.date()).days + 1
    if days > MAX_QUERY_DAYS:
        raise ValueError(f"El rango de fechas no puede superar {MAX_QUERY_DAYS} días.")

    sk_range = Key("SK").between(
        _sortable_timestamp(start), _sortable_timestamp(end) + _SK_UPPER_SUFFIX
    )
    events = []
    for offset in range(days):
        key_condition = Key("PK").eq(_event_pk(start.date() + timedelta(days=offset))) & sk_range
        kwargs = {"KeyConditionExpression": key_condition}
        while True:
            page = _table().query(**kwargs)
            events.extend(_item_to_event(item) for item in page["Items"])
            if "LastEvaluatedKey" not in page:
                break
            kwargs["ExclusiveStartKey"] = page["LastEvaluatedKey"]
    return events


def update_person_status(person_id: UUID | str, direction: Direction, ts: datetime) -> bool:
    """Set a person's status (ENTRY -> IN, EXIT -> OUT) and lastEventAt.

    Returns False without writing when the person is not in the roster (no PROFILE item),
    or when ts is not newer than the stored lastEventAt: a late retry from aforo-vision's
    queue must not overwrite a more recent crossing.
    """
    try:
        _table().update_item(
            Key={"PK": f"PERSON#{person_id}", "SK": "PROFILE"},
            UpdateExpression="SET #status = :status, lastEventAt = :ts",
            ConditionExpression=(
                "attribute_exists(PK) AND (attribute_not_exists(lastEventAt) OR lastEventAt < :ts)"
            ),
            # "status" is a DynamoDB reserved word.
            ExpressionAttributeNames={"#status": "status"},
            ExpressionAttributeValues={
                ":status": _STATUS_BY_DIRECTION[direction],
                ":ts": _sortable_timestamp(_to_utc(ts)),
            },
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        return False
    return True


def _is_condition_failure(error: ClientError) -> bool:
    return error.response["Error"]["Code"] == "ConditionalCheckFailedException"


def change_occupancy(delta: int) -> int:
    """Atomically add delta to the occupancy counter and return the new value.

    The counter never goes below 0: a decrement larger than the current value clamps it to 0.
    The item is created on first use (ADD treats a missing number as 0).
    """
    if delta == 0:
        return get_occupancy()

    key = {"PK": _OCCUPANCY_PK, "SK": _OCCUPANCY_SK}
    now = _sortable_timestamp(datetime.now(UTC))
    try:
        kwargs = {}
        if delta < 0:
            kwargs["ConditionExpression"] = "currentOccupancy >= :needed"
        response = _table().update_item(
            Key=key,
            UpdateExpression="ADD currentOccupancy :delta SET lastUpdated = :now",
            ExpressionAttributeValues={
                ":delta": delta,
                ":now": now,
                **({":needed": -delta} if delta < 0 else {}),
            },
            ReturnValues="UPDATED_NEW",
            **kwargs,
        )
    except ClientError as e:
        if delta > 0 or not _is_condition_failure(e):
            raise
        # Not enough to subtract (or no counter yet): clamp to 0. The condition makes this
        # safe against a concurrent increment that would have made the first attempt succeed.
        try:
            response = _table().update_item(
                Key=key,
                UpdateExpression="SET currentOccupancy = :zero, lastUpdated = :now",
                ConditionExpression=(
                    "attribute_not_exists(currentOccupancy) OR currentOccupancy < :needed"
                ),
                ExpressionAttributeValues={":zero": 0, ":now": now, ":needed": -delta},
                ReturnValues="UPDATED_NEW",
            )
        except ClientError as retry_error:
            if not _is_condition_failure(retry_error):
                raise
            return change_occupancy(delta)  # a concurrent increment won the race; try again
    return int(response["Attributes"]["currentOccupancy"])


def get_occupancy() -> int:
    """Return the current occupancy, or 0 if the counter item does not exist yet."""
    item = (
        _table()
        .get_item(Key={"PK": _OCCUPANCY_PK, "SK": _OCCUPANCY_SK}, ConsistentRead=True)
        .get("Item")
    )
    return int(item["currentOccupancy"]) if item else 0
