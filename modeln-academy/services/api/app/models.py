"""Relational persistence model for learner state."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def identifier() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    username: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MissionAttempt(Base):
    __tablename__ = "mission_attempts"
    __table_args__ = (UniqueConstraint("user_id", "mission_id", "course_version", name="uq_open_mission_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mission_id: Mapped[str] = mapped_column(String(160), index=True)
    course_version: Mapped[str] = mapped_column(String(64))
    current_beat: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AnswerAttempt(Base):
    __tablename__ = "answer_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    submission_id: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    mission_attempt_id: Mapped[str] = mapped_column(ForeignKey("mission_attempts.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(160), index=True)
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Mastery(Base):
    __tablename__ = "mastery"
    __table_args__ = (UniqueConstraint("user_id", "skill", name="uq_user_skill"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    skill: Mapped[str] = mapped_column(String(160))
    score: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Review(Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("user_id", "question_id", name="uq_user_review_question"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[str] = mapped_column(String(160))
    repetitions: Mapped[int] = mapped_column(Integer, default=0)
    interval_days: Mapped[int] = mapped_column(Integer, default=1)
    ease: Mapped[float] = mapped_column(Float, default=2.5)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=identifier)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    scenario_id: Mapped[str] = mapped_column(String(160), index=True)
    current_state: Mapped[str] = mapped_column(String(160))
    score: Mapped[int] = mapped_column(Integer, default=0)
    course_version: Mapped[str] = mapped_column(String(64))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
