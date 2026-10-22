
import json
from unittest.mock import MagicMock

import pytest

from src.notifications import SNSNotifier


@pytest.fixture
def finding():
    return {
        "finding_id": "demo-finding-001",
        "account": "111122223333",
        "region": "us-east-1",
        "severity": 8.2,
        "resource_type": "Instance",
        "resource_id": "i-0123456789abcdef0",
        "decision": "NOTIFY",
        "reason": "Severity meets notification threshold",
    }


def test_publish_finding_sends_structured_alert(finding):
    mock_sns = MagicMock()
    mock_sns.publish.return_value = {
        "MessageId": "mock-message-123"
    }

    notifier = SNSNotifier(
        topic_arn="arn:aws:sns:us-east-1:111122223333:security-alerts",
        client=mock_sns,
    )

    message_id = notifier.publish_finding(finding)

    assert message_id == "mock-message-123"
    mock_sns.publish.assert_called_once()

    call_args = mock_sns.publish.call_args.kwargs
    assert call_args["Subject"] == (
        "GuardDuty alert: demo-finding-001"
    )
    assert call_args["TopicArn"].endswith(":security-alerts")

    payload = json.loads(call_args["Message"])
    assert payload["finding_id"] == "demo-finding-001"
    assert payload["severity"] == 8.2
    assert payload["decision"] == "NOTIFY"


def test_publish_finding_fails_without_message_id(finding):
    mock_sns = MagicMock()
    mock_sns.publish.return_value = {}

    notifier = SNSNotifier(
        topic_arn="arn:aws:sns:us-east-1:111122223333:security-alerts",
        client=mock_sns,
    )

    with pytest.raises(RuntimeError, match="no MessageId"):
        notifier.publish_finding(finding)


def test_empty_topic_arn_is_rejected():
    with pytest.raises(ValueError, match="SNS topic ARN is required"):
        SNSNotifier(topic_arn="", client=MagicMock())
