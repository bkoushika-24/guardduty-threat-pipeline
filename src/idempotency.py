from enum import Enum


class ClaimResult(str, Enum):
    CLAIMED = "CLAIMED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


def make_idempotency_key(
    account: str,
    region: str,
    finding_id: str,
) -> str:
    """Build a stable key for one finding in one account and Region."""
    if not account or not region or not finding_id:
        raise ValueError("Account, Region, and finding ID are required")

    return f"{account}#{region}#{finding_id}"


class InMemoryIdempotencyStore:
    """Local-only demonstration store; not safe across processes."""

    def __init__(self):
        self._records: dict[str, str] = {}

    def claim(self, key: str) -> ClaimResult:
        """Claim a new finding or report its existing processing state."""
        if not key:
            raise ValueError("Idempotency key is required")

        current = self._records.get(key)

        if current == ClaimResult.COMPLETED.value:
            return ClaimResult.COMPLETED

        if current == ClaimResult.IN_PROGRESS.value:
            return ClaimResult.IN_PROGRESS

        self._records[key] = ClaimResult.IN_PROGRESS.value
        return ClaimResult.CLAIMED

    def mark_completed(self, key: str) -> None:
        if self._records.get(key) != ClaimResult.IN_PROGRESS.value:
            raise ValueError("Finding has not been claimed")

        self._records[key] = ClaimResult.COMPLETED.value

    def release(self, key: str) -> None:
        """Allow a local retry after a failed processing attempt."""
        if self._records.get(key) == ClaimResult.IN_PROGRESS.value:
            del self._records[key]

    def clear(self) -> None:
        """Reset state between local tests."""
        self._records.clear()
