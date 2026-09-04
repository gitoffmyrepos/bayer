"""Internal API for deterministic scoring and review scheduling."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException
from modeln_academy_shared.models import ServiceHealth
from pydantic import BaseModel, Field

from .scoring import AnswerInput, evaluate_answer, update_mastery


class PrivateQuestion(BaseModel):
    id: str
    answer: Any
    explanation: str
    difficulty: int = Field(ge=1, le=5)
    mastery_skill: str
    citation_id: str


class ScoreRequest(BaseModel):
    request_id: str = Field(min_length=1, max_length=160)
    question: PrivateQuestion
    submitted: Any
    hints_used: int = Field(default=0, ge=0, le=5)
    current_mastery: float = Field(default=0, ge=0, le=100)


class ScoreResponse(BaseModel):
    request_id: str
    correct: bool
    score: float
    mastery_skill: str
    previous_mastery: float
    new_mastery: float
    explanation: str
    citation_id: str


def create_app(internal_token: str) -> FastAPI:
    app = FastAPI(title="ModelN Academy Learning Engine", version="1.0.0")

    def require_internal_token(x_internal_token: str | None = Header(default=None)) -> None:
        if not x_internal_token or x_internal_token != internal_token:
            raise HTTPException(status_code=403, detail="Internal service authorization failed")

    @app.get("/health/live")
    def health() -> ServiceHealth:
        return ServiceHealth(service="learning", status="ok", version="1.0.0")

    @app.post("/internal/score", dependencies=[Depends(require_internal_token)])
    def score(request: ScoreRequest) -> ScoreResponse:
        evaluation = evaluate_answer(
            AnswerInput(
                expected=request.question.answer,
                submitted=request.submitted,
                hints_used=request.hints_used,
            )
        )
        return ScoreResponse(
            request_id=request.request_id,
            correct=evaluation.correct,
            score=evaluation.score,
            mastery_skill=request.question.mastery_skill,
            previous_mastery=request.current_mastery,
            new_mastery=update_mastery(
                request.current_mastery,
                evaluation.score,
                request.question.difficulty,
            ),
            explanation=request.question.explanation,
            citation_id=request.question.citation_id,
        )

    return app


def default_app() -> FastAPI:
    token = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not token:
        raise RuntimeError("INTERNAL_SERVICE_TOKEN is required")
    return create_app(token)
