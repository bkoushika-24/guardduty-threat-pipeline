import pytest
from unittest.mock import MagicMock
import json
from pathlib import Path

import pytest

from src.handler import lambda_handler, idempotency_store


SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "guardduty_finding.json"
)


@pytest.fixture(autouse=True)
def reset_idempotency_store():
    idempotency_store.clear()


def load_event():
    return json.loads(
        SAMPLE_PATH.read_text(encoding="utf-8-sig")
    )


def test_handler_processes_high_severity_finding():
    response = lambda_handler(load_event(), None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["result"]["decision"] == "NOTIFY"
    assert body["result"]["finding_id"] == "demo-finding-001"


def test_handler_processes_low_severity_finding():
    event = load_event()
    event["detail"]["severity"] = 3.0

    response = lambda_handler(event, None)

    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["result"]["decision"] == "IGNORE"


def test_handler_rejects_invalid_event():
    event = load_event()
    event["source"] = "invalid.source"

    response = lambda_handler(event, None)

    assert response["statusCode"] == 400
    body = json.loads(response["body"])
    assert body["message"] == "Invalid GuardDuty event"


def test_handler_skips_completed_duplicate():
    event = load_event()

    first = lambda_handler(event, None)
    second = lambda_handler(event, None)

    assert first["statusCode"] == 200
    assert json.loads(first["body"])["duplicate"] is False

    assert second["statusCode"] == 200
    assert json.loads(second["body"])["duplicate"] is True

import json
from unittest.mock import MagicMock

import pytest

import src.handler as handler


def test_high_severity_finding_publishes_alert(monkeypatch):
    handler.idempotency_store.clear()
    mock_notifier = MagicMock()
    mock_notifier.publish_finding.return_value = "mock-sns-123"
    monkeypatch.setattr(handler, "notifier", mock_notifier)

    event = json.loads(
        open("samples/guardduty_finding.json", encoding="utf-8-sig").read()
    )

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    mock_notifier.publish_finding.assert_called_once()
    assert json.loads(response["body"])["duplicate"] is False


def test_low_severity_finding_does_not_publish_alert(monkeypatch):
    handler.idempotency_store.clear()
    mock_notifier = MagicMock()
    monkeypatch.setattr(handler, "notifier", mock_notifier)

    event = json.loads(
        open("samples/guardduty_finding.json", encoding="utf-8-sig").read()
    )
    event["detail"]["severity"] = 3.0

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    mock_notifier.publish_finding.assert_not_called()


def test_notification_failure_releases_claim_for_retry(monkeypatch):
    handler.idempotency_store.clear()
    mock_notifier = MagicMock()
    mock_notifier.publish_finding.side_effect = RuntimeError(
        "Simulated SNS outage"
    )

    monkeypatch.setattr(handler, "notifier", mock_notifier)

    event = json.loads(
        open("samples/guardduty_finding.json", encoding="utf-8-sig").read()
    )

    with pytest.raises(RuntimeError, match="Simulated SNS outage"):
        handler.lambda_handler(event, None)

    # Retry with a recovered SNS service.
    mock_notifier.publish_finding.side_effect = None
    mock_notifier.publish_finding.return_value = "mock-sns-retry-123"

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    assert mock_notifier.publish_finding.call_count == 2

def test_metrics_failure_does_not_block_finding_processing(monkeypatch):
    import json
    import src.handler as handler

    handler.idempotency_store.clear()
    monkeypatch.setattr(
        handler,
        "metrics",
        MagicMock(record=MagicMock(side_effect=RuntimeError("CloudWatch down"))),
    )
    monkeypatch.setattr(handler, "notifier", None)

    with open(
        "samples/guardduty_finding.json",
        encoding="utf-8-sig",
    ) as file:
        event = json.load(file)

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200


def test_metrics_failure_does_not_block_sns_alert(monkeypatch):
    import json
    import src.handler as handler

    handler.idempotency_store.clear()
    mock_notifier = MagicMock()
    mock_notifier.publish_finding.return_value = "mock-sns-456"

    monkeypatch.setattr(handler, "notifier", mock_notifier)
    monkeypatch.setattr(
        handler,
        "metrics",
        MagicMock(record=MagicMock(side_effect=RuntimeError("CloudWatch down"))),
    )

    with open(
        "samples/guardduty_finding.json",
        encoding="utf-8-sig",
    ) as file:
        event = json.load(file)

    response = handler.lambda_handler(event, None)

    assert response["statusCode"] == 200
    mock_notifier.publish_finding.assert_called_once()

def test_dynamodb_completion_failure_after_sns_publish(monkeypatch):
    import json
    import src.handler as handler

    handler.idempotency_store.clear()

    mock_notifier = MagicMock()
    mock_notifier.publish_finding.return_value = "mock-sns-789"
    monkeypatch.setattr(handler, "notifier", mock_notifier)

    store = handler.idempotency_store
    original_mark_completed = store.mark_completed

    def fail_mark_completed(*args, **kwargs):
        raise RuntimeError("Simulated DynamoDB completion failure")

    monkeypatch.setattr(store, "mark_completed", fail_mark_completed)

    with open(
        "samples/guardduty_finding.json",
        encoding="utf-8-sig",
    ) as file:
        event = json.load(file)

    with pytest.raises(
        RuntimeError,
        match="Simulated DynamoDB completion failure",
    ):
        handler.lambda_handler(event, None)

    mock_notifier.publish_finding.assert_called_once()

    # Restore the method so cleanup or subsequent tests are not affected.
    monkeypatch.setattr(store, "mark_completed", original_mark_completed)

