"""Cross-farm queries and context for the platform operator dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.models import (
    AuditLog,
    FuelEntry,
    Group,
    GroupSubscription,
    MaintenanceLog,
    User,
    UserGroup,
    UserSession,
    Vehicle,
)
from app.services.audit_ui import list_audit_logs_for_group
from app.time_utils import utc_now


def _case_insensitive_contains(column, term: str):
    pattern = f"%{term.strip()}%"
    if settings.DATABASE_URL.startswith("postgresql"):
        return column.ilike(pattern)
    return func.lower(column).like(pattern.lower())


def mask_invite_code(invite_code: str) -> str:
    if invite_code.startswith("FARM-"):
        return "FARM-•••••"
    if len(invite_code) <= 4:
        return "•••••"
    return invite_code[:4] + "•••••"


def _subscription_tier_label(tier: str | None) -> str:
    return tier if tier else "free"


def _group_status_label(deleted_at: datetime | None) -> str:
    return "deleted" if deleted_at is not None else "active"


@dataclass(frozen=True)
class FarmListRow:
    id: int
    name: str
    invite_code_masked: str
    created_at: datetime
    status: str
    subscription_tier: str
    member_count: int
    vehicle_count: int
    last_activity: datetime | None


def list_farms(
    db: Session,
    *,
    status: str = "active",
    search: str | None = None,
) -> list[FarmListRow]:
    member_counts = (
        db.query(
            UserGroup.group_id, func.count(UserGroup.user_id).label("member_count")
        )
        .group_by(UserGroup.group_id)
        .subquery()
    )
    vehicle_counts = (
        db.query(Vehicle.group_id, func.count(Vehicle.id).label("vehicle_count"))
        .filter(Vehicle.deleted_at == None)  # noqa: E711
        .group_by(Vehicle.group_id)
        .subquery()
    )
    fuel_activity = (
        db.query(
            FuelEntry.group_id,
            func.max(FuelEntry.created_at).label("last_fuel_at"),
        )
        .filter(FuelEntry.deleted_at == None)  # noqa: E711
        .group_by(FuelEntry.group_id)
        .subquery()
    )
    audit_activity = (
        db.query(
            AuditLog.group_id,
            func.max(AuditLog.created_at).label("last_audit_at"),
        )
        .filter(AuditLog.group_id.isnot(None))
        .group_by(AuditLog.group_id)
        .subquery()
    )

    query = (
        db.query(
            Group,
            func.coalesce(member_counts.c.member_count, 0).label("member_count"),
            func.coalesce(vehicle_counts.c.vehicle_count, 0).label("vehicle_count"),
            fuel_activity.c.last_fuel_at,
            audit_activity.c.last_audit_at,
        )
        .outerjoin(member_counts, member_counts.c.group_id == Group.id)
        .outerjoin(vehicle_counts, vehicle_counts.c.group_id == Group.id)
        .outerjoin(fuel_activity, fuel_activity.c.group_id == Group.id)
        .outerjoin(audit_activity, audit_activity.c.group_id == Group.id)
    )

    if status == "active":
        query = query.filter(Group.deleted_at == None)  # noqa: E711
    elif status == "deleted":
        query = query.filter(Group.deleted_at != None)  # noqa: E711
    elif status != "all":
        status = "active"
        query = query.filter(Group.deleted_at == None)  # noqa: E711

    if search and search.strip():
        query = query.filter(_case_insensitive_contains(Group.name, search.strip()))

    query = query.order_by(Group.created_at.desc(), Group.id.desc())
    rows: list[FarmListRow] = []
    for group, member_count, vehicle_count, last_fuel_at, last_audit_at in query.all():
        last_activity = last_fuel_at
        if last_audit_at and (last_activity is None or last_audit_at > last_activity):
            last_activity = last_audit_at
        rows.append(
            FarmListRow(
                id=group.id,
                name=group.name,
                invite_code_masked=mask_invite_code(group.invite_code),
                created_at=group.created_at,
                status=_group_status_label(group.deleted_at),
                subscription_tier=_subscription_tier_label(group.subscription_tier),
                member_count=int(member_count),
                vehicle_count=int(vehicle_count),
                last_activity=last_activity,
            )
        )
    return rows


def farm_detail_context(db: Session, group_id: int) -> dict | None:
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        return None

    creator = db.query(User).filter(User.id == group.created_by).first()
    memberships = (
        db.query(UserGroup)
        .filter(UserGroup.group_id == group_id)
        .options(joinedload(UserGroup.user))
        .order_by(UserGroup.joined_at.asc())
        .all()
    )
    members = [
        {
            "email": membership.user.email,
            "name": membership.user.name,
            "role": membership.role,
            "joined_at": membership.joined_at,
        }
        for membership in memberships
        if membership.user.deleted_at is None
    ]

    vehicle_count = (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .count()
    )
    fuel_entry_count = (
        db.query(FuelEntry)
        .filter(
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
        )
        .count()
    )
    maintenance_log_count = (
        db.query(MaintenanceLog)
        .filter(
            MaintenanceLog.group_id == group_id,
            MaintenanceLog.deleted_at == None,  # noqa: E711
        )
        .count()
    )

    audit_logs = list_audit_logs_for_group(db, group_id, limit=20)
    audit_user_names = {
        user.id: user.name
        for user in db.query(User).filter(
            User.id.in_({log.user_id for log in audit_logs} or {0})
        )
    }
    audit_rows = [
        {
            "action": log.action,
            "entity_type": log.entity_type,
            "entity_id": log.entity_id,
            "user_name": audit_user_names.get(log.user_id, "Unknown"),
            "created_at": log.created_at,
        }
        for log in audit_logs
    ]

    tier = _subscription_tier_label(group.subscription_tier)
    sub = (
        db.query(GroupSubscription)
        .filter(GroupSubscription.group_id == group_id)
        .first()
    )
    has_stripe_subscription = bool(sub and sub.stripe_subscription_id)
    return {
        "group": group,
        "creator_email": creator.email if creator else None,
        "status": _group_status_label(group.deleted_at),
        "subscription_tier": tier,
        "is_partner_tier": tier == "partner",
        "has_stripe_subscription": has_stripe_subscription,
        "members": members,
        "vehicle_count": vehicle_count,
        "fuel_entry_count": fuel_entry_count,
        "maintenance_log_count": maintenance_log_count,
        "audit_rows": audit_rows,
        "support_view_available": True,
    }


def search_users(db: Session, query: str) -> list[dict]:
    term = query.strip()
    if not term:
        return []

    users = (
        db.query(User)
        .filter(
            User.deleted_at == None,  # noqa: E711
            or_(
                _case_insensitive_contains(User.email, term),
                _case_insensitive_contains(User.name, term),
            ),
        )
        .order_by(User.email.asc())
        .limit(50)
        .all()
    )
    return [_user_search_row(db, user) for user in users]


def _user_memberships(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(UserGroup)
        .filter(UserGroup.user_id == user_id)
        .options(joinedload(UserGroup.group))
        .order_by(UserGroup.joined_at.asc())
        .all()
    )
    return [
        {
            "group_id": row.group_id,
            "group_name": row.group.name,
            "role": row.role,
            "joined_at": row.joined_at,
        }
        for row in rows
    ]


def _user_search_row(db: Session, user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "created_at": user.created_at,
        "memberships": _user_memberships(db, user.id),
    }


def user_detail_context(db: Session, user_id: int) -> dict | None:
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.deleted_at == None,  # noqa: E711
        )
        .first()
    )
    if not user:
        return None

    now = utc_now()
    active_session_count = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at == None,  # noqa: E711
            UserSession.expires_at > now,
        )
        .count()
    )

    return {
        "user": user,
        "memberships": _user_memberships(db, user_id),
        "active_session_count": active_session_count,
    }


def farms_page_context(
    db: Session,
    *,
    status: str = "active",
    search: str | None = None,
) -> dict:
    farms = list_farms(db, status=status, search=search)
    return {
        "farms": farms,
        "status_filter": status,
        "search_query": search or "",
        "show_empty_state": len(farms) == 0,
    }


def users_page_context(db: Session, query: str | None) -> dict:
    q = (query or "").strip()
    results = search_users(db, q) if q else []
    return {
        "search_query": q,
        "users": results,
        "show_empty_state": bool(q) and len(results) == 0,
        "show_prompt": not q,
    }
