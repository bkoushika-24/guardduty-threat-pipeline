from typing import Any

SEVERITY_THRESHOLD = 7.0


def evaluate_finding(event: dict[str, Any]) -> dict[str, Any]:
    """Validate a GuardDuty event and decide whether to notify."""

    if not isinstance(event, dict):
        raise ValueError("Event must be a JSON object")

    if event.get("source") != "aws.guardduty":
        raise ValueError("Unexpected event source")

    if event.get("detail-type") != "GuardDuty Finding":
        raise ValueError("Unexpected event type")

    detail = event.get("detail")
    if not isinstance(detail, dict):
        raise ValueError("Missing or invalid finding detail")

    finding_id = detail.get("id")
    account = event.get("account")
    region = event.get("region")
    severity = detail.get("severity")

    if not isinstance(finding_id, str) or not finding_id.strip():
        raise ValueError("Missing finding ID")

    if not isinstance(account, str) or not account.isdigit() or len(account) != 12:
        raise ValueError("Invalid event account")

    if detail.get("accountId") != account:
        raise ValueError("Account mismatch")

    if not isinstance(region, str) or not region.strip():
        raise ValueError("Missing event Region")

    if detail.get("region") != region:
        raise ValueError("Region mismatch")

    if isinstance(severity, bool) or not isinstance(severity, (int, float)):
        raise ValueError("Severity must be numeric")

    if not 0 <= severity <= 10:
        raise ValueError("Severity must be between 0 and 10")

    resource = detail.get("resource")
    if not isinstance(resource, dict):
        raise ValueError("Missing resource details")

    resource_type = resource.get("resourceType")
    if not isinstance(resource_type, str) or not resource_type:
        raise ValueError("Missing resource type")

    resource_id = None
    if resource_type == "Instance":
        instance_details = resource.get("instanceDetails")
        if not isinstance(instance_details, dict):
            raise ValueError("Missing EC2 instance details")

        resource_id = instance_details.get("instanceId")
        if not isinstance(resource_id, str) or not resource_id.strip():
            raise ValueError("Missing EC2 instance ID")

    should_notify = severity >= SEVERITY_THRESHOLD

    return {
        "finding_id": finding_id,
        "severity": severity,
        "account": account,
        "region": region,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "decision": "NOTIFY" if should_notify else "IGNORE",
        "reason": (
            "Severity meets notification threshold"
            if should_notify
            else "Severity below notification threshold"
        ),
    }
