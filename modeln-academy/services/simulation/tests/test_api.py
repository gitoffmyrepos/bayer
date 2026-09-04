import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.simulation.app.engine import SimulationEngine
from services.simulation.app.main import create_app

ROOT = Path(__file__).parents[3]


def client() -> TestClient:
    course = json.loads((ROOT / "content" / "dist" / "course-v1.json").read_text())
    return TestClient(create_app(SimulationEngine(course["simulations"]), "internal-token"))


def test_start_and_advance_scenario() -> None:
    headers = {"X-Internal-Token": "internal-token"}

    start = client().post("/internal/scenarios/sim-package-0009343/start", headers=headers)
    advanced = client().post(
        "/internal/scenarios/sim-package-0009343/advance",
        headers=headers,
        json={"current_state": "missing-fields", "choice_id": "facts"},
    )

    assert start.status_code == 200
    assert advanced.status_code == 200
    assert advanced.json()["state_id"] == "inspect"


def test_invalid_transition_is_safe_conflict() -> None:
    response = client().post(
        "/internal/scenarios/sim-package-0009343/advance",
        headers={"X-Internal-Token": "internal-token"},
        json={"current_state": "missing-fields", "choice_id": "tampered"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_transition"
