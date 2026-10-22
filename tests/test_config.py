import pytest

from src.config import validate_configuration


def test_local_mode_does_not_require_aws_settings():
    validate_configuration({"APP_ENV": "local"})


def test_production_mode_accepts_required_settings():
    validate_configuration({
        "APP_ENV": "production",
        "IDEMPOTENCY_TABLE": "guardduty-idempotency",
        "SNS_TOPIC_ARN": (
            "arn:aws:sns:us-east-1:111122223333:security-alerts"
        ),
    })


@pytest.mark.parametrize(
    "missing_setting",
    ["IDEMPOTENCY_TABLE", "SNS_TOPIC_ARN"],
)
def test_production_mode_rejects_missing_settings(missing_setting):
    settings = {
        "APP_ENV": "production",
        "IDEMPOTENCY_TABLE": "guardduty-idempotency",
        "SNS_TOPIC_ARN": (
            "arn:aws:sns:us-east-1:111122223333:security-alerts"
        ),
    }
    settings.pop(missing_setting)

    with pytest.raises(ValueError, match="Missing required"):
        validate_configuration(settings)


def test_unknown_environment_is_rejected():
    with pytest.raises(ValueError, match="APP_ENV"):
        validate_configuration({"APP_ENV": "staging"})

def test_production_mode_rejects_blank_required_settings():
    with pytest.raises(ValueError, match="Missing required"):
        validate_configuration({
            "APP_ENV": "production",
            "IDEMPOTENCY_TABLE": "   ",
            "SNS_TOPIC_ARN": "",
        })


def test_environment_names_are_case_insensitive():
    validate_configuration({
        "APP_ENV": "LOCAL",
    })
