from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.api.app.db import create_database, seed_user
from services.api.app.main import create_app
from services.api.app.services import InProcessServices

ROOT = Path(__file__).parents[3]


@pytest.fixture
def application(tmp_path: Path):
    database = create_database(f"sqlite+pysqlite:///{tmp_path / 'academy.db'}")
    services = InProcessServices(
        ROOT / "content" / "dist" / "course-v1.json",
        ROOT / "content" / "dist" / "search-v1.json",
    )
    app = create_app(database, services, secure_cookies=False)
    seed_user(database, "kelvin", "Learn-ModelN-2026", "Kelvin")
    return app


def sign_in(client: TestClient) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": "kelvin", "password": "Learn-ModelN-2026"},
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


def test_login_sets_opaque_http_only_session_cookie(application) -> None:
    with TestClient(application) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "kelvin", "password": "Learn-ModelN-2026"},
        )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "academy_session=" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Learn-ModelN-2026" not in cookie


def test_login_sets_refresh_safe_csrf_cookie(application) -> None:
    with TestClient(application) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": "kelvin", "password": "Learn-ModelN-2026"},
        )

    cookies = response.headers.get_list("set-cookie")
    assert any("academy_csrf=" in cookie and "HttpOnly" not in cookie for cookie in cookies)


def test_invalid_login_returns_safe_error(application) -> None:
    with TestClient(application) as client:
        response = client.post("/api/auth/login", json={"username": "kelvin", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "invalid_credentials"


def test_repeated_invalid_logins_are_rate_limited(application) -> None:
    with TestClient(application) as client:
        responses = [client.post("/api/auth/login", json={"username": "kelvin", "password": "wrong"}) for _attempt in range(6)]

    assert responses[-1].status_code == 429
    assert responses[-1].json()["detail"]["code"] == "login_rate_limited"


def test_mutation_requires_csrf_token(application) -> None:
    with TestClient(application) as client:
        sign_in(client)
        response = client.post("/api/missions/mission-01/start")

    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "csrf_failed"


def test_mission_resume_is_shared_across_clients(application) -> None:
    with TestClient(application) as phone, TestClient(application) as desktop:
        phone_csrf = sign_in(phone)
        desktop_csrf = sign_in(desktop)
        started = phone.post("/api/missions/mission-01/start", headers={"X-CSRF-Token": phone_csrf})
        advanced = phone.patch(
            f"/api/attempts/{started.json()['attempt_id']}/beat",
            headers={"X-CSRF-Token": phone_csrf},
            json={"beat": 3},
        )
        resumed = desktop.post("/api/missions/mission-01/start", headers={"X-CSRF-Token": desktop_csrf})

    assert started.status_code == 200
    assert advanced.status_code == 200
    assert resumed.json()["attempt_id"] == started.json()["attempt_id"]
    assert resumed.json()["current_beat"] == 3


def test_concurrent_mission_starts_are_idempotent(application) -> None:
    with TestClient(application) as first, TestClient(application) as second:
        first_csrf = sign_in(first)
        second_csrf = sign_in(second)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(
                pool.map(
                    lambda client_and_token: client_and_token[0].post(
                        "/api/missions/mission-02/start",
                        headers={"X-CSRF-Token": client_and_token[1]},
                    ),
                    [(first, first_csrf), (second, second_csrf)],
                )
            )

    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json()["attempt_id"] == responses[1].json()["attempt_id"]


def test_answer_submission_is_scored_persisted_and_idempotent(application) -> None:
    with TestClient(application) as client:
        csrf = sign_in(client)
        started = client.post("/api/missions/mission-01/start", headers={"X-CSRF-Token": csrf}).json()
        payload = {
            "submission_id": "submission-one",
            "answer": "see-the-system",
            "hints_used": 0,
        }
        first = client.post(
            f"/api/attempts/{started['attempt_id']}/answers/chapter-1-world",
            headers={"X-CSRF-Token": csrf},
            json=payload,
        )
        second = client.post(
            f"/api/attempts/{started['attempt_id']}/answers/chapter-1-world",
            headers={"X-CSRF-Token": csrf},
            json=payload,
        )

    assert first.status_code == 200
    assert first.json() == second.json()
    assert first.json()["correct"] is True
    assert first.json()["explanation"]
    assert first.json()["citation_id"]


def test_dashboard_combines_campaign_and_mastery(application) -> None:
    with TestClient(application) as client:
        sign_in(client)
        response = client.get("/api/dashboard")

    assert response.status_code == 200, response.text
    assert len(response.json()["worlds"]) == 7
    assert response.json()["recommended_mission_id"] == "mission-01"
    assert "mastery" in response.json()


def test_answer_schedules_question_for_daily_review(application) -> None:
    with TestClient(application) as client:
        csrf = sign_in(client)
        started = client.post("/api/missions/mission-01/start", headers={"X-CSRF-Token": csrf}).json()
        client.post(
            f"/api/attempts/{started['attempt_id']}/answers/chapter-1-world",
            headers={"X-CSRF-Token": csrf},
            json={"submission_id": "review-me", "answer": "wrong", "hints_used": 0},
        )
        queue = client.get("/api/reviews/queue")

    assert queue.status_code == 200
    assert queue.json()[0]["question_id"] == "chapter-1-world"
    assert queue.json()[0]["due_at"]


def test_daily_review_answer_does_not_require_an_open_mission(application) -> None:
    with TestClient(application) as client:
        csrf = sign_in(client)
        response = client.post(
            "/api/reviews/chapter-1-world/answer",
            headers={"X-CSRF-Token": csrf},
            json={"submission_id": "daily-one", "answer": "see-the-system", "hints_used": 0},
        )

    assert response.status_code == 200
    assert response.json()["correct"] is True


def test_simulation_run_persists_branch_and_score(application) -> None:
    with TestClient(application) as client:
        csrf = sign_in(client)
        started = client.post(
            "/api/simulations/sim-missing-inbound/start",
            headers={"X-CSRF-Token": csrf},
        )
        advanced = client.post(
            f"/api/simulations/runs/{started.json()['run_id']}/choices/identify",
            headers={"X-CSRF-Token": csrf},
        )

    assert started.status_code == 200
    assert advanced.status_code == 200
    assert advanced.json()["state_id"] == "identity"
    assert advanced.json()["score"] == 20


def test_authenticated_atlas_search_returns_source_backed_results(application) -> None:
    with TestClient(application) as client:
        sign_in(client)
        response = client.get("/api/search", params={"q": "SAP_P4S_DIRECTSALES"})

    assert response.status_code == 200
    assert any("205" in result["text"] for result in response.json())


def test_simulation_catalog_and_reference_are_available_to_signed_in_learner(application) -> None:
    with TestClient(application) as client:
        sign_in(client)
        simulations = client.get("/api/simulations")
        reference = client.get("/api/references/chapter-1-model-n-and-middleware-from-zero")

    assert simulations.status_code == 200
    assert len(simulations.json()) == 2
    assert reference.status_code == 200
    assert len(reference.json()["content"]) >= 200


def test_grounded_coach_returns_only_cited_atlas_evidence(application) -> None:
    with TestClient(application) as client:
        sign_in(client)
        response = client.get("/api/coach", params={"q": "What is SAP_P4S_DIRECTSALES?"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["grounded"] is True
    assert payload["citations"]
    assert "SAP_P4S_DIRECTSALES" in payload["answer"]


def test_grounded_coach_fails_closed_when_no_evidence_matches(application) -> None:
    with TestClient(application) as client:
        sign_in(client)
        response = client.get("/api/coach", params={"q": "zxqv nonexistent topic"})

    assert response.status_code == 200
    assert response.json()["grounded"] is False
    assert response.json()["citations"] == []


def test_logout_revokes_session(application) -> None:
    with TestClient(application) as client:
        csrf = sign_in(client)
        logout = client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf})
        me = client.get("/api/me")

    assert logout.status_code == 204
    assert me.status_code == 401
