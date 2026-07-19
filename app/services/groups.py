"""Group listing and membership mutations."""

import logging

from sqlalchemy.orm import Session

from app.enums import Role
from app.models import Group, GroupSubscription, User, UserGroup
from app.schemas import GroupCreate
from app.services.billing import stripe_client
from app.services.billing.subscriptions import ensure_group_subscription
from app.services.invite_codes import generate_unique_invite_code
from app.services.membership import count_group_admins, get_membership
from app.time_utils import utc_now

logger = logging.getLogger(__name__)


class GroupActionError(Exception):
    """User-recoverable group action error for SSR form rendering."""


def user_groups_context(db: Session, user: User, active_group_id: int | None) -> dict:
    rows = (
        db.query(Group, UserGroup.role)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .filter(
            UserGroup.user_id == user.id,
            Group.deleted_at == None,  # noqa: E711
        )
        .all()
    )
    return {
        "groups": [{"group": g, "role": r} for g, r in rows],
        "active_group_id": active_group_id,
    }


def create_group(db: Session, user: User, data: GroupCreate) -> Group:
    group = Group(
        name=data.name,
        invite_code=generate_unique_invite_code(db),
        created_by=user.id,
    )
    db.add(group)
    db.flush()
    db.add(UserGroup(user_id=user.id, group_id=group.id, role=Role.admin.value))
    db.flush()
    ensure_group_subscription(db, group.id)
    return group


def join_group_by_invite_code(db: Session, user: User, invite_code: str) -> Group:
    group = (
        db.query(Group)
        .filter(
            Group.invite_code == invite_code,
            Group.deleted_at == None,  # noqa: E711
        )
        .first()
    )
    if not group:
        raise GroupActionError("Ungültiger Einladungscode")

    if get_membership(db, user.id, group.id):
        raise GroupActionError("Du bist bereits Mitglied dieser Gruppe")

    db.add(
        UserGroup(
            user_id=user.id,
            group_id=group.id,
            role=Role.contributor.value,
        )
    )
    db.flush()
    return group


def switchable_group_for_user(db: Session, user: User, group_id: int) -> Group | None:
    if not get_membership(db, user.id, group_id):
        return None
    return (
        db.query(Group)
        .filter(
            Group.id == group_id,
            Group.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def leave_group(db: Session, user: User, group_id: int) -> bool:
    membership = get_membership(db, user.id, group_id)
    if not membership:
        return False

    if membership.role == Role.admin.value and count_group_admins(db, group_id) <= 1:
        raise GroupActionError(
            "Als alleiniger Admin kannst du die Gruppe nicht verlassen. "
            "Bitte zuerst einen weiteren Admin bestellen."
        )

    db.delete(membership)
    db.flush()
    return True


def soft_delete_group_as_admin(db: Session, user: User, group_id: int) -> Group | None:
    membership = get_membership(db, user.id, group_id)
    if not membership or membership.role != Role.admin.value:
        raise PermissionError("Forbidden")

    group = (
        db.query(Group)
        .filter(
            Group.id == group_id,
            Group.deleted_at == None,  # noqa: E711
        )
        .first()
    )
    if not group:
        return None

    group.deleted_at = utc_now()
    sub = (
        db.query(GroupSubscription)
        .filter(GroupSubscription.group_id == group_id)
        .first()
    )
    if sub and sub.stripe_subscription_id:
        try:
            stripe_client.cancel_subscription(sub.stripe_subscription_id)
        except Exception:
            logger.exception(
                "Failed to cancel Stripe subscription %s for group %s",
                sub.stripe_subscription_id,
                group_id,
            )
    db.flush()
    return group
