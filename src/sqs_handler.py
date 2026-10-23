
import json
import logging
from typing import Any

from src.handler import lambda_handler

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def sqs_lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Process an SQS batch and report individual record failures."""

    records = event.get("Records") if isinstance(event, dict) else None

    if not isinstance(records, list):
        raise ValueError("SQS event must contain a Records list")

    batch_item_failures = []

    for record in records:
        message_id = (
            record.get("messageId")
            if isinstance(record, dict)
            else None
        )

        try:
            if not isinstance(message_id, str) or not message_id:
                raise ValueError("SQS record is missing messageId")

            body = record.get("body")
            if not isinstance(body, str):
                raise ValueError("SQS record body must be a JSON string")

            finding = json.loads(body)

            if not isinstance(finding, dict):
                raise ValueError("SQS message body must be a JSON object")

            response = lambda_handler(finding, context)
            status_code = response.get("statusCode")

            if status_code != 200:
                event_name = (
                    "sqs_record_invalid"
                    if status_code == 400
                    else "sqs_record_processing_failed"
                )

                logger.error(json.dumps({
                    "event": event_name,
                    "message_id": message_id,
                    "status_code": status_code,
                }))

                batch_item_failures.append({
                    "itemIdentifier": message_id,
                })

        except Exception as exc:
            logger.error(json.dumps({
                "event": "sqs_record_processing_failed",
                "message_id": message_id,
                "error_type": type(exc).__name__,
            }))

            if isinstance(message_id, str) and message_id:
                batch_item_failures.append({
                    "itemIdentifier": message_id,
                })
            else:
                # Without a message ID, we cannot safely identify a partial
                # failure. Fail the whole invocation instead.
                raise

    return {"batchItemFailures": batch_item_failures}

def test_non_string_body_marks_only_record_failed():
    event = {
        "Records": [
            {
                "messageId": "message-bad-body",
                "body": {"unexpected": "object"},
            }
        ]
    }

    response = sqs_lambda_handler(event, None)

    assert response == {
        "batchItemFailures": [
            {"itemIdentifier": "message-bad-body"}
        ]
    }
