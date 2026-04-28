"""allow nullable audit log group id

Revision ID: 8b6f2f4d9c3a
Revises: 1e298c1a86d6
Create Date: 2026-04-28 22:39:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8b6f2f4d9c3a"
down_revision: Union[str, Sequence[str], None] = "1e298c1a86d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "group_id",
            existing_type=sa.Integer(),
            nullable=True,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("audit_logs") as batch_op:
        batch_op.alter_column(
            "group_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
