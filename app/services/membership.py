"""Membership helpers for group-scoped list pages (edit/delete affordances)."""

from sqlalchemy.orm import Session

from app.dependencies import ROLE_HIERARCHY
from app.enums import Role
from app.models import User, UserGroup


def get_membership(db: Session, user_id: int, group_id: int) -> UserGroup | None:
    return (
        db.query(UserGroup)
        .filter(
            UserGroup.user_id == user_id,
            UserGroup.group_id == group_id,
        )
        .first()
    )


def count_group_admins(db: Session, group_id: int) -> int:
    return (
        db.query(UserGroup)
        .filter(
            UserGroup.group_id == group_id,
            UserGroup.role == Role.admin.value,
        )
        .count()
    )


def group_page_capabilities(db: Session, user: User, group_id: int) -> dict[str, bool]:
    ug = get_membership(db, user.id, group_id)
    can_edit = bool(
        ug and ROLE_HIERARCHY.get(ug.role, 0) >= ROLE_HIERARCHY[Role.contributor.value]
    )
    can_delete = bool(ug and ug.role == Role.admin.value)
    can_view_audit = can_delete
    return {
        "can_edit": can_edit,
        "can_delete": can_delete,
        "can_view_audit": can_view_audit,
    }
