"""Membership helpers for group-scoped list pages (edit/delete affordances)."""

from sqlalchemy.orm import Session

from app.dependencies import ROLE_HIERARCHY
from app.enums import Role
from app.models import User, UserGroup


def group_page_capabilities(db: Session, user: User, group_id: int) -> dict[str, bool]:
    ug = (
        db.query(UserGroup)
        .filter(
            UserGroup.user_id == user.id,
            UserGroup.group_id == group_id,
        )
        .first()
    )
    can_edit = bool(
        ug and ROLE_HIERARCHY.get(ug.role, 0) >= ROLE_HIERARCHY[Role.contributor.value]
    )
    can_delete = bool(ug and ug.role == Role.admin.value)
    return {"can_edit": can_edit, "can_delete": can_delete}
