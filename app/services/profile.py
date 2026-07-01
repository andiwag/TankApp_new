"""User profile updates and password changes."""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.auth import hash_password, verify_password
from app.enums import Role
from app.models import FuelEntry, Group, MaintenanceLog, User, UserGroup
from app.schemas import EMAIL_DUPLICATE_MESSAGE, PasswordChange, UserUpdate
from app.services.membership import count_group_admins
from app.time_utils import utc_now

_WRONG_CURRENT_PASSWORD = "Current password is incorrect"
_SOLE_ADMIN_DELETE_MSG = (
    "You cannot delete your account while you are the sole admin of a group. "
    "Promote another admin or delete the group first."
)
_DELETED_USER_NAME = "Deleted user"


def _deleted_email(user_id: int) -> str:
    return f"deleted-{user_id}@deleted.tankly.invalid"


def update_user_profile(db: Session, user: User, data: UserUpdate) -> str | None:
    """Apply profile fields. Returns an error message, or None on success."""
    if data.email is not None:
        normalized_email = data.email
        if normalized_email != user.email:
            other = (
                db.query(User)
                .filter(
                    User.email == normalized_email,
                    User.id != user.id,
                )
                .first()
            )
            if other:
                return EMAIL_DUPLICATE_MESSAGE
        user.email = normalized_email

    if data.name is not None:
        user.name = data.name

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return EMAIL_DUPLICATE_MESSAGE
    db.refresh(user)
    return None


def change_user_password(db: Session, user: User, data: PasswordChange) -> str | None:
    """Change password after verifying the current one. Returns error or None."""
    if not verify_password(data.current_password, user.password_hash):
        return _WRONG_CURRENT_PASSWORD

    user.password_hash = hash_password(data.new_password)
    db.commit()
    db.refresh(user)
    return None


def sole_admin_group_names(db: Session, user: User) -> list[str]:
    """Return names of active groups where the user is the only admin."""
    rows = (
        db.query(Group.name, UserGroup.group_id)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .filter(
            UserGroup.user_id == user.id,
            UserGroup.role == Role.admin.value,
            Group.deleted_at == None,  # noqa: E711
        )
        .all()
    )
    return [name for name, group_id in rows if count_group_admins(db, group_id) <= 1]


def export_user_personal_data(db: Session, user: User) -> dict:
    """Build a JSON-serializable export of the user's personal data."""
    memberships = (
        db.query(Group.name, UserGroup.role, UserGroup.joined_at, Group.deleted_at)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .filter(UserGroup.user_id == user.id)
        .order_by(Group.name)
        .all()
    )
    fuel_entries = (
        db.query(FuelEntry)
        .options(joinedload(FuelEntry.vehicle))
        .filter(
            FuelEntry.user_id == user.id,
            FuelEntry.deleted_at == None,  # noqa: E711
        )
        .order_by(FuelEntry.entry_date.desc(), FuelEntry.id.desc())
        .all()
    )
    maintenance_logs = (
        db.query(MaintenanceLog)
        .options(joinedload(MaintenanceLog.vehicle))
        .filter(
            MaintenanceLog.user_id == user.id,
            MaintenanceLog.deleted_at == None,  # noqa: E711
        )
        .order_by(MaintenanceLog.service_date.desc(), MaintenanceLog.id.desc())
        .all()
    )
    return {
        "exported_at": utc_now().isoformat(),
        "profile": {
            "name": user.name,
            "email": user.email,
            "created_at": user.created_at.isoformat(),
        },
        "group_memberships": [
            {
                "group_name": name,
                "role": role,
                "joined_at": joined_at.isoformat(),
                "group_deleted": deleted_at is not None,
            }
            for name, role, joined_at, deleted_at in memberships
        ],
        "fuel_entries": [
            {
                "id": entry.id,
                "group_id": entry.group_id,
                "vehicle_name": entry.vehicle.name,
                "entry_date": entry.entry_date.isoformat(),
                "fuel_amount_l": entry.fuel_amount_l,
                "usage_reading": entry.usage_reading,
                "full_tank": entry.full_tank,
                "total_cost_eur": entry.total_cost_eur,
                "notes": entry.notes,
                "created_at": entry.created_at.isoformat(),
            }
            for entry in fuel_entries
        ],
        "maintenance_logs": [
            {
                "id": log.id,
                "group_id": log.group_id,
                "vehicle_name": log.vehicle.name,
                "service_date": log.service_date.isoformat(),
                "description": log.description,
                "usage_reading": log.usage_reading,
                "cost_eur": log.cost_eur,
                "next_service_date": (
                    log.next_service_date.isoformat() if log.next_service_date else None
                ),
                "next_service_usage": log.next_service_usage,
                "created_at": log.created_at.isoformat(),
            }
            for log in maintenance_logs
        ],
    }


def delete_user_account(db: Session, user: User, password: str) -> str | None:
    """Soft-delete and anonymize the user after password verification."""
    if not verify_password(password, user.password_hash):
        return _WRONG_CURRENT_PASSWORD

    if sole_admin_group_names(db, user):
        return _SOLE_ADMIN_DELETE_MSG

    db.query(UserGroup).filter(UserGroup.user_id == user.id).delete()

    user.name = _DELETED_USER_NAME
    user.email = _deleted_email(user.id)
    user.password_hash = hash_password(str(uuid.uuid4()))
    user.deleted_at = utc_now()

    from app.services.sessions import revoke_all_user_sessions

    revoke_all_user_sessions(db, user.id)
    db.commit()
    return None
