"""Group settings page context and member-management mutations."""

from sqlalchemy.orm import Session

from app.enums import Role
from app.models import Group, User, UserGroup
from app.services.invite_codes import generate_unique_invite_code
from app.services.membership import get_membership


def list_group_members(db: Session, group_id: int) -> list[UserGroup]:
    return (
        db.query(UserGroup)
        .join(User, User.id == UserGroup.user_id)
        .filter(
            UserGroup.group_id == group_id,
            User.deleted_at == None,  # noqa: E711
        )
        .order_by(User.name.asc(), User.email.asc())
        .all()
    )


def group_settings_context(db: Session, user: User, group: Group) -> dict:
    membership = get_membership(db, user.id, group.id)
    is_admin = bool(membership and membership.role == Role.admin.value)
    return {
        "group": group,
        "members": list_group_members(db, group.id),
        "is_admin": is_admin,
        "roles": [role.value for role in Role],
    }


def regenerate_group_invite_code(db: Session, group: Group) -> str:
    group.invite_code = generate_unique_invite_code(db)
    db.commit()
    db.refresh(group)
    return group.invite_code


def change_member_role(
    db: Session,
    *,
    group_id: int,
    actor_user_id: int,
    member_user_id: int,
    role: str,
) -> bool:
    if role not in {role.value for role in Role}:
        raise ValueError("Ungültige Rolle.")
    if actor_user_id == member_user_id:
        raise PermissionError("Du kannst deine eigene Rolle nicht ändern.")

    membership = get_membership(db, member_user_id, group_id)
    if not membership:
        return False

    membership.role = role
    db.flush()
    return True


def remove_member(
    db: Session,
    *,
    group_id: int,
    actor_user_id: int,
    member_user_id: int,
) -> bool:
    if actor_user_id == member_user_id:
        raise PermissionError("Du kannst dich nicht selbst entfernen.")

    membership = get_membership(db, member_user_id, group_id)
    if not membership:
        return False

    db.delete(membership)
    db.flush()
    return True
