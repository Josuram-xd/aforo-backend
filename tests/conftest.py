import boto3
import pytest
from moto import mock_aws

from db import dynamo_client
from tests.helpers import TABLE_NAME


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
