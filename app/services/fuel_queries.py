"""Shared SQLAlchemy query helpers for fuel entries scoped to a group."""

from sqlalchemy.orm import Session

from app.models import FuelEntry, Vehicle


def active_fuel_entries_for_group(db: Session, group_id: int):
    """Fuel entries in ``group_id`` on non-deleted vehicles, excluding soft-deleted entries."""
    return (
        db.query(FuelEntry)
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .filter(
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
    )
