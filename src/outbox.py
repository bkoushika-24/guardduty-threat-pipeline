
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Lock
from typing import Any
from uuid import uuid4


class OutboxStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SENT = "SENT"
    RETRY = "RETRY"


@dataclass
class OutboxRecord:
    key: str
    payload: dict[str, Any]
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0
    last_error: str | None = None
    created_at: str = ""
    updated_at: str = ""
    owner_token: str | None = None
    lease_until: str | None = None


class InMemoryNotificationOutbox:
    """Local outbox with ownership tokens and expiring claims.

    In-memory only: not durable across restarts and not suitable
    for coordination between separate processes or Lambda instances.
    """

    def __init__(self, lease_seconds: int = 300) -> None:
        if (
            not isinstance(lease_seconds, int)
            or isinstance(lease_seconds, bool)
            or lease_seconds <= 0
        ):
            raise ValueError("lease_seconds must be a positive integer")

        self.lease_seconds = lease_seconds
        self._records: dict[str, OutboxRecord] = {}
        self._lock = Lock()

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _timestamp(value: datetime) -> str:
        return value.isoformat()

    @staticmethod
    def _parse_timestamp(value: str) -> datetime:
        return datetime.fromisoformat(value)

    def enqueue(
        self,
        key: str,
        payload: dict[str, Any],
    ) -> OutboxRecord:
        if not isinstance(key, str) or not key.strip():
            raise ValueError("Outbox key is required")

        if not isinstance(payload, dict) or not payload:
            raise ValueError("Outbox payload must be a non-empty object")

        with self._lock:
            existing = self._records.get(key)

            if existing is not None:
                return deepcopy(existing)

            now = self._now()
            record = OutboxRecord(
                key=key,
                payload=deepcopy(payload),
                created_at=self._timestamp(now),
                updated_at=self._timestamp(now),
            )
            self._records[key] = record
            return deepcopy(record)

    def get(self, key: str) -> OutboxRecord | None:
        with self._lock:
            record = self._records.get(key)
            return deepcopy(record) if record is not None else None

    def claim(self, key: str) -> OutboxRecord | None:
        """Claim a pending/retryable record or reclaim an expired lease."""
        with self._lock:
            record = self._records.get(key)

            if record is None:
                return None

            now = self._now()

            if record.status == OutboxStatus.IN_PROGRESS:
                if record.lease_until is None:
                    return None

                lease_expiry = self._parse_timestamp(record.lease_until)
                if lease_expiry > now:
                    return None

                # The old owner has lost its lease. Replace its token.
            elif record.status not in {
                OutboxStatus.PENDING,
                OutboxStatus.RETRY,
            }:
                return None

            record.status = OutboxStatus.IN_PROGRESS
            record.attempts += 1
            record.owner_token = str(uuid4())
            record.lease_until = self._timestamp(
                now + timedelta(seconds=self.lease_seconds)
            )
            record.updated_at = self._timestamp(now)
            return deepcopy(record)

    def mark_sent(self, key: str, owner_token: str) -> None:
        with self._lock:
            record = self._require_owner(key, owner_token)
            record.status = OutboxStatus.SENT
            record.last_error = None
            record.owner_token = None
            record.lease_until = None
            record.updated_at = self._timestamp(self._now())

    def mark_retry(
        self,
        key: str,
        owner_token: str,
        error: str,
    ) -> None:
        if not isinstance(error, str) or not error.strip():
            raise ValueError("Retry error description is required")

        with self._lock:
            record = self._require_owner(key, owner_token)
            record.status = OutboxStatus.RETRY
            record.last_error = error
            record.owner_token = None
            record.lease_until = None
            record.updated_at = self._timestamp(self._now())

    def _require_owner(
        self,
        key: str,
        owner_token: str,
    ) -> OutboxRecord:
        record = self._records.get(key)

        if (
            record is None
            or record.status != OutboxStatus.IN_PROGRESS
            or not owner_token
            or record.owner_token != owner_token
        ):
            raise ValueError("Claim ownership check failed")

        if record.lease_until is None:
            raise ValueError("Claim lease is missing")

        if self._parse_timestamp(record.lease_until) <= self._now():
            raise ValueError("Claim lease has expired")

        return record

    def list_pending(self) -> list[OutboxRecord]:
        with self._lock:
            return [
                deepcopy(record)
                for record in self._records.values()
                if record.status in {
                    OutboxStatus.PENDING,
                    OutboxStatus.RETRY,
                }
            ]
