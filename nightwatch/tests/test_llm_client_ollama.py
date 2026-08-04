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
            "options": {"temperature": 0.1, "num_predict": 2048},
        },
    )
    response.raise_for_status.assert_called_once_with()
    assert result == "grounded analysis"
