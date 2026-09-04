"""Authenticated API facade and learner-progress application."""

import hmac
import os
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Response
from modeln_academy_shared.models import ApiError, ServiceHealth
from pydantic import BaseModel, Field
from sqlalchemy import select

from .auth import new_token, token_hash, verify_password
from .db import Database, create_database, seed_user
from .models import AnswerAttempt, Mastery, MissionAttempt, Review, Session, SimulationRun, User
from .services import AcademyServices, HttpServices

SESSION_COOKIE = "academy_session"


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class BeatRequest(BaseModel):
    beat: int = Field(ge=0, le=4)


class AnswerRequest(BaseModel):
    submission_id: str = Field(min_length=1, max_length=160)
    answer: Any
    hints_used: int = Field(default=0, ge=0, le=5)


def api_error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail=ApiError(code=code, message=message).model_dump())


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def create_app(
    database: Database,
    services: AcademyServices,
    *,
    secure_cookies: bool = True,
) -> FastAPI:
    app = FastAPI(title="ModelN Academy API", version="1.0.0")
    failed_logins: dict[str, list[float]] = defaultdict(list)

    def current_session(
        academy_session: Annotated[str | None, Cookie()] = None,
    ) -> tuple[User, Session]:
        if not academy_session:
            raise api_error(401, "authentication_required", "Sign in to continue.")
        with database.sessions() as db:
            session_record = db.scalar(select(Session).where(Session.token_hash == token_hash(academy_session)))
            if not session_record or aware(session_record.expires_at) <= datetime.now(UTC):
                raise api_error(401, "session_expired", "Your session has expired. Sign in again.")
            user = db.get(User, session_record.user_id)
            if not user:
                raise api_error(401, "authentication_required", "Sign in to continue.")
            db.expunge(user)
            db.expunge(session_record)
            return user, session_record

    def csrf_session(
        identity: Annotated[tuple[User, Session], Depends(current_session)],
        x_csrf_token: Annotated[str | None, Header()] = None,
    ) -> tuple[User, Session]:
        if not x_csrf_token or not hmac.compare_digest(token_hash(x_csrf_token), identity[1].csrf_hash):
            raise api_error(403, "csrf_failed", "Refresh the page and try again.")
        return identity

    @app.get("/api/health/live")
    def live() -> ServiceHealth:
        return ServiceHealth(service="api", status="ok", version="1.0.0")

    @app.get("/api/health/ready")
    def ready() -> ServiceHealth:
        try:
            _course_version = services.course_version
            with database.sessions() as db:
                db.execute(select(1))
        except Exception as exc:
            raise api_error(503, "dependency_unavailable", "The academy is starting up.") from exc
        return ServiceHealth(service="api", status="ok", version="1.0.0")

    @app.post("/api/auth/login")
    def login(request: LoginRequest, response: Response) -> dict[str, str]:
        username = request.username.strip().casefold()
        cutoff = time.monotonic() - 300
        failed_logins[username] = [stamp for stamp in failed_logins[username] if stamp >= cutoff]
        if len(failed_logins[username]) >= 5:
            raise api_error(
                429,
                "login_rate_limited",
                "Too many sign-in attempts. Wait a few minutes and try again.",
            )
        with database.sessions.begin() as db:
            user = db.scalar(select(User).where(User.username == username))
            if not user or not verify_password(user.password_hash, request.password):
                failed_logins[username].append(time.monotonic())
                raise api_error(401, "invalid_credentials", "The username or password is incorrect.")
            failed_logins.pop(username, None)
            session_token = new_token()
            csrf_token = new_token()
            now = datetime.now(UTC)
            db.add(
                Session(
                    user_id=user.id,
                    token_hash=token_hash(session_token),
                    csrf_hash=token_hash(csrf_token),
                    created_at=now,
                    expires_at=now + timedelta(hours=12),
                )
            )
            response.set_cookie(
                SESSION_COOKIE,
                session_token,
                max_age=43200,
                secure=secure_cookies,
                httponly=True,
                samesite="strict",
                path="/",
            )
            return {"display_name": user.display_name, "csrf_token": csrf_token}

    @app.post("/api/auth/logout", status_code=204)
    def logout(
        response: Response,
        identity: Annotated[tuple[User, Session], Depends(csrf_session)],
    ) -> Response:
        with database.sessions.begin() as db:
            record = db.get(Session, identity[1].id)
            if record:
                db.delete(record)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.status_code = 204
        return response

    @app.get("/api/me")
    def me(identity: Annotated[tuple[User, Session], Depends(current_session)]) -> dict[str, str]:
        return {"id": identity[0].id, "display_name": identity[0].display_name}

    @app.get("/api/dashboard")
    def dashboard(
        identity: Annotated[tuple[User, Session], Depends(current_session)],
    ) -> dict[str, Any]:
        worlds = services.worlds()
        with database.sessions() as db:
            attempts = list(db.scalars(select(MissionAttempt).where(MissionAttempt.user_id == identity[0].id)))
            mastery = list(db.scalars(select(Mastery).where(Mastery.user_id == identity[0].id)))
        completed = {attempt.mission_id for attempt in attempts if attempt.completed_at}
        recommended = next(
            (mission["id"] for world in worlds for mission in world["missions"] if mission["id"] not in completed),
            None,
        )
        return {
            "worlds": worlds,
            "recommended_mission_id": recommended,
            "mastery": {item.skill: item.score for item in mastery},
            "completed_missions": sorted(completed),
        }

    @app.get("/api/missions/{mission_id}")
    def mission(
        mission_id: str,
        _identity: Annotated[tuple[User, Session], Depends(current_session)],
    ) -> dict[str, Any]:
        result = services.mission(mission_id)
        if not result:
            raise api_error(404, "mission_not_found", "That mission does not exist.")
        return result

    @app.get("/api/questions/{question_id}")
    def question(
        question_id: str,
        _identity: Annotated[tuple[User, Session], Depends(current_session)],
    ) -> dict[str, Any]:
        result = services.public_question(question_id)
        if not result:
            raise api_error(404, "question_not_found", "That question does not exist.")
        return result

    @app.post("/api/missions/{mission_id}/start")
    def start_mission(
        mission_id: str,
        identity: Annotated[tuple[User, Session], Depends(csrf_session)],
    ) -> dict[str, Any]:
        if not services.mission(mission_id):
            raise api_error(404, "mission_not_found", "That mission does not exist.")
        with database.sessions.begin() as db:
            attempt = db.scalar(
                select(MissionAttempt).where(
                    MissionAttempt.user_id == identity[0].id,
                    MissionAttempt.mission_id == mission_id,
                    MissionAttempt.course_version == services.course_version,
                )
            )
            if not attempt:
                attempt = MissionAttempt(
                    user_id=identity[0].id,
                    mission_id=mission_id,
                    course_version=services.course_version,
                    current_beat=0,
                    started_at=datetime.now(UTC),
                )
                db.add(attempt)
                db.flush()
            return {
                "attempt_id": attempt.id,
                "mission_id": attempt.mission_id,
                "course_version": attempt.course_version,
                "current_beat": attempt.current_beat,
            }

    @app.patch("/api/attempts/{attempt_id}/beat")
    def update_beat(
        attempt_id: str,
        request: BeatRequest,
        identity: Annotated[tuple[User, Session], Depends(csrf_session)],
    ) -> dict[str, Any]:
        with database.sessions.begin() as db:
            attempt = db.get(MissionAttempt, attempt_id)
            if not attempt or attempt.user_id != identity[0].id:
                raise api_error(404, "attempt_not_found", "That mission attempt does not exist.")
            attempt.current_beat = request.beat
            if request.beat == 4:
                attempt.completed_at = datetime.now(UTC)
            return {"attempt_id": attempt.id, "current_beat": attempt.current_beat}

    @app.post("/api/attempts/{attempt_id}/answers/{question_id}")
    def answer(
        attempt_id: str,
        question_id: str,
        request: AnswerRequest,
        identity: Annotated[tuple[User, Session], Depends(csrf_session)],
    ) -> dict[str, Any]:
        with database.sessions.begin() as db:
            prior = db.scalar(
                select(AnswerAttempt).where(
                    AnswerAttempt.submission_id == request.submission_id,
                    AnswerAttempt.user_id == identity[0].id,
                )
            )
            if prior:
                return dict(prior.result)
            attempt = db.get(MissionAttempt, attempt_id)
            if not attempt or attempt.user_id != identity[0].id:
                raise api_error(404, "attempt_not_found", "That mission attempt does not exist.")
            public_question = services.public_question(question_id)
            if not public_question:
                raise api_error(404, "question_not_found", "That question does not exist.")
            skill = str(public_question["mastery_skill"])
            mastery = db.scalar(
                select(Mastery).where(
                    Mastery.user_id == identity[0].id,
                    Mastery.skill == skill,
                )
            )
            current_mastery = mastery.score if mastery else 0.0
            try:
                result = services.score(
                    {
                        "request_id": request.submission_id,
                        "question_id": question_id,
                        "submitted": request.answer,
                        "hints_used": request.hints_used,
                        "current_mastery": current_mastery,
                    }
                )
            except KeyError as exc:
                raise api_error(404, "question_not_found", "That question does not exist.") from exc
            now = datetime.now(UTC)
            if mastery:
                mastery.score = result["new_mastery"]
                mastery.updated_at = now
            else:
                db.add(
                    Mastery(
                        user_id=identity[0].id,
                        skill=skill,
                        score=result["new_mastery"],
                        updated_at=now,
                    )
                )
            db.add(
                AnswerAttempt(
                    submission_id=request.submission_id,
                    user_id=identity[0].id,
                    mission_attempt_id=attempt.id,
                    question_id=question_id,
                    result=result,
                    created_at=now,
                )
            )
            review = db.scalar(
                select(Review).where(
                    Review.user_id == identity[0].id,
                    Review.question_id == question_id,
                )
            )
            scheduled = services.schedule(
                {
                    "repetitions": review.repetitions if review else 0,
                    "interval_days": review.interval_days if review else 0,
                    "ease": review.ease if review else 2.5,
                    "quality": 5 if result["correct"] and request.hints_used == 0 else 2,
                }
            )
            due_at = datetime.fromisoformat(scheduled["due_at"])
            if review:
                review.repetitions = scheduled["repetitions"]
                review.interval_days = scheduled["interval_days"]
                review.ease = scheduled["ease"]
                review.due_at = due_at
            else:
                db.add(
                    Review(
                        user_id=identity[0].id,
                        question_id=question_id,
                        repetitions=scheduled["repetitions"],
                        interval_days=scheduled["interval_days"],
                        ease=scheduled["ease"],
                        due_at=due_at,
                    )
                )
            return result

    @app.get("/api/reviews/queue")
    def review_queue(
        identity: Annotated[tuple[User, Session], Depends(current_session)],
    ) -> list[dict[str, Any]]:
        with database.sessions() as db:
            reviews = list(db.scalars(select(Review).where(Review.user_id == identity[0].id).order_by(Review.due_at).limit(20)))
        return [
            {
                "question_id": review.question_id,
                "due_at": aware(review.due_at).isoformat(),
                "repetitions": review.repetitions,
            }
            for review in reviews
        ]

    @app.post("/api/simulations/{scenario_id}/start")
    def start_simulation(
        scenario_id: str,
        identity: Annotated[tuple[User, Session], Depends(csrf_session)],
    ) -> dict[str, Any]:
        try:
            state = services.start_simulation(scenario_id)
        except (KeyError, ValueError) as exc:
            raise api_error(404, "scenario_not_found", "That scenario does not exist.") from exc
        now = datetime.now(UTC)
        with database.sessions.begin() as db:
            run = SimulationRun(
                user_id=identity[0].id,
                scenario_id=scenario_id,
                current_state=state["state_id"],
                score=0,
                course_version=services.course_version,
                started_at=now,
            )
            db.add(run)
            db.flush()
            return {"run_id": run.id, "score": run.score, **state}

    @app.post("/api/simulations/runs/{run_id}/choices/{choice_id}")
    def advance_simulation(
        run_id: str,
        choice_id: str,
        identity: Annotated[tuple[User, Session], Depends(csrf_session)],
    ) -> dict[str, Any]:
        with database.sessions.begin() as db:
            run = db.get(SimulationRun, run_id)
            if not run or run.user_id != identity[0].id:
                raise api_error(404, "simulation_run_not_found", "That simulation run does not exist.")
            try:
                state = services.advance_simulation(
                    run.scenario_id,
                    run.current_state,
                    choice_id,
                )
            except ValueError as exc:
                raise api_error(409, "invalid_transition", "That choice is no longer valid.") from exc
            run.current_state = state["state_id"]
            run.score += state["score_delta"]
            if state["terminal"]:
                run.completed_at = datetime.now(UTC)
            return {"run_id": run.id, "score": run.score, **state}

    @app.get("/api/search")
    def search(
        _identity: Annotated[tuple[User, Session], Depends(current_session)],
        q: str = Query(min_length=2, max_length=120),
        limit: int = Query(default=10, ge=1, le=25),
    ) -> list[dict[str, Any]]:
        return services.search(q, limit)

    return app


def default_app() -> FastAPI:
    database_url = os.environ.get("DATABASE_URL")
    internal_token = os.environ.get("INTERNAL_SERVICE_TOKEN")
    if not database_url or not internal_token:
        raise RuntimeError("DATABASE_URL and INTERNAL_SERVICE_TOKEN are required")
    database = create_database(database_url, create_schema=False)
    seed_users = os.environ.get("SEED_USERS")
    if seed_users:
        username, display_name, password = seed_users.split(":", 2)
        seed_user(database, username, password, display_name)
    services = HttpServices(
        os.getenv("CONTENT_SERVICE_URL", "http://content:8080"),
        os.getenv("LEARNING_SERVICE_URL", "http://learning:8080"),
        os.getenv("SIMULATION_SERVICE_URL", "http://simulation:8080"),
        internal_token,
    )
    return create_app(database, services, secure_cookies=True)
