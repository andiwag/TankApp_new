"""Regression checks for storage-tank Alembic migrations on Postgres."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import pytest
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
TANK_MIGRATION = (
    ROOT / "alembic" / "versions" / "f6a8b0c2d4e5_add_storage_tanks_and_ledger.py"
)
FILL_SOURCE_MIGRATION = (
    ROOT / "alembic" / "versions" / "a7b9c1d3e5f6_add_fill_source_to_fuel_entries.py"
)

TEST_DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite://")
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
