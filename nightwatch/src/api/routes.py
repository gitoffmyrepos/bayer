"""
Nightwatch API Routes
======================
REST endpoints for querying Nightwatch status and triggering checks.

Endpoints:
  GET  /health        — Nightwatch itself is healthy
  GET  /status        — Current monitored application status
  GET  /incidents     — Recent incidents (paginated)
  POST /check         — Trigger an immediate check cycle
  GET  /adapters      — List configured adapters and components
  GET  /metrics       — Prometheus-compatible metrics
  POST /report        — Generate AI incident report
  GET  /schedule      — Scheduler status

Author: Nova ⚡ | Nightwatch Platform
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel

import structlog

log = structlog.get_logger("nightwatch.api")

router = APIRouter()

# These are injected by main.py via app.state
def get_engines(request):
    return request.app.state.engines

def get_config(request):
    return request.app.state.config

def get_scheduler(request):
    return request.app.state.scheduler


# ─── Request/Response Models ──────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    version: str = "2.0.0"
    timestamp: str
    uptime_seconds: float


class CheckTriggerRequest(BaseModel):
    adapter: Optional[str] = None  # If None, check all adapters


class CheckTriggerResponse(BaseModel):
    triggered: bool
    adapter: Optional[str]
    message: str


class IncidentReportRequest(BaseModel):
    incident_id: str
    adapter: Optional[str] = None


# ─── Routes ──────────────────────────────────────────────────────────────────

@router.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check(request=None):
    """
    Nightwatch system health. Returns 200 if the platform itself is running.
    This does NOT check monitored applications — see /status for that.
    """
    from fastapi import Request
    uptime = 0.0
    if hasattr(request.app.state, "start_time"):
        uptime = (datetime.now(timezone.utc) - request.app.state.start_time).total_seconds()

    return HealthResponse(
        status="ok",
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=uptime,
    )


@router.get("/status", tags=["monitoring"])
async def get_status(request=None):
    """
    Current health status of all monitored applications.
    Returns the last check results for each configured adapter.
    """
    engines = request.app.state.engines
    if not engines:
        raise HTTPException(status_code=503, detail="No adapters configured")

    statuses = {}
    for adapter_name, engine in engines.items():
        statuses[adapter_name] = engine.get_status()

    overall = "healthy"
    for status in statuses.values():
        if status.get("status") == "unhealthy":
            overall = "unhealthy"
            break
        elif status.get("status") not in ("healthy", "starting"):
            overall = "degraded"

    return {
        "overall": overall,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "adapters": statuses,
    }


@router.get("/incidents", tags=["monitoring"])
async def get_incidents(
    request=None,
    limit: int = Query(20, ge=1, le=100),
    active_only: bool = Query(False),
    adapter: Optional[str] = Query(None),
):
    """
    List recent incidents across all (or a specific) adapter.
    """
    engines = request.app.state.engines

    all_incidents = []
    for name, engine in engines.items():
        if adapter and name != adapter:
            continue
        incidents = engine.get_incidents(limit=limit, active_only=active_only)
        all_incidents.extend(incidents)

    # Sort by started_at descending
    all_incidents.sort(key=lambda i: i.get("started_at", ""), reverse=True)

    return {
        "total": len(all_incidents),
        "incidents": all_incidents[:limit],
        "filters": {"active_only": active_only, "adapter": adapter},
    }


@router.post("/check", response_model=CheckTriggerResponse, tags=["monitoring"])
async def trigger_check(
    request=None,
    body: CheckTriggerRequest = CheckTriggerRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
):
    """
    Trigger an immediate check cycle (outside the normal schedule).
    Runs in the background and returns immediately.
    """
    engines = request.app.state.engines

    if body.adapter:
        if body.adapter not in engines:
            raise HTTPException(status_code=404, detail=f"Adapter '{body.adapter}' not found")
        target_engines = {body.adapter: engines[body.adapter]}
    else:
        target_engines = engines

    import asyncio

    async def run_checks():
        for name, engine in target_engines.items():
            log.info("manual_check_triggered", adapter=name)
            await engine.run_check_cycle()

    background_tasks.add_task(asyncio.create_task, run_checks())

    return CheckTriggerResponse(
        triggered=True,
        adapter=body.adapter,
        message=f"Check triggered for {body.adapter or 'all adapters'}",
    )


@router.get("/adapters", tags=["configuration"])
async def list_adapters(request=None):
    """
    List all configured adapters and their monitored components.
    """
    engines = request.app.state.engines

    adapters = []
    for name, engine in engines.items():
        adapter = engine.adapter
        components = adapter.get_component_inventory()
        adapters.append({
            "name": name,
            "application": adapter.application_name,
            "class": adapter.__class__.__name__,
            "is_running": engine.is_running,
            "check_count": engine.check_count,
            "component_count": len(components),
            "components": [c.to_dict() for c in components],
            "architecture": adapter.describe_architecture(),
        })

    return {
        "adapter_count": len(adapters),
        "adapters": adapters,
    }


@router.get("/metrics", tags=["monitoring"])
async def get_metrics(request=None, adapter: Optional[str] = Query(None)):
    """
    Current metrics snapshot from all (or a specific) adapter.
    Returns raw metrics collected during the last check cycle.
    """
    engines = request.app.state.engines

    results = {}
    for name, engine in engines.items():
        if adapter and name != adapter:
            continue
        status = engine.get_status()
        results[name] = status.get("metrics_summary", {})

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "metrics": results,
    }


@router.get("/schedule", tags=["system"])
async def get_schedule(request=None):
    """
    Scheduler status — shows all registered tasks and their last run times.
    """
    scheduler = request.app.state.scheduler
    return {
        "tasks": scheduler.get_status() if scheduler else [],
    }


@router.post("/report", tags=["ai"])
async def generate_report(
    request=None,
    body: IncidentReportRequest = IncidentReportRequest(incident_id=""),
):
    """
    Generate an AI incident report for a specific incident ID.
    """
    engines = request.app.state.engines

    # Find the incident
    for name, engine in engines.items():
        if body.adapter and name != body.adapter:
            continue
        incidents = engine.get_incidents(limit=100)
        for incident in incidents:
            if incident.get("id") == body.incident_id:
                # Generate report using the LLM
                llm = request.app.state.llm_client
                if llm:
                    report = llm.generate_incident_report(incident)
                    return {"incident_id": body.incident_id, "report": report}
                else:
                    raise HTTPException(status_code=503, detail="LLM not configured")

    raise HTTPException(status_code=404, detail=f"Incident '{body.incident_id}' not found")
