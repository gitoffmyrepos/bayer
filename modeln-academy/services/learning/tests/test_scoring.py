from datetime import UTC, datetime

from services.learning.app.scheduler import ReviewState, schedule_review
from services.learning.app.scoring import AnswerInput, evaluate_answer, select_weak_skill, update_mastery


def test_objective_answers_ignore_case_and_outer_whitespace() -> None:
    result = evaluate_answer(AnswerInput(expected="Configured", submitted=" configured "))

    assert result.correct is True
    assert result.score == 1.0


def test_ordering_answers_require_exact_order() -> None:
    result = evaluate_answer(AnswerInput(expected=["SFTP", "S3", "Glue"], submitted=["S3", "SFTP", "Glue"]))

    assert result.correct is False
    assert result.score == 0.0


def test_hints_reduce_credit_without_hiding_correctness() -> None:
    result = evaluate_answer(AnswerInput(expected="S3", submitted="S3", hints_used=2))

    assert result.correct is True
    assert result.score == 0.7


def test_mastery_moves_gradually_and_is_bounded() -> None:
    assert update_mastery(current=40.0, answer_score=1.0, difficulty=3) == 49.0
    assert update_mastery(current=98.0, answer_score=1.0, difficulty=3) == 100.0
    assert update_mastery(current=2.0, answer_score=0.0, difficulty=3) == 0.0


def test_weak_skill_selection_prefers_lowest_mastery() -> None:
    assert select_weak_skill({"trace_inbound": 72.0, "classify_evidence": 31.0}) == "classify_evidence"


def test_successful_review_expands_interval() -> None:
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    result = schedule_review(ReviewState(repetitions=1, interval_days=1, ease=2.5), quality=5, now=now)

    assert result.repetitions == 2
    assert result.interval_days == 6
    assert result.due_at.isoformat() == "2026-09-10T12:00:00+00:00"


def test_failed_review_resets_repetition_and_returns_tomorrow() -> None:
    now = datetime(2026, 9, 4, 12, tzinfo=UTC)
    result = schedule_review(ReviewState(repetitions=4, interval_days=20, ease=2.7), quality=2, now=now)

    assert result.repetitions == 0
    assert result.interval_days == 1
    assert result.due_at.isoformat() == "2026-09-05T12:00:00+00:00"
