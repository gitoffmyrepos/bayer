"""Immutable in-memory course bundle store."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any


class InvalidCourseBundleError(ValueError):
    """Raised when a course bundle cannot satisfy the service contract."""


class CourseStore:
    """Load and query one immutable course release."""

    def __init__(self, course_path: Path, search_path: Path) -> None:
        try:
            self._course = json.loads(course_path.read_text(encoding="utf-8"))
            self._search = json.loads(search_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InvalidCourseBundleError("Course bundle could not be loaded") from exc
        self._validate()
        self._missions = {mission["id"]: mission for world in self._course["worlds"] for mission in world["missions"]}
        self._questions = {question["id"]: question for question in self._course["questions"]}

    def _validate(self) -> None:
        version = self._course.get("metadata", {}).get("version")
        if not version or version != self._search.get("version"):
            raise InvalidCourseBundleError("Course and search versions do not match")
        if not self._course.get("worlds") or not self._course.get("references"):
            raise InvalidCourseBundleError("Course bundle is incomplete")

    @property
    def version(self) -> str:
        return str(self._course["metadata"]["version"])

    def metadata(self) -> dict[str, Any]:
        return deepcopy(self._course["metadata"])

    def worlds(self) -> list[dict[str, Any]]:
        worlds = deepcopy(self._course["worlds"])
        for world in worlds:
            for mission in world["missions"]:
                mission["beats"] = [{key: value for key, value in beat.items() if key != "question_ids"} for beat in mission["beats"]]
        return worlds

    def mission(self, mission_id: str) -> dict[str, Any] | None:
        mission = self._missions.get(mission_id)
        return deepcopy(mission) if mission else None

    def public_question(self, question_id: str) -> dict[str, Any] | None:
        question = self._questions.get(question_id)
        if not question:
            return None
        return {key: deepcopy(value) for key, value in question.items() if key not in {"answer", "explanation"}}

    def internal_question(self, question_id: str) -> dict[str, Any] | None:
        question = self._questions.get(question_id)
        return deepcopy(question) if question else None

    def simulations(self) -> list[dict[str, Any]]:
        return deepcopy(self._course["simulations"])

    def public_simulations(self) -> list[dict[str, str]]:
        return [
            {"id": str(simulation["id"]), "title": str(simulation["title"])}
            for simulation in self._course["simulations"]
        ]

    def references(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._course["references"])

    def reference(self, reference_id: str) -> dict[str, Any] | None:
        reference = self._course["references"].get(reference_id)
        return deepcopy(reference) if reference else None

    def search(self, query: str, limit: int) -> list[dict[str, Any]]:
        stop_words = {
            "a",
            "an",
            "and",
            "are",
            "for",
            "how",
            "in",
            "is",
            "of",
            "the",
            "to",
            "what",
            "where",
            "which",
        }
        terms = [
            term
            for term in re.findall(r"[a-z0-9][a-z0-9_-]*", query.casefold())
            if term not in stop_words
        ]
        if not terms:
            return []
        ranked: list[tuple[int, dict[str, Any]]] = []
        for document in self._search["documents"]:
            haystack = f"{document['title']} {document['text']}".casefold()
            counts = [haystack.count(term) for term in terms]
            score = sum(counts)
            if all(counts):
                public = deepcopy(document)
                public["score"] = score
                ranked.append((score, public))
        ranked.sort(key=lambda item: (-item[0], item[1]["title"]))
        return [document for _score, document in ranked[:limit]]
