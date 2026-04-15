"""
Nightwatch Config Loader
========================
Loads YAML config with ${ENV_VAR} substitution.
All config can be overridden by environment variables.

Usage:
    from src.core.config import NightwatchConfig
    cfg = NightwatchConfig.load("config/nightwatch.yaml")
"""

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml


_ENV_VAR_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _substitute_env_vars(value: Any) -> Any:
    """Recursively substitute ${ENV_VAR} patterns in config values."""
    if isinstance(value, str):
        def _replace(match: re.Match) -> str:
            var_name = match.group(1)
            env_val = os.environ.get(var_name, "")
            if not env_val:
                import structlog
                log = structlog.get_logger()
                log.warning("env_var_not_set", variable=var_name)
            return env_val
        return _ENV_VAR_PATTERN.sub(_replace, value)
    elif isinstance(value, dict):
        return {k: _substitute_env_vars(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_substitute_env_vars(item) for item in value]
    return value


class NightwatchConfig:
    """Loaded, validated Nightwatch configuration."""

    def __init__(self, raw: dict):
        self._raw = raw

    @classmethod
    def load(cls, config_path: str) -> "NightwatchConfig":
        """Load config from a YAML file with env-var substitution."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(path) as f:
            raw = yaml.safe_load(f)

        resolved = _substitute_env_vars(raw)
        return cls(resolved)

    @classmethod
    def load_adapter_config(cls, config_file: str, base_dir: Optional[str] = None) -> dict:
        """Load an adapter-specific config file."""
        if base_dir:
            path = Path(base_dir) / config_file
        else:
            path = Path(config_file)

        if not path.exists():
            # Try relative to nightwatch root
            nightwatch_root = Path(__file__).parent.parent.parent
            path = nightwatch_root / "config" / config_file

        if not path.exists():
            raise FileNotFoundError(f"Adapter config not found: {config_file}")

        with open(path) as f:
            raw = yaml.safe_load(f)

        return _substitute_env_vars(raw)

    # ─── Accessors ────────────────────────────────────────────────────────────

    @property
    def nightwatch(self) -> dict:
        return self._raw.get("nightwatch", {})

    @property
    def check_interval_seconds(self) -> int:
        return self.nightwatch.get("check_interval_seconds", 60)

    @property
    def max_incidents_history(self) -> int:
        return self.nightwatch.get("max_incidents_history", 100)

    @property
    def llm(self) -> dict:
        return self._raw.get("llm", {})

    @property
    def llm_provider(self) -> str:
        return self.llm.get("provider", "anthropic")

    @property
    def remediation_llm(self) -> dict:
        """Optional dedicated LLM for auto-remediation / healing. Falls back to primary `llm`."""
        return self._raw.get("remediation_llm", {}) or self.llm

    @property
    def adapters(self) -> list:
        return self._raw.get("adapters", [])

    @property
    def alerting(self) -> dict:
        return self._raw.get("alerting", {})

    @property
    def api(self) -> dict:
        return self._raw.get("api", {})

    def get_adapter_configs(self) -> list:
        """Return only enabled adapters."""
        return [a for a in self.adapters if a.get("enabled", True)]

    def raw(self) -> dict:
        return self._raw
