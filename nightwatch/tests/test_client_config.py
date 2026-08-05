"""
Unit tests for src.k8s.client_config.normalize_incluster_bearer.

Reproduces the kubernetes-client in-cluster auth bug where the SA token is
stored under api_key['authorization'] with a lowercase 'bearer ' scheme while
Configuration.auth_settings() only emits an Authorization header for
api_key['BearerToken'] — causing system:anonymous 403s.
"""

from src.k8s.client_config import (
    configure_incluster_bearer,
    normalize_incluster_bearer,
)


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


def test_refresh_hook_keeps_rotated_token_normalized():
    cfg = _FakeConfiguration(api_key={"authorization": "bearer TOKEN123"})

    def rotate(configuration):
        configuration.api_key["authorization"] = "bearer TOKEN456"

    cfg.refresh_api_key_hook = rotate
    configure_incluster_bearer(cfg)

    cfg.refresh_api_key_hook(cfg)

    assert cfg.auth_settings()["BearerToken"]["value"] == "Bearer TOKEN456"


def test_refresh_hook_survives_loader_reinstalling_itself():
    cfg = _FakeConfiguration(api_key={"BearerToken": "bearer TOKEN123"})
    tokens = iter(["TOKEN456", "TOKEN789"])

    def refresh(configuration):
        configuration.api_key["BearerToken"] = f"bearer {next(tokens)}"
        configuration.refresh_api_key_hook = refresh

    cfg.refresh_api_key_hook = refresh
    configure_incluster_bearer(cfg)

    cfg.refresh_api_key_hook(cfg)
    cfg.refresh_api_key_hook(cfg)

    assert cfg.auth_settings()["BearerToken"]["value"] == "Bearer TOKEN789"


def test_configure_incluster_bearer_is_idempotent():
    cfg = _FakeConfiguration(api_key={"authorization": "bearer TOKEN123"})
    configure_incluster_bearer(cfg)
    first_hook = cfg.refresh_api_key_hook

    configure_incluster_bearer(cfg)

    assert cfg.refresh_api_key_hook is first_hook
