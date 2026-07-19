"""Regression checks for the Stripe billing Alembic migration."""

from pathlib import Path

BILLING_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "alembic"
    / "versions"
    / "e5f7a9b1c3d4_add_group_subscriptions_and_billing_events.py"
)


def test_billing_migration_seed_uses_sql_boolean_not_integer():
    """Postgres rejects integer 0 for boolean columns even when seeding 0 rows."""
    source = BILLING_MIGRATION.read_text(encoding="utf-8")
    assert "cancel_at_period_end" in source
    assert ", 0, CURRENT_TIMESTAMP" not in source
    assert (
        ", false, CURRENT_TIMESTAMP" in source or ", FALSE, CURRENT_TIMESTAMP" in source
    )
