"""Internal-service gateway implementations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol

import httpx

from services.content.app.store import CourseStore
from services.learning.app.scheduler import ReviewState, schedule_review
from services.learning.app.scoring import AnswerInput, evaluate_answer, update_mastery
from services.simulation.app.engine import SimulationEngine


class AcademyServices(Protocol):
    @property
    def course_version(self) -> str: ...
    def worlds(self) -> list[dict[str, Any]]: ...
    def mission(self, mission_id: str) -> dict[str, Any] | None: ...
    def public_question(self, question_id: str) -> dict[str, Any] | None: ...
    def score(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def schedule(self, request: dict[str, Any]) -> dict[str, Any]: ...
    def search(self, query: str, limit: int) -> list[dict[str, Any]]: ...
    def start_simulation(self, scenario_id: str) -> dict[str, Any]: ...
    def advance_simulation(self, scenario_id: str, current_state: str, choice_id: str) -> dict[str, Any]: ...


class InProcessServices:
    """Real service logic in-process for tests and local development."""

    def __init__(self, course_path: Path, search_path: Path) -> None:
        self._content = CourseStore(course_path, search_path)
        course = json.loads(course_path.read_text(encoding="utf-8"))
        self._simulator = SimulationEngine(course["simulations"])

    @property
    def course_version(self) -> str:
        return self._content.version

    def worlds(self) -> list[dict[str, Any]]:
        return self._content.worlds()

    def mission(self, mission_id: str) -> dict[str, Any] | None:
        return self._content.mission(mission_id)

    def public_question(self, question_id: str) -> dict[str, Any] | None:
        return self._content.public_question(question_id)

    def score(self, request: dict[str, Any]) -> dict[str, Any]:
        question = self._content.internal_question(request["question_id"])
        if not question:
            raise KeyError("question does not exist")
        evaluation = evaluate_answer(
            AnswerInput(
                expected=question["answer"],
                submitted=request["submitted"],
                hints_used=request["hints_used"],
            )
        )
        return {
            "request_id": request["request_id"],
            "correct": evaluation.correct,
            "score": evaluation.score,
            "mastery_skill": question["mastery_skill"],
            "previous_mastery": request["current_mastery"],
            "new_mastery": update_mastery(request["current_mastery"], evaluation.score, question["difficulty"]),
            "explanation": question["explanation"],
            "citation_id": question["citation_id"],
        }

    def schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        result = schedule_review(
            ReviewState(
                repetitions=request["repetitions"],
                interval_days=request["interval_days"],
                ease=request["ease"],
            ),
            request["quality"],
        )
        return result.model_dump(mode="json")

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return self._content.search(query, limit)

    def start_simulation(self, scenario_id: str) -> dict[str, Any]:
        return self._simulator.start(scenario_id)

    def advance_simulation(self, scenario_id: str, current_state: str, choice_id: str) -> dict[str, Any]:
        return self._simulator.advance(scenario_id, current_state, choice_id)


class HttpServices:
    """Cluster-local HTTP adapter for independently deployed services."""

    def __init__(
        self,
        content_url: str,
        learning_url: str,
        simulation_url: str,
        internal_token: str,
    ) -> None:
        self._content_url = content_url.rstrip("/")
        self._learning_url = learning_url.rstrip("/")
        self._simulation_url = simulation_url.rstrip("/")
        self._headers = {"X-Internal-Token": internal_token}

    def _get(self, url: str, *, params: dict[str, Any] | None = None) -> Any:
        response = httpx.get(url, params=params, headers=self._headers, timeout=5)
        response.raise_for_status()
        return response.json()

    def _post(self, url: str, payload: dict[str, Any] | None = None) -> Any:
        response = httpx.post(url, json=payload, headers=self._headers, timeout=5)
        response.raise_for_status()
        return response.json()

    @property
    def course_version(self) -> str:
        return str(self._get(f"{self._content_url}/v1/metadata")["version"])

    def worlds(self) -> list[dict[str, Any]]:
        return list(self._get(f"{self._content_url}/v1/worlds"))

    def mission(self, mission_id: str) -> dict[str, Any] | None:
        try:
            return dict(self._get(f"{self._content_url}/v1/missions/{mission_id}"))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    def public_question(self, question_id: str) -> dict[str, Any] | None:
        try:
            return dict(self._get(f"{self._content_url}/v1/questions/{question_id}"))
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return None
            raise

    def score(self, request: dict[str, Any]) -> dict[str, Any]:
        question = self._get(f"{self._content_url}/internal/questions/{request['question_id']}")
        payload = {
            "request_id": request["request_id"],
            "question": question,
            "submitted": request["submitted"],
            "hints_used": request["hints_used"],
            "current_mastery": request["current_mastery"],
        }
        return dict(self._post(f"{self._learning_url}/internal/score", payload))

    def schedule(self, request: dict[str, Any]) -> dict[str, Any]:
        return dict(self._post(f"{self._learning_url}/internal/schedule", request))

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        return list(self._get(f"{self._content_url}/v1/search", params={"q": query, "limit": limit}))

    def start_simulation(self, scenario_id: str) -> dict[str, Any]:
        return dict(self._post(f"{self._simulation_url}/internal/scenarios/{scenario_id}/start"))

    def advance_simulation(self, scenario_id: str, current_state: str, choice_id: str) -> dict[str, Any]:
        return dict(
            self._post(
                f"{self._simulation_url}/internal/scenarios/{scenario_id}/advance",
                {"current_state": current_state, "choice_id": choice_id},
            )
        )
