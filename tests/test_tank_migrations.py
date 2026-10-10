"""Regression checks for storage-tank Alembic migrations on Postgres."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from app.config import settings
from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    inspect,
    text,
)

ROOT = Path(__file__).resolve().parents[1]
TANK_MIGRATION = (
    ROOT / "alembic" / "versions" / "f6a8b0c2d4e5_add_storage_tanks_and_ledger.py"
)
FILL_SOURCE_MIGRATION = (
    ROOT / "alembic" / "versions" / "a7b9c1d3e5f6_add_fill_source_to_fuel_entries.py"
)

TEST_DATABASE_URL = (
    os.environ.get("TEST_DATABASE_URL")
    or settings.TEST_DATABASE_URL
    or os.environ.get("DATABASE_URL", "sqlite://")
)
_USE_POSTGRES = TEST_DATABASE_URL.startswith("postgresql")
PARENT_REVISION = "c8d0e2f4a6b8"


def test_storage_tanks_migration_reuses_fuel_type_with_postgresql_enum():
    """sa.Enum ignores create_type=False; only postgresql.ENUM honors it."""
    source = TANK_MIGRATION.read_text(encoding="utf-8")
    assert "postgresql.ENUM" in source
    assert 'name="fuel_type_enum"' in source
    assert "create_type=False" in source
    assert 'sa.Enum("diesel", "petrol", name="fuel_type_enum"' not in source


def test_fill_source_migration_uses_postgresql_enum_create_type_false():
    source = FILL_SOURCE_MIGRATION.read_text(encoding="utf-8")
    assert "postgresql.ENUM" in source
    assert 'name="fill_source_enum"' in source
    assert "create_type=False" in source
    assert 'sa.Enum("external", "farm", name="fill_source_enum"' not in source


def test_tank_movement_enum_created_explicitly_with_checkfirst():
    source = TANK_MIGRATION.read_text(encoding="utf-8")
    assert 'name="tank_movement_type_enum"' in source
    assert "create_type=False" in source
    assert "tank_movement_type_enum.create(" in source
    assert "checkfirst=True" in source


def _admin_url_and_db_name(database_url: str) -> tuple[str, str]:
    parsed = urlparse(database_url)
    db_name = parsed.path.lstrip("/")
    admin = parsed._replace(path="/postgres")
    return urlunparse(admin), db_name


def _run_alembic(database_url: str, *args: str) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env={
            **os.environ,
            "DATABASE_URL": database_url,
            "ENV": "development",
        },
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = "\n".join(
            part for part in (result.stderr, result.stdout) if part
        ).strip()
        raise RuntimeError(detail or f"alembic {' '.join(args)} failed")


@pytest.mark.parametrize("column_already_added", [False, True])
def test_user_last_group_migration_supports_sqlite_and_partial_upgrade(
    tmp_path, column_already_added
):
    database_path = tmp_path / "last_group_migration.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    engine = create_engine(database_url)
    metadata = MetaData()
    groups = Table("groups", metadata, Column("id", Integer, primary_key=True))
    user_columns = [
        Column("id", Integer, primary_key=True),
        Column("email", String(320), nullable=False),
    ]
    if column_already_added:
        user_columns.append(Column("last_group_id", Integer, nullable=True))
    users = Table("users", metadata, *user_columns)
    revisions = Table(
        "alembic_version",
        metadata,
        Column("version_num", String(32), primary_key=True),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(groups.insert().values(id=1))
        user_data = {"id": 1, "email": "local@example.test"}
        if column_already_added:
            user_data["last_group_id"] = 1
        connection.execute(users.insert().values(**user_data))
        connection.execute(revisions.insert().values(version_num="a7b9c1d3e5f6"))
    engine.dispose()

    _run_alembic(database_url, "upgrade", "d1e3f5a7b9c2")

    upgraded_engine = create_engine(database_url)
    upgraded_inspector = inspect(upgraded_engine)
    user_columns = {
        column["name"] for column in upgraded_inspector.get_columns("users")
    }
    foreign_keys = upgraded_inspector.get_foreign_keys("users")
    with upgraded_engine.connect() as connection:
        saved_user = connection.execute(
            text("SELECT id, email, last_group_id FROM users WHERE id = 1")
        ).one()
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    upgraded_engine.dispose()

    assert "last_group_id" in user_columns
    assert any(
        foreign_key["name"] == "fk_users_last_group_id" for foreign_key in foreign_keys
    )
    assert saved_user == (1, "local@example.test", 1 if column_already_added else None)
    assert revision == "d1e3f5a7b9c2"

    _run_alembic(database_url, "downgrade", "a7b9c1d3e5f6")

    downgraded_engine = create_engine(database_url)
    downgraded_inspector = inspect(downgraded_engine)
    with downgraded_engine.connect() as connection:
        revision = connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one()
    downgraded_engine.dispose()

    assert "last_group_id" not in {
        column["name"] for column in downgraded_inspector.get_columns("users")
    }
    assert revision == "a7b9c1d3e5f6"


@pytest.mark.skipif(not _USE_POSTGRES, reason="Postgres-only deploy simulation")
def test_upgrade_from_parent_revision_does_not_recreate_fuel_type_enum():
    """Deploy path: DB already has fuel_type_enum, only new revisions run.

    Full ``alembic upgrade head`` on an empty DB can hide this bug because
    SQLAlchemy memos enum names for the lifetime of one Alembic process.
    """
    admin_url, base_db = _admin_url_and_db_name(TEST_DATABASE_URL)
    scratch_db = f"{base_db}_tank_mig_scratch"
    scratch_url = urlunparse(
        urlparse(TEST_DATABASE_URL)._replace(path=f"/{scratch_db}")
    )

    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_db}"'))
            conn.execute(text(f'CREATE DATABASE "{scratch_db}"'))
        try:
            _run_alembic(scratch_url, "upgrade", PARENT_REVISION)
            _run_alembic(scratch_url, "upgrade", "head")
            engine = create_engine(scratch_url)
            with engine.connect() as conn:
                tables = {
                    row[0]
                    for row in conn.execute(
                        text(
                            "SELECT tablename FROM pg_tables "
                            "WHERE schemaname = 'public'"
                        )
                    )
                }
                assert "storage_tanks" in tables
                assert "tank_ledger_entries" in tables
            engine.dispose()
        finally:
            with admin.connect() as conn:
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) "
                        "FROM pg_stat_activity "
                        f"WHERE datname = '{scratch_db}' "
                        "AND pid <> pg_backend_pid()"
                    )
                )
                conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_db}"'))
    finally:
        admin.dispose()
