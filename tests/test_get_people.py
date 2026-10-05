import json
from datetime import UTC, datetime

from db import dynamo_client
from handlers.get_people import handler
from models.event import Direction

ANA_ID = "7d1f7a52-3c1e-4a53-8a0e-5b9d2c3e4f10"
BEA_ID = "2a9c4e10-5b6d-4f7a-9c8b-1d2e3f4a5b6c"


def add_person(table, person_id, name):
    table.put_item(
        Item={
            "PK": f"PERSON#{person_id}",
            "SK": "PROFILE",
            "personId": person_id,
            "name": name,
            "status": "OUT",
        }
    )


def test_empty_table_returns_empty_list(table):
    response = handler({}, None)

    assert response["statusCode"] == 200
    assert response["headers"]["Content-Type"] == "application/json"
    assert json.loads(response["body"]) == []


def test_lists_people_sorted_by_name_with_status(table):
    add_person(table, BEA_ID, "Beatriz")
    add_person(table, ANA_ID, "Ana")
    dynamo_client.update_person_status(
        ANA_ID, Direction.ENTRY, datetime(2026, 9, 30, 14, 32, tzinfo=UTC)
    )

    body = json.loads(handler({}, None)["body"])

    assert body == [
        {
            "personId": ANA_ID,
            "name": "Ana",
            "status": "IN",
            "lastEventAt": "2026-09-30T14:32:00.000000Z",
        },
        {"personId": BEA_ID, "name": "Beatriz", "status": "OUT", "lastEventAt": None},
    ]


def test_ignores_events_and_occupancy_counter(table):
    add_person(table, ANA_ID, "Ana")
    dynamo_client.change_occupancy(1)
    table.put_item(Item={"PK": "EVENT#2026-09-30", "SK": "2026-09-30T14:32:00.000000Z#x"})

    body = json.loads(handler({}, None)["body"])

    assert [person["personId"] for person in body] == [ANA_ID]
