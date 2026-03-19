"""
Nightwatch Monitoring Engine
=============================
The universal monitoring loop. Works with ANY adapter — no application-specific logic here.

Flow per check cycle:
  1. adapter.collect_metrics()     → current health data
  2. adapter.collect_logs()        → recent error logs
  3. adapter.run_health_checks()   → list of HealthCheck results
  4. If any check FAIL/WARN:       → llm.diagnose(metrics, logs, error)
  5. If severity >= threshold:     → alert_manager.send_alert(diagnosis)
  6. Persist incident to history

Author: Nova ⚡ | Nightwatch Platform
"""

import asyncio
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Optional

import structlog

from src.adapters.base_adapter import BaseNightwatchAdapter, CheckStatus, HealthCheck
from src.core.alert_manager import AlertManager
from src.core.llm_client import NightwatchLLMClient, LLMError

log = structlog.get_logger("nightwatch.engine")


class Incident:
    """Represents a detected monitoring incident."""

    def __init__(
        self,
        adapter_name: str,
        title: str,
        severity: str,
        failing_checks: list[HealthCheck],
        metrics: dict,
        logs: list[str],
        diagnosis: Optional[dict] = None,
    ):
        self.id = str(uuid.uuid4())[:8]
        self.adapter_name = adapter_name
        self.title = title
        self.severity = severity
        self.failing_checks = failing_checks
        self.metrics = metrics
        self.logs = logs
        self.diagnosis = diagnosis or {}
        self.started_at = datetime.now(timezone.utc)
        self.resolved_at: Optional[datetime] = None
        self.alert_sent = False

    @property
    def is_active(self) -> bool:
        return self.resolved_at is None

    @property
    def duration_seconds(self) -> float:
        end = self.resolved_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def to_dict(self) -> dict:
        # Primary component + message for UI table
        primary = self.failing_checks[0] if self.failing_checks else None
        component = primary.component if primary else self.adapter_name
        message = primary.message if len(self.failing_checks) == 1 else self.title
        return {
            "id": self.id,
            # UI reads both 'adapter' and 'adapter_name'
            "adapter": self.adapter_name,
            "adapter_name": self.adapter_name,
            "title": self.title,
            "severity": self.severity,
            # UI reads these fields directly in IncidentRow
            "component": component,
            "message": message,
            "status": "active" if self.is_active else "resolved",
            "is_active": self.is_active,
            "failing_checks": [
                {"name": c.name, "status": c.status.value,
                 "message": c.message, "component": c.component}
                for c in self.failing_checks
            ],
            "started_at": self.started_at.isoformat(),
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
            "duration_seconds": self.duration_seconds,
            "diagnosis": self.diagnosis,
            # UI reads ai_analysis directly
            "ai_analysis": (
                self.diagnosis.get("root_cause", "") +
                (" | " + self.diagnosis.get("recommendation", "") if self.diagnosis.get("recommendation") else "")
            ) if self.diagnosis else "",
            "alert_sent": self.alert_sent,
        }


class NightwatchEngine:
    """
    Universal monitoring loop. Works with ANY adapter.

    To monitor a new application, just pass a different adapter:
        engine = NightwatchEngine(adapter=MyNewAdapter(), llm=llm_client, config=cfg)
    """

    # Severities that trigger alerts (configurable)
    ALERT_SEVERITIES = {"critical", "high"}

    def __init__(
        self,
        adapter: BaseNightwatchAdapter,
        llm_client: NightwatchLLMClient,
        config: dict,
        max_incidents: int = 100,
    ):
        self.adapter = adapter
        self.llm = llm_client
        self.alert_manager = AlertManager(config.get("alerting", {}))
        self.config = config

        # Engine settings
        self.check_interval = config.get("nightwatch", {}).get("check_interval_seconds", 60)
        self.alert_severities = set(
            config.get("nightwatch", {}).get("alert_severities", ["critical", "high"])
        )
        self.enable_ai_diagnosis = config.get("nightwatch", {}).get("enable_ai_diagnosis", True)

        # State
        self._incidents: deque[Incident] = deque(maxlen=max_incidents)
        self._last_check: Optional[datetime] = None
        self._last_status: Optional[dict] = None
        self._is_running = False
        self._check_count = 0
        self._consecutive_failures = 0

    # ─── Main Loop ────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Main monitoring loop. Runs indefinitely until cancelled."""
        self._is_running = True
        app_name = self.adapter.application_name
        log.info("engine_starting", application=app_name, interval_seconds=self.check_interval)

        while self._is_running:
            cycle_start = asyncio.get_event_loop().time()
            await self.run_check_cycle()
            elapsed = asyncio.get_event_loop().time() - cycle_start

            sleep_time = max(0, self.check_interval - elapsed)
            await asyncio.sleep(sleep_time)

    def stop(self) -> None:
        self._is_running = False
        log.info("engine_stopped", application=self.adapter.application_name)

    # ─── Check Cycle ──────────────────────────────────────────────────────────

    async def run_check_cycle(self) -> dict:
        """
        Execute one full check cycle. Returns a status summary.

        Steps:
            1. Collect metrics and logs from the adapter
            2. Run all health checks
            3. If unhealthy: AI diagnosis
            4. If critical/high: send alert
            5. Record incident
        """
        self._check_count += 1
        app_name = self.adapter.application_name
        cycle_id = f"{app_name}-cycle-{self._check_count}"

        log.info("check_cycle_start", cycle=cycle_id, application=app_name)

        try:
            # Step 1: Collect data
            metrics, logs = await asyncio.gather(
                asyncio.get_event_loop().run_in_executor(None, self.adapter.collect_metrics),
                asyncio.get_event_loop().run_in_executor(None, lambda: self.adapter.collect_logs(lookback_minutes=15)),
            )

            # Step 2: Health checks
            health_checks = await asyncio.get_event_loop().run_in_executor(
                None, self.adapter.run_health_checks
            )

            failing = [c for c in health_checks if c.status in (CheckStatus.FAIL, CheckStatus.WARN)]
            critical = [c for c in health_checks if c.status == CheckStatus.FAIL]
            healthy = len(failing) == 0

            self._last_check = datetime.now(timezone.utc)

            if healthy:
                self._consecutive_failures = 0
                log.info("check_cycle_healthy", cycle=cycle_id, checks=len(health_checks))
                status = self._build_status(health_checks, metrics, "healthy", None)
                self._last_status = status
                return status

            # Step 3: Something is wrong — AI diagnosis
            self._consecutive_failures += 1
            severity = self._determine_severity(failing, critical)

            log.warning(
                "check_cycle_unhealthy",
                cycle=cycle_id,
                failing=len(failing),
                critical=len(critical),
                severity=severity,
            )

            diagnosis = {}
            if self.enable_ai_diagnosis:
                diagnosis = await self._run_ai_diagnosis(metrics, logs, failing)

            # Step 4: Create incident
            title = self._build_incident_title(failing)
            incident = Incident(
                adapter_name=app_name,
                title=title,
                severity=severity,
                failing_checks=failing,
                metrics=metrics,
                logs=logs,
                diagnosis=diagnosis,
            )
            self._incidents.append(incident)

            # Step 5: Send alert if severity warrants it
            if severity in self.alert_severities:
                await self._send_incident_alert(incident)
                incident.alert_sent = True

            status = self._build_status(health_checks, metrics, "unhealthy", incident)
            self._last_status = status
            return status

        except asyncio.CancelledError:
            raise
        except Exception as e:
            log.error("check_cycle_error", cycle=cycle_id, error=str(e), exc_info=True)
            self._consecutive_failures += 1
            return {"status": "error", "error": str(e), "cycle": cycle_id}

    # ─── AI Diagnosis ────────────────────────────────────────────────────────

    async def _run_ai_diagnosis(
        self, metrics: dict, logs: list[str], failing: list[HealthCheck]
    ) -> dict:
        """Run AI root cause analysis on failing checks."""
        error_summary = "\n".join(
            f"- {c.name}: {c.status.value} — {c.message}"
            for c in failing
        )
        try:
            diagnosis = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.llm.diagnose(
                    metrics=metrics,
                    logs=logs,
                    error=error_summary,
                    architecture=self.adapter.describe_architecture(),
                ),
            )
            log.info("ai_diagnosis_complete", severity=diagnosis.get("severity"), confidence=diagnosis.get("confidence"))
            return diagnosis
        except LLMError as e:
            log.warning("ai_diagnosis_failed", error=str(e))
            return {
                "root_cause": "AI diagnosis unavailable",
                "severity": "unknown",
                "recommendation": f"Investigate failing checks: {error_summary}",
                "auto_fix_possible": False,
                "confidence": 0.0,
            }

    # ─── Alerting ─────────────────────────────────────────────────────────────

    async def _send_incident_alert(self, incident: Incident) -> None:
        """Send alert for an incident."""
        failing_list = "\n".join(
            f"• {c.name}: {c.message}" for c in incident.failing_checks
        )
        body = f"**Failing Checks:**\n{failing_list}"

        if incident.diagnosis:
            body += f"\n\n**Root Cause (AI):** {incident.diagnosis.get('root_cause', 'Unknown')}"
            body += f"\n**Recommendation:** {incident.diagnosis.get('recommendation', 'Manual investigation required')}"

        metadata = {
            "incident_id": incident.id,
            "failing_checks": len(incident.failing_checks),
            "consecutive_failures": self._consecutive_failures,
            "adapter": incident.adapter_name,
        }

        if incident.diagnosis.get("auto_fix_possible"):
            metadata["auto_fix"] = incident.diagnosis.get("auto_fix_command", "N/A")

        await self.alert_manager.send_alert(
            title=incident.title,
            body=body,
            severity=incident.severity,
            application=incident.adapter_name,
            metadata=metadata,
            incident_id=incident.id,
            dedup_key=f"{incident.adapter_name}-{incident.severity}",
        )

    # ─── Status / History ─────────────────────────────────────────────────────

    def get_status(self) -> dict:
        """Return current status summary."""
        return self._last_status or {
            "status": "starting",
            "application": self.adapter.application_name,
            "last_check": None,
            "check_count": self._check_count,
        }

    def get_incidents(self, limit: int = 20, active_only: bool = False) -> list[dict]:
        """Return recent incidents."""
        incidents = list(self._incidents)
        if active_only:
            incidents = [i for i in incidents if i.is_active]
        return [i.to_dict() for i in reversed(incidents[:limit])]

    def get_active_incidents(self) -> list[dict]:
        return self.get_incidents(active_only=True)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _determine_severity(self, failing: list[HealthCheck], critical: list[HealthCheck]) -> str:
        """Determine overall incident severity from failing checks."""
        if not failing:
            return "low"
        if len(critical) >= 2:
            return "critical"
        if len(critical) >= 1:
            return "high"
        if len(failing) >= 3:
            return "high"
        return "medium"

    def _build_incident_title(self, failing: list[HealthCheck]) -> str:
        """Build a descriptive incident title."""
        app = self.adapter.application_name
        if len(failing) == 1:
            return f"{app}: {failing[0].name} {failing[0].status.value}"
        return f"{app}: {len(failing)} checks failing ({', '.join(c.name for c in failing[:3])}{'...' if len(failing) > 3 else ''})"

    def _build_status(
        self,
        health_checks: list[HealthCheck],
        metrics: dict,
        overall: str,
        incident: Optional[Incident],
    ) -> dict:
        # Group checks by component to build the component list the UI AdapterCard reads
        components_map: dict = {}
        for c in health_checks:
            comp_key = c.component or "General"
            if comp_key not in components_map:
                components_map[comp_key] = {
                    "name": comp_key,
                    "type": "service",
                    "status": "healthy",
                    "last_seen": datetime.now(timezone.utc).isoformat(),
                    "checks": [],
                }
            entry = components_map[comp_key]
            entry["checks"].append({
                "name": c.name, "status": c.status.value, "message": c.message
            })
            # Downgrade component status if any check is failing
            if c.status == CheckStatus.FAIL:
                entry["status"] = "unhealthy"
            elif c.status == CheckStatus.WARN and entry["status"] == "healthy":
                entry["status"] = "degraded"

        return {
            "status": overall,
            "application": self.adapter.application_name,
            "last_check": self._last_check.isoformat() if self._last_check else None,
            "check_count": self._check_count,
            "consecutive_failures": self._consecutive_failures,
            # Flat list for raw access
            "health_checks": [
                {"name": c.name, "status": c.status.value,
                 "message": c.message, "component": c.component}
                for c in health_checks
            ],
            # Nested structure the UI AdapterCard reads: data.details.components
            "details": {
                "components": list(components_map.values()),
                "total_checks": len(health_checks),
                "failing_checks": sum(1 for c in health_checks if c.status.value in ("fail", "warn")),
            },
            "metrics_summary": {k: v for k, v in list(metrics.items())[:10]},
            "active_incident": incident.to_dict() if incident else None,
        }

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def check_count(self) -> int:
        return self._check_count
