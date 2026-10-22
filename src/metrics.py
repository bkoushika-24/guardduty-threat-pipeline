
import logging
import os
from typing import Any

import boto3

logger = logging.getLogger(__name__)


class PipelineMetrics:
    """Record operational metrics locally or in CloudWatch."""

    NAMESPACE = "SecureGuardDutyPipeline"

    def __init__(self, client: Any = None):
        self.client = client

    def record(self, metric_name: str, value: float = 1.0) -> None:
        """Record one count metric, using CloudWatch when configured."""
        if not metric_name:
            raise ValueError("Metric name is required")

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("Metric value must be numeric")

        if self.client is None:
            logger.info(
                "pipeline_metric name=%s value=%s",
                metric_name,
                value,
            )
            return

        self.client.put_metric_data(
            Namespace=self.NAMESPACE,
            MetricData=[{
                "MetricName": metric_name,
                "Value": value,
                "Unit": "Count",
            }],
        )


def build_metrics() -> PipelineMetrics:
    """Enable CloudWatch metrics when explicitly configured."""
    if os.getenv("CLOUDWATCH_METRICS_ENABLED", "").lower() != "true":
        return PipelineMetrics()

    client = boto3.client(
        "cloudwatch",
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )
    return PipelineMetrics(client=client)
