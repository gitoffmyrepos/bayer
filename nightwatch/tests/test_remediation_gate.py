import pytest
from types import SimpleNamespace

from src.adapters.base_adapter import (
    BaseNightwatchAdapter,
    CheckStatus,
    Component,
    HealthCheck,
)
from src.core.config import NightwatchConfig
from src.core.engine import NightwatchEngine
from src.core.remediation_gate import remediation_enabled
from src.api.main import generate_report


def test_remediation_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)

    assert remediation_enabled({"healing": {"mode": "auto_remediate"}}) is False


def test_remediation_requires_env_and_config(monkeypatch):
    monkeypatch.setenv("REMEDIATION_ENABLED", "true")

    assert remediation_enabled({"healing": {"mode": "auto_remediate"}}) is True
    assert remediation_enabled({"healing": {"mode": "observe_only"}}) is False


def test_remediation_rejects_unrecognized_env_values(monkeypatch):
    monkeypatch.setenv("REMEDIATION_ENABLED", "enabled")

    assert remediation_enabled({"healing": {"mode": "auto_remediate"}}) is False


def test_remediation_llm_is_loaded_from_enabled_healing_config(monkeypatch):
    monkeypatch.setenv("REMEDIATION_ENABLED", "true")
    raw = {
        "llm": {"provider": "ollama", "model": "qwen3:14b"},
        "healing": {
            "mode": "auto_remediate",
            "remediation_llm": {
                "provider": "anthropic",
                "model": "MiniMax-M2.7",
            },
        },
    }
    config = NightwatchConfig(raw)

    assert remediation_enabled(config.raw()) is True
    assert config.remediation_llm == raw["healing"]["remediation_llm"]


class _UnknownAdapter(BaseNightwatchAdapter):
    @property
    def application_name(self):
        return "unknown-demo"

    def collect_metrics(self):
        return {"eks": []}

    def collect_logs(self, lookback_minutes=15):
        return []

    def run_health_checks(self):
        return [
            HealthCheck(
                name="aws_eks_collection",
                status=CheckStatus.UNKNOWN,
                message="EKS inventory unavailable",
                component="AWS Provider",
            )
        ]

    def get_component_inventory(self):
        return [Component("aws", "provider", "AWS Provider")]


class _UnusedLLM:
    model = "unused"


@pytest.mark.asyncio
async def test_unknown_collection_check_never_produces_healthy_cycle(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)
    engine = NightwatchEngine(
        adapter=_UnknownAdapter({}),
        llm_client=_UnusedLLM(),
        config={
            "nightwatch": {"enable_ai_diagnosis": False},
            "healing": {"mode": "observe_only"},
            "alerting": {},
        },
    )

    status = await engine.run_check_cycle()

    assert status["status"] == "degraded"
    assert status["details"]["failing_checks"] == 1
    assert status["details"]["components"][0]["status"] == "unknown"
    assert status["active_incident"] is not None


@pytest.mark.asyncio
async def test_report_accepts_adapter_application_name():
    class ReportEngine:
        adapter = SimpleNamespace(application_name="AWS Infrastructure Estate")

        def get_incidents(self, limit=100):
            return [{"id": "incident-1", "title": "capacity mismatch"}]

    class ReportLLM:
        def generate_incident_report(self, incident):
            return f"report for {incident['id']}"

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                engines={"aws-infrastructure": ReportEngine()},
                llm_client=ReportLLM(),
            )
        )
    )

    response = await generate_report(
        request,
        {"incident_id": "incident-1", "adapter": "AWS Infrastructure Estate"},
    )

    assert response == {
        "incident_id": "incident-1",
        "report": "report for incident-1",
    }
