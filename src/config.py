
import os
from typing import Mapping


def validate_configuration(
    environ: Mapping[str, str] | None = None,
) -> None:
    """Validate required settings when running in production."""
    env = os.environ if environ is None else environ

    app_env = env.get("APP_ENV", "local").strip().lower()

    if app_env not in {"local", "production"}:
        raise ValueError(
            "APP_ENV must be either 'local' or 'production'"
        )

    if app_env == "local":
        return

    required_settings = (
        "IDEMPOTENCY_TABLE",
        "SNS_TOPIC_ARN",
    )

    missing = [
        name for name in required_settings
        if not env.get(name, "").strip()
    ]

    if missing:
        raise ValueError(
            "Missing required production settings: "
            + ", ".join(missing)
        )
