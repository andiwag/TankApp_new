"""Maintenance log listing and mutations for the active group."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session, joinedload

from app.models import MaintenanceLog, User, Vehicle
from app.schemas import MaintenanceLogCreate, MaintenanceLogUpdate
from app.services.membership import group_page_capabilities


def list_maintenance_logs_for_group(db: Session, group_id: int) -> list[MaintenanceLog]:
    return (
        db.query(MaintenanceLog)
        .join(Vehicle, Vehicle.id == MaintenanceLog.vehicle_id)
        .options(joinedload(MaintenanceLog.vehicle), joinedload(MaintenanceLog.user))
        .filter(
            MaintenanceLog.group_id == group_id,
            MaintenanceLog.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(MaintenanceLog.service_date.desc(), MaintenanceLog.id.desc())
        .all()
    )


def get_active_maintenance_log_in_group(
    db: Session, log_id: int, group_id: int
) -> MaintenanceLog | None:
    return (
        db.query(MaintenanceLog)
        .join(Vehicle, Vehicle.id == MaintenanceLog.vehicle_id)
        .options(joinedload(MaintenanceLog.vehicle))
        .filter(
            MaintenanceLog.id == log_id,
            MaintenanceLog.group_id == group_id,
            MaintenanceLog.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def maintenance_page_context(db: Session, user: User, group_id: int) -> dict:
    logs = list_maintenance_logs_for_group(db, group_id)
    return {
        "logs": logs,
        **group_page_capabilities(db, user, group_id),
    }


def create_maintenance_log(
    db: Session,
    user_id: int,
    group_id: int,
    vehicle: Vehicle,
    data: MaintenanceLogCreate,
) -> MaintenanceLog:
    assert vehicle.group_id == group_id
    log = MaintenanceLog(
        vehicle_id=vehicle.id,
        group_id=group_id,
        user_id=user_id,
        service_date=data.service_date,
        usage_reading=data.usage_reading,
        description=data.description,
        cost_eur=data.cost_eur,
        next_service_date=data.next_service_date,
        next_service_usage=data.next_service_usage,
    )
    db.add(log)
    db.flush()
    db.refresh(log)
    return log


def apply_maintenance_log_update(
    db: Session, log: MaintenanceLog, data: MaintenanceLogUpdate
) -> None:
    previous_next_date = log.next_service_date
    effective_service_date = (
        data.service_date if data.service_date is not None else log.service_date
    )
    effective_next_date = (
        data.next_service_date
        if data.next_service_date is not None
        else log.next_service_date
    )
    if effective_next_date is not None and effective_next_date < effective_service_date:
        raise ValueError("next_service_date must be on or after service_date")

    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(log, name, value)
    if (
        data.next_service_date is not None
        and data.next_service_date != previous_next_date
    ):
        log.reminder_sent_at = None
    log.updated_at = datetime.now(UTC)
    db.flush()
    db.refresh(log)


def soft_delete_maintenance_log(db: Session, log: MaintenanceLog) -> None:
    log.deleted_at = datetime.now(UTC)
    db.flush()
    db.refresh(log)
