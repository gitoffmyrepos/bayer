"""Pure, transparent answer scoring and mastery functions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnswerInput(BaseModel):
    """A submitted response paired with its private accepted answer."""

    expected: Any
    submitted: Any
    hints_used: int = Field(default=0, ge=0, le=5)


class Evaluation(BaseModel):
    """Deterministic answer evaluation."""

    correct: bool
    score: float = Field(ge=0, le=1)


def normalize(value: Any) -> Any:
    if isinstance(value, str):
        return " ".join(value.casefold().split())
    if isinstance(value, list):
        return [normalize(item) for item in value]
    if isinstance(value, dict):
        return {key: normalize(item) for key, item in sorted(value.items())}
    return value


def evaluate_answer(answer: AnswerInput) -> Evaluation:
    correct = normalize(answer.expected) == normalize(answer.submitted)
    if not correct:
        return Evaluation(correct=False, score=0.0)
    hint_penalty = min(answer.hints_used * 0.15, 0.6)
    return Evaluation(correct=True, score=round(1.0 - hint_penalty, 2))


def update_mastery(current: float, answer_score: float, difficulty: int) -> float:
    """Move mastery by a bounded, inspectable amount."""
    delta = difficulty * 3 * ((2 * answer_score) - 1)
    return round(min(100.0, max(0.0, current + delta)), 2)


def select_weak_skill(mastery: dict[str, float]) -> str | None:
    if not mastery:
        return None
    return min(mastery.items(), key=lambda item: (item[1], item[0]))[0]
