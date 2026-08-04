"""Secret-safe LLM provider configuration metadata and request validation."""

from __future__ import annotations

import os
from urllib.parse import urlparse


class LLMSettingsError(ValueError):
    """Raised when request-scoped LLM settings are invalid."""


class LLMSettingsStore:
    """Expose deployment settings without exposing credential values."""

    PROVIDERS = ("ollama", "openai", "anthropic", "deepseek")
    _ENV_KEYS = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
    }

    def __init__(self, base_config: dict):
        self._base_config = dict(base_config)

    @property
    def provider(self) -> str:
        return str(self._base_config.get("provider") or "").lower()

    def _api_key(self, provider: str) -> str:
        env_name = self._ENV_KEYS.get(provider)
        if env_name and os.environ.get(env_name):
            return os.environ[env_name]
        if provider == self.provider:
            return str(self._base_config.get("api_key") or "")
        return ""

    def client_config(self) -> dict:
        config = dict(self._base_config)
        config["provider"] = self.provider
        config["api_key"] = self._api_key(self.provider)
        return config

    def public_settings(self) -> dict:
        config = self.client_config()
        provider = config.get("provider", "")
        return {
            "provider": provider,
            "model": config.get("model") or "",
            "base_url": config.get("base_url") or "",
            "api_key_configured": provider == "ollama" or bool(config.get("api_key")),
            "configured": self._is_complete(config),
            "configured_providers": {
                name: (name == "ollama" or bool(self._api_key(name)))
                for name in self.PROVIDERS
            },
            "persistence_enabled": False,
        }

    def candidate_config(
        self,
        *,
        provider: str,
        model: str,
        base_url: str,
        api_key: str | None,
    ) -> dict:
        provider = provider.strip().lower()
        model = model.strip()
        base_url = base_url.strip().rstrip("/")
        self._validate(provider, model, base_url)
        config = dict(self._base_config)
        config.update({"provider": provider, "model": model, "base_url": base_url})
        config["api_key"] = api_key.strip() if api_key and api_key.strip() else self._api_key(provider)
        if not self._is_complete(config):
            raise LLMSettingsError(f"An API key is required for provider '{provider}'")
        return config

    @staticmethod
    def _is_complete(config: dict) -> bool:
        if not config.get("provider") or not config.get("model"):
            return False
        if config["provider"] == "ollama":
            return bool(config.get("base_url"))
        return bool(config.get("api_key"))

    def _validate(self, provider: str, model: str, base_url: str) -> None:
        if provider not in self.PROVIDERS:
            raise LLMSettingsError(f"Unsupported LLM provider '{provider}'")
        if not model:
            raise LLMSettingsError("model is required")
        if provider == "ollama" and not base_url:
            raise LLMSettingsError("base_url is required for Ollama")
        if base_url:
            parsed = urlparse(base_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise LLMSettingsError("base_url must be an absolute HTTP(S) URL")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise LLMSettingsError("base_url must not contain credentials, query parameters, or fragments")
