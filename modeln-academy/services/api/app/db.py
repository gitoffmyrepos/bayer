"""Database construction and idempotent learner seeding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session as OrmSession
from sqlalchemy.orm import sessionmaker

from .auth import hash_password
from .models import Base, User


@dataclass(frozen=True)
class Database:
    engine: Engine
    sessions: sessionmaker[OrmSession]


def normalize_database_url(url: str) -> str:
    """Select the bundled psycopg 3 driver for CloudNativePG connection URIs."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def create_database(url: str, create_schema: bool = True) -> Database:
    url = normalize_database_url(url)
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
    database = Database(engine=engine, sessions=sessionmaker(engine, expire_on_commit=False))
    if create_schema:
        Base.metadata.create_all(engine)
    return database


def seed_user(database: Database, username: str, password: str, display_name: str) -> User:
    normalized = username.strip().casefold()
    with database.sessions.begin() as session:
        existing = session.scalar(select(User).where(User.username == normalized))
        if existing:
            return existing
        user = User(
            username=normalized,
            display_name=display_name.strip(),
            password_hash=hash_password(password),
            created_at=datetime.now(UTC),
        )
        session.add(user)
        session.flush()
        return user
