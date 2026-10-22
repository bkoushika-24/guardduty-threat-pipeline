
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from src.dynamodb_idempotency import DynamoDBIdempotencyStore
from src.idempotency import ClaimResult


@pytest.fixture
def table():
    return MagicMock()


@pytest.fixture
def store(table):
    return DynamoDBIdempotencyStore(
        table_name="test-idempotency",
        table=table,
        lease_seconds=300,
    )


def conditional_failure(operation="PutItem"):
    return ClientError(
        {
            "Error": {
                "Code": "ConditionalCheckFailedException",
                "Message": "Condition failed",
            }
        },
        operation,
    )


def test_first_claim_succeeds(store, table):
    result, owner = store.claim("account#region#finding-1")

    assert result == ClaimResult.CLAIMED
    assert owner
    kwargs = table.put_item.call_args.kwargs
    assert kwargs["Item"]["status"] == "IN_PROGRESS"
    assert kwargs["Item"]["owner_token"] == owner
    assert kwargs["Item"]["lease_until"] > 0


def test_completed_duplicate_is_detected(store, table):
    table.put_item.side_effect = conditional_failure()
    table.get_item.return_value = {
        "Item": {
            "idempotency_key": "account#region#finding-1",
            "status": "COMPLETED",
        }
    }

    result, owner = store.claim("account#region#finding-1")

    assert result == ClaimResult.COMPLETED
    assert owner is None


def test_active_lease_is_not_stolen(store, table, monkeypatch):
    import src.dynamodb_idempotency as module

    monkeypatch.setattr(module.time, "time", lambda: 1000)
    table.put_item.side_effect = conditional_failure()
    table.get_item.return_value = {
        "Item": {
            "idempotency_key": "account#region#finding-1",
            "status": "IN_PROGRESS",
            "owner_token": "existing-owner",
            "lease_until": 1100,
        }
    }

    result, owner = store.claim("account#region#finding-1")

    assert result == ClaimResult.IN_PROGRESS
    assert owner is None
    table.update_item.assert_not_called()


def test_expired_lease_can_be_reclaimed(store, table, monkeypatch):
    import src.dynamodb_idempotency as module

    monkeypatch.setattr(module.time, "time", lambda: 1000)
    table.put_item.side_effect = conditional_failure()
    table.get_item.return_value = {
        "Item": {
            "idempotency_key": "account#region#finding-1",
            "status": "IN_PROGRESS",
            "owner_token": "old-owner",
            "lease_until": 900,
        }
    }

    result, owner = store.claim("account#region#finding-1")

    assert result == ClaimResult.CLAIMED
    assert owner
    kwargs = table.update_item.call_args.kwargs
    assert kwargs["ExpressionAttributeValues"][":now"] == 1000
    assert kwargs["ExpressionAttributeValues"][":owner"] == owner


def test_mark_completed_requires_owner(store, table):
    store.mark_completed("account#region#finding-1", "owner-1")

    kwargs = table.update_item.call_args.kwargs
    assert kwargs["ExpressionAttributeValues"][":owner"] == "owner-1"
    assert "owner_token = :owner" in kwargs["ConditionExpression"]


def test_release_requires_owner(store, table):
    store.release("account#region#finding-1", "owner-1")

    kwargs = table.delete_item.call_args.kwargs
    assert kwargs["ExpressionAttributeValues"][":owner"] == "owner-1"
    assert "owner_token = :owner" in kwargs["ConditionExpression"]


def test_claim_rejects_empty_key(store):
    with pytest.raises(ValueError, match="Idempotency key"):
        store.claim("")


def test_unexpected_dynamodb_error_is_propagated(store, table):
    table.put_item.side_effect = ClientError(
        {
            "Error": {
                "Code": "ProvisionedThroughputExceededException",
                "Message": "Temporary capacity issue",
            }
        },
        "PutItem",
    )

    with pytest.raises(ClientError):
        store.claim("account#region#finding-1")


def test_nonpositive_lease_is_rejected(table):
    with pytest.raises(ValueError, match="Lease duration"):
        DynamoDBIdempotencyStore(
            table_name="test-idempotency",
            table=table,
            lease_seconds=0,
        )
