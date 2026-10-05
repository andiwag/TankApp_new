"""Add users.last_group_id for the farm opened by default."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e3f5a7b9c2"
down_revision: str | None = "a7b9c1d3e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_group_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_users_last_group_id",
        "users",
        "groups",
        ["last_group_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_users_last_group_id", "users", type_="foreignkey")
    op.drop_column("users", "last_group_id")
