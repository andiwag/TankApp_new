"""Membership helpers for group-scoped list pages (edit/delete affordances)."""

from sqlalchemy.orm import Session

from app.dependencies import ROLE_HIERARCHY
from app.enums import Role
from app.models import User, UserGroup
from app.services.entitlements import effective_tier, tier_has_feature


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
        .join(User, User.id == UserGroup.user_id)
        .filter(
            UserGroup.group_id == group_id,
            UserGroup.role == Role.admin.value,
            User.deleted_at == None,  # noqa: E711
        )
        .count()
    )


def list_group_admin_users(db: Session, group_id: int) -> list[User]:
    return (
        db.query(User)
        .join(UserGroup, UserGroup.user_id == User.id)
        .filter(
            UserGroup.group_id == group_id,
            UserGroup.role == Role.admin.value,
            User.deleted_at == None,  # noqa: E711
        )
        .all()
    )


def group_page_capabilities(db: Session, user: User, group_id: int) -> dict[str, bool]:
    ug = get_membership(db, user.id, group_id)
    can_edit = bool(
        ug and ROLE_HIERARCHY.get(ug.role, 0) >= ROLE_HIERARCHY[Role.contributor.value]
    )
    can_delete = bool(ug and ug.role == Role.admin.value)
    can_view_audit = can_delete
    tier = effective_tier(db, group_id)
    return {
        "can_edit": can_edit,
        "can_delete": can_delete,
        "can_view_audit": can_view_audit,
        "can_export": tier_has_feature(tier, "export"),
        "can_maintenance": tier_has_feature(tier, "maintenance"),
        "can_analytics": tier_has_feature(tier, "analytics"),
    }
