
import json
import os
from typing import Any

import boto3


class SNSNotifier:
    """Publish security finding alerts to an SNS topic."""

    def __init__(
        self,
        topic_arn: str,
        region_name: str = "us-east-1",
        client: Any = None,
    ):
        if not topic_arn:
            raise ValueError("SNS topic ARN is required")

        self.topic_arn = topic_arn
        self.client = client or boto3.client(
            "sns",
            region_name=region_name,
        )

    def publish_finding(self, finding: dict[str, Any]) -> str:
        """Publish a structured alert and return the SNS message ID."""
        message = {
            "event": "GuardDutyFinding",
            "finding_id": finding["finding_id"],
            "account": finding["account"],
            "region": finding["region"],
            "severity": finding["severity"],
            "resource_type": finding["resource_type"],
            "resource_id": finding["resource_id"],
            "decision": finding["decision"],
            "reason": finding["reason"],
        }

        response = self.client.publish(
            TopicArn=self.topic_arn,
            Subject=f"GuardDuty alert: {finding['finding_id']}",
            Message=json.dumps(message),
        )

        message_id = response.get("MessageId")
        if not message_id:
            raise RuntimeError("SNS publish returned no MessageId")

        return message_id


def build_notifier():
    """Create an SNS notifier only when a topic is configured."""
    topic_arn = os.getenv("SNS_TOPIC_ARN")

    if not topic_arn:
        return None

    return SNSNotifier(
        topic_arn=topic_arn,
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )
