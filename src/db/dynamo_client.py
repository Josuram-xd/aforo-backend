"""DynamoDB access for the AforoPilot table (defined in the aforo-db repo).

Key design (see aforo-db/ARCHITECTURE.md):
- Events: PK = EVENT#<YYYY-MM-DD>, SK = <timestamp>#<eventId>, both in UTC.
"""

import os
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from functools import cache

import boto3
from boto3.dynamodb.conditions import Key

from models.event import AforoEvent

# Upper bound on how many daily partitions a single query_events call may touch.
MAX_QUERY_DAYS = 31

# Fixed-width UTC format so sort keys order lexicographically by time
# ("...00Z" and "...00.5Z" would sort the wrong way if mixed).
_SK_TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"
# Sorts after any eventId (UUID chars), making the upper bound inclusive.
_SK_UPPER_SUFFIX = "#~"

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


def _sk_timestamp(ts: datetime) -> str:
    return ts.strftime(_SK_TIMESTAMP_FORMAT)


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
    item["SK"] = f"{_sk_timestamp(ts)}#{event.event_id}"
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

    sk_range = Key("SK").between(_sk_timestamp(start), _sk_timestamp(end) + _SK_UPPER_SUFFIX)
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
