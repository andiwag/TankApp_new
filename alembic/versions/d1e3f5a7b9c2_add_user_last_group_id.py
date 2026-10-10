"""Add users.last_group_id for the farm opened by default."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1e3f5a7b9c2"
down_revision: str | None = "a7b9c1d3e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    foreign_key_names = {
        foreign_key["name"] for foreign_key in inspector.get_foreign_keys("users")
    }

    if (
        "last_group_id" not in user_columns
        or "fk_users_last_group_id" not in foreign_key_names
    ):
        with op.batch_alter_table("users") as batch_op:
            if "last_group_id" not in user_columns:
                batch_op.add_column(
                    sa.Column("last_group_id", sa.Integer(), nullable=True)
                )
            if "fk_users_last_group_id" not in foreign_key_names:
                batch_op.create_foreign_key(
                    "fk_users_last_group_id",
                    "groups",
                    ["last_group_id"],
                    ["id"],
                    ondelete="SET NULL",
                )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    user_columns = {column["name"] for column in inspector.get_columns("users")}
    foreign_key_names = {
        foreign_key["name"] for foreign_key in inspector.get_foreign_keys("users")
    }

    if "last_group_id" in user_columns or "fk_users_last_group_id" in foreign_key_names:
        with op.batch_alter_table("users") as batch_op:
            if "fk_users_last_group_id" in foreign_key_names:
                batch_op.drop_constraint("fk_users_last_group_id", type_="foreignkey")
            if "last_group_id" in user_columns:
                batch_op.drop_column("last_group_id")
