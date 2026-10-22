import pytest

from src.idempotency import (
    ClaimResult,
    InMemoryIdempotencyStore,
    make_idempotency_key,
)


def test_first_claim_succeeds():
    store = InMemoryIdempotencyStore()

    result = store.claim("account#region#finding-1")

    assert result == ClaimResult.CLAIMED


def test_second_claim_reports_in_progress():
    store = InMemoryIdempotencyStore()
    key = "account#region#finding-1"

    store.claim(key)
    result = store.claim(key)

    assert result == ClaimResult.IN_PROGRESS


def test_completed_finding_is_not_claimed_again():
    store = InMemoryIdempotencyStore()
    key = "account#region#finding-1"

    store.claim(key)
    store.mark_completed(key)

    assert store.claim(key) == ClaimResult.COMPLETED


def test_release_allows_retry():
    store = InMemoryIdempotencyStore()
    key = "account#region#finding-1"

    store.claim(key)
    store.release(key)

    assert store.claim(key) == ClaimResult.CLAIMED


def test_key_includes_account_region_and_finding():
    key = make_idempotency_key(
        "111122223333",
        "us-east-1",
        "finding-1",
    )

    assert key == "111122223333#us-east-1#finding-1"


def test_key_requires_all_fields():
    with pytest.raises(ValueError):
        make_idempotency_key("", "us-east-1", "finding-1")
