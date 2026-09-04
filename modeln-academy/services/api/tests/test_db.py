from sqlalchemy import create_engine, inspect

from services.api.app.db import normalize_database_url
from services.api.app.migrate import migrate


def test_cnpg_uri_selects_installed_psycopg_driver() -> None:
    assert normalize_database_url("postgresql://academy:secret@academy-pg-rw:5432/academy") == (
        "postgresql+psycopg://academy:secret@academy-pg-rw:5432/academy"
    )


def test_explicit_database_driver_is_preserved() -> None:
    url = "postgresql+psycopg://academy:secret@academy-pg-rw:5432/academy"
    assert normalize_database_url(url) == url


def test_migration_entrypoint_creates_complete_initial_schema(tmp_path) -> None:
    url = f"sqlite+pysqlite:///{tmp_path / 'migration.db'}"

    migrate(url)

    assert set(inspect(create_engine(url)).get_table_names()) >= {
        "users",
        "sessions",
        "mission_attempts",
        "answer_attempts",
        "mastery",
        "reviews",
        "simulation_runs",
    }
