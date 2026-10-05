import json

from db import dynamo_client
from handlers.get_aforo import handler


def test_empty_table_returns_zero_and_no_timestamp(table):
    response = handler({}, None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"currentOccupancy": 0, "lastUpdated": None}


def test_returns_current_occupancy_and_last_update(table):
    dynamo_client.change_occupancy(3)
    dynamo_client.change_occupancy(-1)

    response = handler({}, None)

    body = json.loads(response["body"])
    assert response["headers"]["Content-Type"] == "application/json"
    assert body["currentOccupancy"] == 2
    assert body["lastUpdated"].endswith("Z")
