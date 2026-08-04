import pytest

from src.core.llm_settings import LLMSettingsError, LLMSettingsStore


def test_settings_expose_metadata_without_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-provider-key")
    store = LLMSettingsStore(
        {"provider": "openai", "model": "configured-model", "base_url": ""},
    )

    public = store.public_settings()
    assert public["api_key_configured"] is True
    assert "private-provider-key" not in str(public)


def test_cloud_provider_requires_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    store = LLMSettingsStore(
        {"provider": "ollama", "model": "local-model", "base_url": "http://ollama:11434"}
    )

    with pytest.raises(LLMSettingsError, match="API key is required"):
        store.candidate_config(
            provider="anthropic",
            model="configured-model",
            base_url="",
            api_key=None,
        )


def test_ollama_requires_absolute_endpoint():
    store = LLMSettingsStore({})

    with pytest.raises(LLMSettingsError, match="absolute HTTP"):
        store.candidate_config(
            provider="ollama",
            model="local-model",
            base_url="ollama:11434",
            api_key=None,
        )
