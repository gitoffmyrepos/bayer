"""Fail-closed capability gate for Nightwatch remediation components."""

import os


_ENABLED_VALUES = {"1", "true", "yes", "on"}


def remediation_enabled(config: dict) -> bool:
    """Return true only when both deployment and application opt in.

    Requiring two independent controls prevents a legacy ``auto_remediate``
    configuration from enabling write-capable clients in an observe-only
    deployment.
    """

    env_enabled = (
        os.getenv("REMEDIATION_ENABLED", "false").strip().lower()
        in _ENABLED_VALUES
    )
    return env_enabled and config.get("healing", {}).get("mode") == "auto_remediate"
