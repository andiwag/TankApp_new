"""Service reminder queries and notification helpers."""

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.enums import Role
from app.models import FuelEntry, MaintenanceLog, User, UserGroup, Vehicle


def _today() -> date:
    return date.today()


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _latest_usage_by_vehicle(db: Session, group_id: int) -> dict[int, float]:
    rows = (
        db.query(FuelEntry.vehicle_id, func.max(FuelEntry.usage_reading))
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .filter(
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .group_by(FuelEntry.vehicle_id)
        .all()
    )
    return {vehicle_id: float(reading) for vehicle_id, reading in rows}


def _reminder_status(
    *,
    today: date,
    next_service_date: date | None,
    next_service_usage: float | None,
    latest_usage: float | None,
    horizon_days: int,
) -> str | None:
    overdue = False
    due_soon = False

    if next_service_date is not None:
        if next_service_date < today:
            overdue = True
        elif next_service_date <= today + timedelta(days=horizon_days):
            due_soon = True

    if next_service_usage is not None and latest_usage is not None:
        if latest_usage >= next_service_usage:
            overdue = True
        elif latest_usage >= next_service_usage * 0.9:
            due_soon = True

    if overdue:
        return "overdue"
    if due_soon:
        return "due_soon"
    return None


def format_reminder_due_detail(
    log: MaintenanceLog,
    *,
    latest_usage: float | None,
) -> str:
    parts: list[str] = []
    if log.next_service_date is not None:
        parts.append(f"due by {log.next_service_date.isoformat()}")
    if log.next_service_usage is not None:
        current = "unknown" if latest_usage is None else str(latest_usage)
        parts.append(f"due at {log.next_service_usage} (current: {current})")
    return "; ".join(parts) if parts else "due soon"


def list_group_reminders(
    db: Session,
    group_id: int,
    *,
    today: date | None = None,
    horizon_days: int = 30,
) -> list[dict]:
    anchor = today if today is not None else _today()
    usage_by_vehicle = _latest_usage_by_vehicle(db, group_id)
    logs = (
        db.query(MaintenanceLog)
        .join(Vehicle, Vehicle.id == MaintenanceLog.vehicle_id)
        .options(joinedload(MaintenanceLog.vehicle))
        .filter(
            MaintenanceLog.group_id == group_id,
            MaintenanceLog.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(MaintenanceLog.service_date.desc(), MaintenanceLog.id.desc())
        .all()
    )

    reminders: list[dict] = []
    for log in logs:
        if log.next_service_date is None and log.next_service_usage is None:
            continue
        status = _reminder_status(
            today=anchor,
            next_service_date=log.next_service_date,
            next_service_usage=log.next_service_usage,
            latest_usage=usage_by_vehicle.get(log.vehicle_id),
            horizon_days=horizon_days,
        )
        if status is None:
            continue
        reminders.append(
            {
                "log_id": log.id,
                "vehicle_name": log.vehicle.name,
                "description": log.description,
                "status": status,
                "next_service_date": log.next_service_date,
                "next_service_usage": log.next_service_usage,
            }
        )
    reminders.sort(
        key=lambda row: (
            0 if row["status"] == "overdue" else 1,
            row["next_service_date"] or date.max,
        )
    )
    return reminders


def _group_admins(db: Session, group_id: int) -> list[User]:
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


def list_due_email_reminders(
    db: Session,
    *,
    today: date | None = None,
    horizon_days: int = 7,
) -> list[tuple[MaintenanceLog, list[User], str]]:
    """Return maintenance logs due for email with admin recipients and due detail."""
    anchor = today if today is not None else _today()
    logs = (
        db.query(MaintenanceLog)
        .join(Vehicle, Vehicle.id == MaintenanceLog.vehicle_id)
        .options(joinedload(MaintenanceLog.vehicle))
        .filter(
            MaintenanceLog.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
            MaintenanceLog.reminder_sent_at == None,  # noqa: E711
        )
        .all()
    )

    usage_cache: dict[int, dict[int, float]] = {}
    due: list[tuple[MaintenanceLog, list[User], str]] = []
    for log in logs:
        if log.next_service_date is None and log.next_service_usage is None:
            continue

        if log.group_id not in usage_cache:
            usage_cache[log.group_id] = _latest_usage_by_vehicle(db, log.group_id)
        latest_usage = usage_cache[log.group_id].get(log.vehicle_id)

        if (
            _reminder_status(
                today=anchor,
                next_service_date=log.next_service_date,
                next_service_usage=log.next_service_usage,
                latest_usage=latest_usage,
                horizon_days=horizon_days,
            )
            is None
        ):
            continue

        admins = _group_admins(db, log.group_id)
        if not admins:
            continue

        due_detail = format_reminder_due_detail(log, latest_usage=latest_usage)
        due.append((log, admins, due_detail))
    return due


def try_claim_reminder_send(db: Session, log_id: int) -> MaintenanceLog | None:
    """Atomically claim a reminder so concurrent cron runs do not duplicate emails."""
    claimed = (
        db.query(MaintenanceLog)
        .filter(
            MaintenanceLog.id == log_id,
            MaintenanceLog.deleted_at == None,  # noqa: E711
            MaintenanceLog.reminder_sent_at == None,  # noqa: E711
        )
        .update(
            {MaintenanceLog.reminder_sent_at: _utcnow()},
            synchronize_session=False,
        )
    )
    if claimed == 0:
        db.rollback()
        return None
    db.commit()
    return (
        db.query(MaintenanceLog)
        .options(joinedload(MaintenanceLog.vehicle))
        .filter(MaintenanceLog.id == log_id)
        .first()
    )


def release_reminder_claim(db: Session, log_id: int) -> None:
    db.query(MaintenanceLog).filter(MaintenanceLog.id == log_id).update(
        {MaintenanceLog.reminder_sent_at: None},
        synchronize_session=False,
    )
    db.commit()
