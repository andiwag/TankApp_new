"""add adblue_amount_l to fuel entries

Revision ID: c8d0e2f4a6b8
Revises: e5f7a9b1c3d4
Create Date: 2026-07-19

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c8d0e2f4a6b8"
down_revision: Union[str, None] = "e5f7a9b1c3d4"
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
