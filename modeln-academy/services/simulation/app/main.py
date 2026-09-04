"""Internal API for deterministic incident simulations."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from modeln_academy_shared.models import ApiError, ServiceHealth
from pydantic import BaseModel

from .engine import SimulationEngine, TransitionError


class AdvanceRequest(BaseModel):
    current_state: str
    choice_id: str


def create_app(engine: SimulationEngine, internal_token: str) -> FastAPI:
    app = FastAPI(title="ModelN Academy Simulation Engine", version="1.0.0")

    def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
        if not x_internal_token or x_internal_token != internal_token:
            raise HTTPException(status_code=403, detail="Internal service authorization failed")

    @app.get("/health/live")
    def health() -> ServiceHealth:
        return ServiceHealth(service="simulation", status="ok", version="1.0.0")

    @app.post(
        "/internal/scenarios/{scenario_id}/start",
        dependencies=[Depends(require_internal_token)],
    )
    def start(scenario_id: str) -> dict:
        try:
            return engine.start(scenario_id)
        except TransitionError as exc:
            error = ApiError(code="scenario_not_found", message="That scenario does not exist.")
            raise HTTPException(status_code=404, detail=error.model_dump()) from exc

    @app.post(
        "/internal/scenarios/{scenario_id}/advance",
        dependencies=[Depends(require_internal_token)],
    )
    def advance(scenario_id: str, request: AdvanceRequest) -> dict:
        try:
            return engine.advance(scenario_id, request.current_state, request.choice_id)
        except TransitionError as exc:
            error = ApiError(
                code="invalid_transition",
                message="That choice is not valid for the current scenario state.",
            )
            raise HTTPException(status_code=409, detail=error.model_dump()) from exc

    return app


def default_app() -> FastAPI:
    token = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    course_path = Path(os.getenv("COURSE_PATH", "/app/content/course-v1.json"))
    course = json.loads(course_path.read_text(encoding="utf-8"))
    return create_app(SimulationEngine(course["simulations"]), token)
