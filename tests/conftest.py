"""Shared pytest fixtures for the test suite."""

import os
import uuid

import boto3
import pytest

TEST_TABLE_NAME = f"CreditCardPayoffTest_{uuid.uuid4().hex[:8]}"
DYNAMODB_ENDPOINT = os.environ.get("DYNAMODB_ENDPOINT", "http://localhost:8000")


@pytest.fixture(scope="session")
def dynamodb_test_table():
    """Create a dedicated test table in DynamoDB Local, tear it down after the session."""
    client = boto3.client(
        "dynamodb", endpoint_url=DYNAMODB_ENDPOINT, region_name="us-east-1"
    )
    client.create_table(
        TableName=TEST_TABLE_NAME,
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
    client.get_waiter("table_exists").wait(TableName=TEST_TABLE_NAME)
    yield TEST_TABLE_NAME
    client.delete_table(TableName=TEST_TABLE_NAME)


@pytest.fixture(autouse=True)
def _patch_db_env(dynamodb_test_table, monkeypatch):
    """Point database.py at the test table and reset its cached table reference."""
    import database

    monkeypatch.setenv("DYNAMODB_ENDPOINT", DYNAMODB_ENDPOINT)
    monkeypatch.setenv("DYNAMODB_TABLE", dynamodb_test_table)
    # Reset the cached table so _get_table() picks up the test table
    database._table = None
    yield
    database._table = None


@pytest.fixture()
def clean_table(dynamodb_test_table):
    """Wipe all items from the test table before and after each test."""
    _wipe_table(dynamodb_test_table)
    yield
    _wipe_table(dynamodb_test_table)


def _wipe_table(table_name):
    """Delete every item from the given DynamoDB table."""
    resource = boto3.resource(
        "dynamodb", endpoint_url=DYNAMODB_ENDPOINT, region_name="us-east-1"
    )
    table = resource.Table(table_name)
    response = table.scan()
    with table.batch_writer() as batch:
        for item in response.get("Items", []):
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
