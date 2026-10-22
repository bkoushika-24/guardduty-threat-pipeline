import time
import uuid
from typing import Any

import boto3
from botocore.exceptions import ClientError

from src.idempotency import ClaimResult


class DynamoDBIdempotencyStore:
    """Lease-based idempotency store for AWS deployments."""

    def __init__(
        self,
        table_name: str,
        region_name: str = "us-east-1",
        table: Any = None,
        lease_seconds: int = 300,
    ):
        if not table_name:
            raise ValueError("DynamoDB table name is required")
        if lease_seconds <= 0:
            raise ValueError("Lease duration must be positive")

        self.lease_seconds = lease_seconds

        if table is not None:
            self.table = table
        else:
            dynamodb = boto3.resource(
                "dynamodb",
                region_name=region_name,
            )
            self.table = dynamodb.Table(table_name)

    @staticmethod
    def _error_code(exc: ClientError) -> str | None:
        return exc.response.get("Error", {}).get("Code")

    def claim(
        self,
        key: str,
    ) -> tuple[ClaimResult, str | None]:
        """Claim a finding and return its ownership token when claimed."""
        if not key:
            raise ValueError("Idempotency key is required")

        now = int(time.time())
        owner = str(uuid.uuid4())
        lease_until = now + self.lease_seconds

        try:
            self.table.put_item(
                Item={
                    "idempotency_key": key,
                    "status": ClaimResult.IN_PROGRESS.value,
                    "owner_token": owner,
                    "lease_until": lease_until,
                },
                ConditionExpression=(
                    "attribute_not_exists(idempotency_key)"
                ),
            )
            return ClaimResult.CLAIMED, owner

        except ClientError as exc:
            if self._error_code(exc) != "ConditionalCheckFailedException":
                raise

        response = self.table.get_item(
            Key={"idempotency_key": key},
            ConsistentRead=True,
        )
        item = response.get("Item")

        if item is None:
            raise RuntimeError(
                "Idempotency record disappeared during claim"
            )

        if item.get("status") == ClaimResult.COMPLETED.value:
            return ClaimResult.COMPLETED, None

        if item.get("status") != ClaimResult.IN_PROGRESS.value:
            raise RuntimeError("Idempotency record has an unknown status")

        current_lease = item.get("lease_until")
        if not isinstance(current_lease, (int, float)):
            raise RuntimeError("In-progress record has no valid lease")

        if current_lease > now:
            return ClaimResult.IN_PROGRESS, None

        # Recover an expired claim only if it is still expired.
        try:
            self.table.update_item(
                Key={"idempotency_key": key},
                UpdateExpression=(
                    "SET owner_token = :owner, lease_until = :lease"
                ),
                ConditionExpression=(
                    "#status = :in_progress "
                    "AND lease_until <= :now"
                ),
                ExpressionAttributeNames={
                    "#status": "status",
                },
                ExpressionAttributeValues={
                    ":owner": owner,
                    ":lease": lease_until,
                    ":in_progress": ClaimResult.IN_PROGRESS.value,
                    ":now": now,
                },
            )
            return ClaimResult.CLAIMED, owner

        except ClientError as exc:
            if self._error_code(exc) != "ConditionalCheckFailedException":
                raise

            # Another invocation may have renewed or taken the lease.
            return ClaimResult.IN_PROGRESS, None

    def mark_completed(self, key: str, owner_token: str) -> None:
        """Complete a finding only if this invocation owns an active claim."""
        if not owner_token:
            raise ValueError("Owner token is required")

        now = int(time.time())

        try:
            self.table.update_item(
                Key={"idempotency_key": key},
                UpdateExpression=(
                    "SET #status = :completed "
                    "REMOVE lease_until, owner_token"
                ),
                ConditionExpression=(
                    "#status = :in_progress "
                    "AND owner_token = :owner "
                    "AND lease_until > :now"
                ),
                ExpressionAttributeNames={
                    "#status": "status",
                },
                ExpressionAttributeValues={
                    ":completed": ClaimResult.COMPLETED.value,
                    ":in_progress": ClaimResult.IN_PROGRESS.value,
                    ":owner": owner_token,
                    ":now": now,
                },
            )

        except ClientError as exc:
            if self._error_code(exc) == "ConditionalCheckFailedException":
                raise ValueError(
                    "Claim is not active under this owner"
                ) from exc
            raise

    def release(self, key: str, owner_token: str) -> None:
        """Release only a claim still active under this owner."""
        if not owner_token:
            raise ValueError("Owner token is required")

        now = int(time.time())

        try:
            self.table.delete_item(
                Key={"idempotency_key": key},
                ConditionExpression=(
                    "#status = :in_progress "
                    "AND owner_token = :owner "
                    "AND lease_until > :now"
                ),
                ExpressionAttributeNames={
                    "#status": "status",
                },
                ExpressionAttributeValues={
                    ":in_progress": ClaimResult.IN_PROGRESS.value,
                    ":owner": owner_token,
                    ":now": now,
                },
            )

        except ClientError as exc:
            if self._error_code(exc) == "ConditionalCheckFailedException":
                raise ValueError(
                    "Claim is not active under this owner"
                ) from exc
            raise
