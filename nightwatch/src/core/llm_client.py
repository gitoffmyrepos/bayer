"""
Nightwatch Multi-LLM Client
============================
Routes AI requests to any configured LLM provider:
  - Anthropic Claude (claude-3-haiku, claude-3-sonnet, etc.)
  - OpenAI (gpt-4o, gpt-4o-mini, etc.)
  - DeepSeek (deepseek-chat — OpenAI-compatible API)
  - Ollama (local models: qwen3:14b, llama3, mistral, etc.)

Configured via nightwatch.yaml [llm] section or env vars.

Author: Nova ⚡ | Nightwatch Platform
"""

import json
import time
from typing import Optional

import httpx
import structlog

log = structlog.get_logger("nightwatch.llm")


class LLMError(Exception):
    """Raised when LLM request fails after retries."""
    pass


class NightwatchLLMClient:
    """
    Universal LLM client for Nightwatch.

    Routes to any configured provider. All methods return plain text or
    structured dicts — no provider-specific objects leak out.

    Config examples:
        {"provider": "anthropic", "model": "claude-3-haiku-20240307", "api_key": "sk-ant-..."}
        {"provider": "openai",    "model": "gpt-4o-mini",              "api_key": "sk-..."}
        {"provider": "deepseek",  "model": "deepseek-chat",            "api_key": "sk-..."}
        {"provider": "ollama",    "model": "qwen3:14b",                "base_url": "http://localhost:11434"}
    """

    PROVIDERS = ["openai", "anthropic", "deepseek", "ollama"]

    # DeepSeek uses OpenAI-compatible API at this base URL
    DEEPSEEK_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(self, config: dict):
        import os
        self.provider = config.get("provider", "anthropic").lower()
        self.model = config.get("model", self._default_model())
        # Fall back to environment variables if api_key not set in config
        _env_key_map = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
        }
        self.api_key = config.get("api_key", "") or os.environ.get(_env_key_map.get(self.provider, ""), "")
        self.base_url = config.get("base_url", "")
        self.timeout = config.get("timeout_seconds", 60)
        self.max_tokens = config.get("max_tokens", 2048)
        self.temperature = config.get("temperature", 0.1)

        if self.provider not in self.PROVIDERS:
            raise ValueError(f"Unknown LLM provider: {self.provider}. Must be one of {self.PROVIDERS}")

        log.info("llm_client_initialized", provider=self.provider, model=self.model)

    def _default_model(self) -> str:
        defaults = {
            "anthropic": "claude-3-haiku-20240307",
            "openai": "gpt-4o-mini",
            "deepseek": "deepseek-chat",
            "ollama": "qwen3:14b",
        }
        return defaults.get(self.provider, "claude-3-haiku-20240307")

    # ─── Public Methods ───────────────────────────────────────────────────────

    def analyze(self, context: str, question: str) -> str:
        """
        General analysis. Returns plain text response.

        Args:
            context: Background information (metrics, logs, architecture description)
            question: What to analyze / diagnose
        """
        prompt = f"""You are Nightwatch, an AI monitoring system. Analyze the following context and answer the question concisely.

CONTEXT:
{context}

QUESTION:
{question}

Respond with a clear, actionable analysis. Be concise — max 3 paragraphs."""

        return self._call(prompt)

    def diagnose(self, metrics: dict, logs: list[str], error: str, architecture: str = "") -> dict:
        """
        AI root cause diagnosis.

        Returns:
            {
                "root_cause": str,
                "severity": "critical" | "high" | "medium" | "low",
                "recommendation": str,
                "auto_fix_possible": bool,
                "auto_fix_command": str | None,
                "confidence": float  # 0.0–1.0
            }
        """
        metrics_str = json.dumps(metrics, indent=2, default=str)
        logs_str = "\n".join(logs[-50:]) if logs else "No logs available"

        prompt = f"""You are Nightwatch, an AI monitoring system performing root cause analysis.

APPLICATION ARCHITECTURE:
{architecture or "Not specified"}

CURRENT METRICS:
{metrics_str}

RECENT ERROR LOGS (last 50 lines):
{logs_str}

ERROR/TRIGGER:
{error}

Perform root cause analysis and respond with ONLY valid JSON in this exact format:
{{
  "root_cause": "Brief description of what caused this issue",
  "severity": "critical|high|medium|low",
  "recommendation": "Step-by-step remediation instructions",
  "auto_fix_possible": true/false,
  "auto_fix_command": "command or null",
  "confidence": 0.85
}}

Severity guide:
- critical: Service down, data loss risk, SLA breach imminent
- high: Degraded performance, partial failure, needs attention within 15 min
- medium: Warning condition, investigate within 1 hour
- low: Informational, no immediate action needed"""

        response_text = self._call(prompt)

        try:
            # Extract JSON from response (LLMs sometimes wrap it in markdown)
            json_match = self._extract_json(response_text)
            result = json.loads(json_match)
            # Validate expected fields
            result.setdefault("root_cause", "Unable to determine root cause")
            result.setdefault("severity", "medium")
            result.setdefault("recommendation", "Manual investigation required")
            result.setdefault("auto_fix_possible", False)
            result.setdefault("auto_fix_command", None)
            result.setdefault("confidence", 0.5)
            return result
        except (json.JSONDecodeError, ValueError) as e:
            log.warning("llm_json_parse_failed", error=str(e), raw_response=response_text[:200])
            return {
                "root_cause": response_text[:500],
                "severity": "medium",
                "recommendation": "Review the analysis above and investigate manually.",
                "auto_fix_possible": False,
                "auto_fix_command": None,
                "confidence": 0.3,
            }

    def generate_incident_report(self, incident: dict) -> str:
        """
        Generate a human-readable incident report from an incident dict.

        Args:
            incident: {
                "title": str,
                "application": str,
                "started_at": str,
                "severity": str,
                "affected_components": list,
                "metrics_snapshot": dict,
                "error_logs": list,
                "diagnosis": dict,
                "timeline": list
            }
        """
        prompt = f"""You are Nightwatch, an AI monitoring system. Generate a professional incident report.

INCIDENT DATA:
{json.dumps(incident, indent=2, default=str)}

Write a clear, concise incident report with these sections:
1. **Executive Summary** (2-3 sentences: what happened, impact, status)
2. **Root Cause** (1-2 sentences)
3. **Timeline** (bullet points)
4. **Impact** (what was affected)
5. **Remediation** (what was done or needs to be done)
6. **Prevention** (how to prevent recurrence)

Use markdown formatting. Be professional and factual."""

        return self._call(prompt)

    def summarize_health(self, health_data: dict, application: str) -> str:
        """Generate a brief health summary for status reporting."""
        prompt = f"""You are Nightwatch, an AI monitoring system. Summarize the health of {application}.

HEALTH DATA:
{json.dumps(health_data, indent=2, default=str)}

Write a 2-3 sentence health summary. Start with overall status (✅ Healthy / ⚠️ Degraded / 🔴 Critical).
Be specific about any issues found."""

        return self._call(prompt)

    # ─── Provider Routing ────────────────────────────────────────────────────

    def _call(self, prompt: str, retries: int = 2) -> str:
        """Route to the configured provider. Retries on transient failures."""
        last_error = None
        for attempt in range(retries + 1):
            try:
                if self.provider == "anthropic":
                    return self._call_anthropic(prompt)
                elif self.provider == "openai":
                    # Use configured base_url if set (e.g. Ollama OpenAI-compat), else real OpenAI
                    _oai_base = self.base_url or "https://api.openai.com/v1"
                    return self._call_openai(prompt, base_url=_oai_base)
                elif self.provider == "deepseek":
                    return self._call_openai(prompt, base_url=self.DEEPSEEK_BASE_URL)
                elif self.provider == "ollama":
                    return self._call_ollama(prompt)
            except Exception as e:
                last_error = e
                if attempt < retries:
                    wait = 2 ** attempt
                    log.warning("llm_retry", attempt=attempt + 1, wait_seconds=wait, error=str(e))
                    time.sleep(wait)

        raise LLMError(f"LLM call failed after {retries + 1} attempts: {last_error}")

    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Claude API (or any Anthropic-compatible endpoint, e.g. MiniMax)."""
        import anthropic
        # Honor base_url so Anthropic-compat providers (MiniMax) work through the same path
        kwargs = {"api_key": self.api_key}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        client = anthropic.Anthropic(**kwargs)
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text

    def _call_openai(self, prompt: str, base_url: str) -> str:
        """Call OpenAI-compatible API (OpenAI, DeepSeek)."""
        from openai import OpenAI
        client = OpenAI(api_key=self.api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content

    def _call_ollama(self, prompt: str) -> str:
        """Call local Ollama instance."""
        base_url = self.base_url or "http://localhost:11434"
        url = f"{base_url}/api/chat"

        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": self.temperature,
                    "num_predict": self.max_tokens,
                },
            })
            response.raise_for_status()
            return response.json()["response"]

    # ─── Helpers ─────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extract JSON object from text that may contain markdown fences."""
        # Try to find ```json ... ``` blocks
        import re
        json_fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_fence:
            return json_fence.group(1)

        # Try to find bare JSON object
        json_bare = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)?\}", text, re.DOTALL)
        if json_bare:
            return json_bare.group(0)

        return text  # Let the caller deal with parse failure
