
from unittest.mock import MagicMock

import pytest

from src.metrics import PipelineMetrics


def test_record_logs_metric_when_cloudwatch_is_disabled(caplog):
    metrics = PipelineMetrics()

    with caplog.at_level("INFO"):
        metrics.record("FindingsProcessed")

    assert "FindingsProcessed" in caplog.text
    assert "pipeline_metric" in caplog.text


def test_record_publishes_metric_to_cloudwatch():
    mock_cloudwatch = MagicMock()
    metrics = PipelineMetrics(client=mock_cloudwatch)

    metrics.record("AlertsPublished", 1)

    mock_cloudwatch.put_metric_data.assert_called_once_with(
        Namespace="SecureGuardDutyPipeline",
        MetricData=[{
            "MetricName": "AlertsPublished",
            "Value": 1,
            "Unit": "Count",
        }],
    )


def test_empty_metric_name_is_rejected():
    metrics = PipelineMetrics()

    with pytest.raises(ValueError, match="Metric name is required"):
        metrics.record("")


def test_boolean_metric_value_is_rejected():
    metrics = PipelineMetrics()

    with pytest.raises(ValueError, match="Metric value must be numeric"):
        metrics.record("FindingsProcessed", True)
