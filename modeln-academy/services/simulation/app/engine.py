"""Deterministic, side-effect-free scenario state machine."""

from __future__ import annotations

from collections import deque
from copy import deepcopy
from typing import Any


class InvalidScenarioError(ValueError):
    """Raised when a scenario definition has an invalid graph."""


class TransitionError(ValueError):
    """Raised when a caller requests an undeclared transition."""


class SimulationEngine:
    """Validate and execute declarative incident simulations."""

    def __init__(self, scenarios: list[dict[str, Any]]) -> None:
        self._scenarios = {scenario["id"]: deepcopy(scenario) for scenario in scenarios}
        if len(self._scenarios) != len(scenarios):
            raise InvalidScenarioError("scenario IDs must be unique")
        for scenario in self._scenarios.values():
            self._validate(scenario)

    def _validate(self, scenario: dict[str, Any]) -> None:
        states = {state["id"]: state for state in scenario.get("states", [])}
        start = scenario.get("start_state")
        if not start or start not in states:
            raise InvalidScenarioError(f"{scenario['id']} has no valid start state")
        for state in states.values():
            for choice in state.get("choices", []):
                if choice.get("next_state") not in states:
                    raise InvalidScenarioError(f"{scenario['id']} choice {choice.get('id')} has an invalid next state")
        seen: set[str] = set()
        queue = deque([start])
        while queue:
            state_id = queue.popleft()
            if state_id in seen:
                continue
            seen.add(state_id)
            queue.extend(choice["next_state"] for choice in states[state_id].get("choices", []))
        unreachable = set(states) - seen
        if unreachable:
            raise InvalidScenarioError(f"{scenario['id']} has unreachable states: {', '.join(sorted(unreachable))}")
        if not any(state.get("terminal") for state in states.values()):
            raise InvalidScenarioError(f"{scenario['id']} has no terminal state")

    def _scenario(self, scenario_id: str) -> dict[str, Any]:
        scenario = self._scenarios.get(scenario_id)
        if not scenario:
            raise TransitionError("scenario does not exist")
        return scenario

    @staticmethod
    def _public_state(state: dict[str, Any]) -> dict[str, Any]:
        return {
            "state_id": state["id"],
            "prompt": state["prompt"],
            "terminal": state["terminal"],
            "choices": [{"id": choice["id"], "label": choice["label"]} for choice in state.get("choices", [])],
        }

    def start(self, scenario_id: str) -> dict[str, Any]:
        scenario = self._scenario(scenario_id)
        states = {state["id"]: state for state in scenario["states"]}
        return self._public_state(states[scenario["start_state"]])

    def advance(self, scenario_id: str, current_state: str, choice_id: str) -> dict[str, Any]:
        scenario = self._scenario(scenario_id)
        states = {state["id"]: state for state in scenario["states"]}
        state = states.get(current_state)
        if not state or state.get("terminal"):
            raise TransitionError("current state cannot accept a choice")
        choice = next(
            (candidate for candidate in state.get("choices", []) if candidate["id"] == choice_id),
            None,
        )
        if not choice:
            raise TransitionError("choice is not valid for the current state")
        result = self._public_state(states[choice["next_state"]])
        result.update(
            {
                "selected_choice": choice["id"],
                "feedback": choice["label"],
                "score_delta": choice["score"],
                "citation_id": choice["citation_id"],
            }
        )
        return result
