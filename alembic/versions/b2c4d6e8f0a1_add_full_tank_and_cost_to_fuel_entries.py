"""add full_tank and total_cost_eur to fuel entries

Revision ID: b2c4d6e8f0a1
Revises: 8b6f2f4d9c3a
Create Date: 2026-06-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b2c4d6e8f0a1"
down_revision: Union[str, None] = "8b6f2f4d9c3a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    fuel_columns = {column["name"] for column in inspector.get_columns("fuel_entries")}

    if "full_tank" not in fuel_columns:
        op.add_column(
            "fuel_entries",
            sa.Column(
                "full_tank", sa.Boolean(), nullable=False, server_default=sa.true()
            ),
        )
    if "total_cost_eur" not in fuel_columns:
        op.add_column(
            "fuel_entries",
            sa.Column("total_cost_eur", sa.Float(), nullable=True),
        )

    # SQLite cannot ALTER COLUMN DROP DEFAULT; Postgres can clean up the default.
    if bind.dialect.name != "sqlite":
        op.alter_column("fuel_entries", "full_tank", server_default=None)


def downgrade() -> None:
    op.drop_column("fuel_entries", "total_cost_eur")
    op.drop_column("fuel_entries", "full_tank")
