"""
Unit tests for src.k8s.client_config.normalize_incluster_bearer.

Reproduces the kubernetes-client in-cluster auth bug where the SA token is
stored under api_key['authorization'] with a lowercase 'bearer ' scheme while
Configuration.auth_settings() only emits an Authorization header for
api_key['BearerToken'] — causing system:anonymous 403s.
"""

from src.k8s.client_config import normalize_incluster_bearer


class _FakeConfiguration:
    """Minimal stand-in mimicking kubernetes.client.Configuration api_key slots."""

    def __init__(self, api_key=None):
        self.api_key = dict(api_key or {})
        self.api_key_prefix = {}

    # Mirrors the real auth_settings(): only emits a header for BearerToken.
    def auth_settings(self):
        auth = {}
        if "BearerToken" in self.api_key:
            prefix = self.api_key_prefix.get("BearerToken")
            value = self.api_key["BearerToken"]
            auth["BearerToken"] = {
                "key": "authorization",
                "value": f"{prefix} {value}" if prefix else value,
            }
        return auth


def test_normalizes_lowercase_bearer_authorization_to_bearer_token():
    cfg = _FakeConfiguration(api_key={"authorization": "bearer TOKEN123"})
    # Before: auth_settings empty -> no Authorization header -> system:anonymous.
    assert cfg.auth_settings() == {}

    normalize_incluster_bearer(cfg)

    assert cfg.api_key["BearerToken"] == "TOKEN123"
    assert cfg.api_key_prefix["BearerToken"] == "Bearer"
    settings = cfg.auth_settings()
    assert settings["BearerToken"]["value"] == "Bearer TOKEN123"


def test_idempotent_on_repeated_calls():
    cfg = _FakeConfiguration(api_key={"authorization": "bearer TOKEN123"})
    normalize_incluster_bearer(cfg)
    normalize_incluster_bearer(cfg)
    assert cfg.api_key["BearerToken"] == "TOKEN123"
    assert cfg.api_key_prefix["BearerToken"] == "Bearer"


def test_handles_already_capitalized_bearer_token_slot():
    cfg = _FakeConfiguration(api_key={"BearerToken": "Bearer TOKEN123"})
    normalize_incluster_bearer(cfg)
    assert cfg.api_key["BearerToken"] == "TOKEN123"
    assert cfg.auth_settings()["BearerToken"]["value"] == "Bearer TOKEN123"


def test_noop_when_no_token_present():
    cfg = _FakeConfiguration(api_key={})
    normalize_incluster_bearer(cfg)
    assert "BearerToken" not in cfg.api_key
    assert cfg.auth_settings() == {}
