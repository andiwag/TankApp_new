"""add fill_source and fuel_tank_id to fuel entries

Revision ID: a7b9c1d3e5f6
Revises: f6a8b0c2d4e5
Create Date: 2026-07-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a7b9c1d3e5f6"
down_revision: Union[str, None] = "f6a8b0c2d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

fill_source_enum = sa.Enum("external", "farm", name="fill_source_enum")


def upgrade() -> None:
    fill_source_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "fuel_entries",
        sa.Column(
            "fill_source",
            fill_source_enum,
            nullable=False,
            server_default="external",
        ),
    )
    op.add_column(
        "fuel_entries",
        sa.Column("fuel_tank_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_fuel_entries_fuel_tank_id",
        "fuel_entries",
        "storage_tanks",
        ["fuel_tank_id"],
        ["id"],
    )
    op.alter_column("fuel_entries", "fill_source", server_default=None)


def downgrade() -> None:
    op.drop_constraint("fk_fuel_entries_fuel_tank_id", "fuel_entries", type_="foreignkey")
    op.drop_column("fuel_entries", "fuel_tank_id")
    op.drop_column("fuel_entries", "fill_source")
    fill_source_enum.drop(op.get_bind(), checkfirst=True)
