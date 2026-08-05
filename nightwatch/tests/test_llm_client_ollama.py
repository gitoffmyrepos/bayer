import json
from unittest.mock import MagicMock, patch

from src.core.llm_client import NightwatchLLMClient


def test_ollama_uses_generate_contract():
    client = NightwatchLLMClient({
        "provider": "ollama",
        "model": "qwen3:14b",
        "base_url": "http://ollama:11434",
    })
    response = MagicMock()
    response.json.return_value = {"response": "grounded analysis"}
    context = MagicMock()
    context.__enter__.return_value.post.return_value = response

    with patch("src.core.llm_client.httpx.Client", return_value=context):
        result = client._call_ollama("explain evidence")

    context.__enter__.return_value.post.assert_called_once_with(
        "http://ollama:11434/api/generate",
        json={
            "model": "qwen3:14b",
            "prompt": "explain evidence",
            "stream": False,
            "think": False,
            "options": {"temperature": 0.1, "num_predict": 2048},
        },
    )
    response.raise_for_status.assert_called_once_with()
    assert result == "grounded analysis"


def test_ollama_diagnosis_enforces_structured_output():
    client = NightwatchLLMClient({
        "provider": "ollama",
        "model": "qwen3:4b",
        "base_url": "http://ollama:11434",
    })
    diagnosis = {
        "root_cause": "The observed workload is unavailable.",
        "severity": "high",
        "recommendation": "Inspect the failing workload events.",
        "auto_fix_possible": False,
        "auto_fix_command": None,
        "confidence": 0.9,
    }
    response = MagicMock()
    response.json.return_value = {"response": json.dumps(diagnosis)}
    context = MagicMock()
    context.__enter__.return_value.post.return_value = response

    with patch("src.core.llm_client.httpx.Client", return_value=context):
        result = client.diagnose(metrics={}, logs=[], error="workload unavailable")

    payload = context.__enter__.return_value.post.call_args.kwargs["json"]
    assert payload["format"] == NightwatchLLMClient.DIAGNOSIS_SCHEMA
    assert "Root cause not established from available evidence" in payload["prompt"]
    assert "set auto_fix_possible to false" in payload["prompt"]
    assert result == diagnosis
