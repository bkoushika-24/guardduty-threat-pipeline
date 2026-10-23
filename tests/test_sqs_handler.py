import json
from pathlib import Path

import pytest
import src.sqs_handler as sqs_module

from src.handler import idempotency_store
from src.sqs_handler import sqs_lambda_handler


SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "guardduty_finding.json"
)


@pytest.fixture(autouse=True)
def reset_store():
    idempotency_store.clear()


def load_finding():
    return json.loads(
        SAMPLE_PATH.read_text(encoding="utf-8-sig")
    )


def sqs_record(message_id, body):
    return {
        "messageId": message_id,
        "receiptHandle": "local-test-receipt",
        "body": json.dumps(body),
        "attributes": {},
        "messageAttributes": {},
        "md5OfBody": "local-test",
        "eventSource": "aws:sqs",
        "eventSourceARN": "arn:aws:sqs:us-east-1:111122223333:demo",
        "awsRegion": "us-east-1",
    }


def test_successful_batch_returns_no_failures():
    event = {
        "Records": [
            sqs_record("msg-1", load_finding()),
            sqs_record("msg-2", {
                **load_finding(),
                "id": "evt-demo-002",
                "detail": {
                    **load_finding()["detail"],
                    "id": "demo-finding-002",
                    "severity": 4.0,
                },
            }),
        ]
    }

    response = sqs_lambda_handler(event, None)

    assert response == {"batchItemFailures": []}


def test_invalid_json_marks_only_that_message_failed():
    good = sqs_record("msg-good", load_finding())
    bad = sqs_record("msg-bad", load_finding())
    bad["body"] = "{not valid JSON"

    response = sqs_lambda_handler(
        {"Records": [good, bad]},
        None,
    )

    assert response == {
        "batchItemFailures": [
            {"itemIdentifier": "msg-bad"}
        ]
    }


def test_invalid_finding_is_reported_as_failure():
    finding = load_finding()
    finding["source"] = "untrusted.source"

    response = sqs_lambda_handler(
        {"Records": [sqs_record("msg-invalid", finding)]},
        None,
    )

    assert response == {
        "batchItemFailures": [
            {"itemIdentifier": "msg-invalid"}
        ]
    }


def test_completed_duplicate_is_successful():
    finding = load_finding()

    event = {
        "Records": [
            sqs_record("msg-1", finding),
            sqs_record("msg-2", finding),
        ]
    }

    response = sqs_lambda_handler(event, None)

    assert response == {"batchItemFailures": []}


def test_missing_records_list_is_rejected():
    with pytest.raises(ValueError, match="Records"):
        sqs_lambda_handler({}, None)
def test_transient_failure_retries_only_failed_message(monkeypatch):
    original_handler = sqs_module.lambda_handler

    def flaky_handler(finding, context):
        if finding["detail"]["id"] == "demo-finding-001":
            raise RuntimeError("Simulated temporary outage")

        return original_handler(finding, context)

    monkeypatch.setattr(sqs_module, "lambda_handler", flaky_handler)

    first_finding = load_finding()
    second_finding = load_finding()
    second_finding["detail"]["id"] = "demo-finding-002"

    event = {
        "Records": [
            sqs_record("msg-fail", first_finding),
            sqs_record("msg-success", second_finding),
        ]
    }

    response = sqs_module.sqs_lambda_handler(event, None)

    assert response == {
        "batchItemFailures": [
            {"itemIdentifier": "msg-fail"}
        ]
    }

def test_unexpected_status_code_marks_record_failed(monkeypatch):
    import src.sqs_handler as sqs_module

    monkeypatch.setattr(
        sqs_module,
        "lambda_handler",
        lambda finding, context: {"statusCode": 500, "body": "error"},
    )

    event = {
        "Records": [{
            "messageId": "message-500",
            "body": '{"example": "finding"}',
        }]
    }

    response = sqs_module.sqs_lambda_handler(event, None)

    assert response == {
        "batchItemFailures": [
            {"itemIdentifier": "message-500"}
        ]
    }


def test_missing_status_code_marks_record_failed(monkeypatch):
    import src.sqs_handler as sqs_module

    monkeypatch.setattr(
        sqs_module,
        "lambda_handler",
        lambda finding, context: {"body": "unexpected response"},
    )

    event = {
        "Records": [{
            "messageId": "message-no-status",
            "body": '{"example": "finding"}',
        }]
    }

    response = sqs_module.sqs_lambda_handler(event, None)

    assert response == {
        "batchItemFailures": [
            {"itemIdentifier": "message-no-status"}
        ]
    }
def test_empty_batch_returns_no_failures():
    response = sqs_lambda_handler({"Records": []}, None)

    assert response == {"batchItemFailures": []}


def test_missing_message_id_fails_invocation():
    event = {
        "Records": [
            {
                "body": json.dumps(load_finding()),
            }
        ]
    }

    with pytest.raises(ValueError, match="messageId"):
        sqs_lambda_handler(event, None)