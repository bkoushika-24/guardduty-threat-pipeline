
import pytest
from datetime import datetime, timedelta, timezone

from src.outbox import InMemoryNotificationOutbox, OutboxStatus


@pytest.fixture
def outbox():
    return InMemoryNotificationOutbox()


@pytest.fixture
def sample_payload():
    return {
        "finding_id": "demo-finding-001",
        "severity": 8.2,
        "decision": "NOTIFY",
    }


def test_enqueue_creates_pending_record(outbox, sample_payload):
    record = outbox.enqueue("finding-001", sample_payload)
    assert record.key == "finding-001"
    assert record.payload == sample_payload
    assert record.status == OutboxStatus.PENDING
    assert record.attempts == 0
    assert record.created_at
    assert record.updated_at


def test_duplicate_enqueue_does_not_create_another_record(
    outbox, sample_payload
):
    first = outbox.enqueue("finding-001", sample_payload)
    second = outbox.enqueue(
        "finding-001", {"finding_id": "different-payload"}
    )

    assert first == second
    assert first is not second
    assert len(outbox.list_pending()) == 1
    assert second.payload == sample_payload


@pytest.mark.parametrize(
    "key,payload",
    [
        ("", {"finding_id": "finding-001"}),
        ("finding-001", {}),
    ],
)
def test_enqueue_rejects_invalid_input(outbox, key, payload):
    with pytest.raises(ValueError):
        outbox.enqueue(key, payload)


def test_claim_moves_pending_record_to_in_progress(
    outbox, sample_payload
):
    outbox.enqueue("finding-001", sample_payload)
    record = outbox.claim("finding-001")

    assert record is not None
    assert record.status == OutboxStatus.IN_PROGRESS
    assert record.attempts == 1
    assert record.owner_token
    assert record.lease_until
    assert outbox.claim("finding-001") is None


def test_missing_record_cannot_be_claimed(outbox):
    assert outbox.claim("missing") is None


def test_mark_sent_completes_claimed_record(outbox, sample_payload):
    outbox.enqueue("finding-001", sample_payload)
    claim = outbox.claim("finding-001")

    outbox.mark_sent("finding-001", claim.owner_token)

    record = outbox.get("finding-001")
    assert record.status == OutboxStatus.SENT
    assert record.last_error is None
    assert record.owner_token is None
    assert record.lease_until is None
    assert outbox.claim("finding-001") is None
    assert outbox.list_pending() == []


def test_failed_delivery_can_be_retried(outbox, sample_payload):
    outbox.enqueue("finding-001", sample_payload)
    first_claim = outbox.claim("finding-001")

    outbox.mark_retry(
        "finding-001", first_claim.owner_token, "Temporary SNS error"
    )

    record = outbox.get("finding-001")
    assert record.status == OutboxStatus.RETRY
    assert record.last_error == "Temporary SNS error"
    assert len(outbox.list_pending()) == 1

    second_claim = outbox.claim("finding-001")
    assert second_claim.status == OutboxStatus.IN_PROGRESS
    assert second_claim.attempts == 2
    assert second_claim.owner_token != first_claim.owner_token


def test_mark_sent_requires_valid_owner(outbox, sample_payload):
    outbox.enqueue("finding-001", sample_payload)

    with pytest.raises(ValueError, match="Claim ownership"):
        outbox.mark_sent("finding-001", "unknown-token")


def test_mark_retry_requires_nonempty_error(outbox, sample_payload):
    outbox.enqueue("finding-001", sample_payload)
    claim = outbox.claim("finding-001")

    with pytest.raises(ValueError, match="error description"):
        outbox.mark_retry("finding-001", claim.owner_token, "  ")


def test_mark_retry_requires_valid_owner(outbox, sample_payload):
    outbox.enqueue("finding-001", sample_payload)
    outbox.claim("finding-001")

    with pytest.raises(ValueError, match="Claim ownership"):
        outbox.mark_retry("finding-001", "wrong-token", "Temporary error")


def test_expired_lease_can_be_reclaimed(outbox, sample_payload):
    now = datetime.now(timezone.utc)
    outbox._now = lambda: now

    outbox.enqueue("finding-001", sample_payload)
    first_claim = outbox.claim("finding-001")

    assert first_claim is not None

    outbox._now = lambda: now + timedelta(
        seconds=outbox.lease_seconds + 1
    )

    second_claim = outbox.claim("finding-001")

    assert second_claim is not None
    assert second_claim.attempts == 2
    assert second_claim.owner_token != first_claim.owner_token


def test_stale_owner_cannot_mark_reclaimed_record_sent(
    outbox, sample_payload
):
    now = datetime.now(timezone.utc)
    outbox._now = lambda: now

    outbox.enqueue("finding-001", sample_payload)
    first_claim = outbox.claim("finding-001")

    assert first_claim is not None

    outbox._now = lambda: now + timedelta(
        seconds=outbox.lease_seconds + 1
    )

    second_claim = outbox.claim("finding-001")
    assert second_claim is not None

    with pytest.raises(ValueError, match="Claim ownership"):
        outbox.mark_sent("finding-001", first_claim.owner_token)

    outbox.mark_sent("finding-001", second_claim.owner_token)
    assert outbox.get("finding-001").status == OutboxStatus.SENT


def test_expired_owner_cannot_mark_record_sent(outbox, sample_payload):
    now = datetime.now(timezone.utc)
    outbox._now = lambda: now

    outbox.enqueue("finding-001", sample_payload)
    claim = outbox.claim("finding-001")

    assert claim is not None

    outbox._now = lambda: now + timedelta(
        seconds=outbox.lease_seconds + 1
    )

    with pytest.raises(ValueError, match="Claim lease has expired"):
        outbox.mark_sent("finding-001", claim.owner_token)


def test_invalid_lease_duration_is_rejected():
    with pytest.raises(ValueError, match="positive integer"):
        InMemoryNotificationOutbox(lease_seconds=0)
