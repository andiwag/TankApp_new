"""add storage tanks and tank ledger entries

Revision ID: f6a8b0c2d4e5
Revises: c8d0e2f4a6b8
Create Date: 2026-07-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a8b0c2d4e5"
down_revision: Union[str, None] = "c8d0e2f4a6b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

tank_movement_type_enum = sa.Enum(
    "delivery",
    "vehicle_withdrawal",
    "external_withdrawal",
    "adjustment",
    name="tank_movement_type_enum",
)


def upgrade() -> None:
    op.create_table(
        "storage_tanks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "fuel_type",
            sa.Enum("diesel", "petrol", name="fuel_type_enum", create_type=False),
            nullable=False,
        ),
        sa.Column("capacity_l", sa.Float(), nullable=True),
        sa.Column("opening_balance_l", sa.Float(), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("opening_balance_l >= 0", name="ck_tank_opening_non_negative"),
        sa.CheckConstraint(
            "capacity_l IS NULL OR capacity_l > 0",
            name="ck_tank_capacity_positive",
        ),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_storage_tanks_group_id", "storage_tanks", ["group_id"])
    op.create_table(
        "tank_ledger_entries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tank_id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("movement_type", tank_movement_type_enum, nullable=False),
        sa.Column("amount_l", sa.Float(), nullable=False),
        sa.Column("entry_date", sa.Date(), nullable=False),
        sa.Column("fuel_entry_id", sa.Integer(), nullable=True),
        sa.Column("recipient_name", sa.String(length=200), nullable=True),
        sa.Column("total_cost_eur", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("amount_l != 0", name="ck_ledger_amount_non_zero"),
        sa.ForeignKeyConstraint(["fuel_entry_id"], ["fuel_entries.id"]),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"]),
        sa.ForeignKeyConstraint(["tank_id"], ["storage_tanks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tank_ledger_entries_tank_id", "tank_ledger_entries", ["tank_id"]
    )
    op.create_index(
        "ix_tank_ledger_entries_fuel_entry_id",
        "tank_ledger_entries",
        ["fuel_entry_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_tank_ledger_entries_fuel_entry_id", table_name="tank_ledger_entries")
    op.drop_index("ix_tank_ledger_entries_tank_id", table_name="tank_ledger_entries")
    op.drop_table("tank_ledger_entries")
    op.drop_index("ix_storage_tanks_group_id", table_name="storage_tanks")
    op.drop_table("storage_tanks")
    tank_movement_type_enum.drop(op.get_bind(), checkfirst=True)