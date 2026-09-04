"""FastAPI entry point for immutable ModelN course content."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from modeln_academy_shared.models import ApiError, ServiceHealth

from .store import CourseStore


def safe_not_found(code: str, message: str) -> HTTPException:
    return HTTPException(status_code=404, detail=ApiError(code=code, message=message).model_dump())


def create_app(store: CourseStore, internal_token: str) -> FastAPI:
    app = FastAPI(title="ModelN Academy Content", version=store.version)

    def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
        if not x_internal_token or x_internal_token != internal_token:
            raise HTTPException(status_code=403, detail="Internal service authorization failed")

    @app.get("/health/live")
    def live() -> ServiceHealth:
        return ServiceHealth(service="content", status="ok", version=store.version)

    @app.get("/health/ready")
    def ready() -> ServiceHealth:
        return ServiceHealth(service="content", status="ok", version=store.version)

    @app.get("/v1/metadata")
    def metadata() -> dict:
        return store.metadata()

    @app.get("/v1/worlds")
    def worlds() -> list[dict]:
        return store.worlds()

    @app.get("/v1/missions/{mission_id}")
    def mission(mission_id: str) -> dict:
        result = store.mission(mission_id)
        if not result:
            raise safe_not_found("mission_not_found", "That mission does not exist.")
        return result

    @app.get("/v1/questions/{question_id}")
    def question(question_id: str) -> dict:
        result = store.public_question(question_id)
        if not result:
            raise safe_not_found("question_not_found", "That question does not exist.")
        return result

    @app.get("/v1/search")
    def search(q: str = Query(min_length=2, max_length=120), limit: int = Query(10, ge=1, le=25)) -> list[dict]:
        return store.search(q, limit)

    @app.get("/internal/questions/{question_id}", dependencies=[Depends(require_internal_token)])
    def internal_question(question_id: str) -> dict:
        result = store.internal_question(question_id)
        if not result:
            raise safe_not_found("question_not_found", "That question does not exist.")
        return result

    @app.get("/internal/simulations", dependencies=[Depends(require_internal_token)])
    def simulations() -> list[dict]:
        return store.simulations()

    @app.get("/internal/references", dependencies=[Depends(require_internal_token)])
    def references() -> dict[str, dict]:
        return store.references()

    return app


def default_app() -> FastAPI:
    root = Path(os.getenv("COURSE_DIR", "/app/content"))
    token = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    return create_app(CourseStore(root / "course-v1.json", root / "search-v1.json"), token)
