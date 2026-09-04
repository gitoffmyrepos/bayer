"""Deterministic spaced-review scheduling."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from pydantic import BaseModel, Field


class ReviewState(BaseModel):
    repetitions: int = Field(default=0, ge=0)
    interval_days: int = Field(default=0, ge=0)
    ease: float = Field(default=2.5, ge=1.3, le=3.5)
    due_at: datetime | None = None


def schedule_review(state: ReviewState, quality: int, now: datetime | None = None) -> ReviewState:
    """Apply the documented SM-2 interval rules."""
    if not 0 <= quality <= 5:
        raise ValueError("quality must be between 0 and 5")
    current_time = now or datetime.now(UTC)
    ease = max(1.3, state.ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)))
    if quality < 3:
        repetitions = 0
        interval = 1
    else:
        repetitions = state.repetitions + 1
        if repetitions == 1:
            interval = 1
        elif repetitions == 2:
            interval = 6
        else:
            interval = max(1, round(state.interval_days * ease))
    return ReviewState(
        repetitions=repetitions,
        interval_days=interval,
        ease=round(ease, 3),
        due_at=current_time + timedelta(days=interval),
    )
