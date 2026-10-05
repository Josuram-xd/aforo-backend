"""Shared constants and helpers for tests that use the moto table fixture (conftest.py)."""

TABLE_NAME = "AforoPilot"
PERSON_ID = "7d1f7a52-3c1e-4a53-8a0e-5b9d2c3e4f10"


def add_person(table, status="OUT"):
    table.put_item(Item={"PK": f"PERSON#{PERSON_ID}", "SK": "PROFILE", "status": status})


def get_person(table):
    return table.get_item(Key={"PK": f"PERSON#{PERSON_ID}", "SK": "PROFILE"})["Item"]
