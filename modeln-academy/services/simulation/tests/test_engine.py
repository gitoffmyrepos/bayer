import json
from pathlib import Path

import pytest

from services.simulation.app.engine import InvalidScenarioError, SimulationEngine, TransitionError

ROOT = Path(__file__).parents[3]


def engine() -> SimulationEngine:
    course = json.loads((ROOT / "content" / "dist" / "course-v1.json").read_text())
    return SimulationEngine(course["simulations"])


def test_start_returns_public_state_without_scoring_consequences() -> None:
    state = engine().start("sim-missing-inbound")

    assert state["state_id"] == "symptom"
    assert state["choices"][0] == {
        "id": "identify",
        "label": "Confirm FGI, source identity, and expected contract",
    }


def test_valid_choice_returns_declared_next_state_and_consequence() -> None:
    transition = engine().advance("sim-missing-inbound", "symptom", "identify")

    assert transition["state_id"] == "identity"
    assert transition["score_delta"] == 20
    assert transition["citation_id"]


def test_choice_replay_is_deterministic() -> None:
    simulator = engine()

    assert simulator.advance("sim-missing-inbound", "symptom", "identify") == simulator.advance("sim-missing-inbound", "symptom", "identify")


def test_tampered_state_or_choice_is_rejected() -> None:
    simulator = engine()

    with pytest.raises(TransitionError):
        simulator.advance("sim-missing-inbound", "not-a-state", "identify")
    with pytest.raises(TransitionError):
        simulator.advance("sim-missing-inbound", "symptom", "not-a-choice")


def test_unreachable_state_is_rejected_when_engine_loads() -> None:
    bad = [
        {
            "id": "bad",
            "start_state": "start",
            "states": [
                {"id": "start", "terminal": True, "prompt": "Done", "choices": []},
                {"id": "orphan", "terminal": True, "prompt": "Never reached", "choices": []},
            ],
        }
    ]

    with pytest.raises(InvalidScenarioError, match="unreachable"):
        SimulationEngine(bad)
