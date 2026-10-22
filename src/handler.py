
import json
import logging
import os
from typing import Any

from src.config import validate_configuration
from src.idempotency import (
    ClaimResult,
    InMemoryIdempotencyStore,
    make_idempotency_key,
)
from src.metrics import build_metrics
from src.notifications import build_notifier
from src.policy import evaluate_finding

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def build_idempotency_store():
    """Use DynamoDB when configured; otherwise use local memory."""
    table_name = os.getenv("IDEMPOTENCY_TABLE")

    if table_name:
        from src.dynamodb_idempotency import DynamoDBIdempotencyStore

        return DynamoDBIdempotencyStore(
            table_name=table_name,
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )

    return InMemoryIdempotencyStore()


# Validate configuration before initializing application dependencies.
validate_configuration()

idempotency_store = build_idempotency_store()
notifier = build_notifier()
metrics = build_metrics()


def record_metric_safely(name: str, value: float = 1.0) -> None:
    """Metrics failures must not interrupt security processing."""
    try:
        metrics.record(name, value)
    except Exception:
        logger.exception(json.dumps({
            "event": "metrics_publish_failed",
            "metric_name": name,
        }))


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Validate, deduplicate, evaluate, and notify for a finding."""

    try:
        result = evaluate_finding(event)
    except ValueError as exc:
        record_metric_safely("ProcessingFailures")
        logger.warning(json.dumps({
            "event": "guardduty_event_rejected",
            "reason": str(exc),
        }))
        return {
            "statusCode": 400,
            "body": json.dumps({
                "message": "Invalid GuardDuty event",
                "error": str(exc),
            }),
        }

    key = make_idempotency_key(
        result["account"],
        result["region"],
        result["finding_id"],
    )

    try:
        claim_response = idempotency_store.claim(key)
    except Exception:
        record_metric_safely("ProcessingFailures")
        raise

    if isinstance(claim_response, tuple):
        claim, owner_token = claim_response
    else:
        claim = claim_response
        owner_token = None

    if claim == ClaimResult.COMPLETED:
        record_metric_safely("DuplicateFindings")
        logger.info(json.dumps({
            "event": "guardduty_duplicate_skipped",
            "finding_id": result["finding_id"],
        }))
        return {
            "statusCode": 200,
            "body": json.dumps({
                "message": "Finding already processed",
                "duplicate": True,
            }),
        }

    if claim == ClaimResult.IN_PROGRESS:
        return {
            "statusCode": 409,
            "body": json.dumps({
                "message": "Finding is already being processed",
                "duplicate": True,
            }),
        }

    try:
        logger.info(json.dumps({
            "event": "guardduty_policy_evaluated",
            "finding_id": result["finding_id"],
            "account": result["account"],
            "region": result["region"],
            "severity": result["severity"],
            "decision": result["decision"],
            "resource_type": result["resource_type"],
        }))

        if result["decision"] == "NOTIFY":
            if notifier is None:
                if os.getenv("IDEMPOTENCY_TABLE"):
                    raise RuntimeError(
                        "SNS_TOPIC_ARN is required for production alerts"
                    )

                logger.warning(json.dumps({
                    "event": "notification_skipped",
                    "finding_id": result["finding_id"],
                    "reason": "SNS_TOPIC_ARN is not configured",
                }))
            else:
                message_id = notifier.publish_finding(result)
                logger.info(json.dumps({
                    "event": "guardduty_alert_published",
                    "finding_id": result["finding_id"],
                    "sns_message_id": message_id,
                }))
                record_metric_safely("AlertsPublished")

        if owner_token is not None:
            idempotency_store.mark_completed(key, owner_token)
        else:
            idempotency_store.mark_completed(key)

        record_metric_safely("FindingsProcessed")

    except Exception:
        record_metric_safely("ProcessingFailures")

        try:
            if owner_token is not None:
                idempotency_store.release(key, owner_token)
            else:
                idempotency_store.release(key)
        except Exception:
            logger.exception("Failed to release idempotency claim")

        logger.exception(
            "GuardDuty finding processing failed; retry may be required"
        )
        raise

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Finding processed successfully",
            "duplicate": False,
            "result": result,
        }),
    }
