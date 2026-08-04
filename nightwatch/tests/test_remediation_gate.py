import asyncio

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
from fastapi import HTTPException

from src.api.main import _build_request_llm, generate_report
from src.core.llm_client import LLMError
from src.core.llm_settings import LLMSettingsStore


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
async def test_unchanged_findings_reuse_ai_diagnosis(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)

    class CountingLLM:
        model = "configured-model"

        def __init__(self):
            self.calls = 0

        def diagnose(self, **_kwargs):
            self.calls += 1
            return {
                "root_cause": "observed API collection failure",
                "severity": "high",
                "recommendation": "inspect the reported API error",
                "auto_fix_possible": False,
                "auto_fix_command": None,
                "confidence": 0.9,
            }

    llm = CountingLLM()
    engine = NightwatchEngine(
        adapter=_UnknownAdapter({}),
        llm_client=llm,
        config={
            "nightwatch": {
                "enable_ai_diagnosis": True,
                "ai_diagnosis_refresh_seconds": 3600,
            },
            "healing": {"mode": "observe_only"},
            "alerting": {},
        },
    )

    first = await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()
    second = await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()

    assert llm.calls == 1
    incidents = engine.get_incidents(limit=2)
    assert first["active_incident"]["ai_diagnosis_status"] == "pending"
    assert second["active_incident"]["ai_diagnosis_status"] == "pending"
    assert all(incident["ai_diagnosis_status"] == "complete" for incident in incidents)
    assert incidents[0]["diagnosis"] == incidents[1]["diagnosis"]
    await engine.stop()


@pytest.mark.asyncio
async def test_background_diagnosis_never_blocks_incident_collection(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)
    engine = NightwatchEngine(
        adapter=_UnknownAdapter({}),
        llm_client=_UnusedLLM(),
        config={
            "nightwatch": {"enable_ai_diagnosis": True},
            "healing": {"mode": "observe_only"},
            "alerting": {},
        },
    )
    diagnosis_started = asyncio.Event()
    release_diagnosis = asyncio.Event()

    async def slow_diagnosis(*_args, **_kwargs):
        diagnosis_started.set()
        await release_diagnosis.wait()
        return {
            "root_cause": "observed API collection failure",
            "severity": "high",
            "recommendation": "inspect the reported API error",
            "auto_fix_possible": False,
            "auto_fix_command": None,
            "confidence": 0.9,
        }

    engine._run_ai_diagnosis = slow_diagnosis

    status = await engine.run_check_cycle()

    assert status["active_incident"] is not None
    assert status["active_incident"]["ai_diagnosis_status"] == "pending"
    await diagnosis_started.wait()
    release_diagnosis.set()
    await engine.wait_for_ai_diagnosis()

    enriched = engine.get_incidents(limit=1)[0]
    assert enriched["ai_diagnosis_status"] == "complete"
    assert enriched["diagnosis"]["root_cause"] == "observed API collection failure"
    assert enriched["ai_diagnosis_model"] == "unused"
    await engine.stop()


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


def test_request_scoped_provider_rejects_arbitrary_ollama_endpoint():
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                llm_settings=LLMSettingsStore({
                    "provider": "ollama",
                    "model": "installed-model",
                    "base_url": "http://ollama:11434",
                })
            )
        )
    )

    with pytest.raises(HTTPException) as exc:
        _build_request_llm(request, {
            "provider": "ollama",
            "model": "installed-model",
            "base_url": "http://cluster-service.private",
        })

    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_report_maps_provider_failure_to_service_unavailable():
    class ReportEngine:
        adapter = SimpleNamespace(application_name="Kubernetes")

        def get_incidents(self, limit=100):
            return [{"id": "incident-1", "title": "capacity mismatch"}]

    class UnavailableLLM:
        provider = "ollama"
        model = "installed-model"

        def generate_incident_report(self, _incident):
            raise LLMError("provider queue full")

    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                engines={"kubernetes": ReportEngine()},
                llm_client=UnavailableLLM(),
            )
        )
    )

    with pytest.raises(HTTPException) as exc:
        await generate_report(request, {"incident_id": "incident-1"})

    assert exc.value.status_code == 503
    assert "configure another provider" in exc.value.detail
