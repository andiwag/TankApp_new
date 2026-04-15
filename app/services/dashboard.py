"""Dashboard statistics for the active group."""

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import FuelEntry, Vehicle
from app.services.fuel_queries import active_fuel_entries_for_group

RECENT_FUEL_ENTRIES_LIMIT = 10


def get_dashboard_context(db: Session, group_id: int) -> dict:
    vehicle_count = (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .count()
    )

    active_entries = active_fuel_entries_for_group(db, group_id)
    fuel_entry_count = active_entries.count()

    total_liters_row = (
        db.query(func.coalesce(func.sum(FuelEntry.fuel_amount_l), 0.0))
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .filter(
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .scalar()
    )
    total_fuel_liters = float(total_liters_row or 0.0)

    recent_fuel_entries = (
        active_fuel_entries_for_group(db, group_id)
        .options(joinedload(FuelEntry.vehicle), joinedload(FuelEntry.user))
        .order_by(FuelEntry.entry_date.desc(), FuelEntry.id.desc())
        .limit(RECENT_FUEL_ENTRIES_LIMIT)
        .all()
    )

    return {
        "vehicle_count": vehicle_count,
        "fuel_entry_count": fuel_entry_count,
        "total_fuel_liters": total_fuel_liters,
        "recent_fuel_entries": recent_fuel_entries,
    }
