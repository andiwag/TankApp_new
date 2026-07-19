"""add adblue_amount_l to fuel entries

Revision ID: e5f7a9b1c3d4
Revises: d4e6f8a0b2c3
Create Date: 2026-07-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f7a9b1c3d4"
down_revision: Union[str, None] = "d4e6f8a0b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("fuel_entries", sa.Column("adblue_amount_l", sa.Float(), nullable=True))
    op.create_check_constraint(
        "ck_adblue_amount_positive",
        "fuel_entries",
        "adblue_amount_l IS NULL OR adblue_amount_l > 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_adblue_amount_positive", "fuel_entries", type_="check")
    op.drop_column("fuel_entries", "adblue_amount_l")
