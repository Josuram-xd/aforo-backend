"""GET /aforo: current occupancy of the room."""

import json
from typing import Any

from db import dynamo_client


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    occupancy, last_updated = dynamo_client.get_occupancy_with_timestamp()
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"currentOccupancy": occupancy, "lastUpdated": last_updated}),
    }
