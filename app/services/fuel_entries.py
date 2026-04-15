"""Fuel entry listing and mutations for the active group."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session, joinedload

from app.models import FuelEntry, User, Vehicle
from app.schemas import FuelEntryCreate, FuelEntryUpdate
from app.services.membership import group_page_capabilities


def list_fuel_entries_for_group(db: Session, group_id: int) -> list[FuelEntry]:
    """List entries for the group, excluding soft-deleted entries and entries for soft-deleted vehicles."""
    return (
        db.query(FuelEntry)
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .options(joinedload(FuelEntry.vehicle), joinedload(FuelEntry.user))
        .filter(
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(FuelEntry.entry_date.desc(), FuelEntry.id.desc())
        .all()
    )


def get_active_fuel_entry_in_group(
    db: Session, entry_id: int, group_id: int
) -> FuelEntry | None:
    """Active entry in the group with a non-deleted vehicle (matches dashboard scope)."""
    return (
        db.query(FuelEntry)
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .options(joinedload(FuelEntry.vehicle))
        .filter(
            FuelEntry.id == entry_id,
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def fuel_entries_page_context(db: Session, user: User, group_id: int) -> dict:
    entries = list_fuel_entries_for_group(db, group_id)
    return {
        "entries": entries,
        **group_page_capabilities(db, user, group_id),
    }


def create_fuel_entry(
    db: Session,
    user_id: int,
    group_id: int,
    vehicle: Vehicle,
    data: FuelEntryCreate,
) -> FuelEntry:
    assert vehicle.group_id == group_id
    entry = FuelEntry(
        vehicle_id=vehicle.id,
        group_id=group_id,
        user_id=user_id,
        fuel_amount_l=data.fuel_amount_l,
        usage_reading=data.usage_reading,
        entry_date=data.entry_date,
        notes=data.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def apply_fuel_entry_update(
    db: Session, entry: FuelEntry, data: FuelEntryUpdate
) -> None:
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(entry, name, value)
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)


def soft_delete_fuel_entry(db: Session, entry: FuelEntry) -> None:
    entry.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
