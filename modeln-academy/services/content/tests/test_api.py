from pathlib import Path

from fastapi.testclient import TestClient

from services.content.app.main import create_app
from services.content.app.store import CourseStore

ROOT = Path(__file__).parents[3]


def client() -> TestClient:
    store = CourseStore(
        ROOT / "content" / "dist" / "course-v1.json",
        ROOT / "content" / "dist" / "search-v1.json",
    )
    return TestClient(create_app(store, internal_token="test-internal-token"))


def test_health_reports_loaded_bundle_version() -> None:
    response = client().get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"service": "content", "status": "ok", "version": "1.0.0"}


def test_world_endpoint_does_not_expose_question_answers() -> None:
    response = client().get("/v1/worlds")

    assert response.status_code == 200
    serialized = response.text
    assert '"answer"' not in serialized
    assert len(response.json()) == 7


def test_mission_returns_five_learning_beats() -> None:
    response = client().get("/v1/missions/mission-01")

    assert response.status_code == 200
    assert [beat["type"] for beat in response.json()["beats"]] == [
        "brief",
        "explore",
        "decide",
        "recall",
        "debrief",
    ]


def test_question_endpoint_returns_prompt_without_answer() -> None:
    response = client().get("/v1/questions/chapter-1-world")

    assert response.status_code == 200
    assert response.json()["prompt"]
    assert "answer" not in response.json()


def test_internal_question_endpoint_returns_scoring_contract() -> None:
    response = client().get(
        "/internal/questions/chapter-1-world",
        headers={"X-Internal-Token": "test-internal-token"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] == "see-the-system"


def test_atlas_search_finds_fgi_205() -> None:
    response = client().get("/v1/search", params={"q": "SAP_P4S_DIRECTSALES", "limit": 5})

    assert response.status_code == 200
    assert any("205" in result["text"] for result in response.json())


def test_unknown_resource_uses_stable_safe_error() -> None:
    response = client().get("/v1/missions/not-a-mission")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "mission_not_found"
    assert response.json()["detail"]["correlation_id"]


def test_internal_endpoint_rejects_missing_token() -> None:
    response = client().get("/internal/questions/chapter-1-world")

    assert response.status_code == 403
