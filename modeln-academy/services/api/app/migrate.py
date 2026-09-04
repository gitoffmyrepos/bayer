"""Idempotent schema bootstrap used by the Kubernetes migration job."""

from __future__ import annotations

import os

from .db import create_database


def migrate(database_url: str) -> None:
    create_database(database_url, create_schema=True)


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    migrate(database_url)


if __name__ == "__main__":
    main()
