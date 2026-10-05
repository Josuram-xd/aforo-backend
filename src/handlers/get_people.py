"""GET /people: enrolled people with their current status."""

import json
from typing import Any

from db import dynamo_client


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(dynamo_client.list_people()),
    }
