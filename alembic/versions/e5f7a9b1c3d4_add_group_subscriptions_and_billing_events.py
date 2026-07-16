"""Add group_subscriptions and billing_events for Stripe billing."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f7a9b1c3d4"
down_revision: Union[str, None] = "d4e6f8a0b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "group_subscriptions",
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("stripe_customer_id", sa.String(length=255), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tier", sa.String(length=16), nullable=False),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.PrimaryKeyConstraint("group_id"),
    )
    op.create_table(
        "billing_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("stripe_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_billing_events_stripe_event_id"),
        "billing_events",
        ["stripe_event_id"],
        unique=True,
    )

    op.execute(
        """
        INSERT INTO group_subscriptions (group_id, status, tier, cancel_at_period_end, updated_at)
        SELECT id, 'active', COALESCE(subscription_tier, 'free'), 0, CURRENT_TIMESTAMP
        FROM groups
        WHERE deleted_at IS NULL
        """
    )

    op.execute(
        """
        UPDATE groups
        SET subscription_tier = 'free'
        WHERE deleted_at IS NULL AND subscription_tier IS NULL
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_billing_events_stripe_event_id"), table_name="billing_events")
    op.drop_table("billing_events")
    op.drop_table("group_subscriptions")
