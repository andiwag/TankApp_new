"""Add maintenance logs and revocable user sessions."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e6f8a0b2c3"
down_revision: Union[str, None] = "b2c4d6e8f0a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "maintenance_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("vehicle_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("usage_reading", sa.Float(), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("cost_eur", sa.Float(), nullable=True),
        sa.Column("next_service_date", sa.Date(), nullable=True),
        sa.Column("next_service_usage", sa.Float(), nullable=True),
        sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "usage_reading IS NULL OR usage_reading >= 0",
            name="ck_maint_usage_non_negative",
        ),
        sa.CheckConstraint(
            "cost_eur IS NULL OR cost_eur >= 0",
            name="ck_maint_cost_non_negative",
        ),
        sa.CheckConstraint(
            "next_service_usage IS NULL OR next_service_usage >= 0",
            name="ck_maint_next_usage_non_negative",
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("user_sessions")
    op.drop_table("maintenance_logs")
