import json
from pathlib import Path

import pytest

from src.policy import evaluate_finding


SAMPLE_PATH = (
    Path(__file__).resolve().parents[1]
    / "samples"
    / "guardduty_finding.json"
)


@pytest.fixture
def event():
    return json.loads(SAMPLE_PATH.read_text(encoding="utf-8-sig"))


def test_high_severity_finding_triggers_notification(event):
    result = evaluate_finding(event)

    assert result["finding_id"] == "demo-finding-001"
    assert result["severity"] == 8.2
    assert result["resource_id"] == "i-0123456789abcdef0"
    assert result["decision"] == "NOTIFY"


def test_low_severity_finding_is_ignored(event):
    event["detail"]["severity"] = 3.0

    result = evaluate_finding(event)

    assert result["decision"] == "IGNORE"


def test_rejects_wrong_event_source(event):
    event["source"] = "example.com"

    with pytest.raises(ValueError, match="source"):
        evaluate_finding(event)


def test_rejects_account_mismatch(event):
    event["detail"]["accountId"] = "999988887777"

    with pytest.raises(ValueError, match="Account mismatch"):
        evaluate_finding(event)


def test_rejects_invalid_severity(event):
    event["detail"]["severity"] = "critical"

    with pytest.raises(ValueError, match="numeric"):
        evaluate_finding(event)


def test_rejects_boolean_severity(event):
    event["detail"]["severity"] = True

    with pytest.raises(ValueError, match="numeric"):
        evaluate_finding(event)


def test_rejects_missing_finding_id(event):
    event["detail"].pop("id")

    with pytest.raises(ValueError, match="finding ID"):
        evaluate_finding(event)


def test_rejects_missing_instance_id(event):
    event["detail"]["resource"]["instanceDetails"].pop("instanceId")

    with pytest.raises(ValueError, match="instance ID"):
        evaluate_finding(event)
