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
    assert second["active_incident"]["ai_diagnosis_status"] == "complete"
    assert len(incidents) == 1
    assert incidents[0]["ai_diagnosis_status"] == "complete"
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
async def test_unavailable_issue_diagnosis_retries_without_new_incident(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)

    class RecoveringLLM:
        provider = "ollama"
        model = "qwen3:4b"

        def __init__(self):
            self.calls = 0

        def diagnose(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                raise LLMError("provider temporarily unavailable")
            return {
                "root_cause": "issue-specific analysis",
                "severity": "high",
                "recommendation": "inspect the affected resource",
                "auto_fix_possible": False,
                "auto_fix_command": None,
                "confidence": 0.9,
            }

    llm = RecoveringLLM()
    engine = NightwatchEngine(
        adapter=_UnknownAdapter({}),
        llm_client=llm,
        config={
            "nightwatch": {
                "enable_ai_diagnosis": True,
                "ai_diagnosis_retry_seconds": 900,
            },
            "healing": {"mode": "observe_only"},
            "alerting": {},
        },
    )

    await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()
    unavailable = engine.get_incidents(limit=1)[0]
    assert unavailable["ai_diagnosis_status"] == "unavailable"

    signature = next(iter(engine._ai_diagnosis_attempts))
    engine._ai_diagnosis_attempts[signature] = 0.0
    await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()

    incidents = engine.get_incidents(limit=10)
    assert llm.calls == 2
    assert len(incidents) == 1
    assert incidents[0]["ai_diagnosis_status"] == "complete"
    assert incidents[0]["diagnosis"]["root_cause"] == "issue-specific analysis"
    await engine.stop()


@pytest.mark.asyncio
async def test_changed_findings_bypass_unchanged_signature_cooldown(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)

    class ChangingAdapter(_UnknownAdapter):
        message = "EKS inventory unavailable"

        def run_health_checks(self):
            return [
                HealthCheck(
                    name="aws_eks_collection",
                    status=CheckStatus.UNKNOWN,
                    message=self.message,
                    component="AWS Provider",
                )
            ]

    class CountingLLM:
        provider = "ollama"
        model = "qwen3:4b"

        def __init__(self):
            self.calls = 0

        def diagnose(self, **_kwargs):
            self.calls += 1
            return {
                "root_cause": f"analysis {self.calls}",
                "severity": "high",
                "recommendation": "inspect the newly observed failure",
                "auto_fix_possible": False,
                "auto_fix_command": None,
                "confidence": 0.9,
            }

    adapter = ChangingAdapter({})
    llm = CountingLLM()
    engine = NightwatchEngine(
        adapter=adapter,
        llm_client=llm,
        config={
            "nightwatch": {
                "enable_ai_diagnosis": True,
                "ai_diagnosis_min_interval_seconds": 900,
                "ai_diagnosis_refresh_seconds": 3600,
            },
            "healing": {"mode": "observe_only"},
            "alerting": {},
        },
    )

    await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()
    adapter.message = "EKS authorization failed"
    await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()
    adapter.message = "EKS inventory unavailable"
    await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()

    incidents = engine.get_incidents(limit=3)
    assert llm.calls == 2
    assert all(incident["ai_diagnosis_status"] == "complete" for incident in incidents)
    assert {incident["diagnosis"]["root_cause"] for incident in incidents} == {
        "analysis 1",
        "analysis 2",
    }
    assert sum(incident["is_active"] for incident in incidents) == 1
    assert incidents[0]["diagnosis"]["root_cause"] == "analysis 1"
    await engine.stop()


@pytest.mark.asyncio
async def test_each_failing_check_gets_issue_scoped_ai_evidence(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)

    class TwoIssueAdapter(_UnknownAdapter):
        def collect_metrics(self):
            return {"cluster": {"nodes_ready": 3}, "unrelated": {"value": 9}}

        def collect_logs(self, lookback_minutes=15):
            return [
                "[api] readiness probe failed",
                "[backup] job exhausted retries",
                "[unrelated-worker] connection reset",
            ]

        def run_health_checks(self):
            return [
                HealthCheck(
                    name="deployment_api_available",
                    status=CheckStatus.FAIL,
                    message="Deployment operations/api has 0/1 replicas available",
                    component="Kubernetes Deployment",
                    metadata={"namespace": "operations", "resource_name": "api"},
                ),
                HealthCheck(
                    name="cronjob_backup_latest_run",
                    status=CheckStatus.FAIL,
                    message="CronJob operations/backup latest Job failed",
                    component="Kubernetes CronJob",
                    metadata={"namespace": "operations", "resource_name": "backup"},
                ),
            ]

    class EvidenceLLM:
        provider = "ollama"
        model = "qwen3:4b"

        def __init__(self):
            self.calls = []

        def diagnose(self, **kwargs):
            self.calls.append(kwargs)
            finding_name = kwargs["metrics"]["finding"]["name"]
            return {
                "root_cause": f"analysis for {finding_name}",
                "severity": "high",
                "recommendation": f"investigate {finding_name}",
                "auto_fix_possible": False,
                "auto_fix_command": None,
                "confidence": 0.9,
            }

    llm = EvidenceLLM()
    engine = NightwatchEngine(
        adapter=TwoIssueAdapter({}),
        llm_client=llm,
        config={
            "nightwatch": {"enable_ai_diagnosis": True},
            "healing": {"mode": "observe_only"},
            "alerting": {},
        },
    )

    await engine.run_check_cycle()
    await engine.wait_for_ai_diagnosis()

    incidents = engine.get_incidents(limit=10)
    assert len(incidents) == 2
    assert len(llm.calls) == 2
    assert {incident["diagnosis"]["root_cause"] for incident in incidents} == {
        "analysis for deployment_api_available",
        "analysis for cronjob_backup_latest_run",
    }
    assert all(len(call["metrics"]["finding"]["name"]) > 0 for call in llm.calls)
    assert all(len(call["error"].splitlines()) == 1 for call in llm.calls)
    assert all("unrelated" not in call["metrics"] for call in llm.calls)
    assert {
        call["metrics"]["finding"]["name"]: call["logs"] for call in llm.calls
    } == {
        "deployment_api_available": ["[api] readiness probe failed"],
        "cronjob_backup_latest_run": ["[backup] job exhausted retries"],
    }
    await engine.stop()


@pytest.mark.asyncio
async def test_recovered_check_resolves_its_active_incident(monkeypatch):
    monkeypatch.delenv("REMEDIATION_ENABLED", raising=False)

    class RecoveringAdapter(_UnknownAdapter):
        recovered = False

        def run_health_checks(self):
            if self.recovered:
                return [
                    HealthCheck(
                        name="aws_eks_collection",
                        status=CheckStatus.OK,
                        message="EKS inventory available",
                        component="AWS Provider",
                    )
                ]
            return super().run_health_checks()

    adapter = RecoveringAdapter({})
    engine = NightwatchEngine(
        adapter=adapter,
        llm_client=_UnusedLLM(),
        config={
            "nightwatch": {"enable_ai_diagnosis": False},
            "healing": {"mode": "observe_only"},
            "alerting": {},
        },
    )

    await engine.run_check_cycle()
    adapter.recovered = True
    status = await engine.run_check_cycle()

    incidents = engine.get_incidents(limit=10)
    assert status["status"] == "healthy"
    assert status["active_incidents"] == []
    assert len(incidents) == 1
    assert incidents[0]["status"] == "resolved"
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
