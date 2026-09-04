from fastapi.testclient import TestClient

from services.learning.app.main import create_app


def test_score_endpoint_returns_idempotent_result() -> None:
    client = TestClient(create_app("internal-token"))
    payload = {
        "request_id": "answer-123",
        "question": {
            "id": "q-1",
            "answer": "configured",
            "explanation": "Configuration is not runtime proof.",
            "difficulty": 2,
            "mastery_skill": "classify_evidence",
            "citation_id": "evidence-legend",
        },
        "submitted": "configured",
        "hints_used": 0,
        "current_mastery": 20,
    }

    first = client.post("/internal/score", json=payload, headers={"X-Internal-Token": "internal-token"})
    second = client.post("/internal/score", json=payload, headers={"X-Internal-Token": "internal-token"})

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["correct"] is True
    assert first.json()["explanation"] == "Configuration is not runtime proof."


def test_internal_endpoint_rejects_bad_token() -> None:
    client = TestClient(create_app("internal-token"))

    response = client.post("/internal/score", json={}, headers={"X-Internal-Token": "wrong"})

    assert response.status_code == 403
