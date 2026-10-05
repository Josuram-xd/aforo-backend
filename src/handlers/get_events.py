"""GET /events: events in a time range (defaults to today, Colombia time)."""

import json
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any

from db import dynamo_client

# The pilot runs in Colombia (UTC-5, no daylight saving), so "today" is the local calendar day.
_COLOMBIA_TZ = timezone(timedelta(hours=-5))


def _response(status_code: int, body: Any) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


def _today_range() -> tuple[datetime, datetime]:
    today = datetime.now(_COLOMBIA_TZ).date()
    start = datetime.combine(today, time.min, tzinfo=_COLOMBIA_TZ)
    return start.astimezone(UTC), (
        start + timedelta(days=1) - timedelta(microseconds=1)
    ).astimezone(UTC)


def _parse_timestamp(name: str, value: str) -> datetime:
    # A "+" in a query string arrives as a space ("...00 05:00"), so restore it.
    try:
        parsed = datetime.fromisoformat(value.replace(" ", "+"))
    except ValueError:
        raise ValueError(
            f"El parámetro '{name}' debe ser una fecha ISO 8601, por ejemplo 2026-09-30T14:00:00Z."
        ) from None
    if parsed.tzinfo is None:
        raise ValueError(
            f"El parámetro '{name}' debe incluir zona horaria (por ejemplo, terminar en Z)."
        )
    return parsed


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    params = event.get("queryStringParameters") or {}
    default_from, default_to = _today_range()
    try:
        from_ts = _parse_timestamp("from", params["from"]) if params.get("from") else default_from
        to_ts = _parse_timestamp("to", params["to"]) if params.get("to") else default_to
        events = dynamo_client.query_events(from_ts, to_ts)
    except ValueError as e:
        return _response(400, {"message": str(e)})

    return _response(200, [e.model_dump(mode="json") for e in events])
