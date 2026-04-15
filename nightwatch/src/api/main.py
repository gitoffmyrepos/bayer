"""
Nightwatch API Main
====================
FastAPI application entry point.

Loads configuration, initializes adapters, starts the monitoring engine,
and serves the REST API.

Run with:
    python -m src.api.main
    # or:
    uvicorn src.api.main:app --host 0.0.0.0 --port 8080

Author: Nova ⚡ | Nightwatch Platform
"""

import asyncio
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import structlog
import uvicorn
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

from src.api.routes import router
from src.core.config import NightwatchConfig
from src.core.engine import NightwatchEngine
from src.core.llm_client import NightwatchLLMClient
from src.core.scheduler import NightwatchScheduler

# ─── Logging setup ───────────────────────────────────────────────────────────

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger("nightwatch")

# ─── Adapter Registry ────────────────────────────────────────────────────────
# Map adapter type names → adapter classes
# To register a new adapter, add it here.

ADAPTER_REGISTRY: dict[str, type] = {}

try:
    from src.adapters.aws_pipeline.adapter import AWSPipelineAdapter
    ADAPTER_REGISTRY["aws_pipeline"] = AWSPipelineAdapter
except ImportError:
    log.warning("adapter_unavailable", type="aws_pipeline")

try:
    from src.adapters.forextrader.adapter import ForexTraderAdapter
    ADAPTER_REGISTRY["forextrader"] = ForexTraderAdapter
except ImportError:
    log.warning("adapter_unavailable", type="forextrader")


def load_adapter(adapter_config: dict, config: NightwatchConfig) -> Optional[object]:
    """Load and initialize an adapter from config."""
    adapter_type = adapter_config.get("type")
    adapter_name = adapter_config.get("name", adapter_type)

    if adapter_type not in ADAPTER_REGISTRY:
        log.error("unknown_adapter_type", type=adapter_type, available=list(ADAPTER_REGISTRY.keys()))
        return None

    AdapterClass = ADAPTER_REGISTRY[adapter_type]

    # Load adapter-specific config
    config_file = adapter_config.get("config_file")
    adapter_cfg = {}

    if config_file:
        try:
            # Resolve path relative to config/ directory
            cfg_root = Path(__file__).parent.parent.parent / "config"
            adapter_cfg = NightwatchConfig.load_adapter_config(config_file, base_dir=str(cfg_root))
        except FileNotFoundError:
            # Try relative to src/adapters/
            try:
                src_root = Path(__file__).parent.parent / "adapters"
                adapter_cfg = NightwatchConfig.load_adapter_config(config_file, base_dir=str(src_root))
            except FileNotFoundError:
                log.warning("adapter_config_not_found", name=adapter_name, config_file=config_file)

    # Inline config overrides config_file
    adapter_cfg.update({k: v for k, v in adapter_config.items()
                        if k not in ("type", "name", "config_file", "enabled")})

    try:
        adapter = AdapterClass(adapter_cfg)
        adapter.initialize()
        log.info("adapter_loaded", name=adapter_name, type=adapter_type,
                 application=adapter.application_name)
        return adapter
    except Exception as e:
        log.error("adapter_init_failed", name=adapter_name, error=str(e))
        return None


# ─── App Lifespan ─────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: load adapters, start monitoring engines. Shutdown: clean up."""
    app.state.start_time = datetime.now(timezone.utc)
    app.state.engines = {}
    app.state.scheduler = NightwatchScheduler()
    app.state.llm_client = None

    # Load config
    config_path = os.environ.get("NIGHTWATCH_CONFIG", "config/nightwatch.yaml")
    if not Path(config_path).exists():
        # Try relative to project root
        project_root = Path(__file__).parent.parent.parent
        config_path = str(project_root / "config" / "nightwatch.yaml")

    try:
        config = NightwatchConfig.load(config_path)
        log.info("config_loaded", path=config_path, llm_provider=config.llm_provider)
    except FileNotFoundError:
        log.warning("config_not_found", path=config_path,
                    hint="Using defaults. Set NIGHTWATCH_CONFIG env var or create config/nightwatch.yaml")
        config = NightwatchConfig({"nightwatch": {}, "llm": {}, "adapters": [], "alerting": {}})

    # Initialize LLM client (monitoring / diagnosis)
    try:
        llm_client = NightwatchLLMClient(config.llm)
        app.state.llm_client = llm_client
        log.info("llm_initialized", provider=config.llm_provider, model=llm_client.model)
    except Exception as e:
        log.warning("llm_init_failed", error=str(e),
                    hint="Monitoring will run without AI analysis")
        llm_client = None

    # Initialize remediation LLM client (healing / fixes) — optional, falls back to monitoring llm
    remediation_client = None
    rem_cfg = config.remediation_llm
    if rem_cfg and rem_cfg is not config.llm:
        try:
            remediation_client = NightwatchLLMClient(rem_cfg)
            app.state.remediation_client = remediation_client
            log.info("remediation_llm_initialized",
                     provider=rem_cfg.get("provider"),
                     model=remediation_client.model)
        except Exception as e:
            log.warning("remediation_llm_init_failed", error=str(e),
                        hint="Remediation will fall back to monitoring LLM")
    if remediation_client is None:
        remediation_client = llm_client

    # Load and start adapters
    enabled_adapters = config.get_adapter_configs()
    if not enabled_adapters:
        log.warning("no_adapters_configured",
                    hint="Add adapters to config/nightwatch.yaml to start monitoring")

    for adapter_config in enabled_adapters:
        adapter_name = adapter_config.get("name", adapter_config.get("type"))
        adapter = load_adapter(adapter_config, config)

        if adapter and llm_client:
            engine = NightwatchEngine(
                adapter=adapter,
                llm_client=llm_client,
                config=config.raw(),
                remediation_llm_client=remediation_client,
            )
            app.state.engines[adapter_name] = engine

            # Register engine as a scheduled task
            app.state.scheduler.add_task(
                name=f"monitor_{adapter_name}",
                coro_fn=engine.run_check_cycle,
                interval_seconds=config.check_interval_seconds,
            )
            log.info("engine_configured", adapter=adapter_name,
                     interval=config.check_interval_seconds)

    # Start all scheduled tasks in background
    if app.state.engines:
        asyncio.create_task(app.state.scheduler.start())
        log.info("nightwatch_started",
                 adapters=list(app.state.engines.keys()),
                 check_interval=config.check_interval_seconds)
    else:
        log.warning("no_engines_started", hint="Configure adapters in nightwatch.yaml")

    yield  # API is running

    # Shutdown
    log.info("nightwatch_stopping")
    app.state.scheduler.stop()
    for engine in app.state.engines.values():
        engine.stop()
        engine.adapter.cleanup()
    log.info("nightwatch_stopped")


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="Nightwatch ⚡",
    description=(
        "Cloud-agnostic AI-powered monitoring platform.\n\n"
        "Monitor ANY application with ANY LLM, run ANYWHERE."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# CORS
# FIX: Restrict CORS to known origins instead of wildcard
_NIGHTWATCH_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "https://forex.strategybase.io,http://localhost:3000",
    ).split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_NIGHTWATCH_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ─── Middleware: inject request object into routes ────────────────────────────

@app.middleware("http")
async def inject_request_middleware(request: Request, call_next):
    """Make the request object available to routes via `request` parameter."""
    response = await call_next(request)
    return response


# ─── Exception Handlers ───────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc))
    # FIX: Do not leak internal error details to the client
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"},
    )


# ─── Include routes ───────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def root():
    """Redirect root to the interactive API documentation."""
    return RedirectResponse(url="/docs")


# Mount routes with request injection
@app.get("/health")
async def health_check(request: Request):
    """Nightwatch system health check."""
    uptime = 0.0
    if hasattr(request.app.state, "start_time"):
        uptime = (datetime.now(timezone.utc) - request.app.state.start_time).total_seconds()
    return {"status": "ok", "version": "2.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(), "uptime_seconds": uptime}


@app.get("/status")
async def get_status(request: Request):
    """Current health status of all monitored applications."""
    engines = request.app.state.engines
    if not engines:
        return {"overall": "no_adapters", "adapters": {},
                "timestamp": datetime.now(timezone.utc).isoformat()}

    statuses = {name: engine.get_status() for name, engine in engines.items()}
    overall = "healthy"
    for s in statuses.values():
        if s.get("status") == "unhealthy":
            overall = "unhealthy"
            break
        elif s.get("status") not in ("healthy", "starting"):
            overall = "degraded"

    return {"overall": overall, "adapters": statuses,
            "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/incidents")
async def get_incidents(
    request: Request,
    limit: int = 20,
    active_only: bool = False,
    adapter: Optional[str] = None,
):
    """List recent incidents."""
    engines = request.app.state.engines
    all_incidents = []
    for name, engine in engines.items():
        if adapter and name != adapter:
            continue
        all_incidents.extend(engine.get_incidents(limit=limit, active_only=active_only))
    all_incidents.sort(key=lambda i: i.get("started_at", ""), reverse=True)
    return {"total": len(all_incidents), "incidents": all_incidents[:limit]}


@app.post("/check")
async def trigger_check(
    request: Request,
    adapter: Optional[str] = None,
):
    """Trigger an immediate check cycle."""
    engines = request.app.state.engines

    if adapter and adapter not in engines:
        raise HTTPException(status_code=404, detail=f"Adapter '{adapter}' not found")

    target = {adapter: engines[adapter]} if adapter else engines

    async def run_all():
        for name, engine in target.items():
            log.info("manual_check", adapter=name)
            await engine.run_check_cycle()

    asyncio.create_task(run_all())
    return {"triggered": True, "adapter": adapter or "all", "message": "Check cycle started"}


@app.get("/adapters")
async def list_adapters(request: Request):
    """List configured adapters and their components."""
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
            "components": [c.to_dict() for c in components],
        })
    return {"adapter_count": len(adapters), "adapters": adapters,
            "registered_types": list(ADAPTER_REGISTRY.keys())}


@app.get("/schedule")
async def get_schedule(request: Request):
    """Scheduler task status."""
    return {"tasks": request.app.state.scheduler.get_status()}



# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    host = os.environ.get("HOST", "0.0.0.0")

    log.info("nightwatch_starting", host=host, port=port)

    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        log_level="info",
        reload=os.environ.get("DEBUG", "false").lower() == "true",
    )
