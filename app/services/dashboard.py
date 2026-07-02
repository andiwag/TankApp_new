"""Dashboard statistics for the active group."""

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import FuelEntry, User, Vehicle
from app.services.fuel_queries import active_fuel_entries_for_group
from app.services.membership import group_page_capabilities

RECENT_FUEL_ENTRIES_LIMIT = 10


def get_dashboard_context(db: Session, user: User, group_id: int) -> dict:
    vehicle_count = (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .count()
    )

    fuel_stats = (
        db.query(
            func.count(FuelEntry.id),
            func.coalesce(func.sum(FuelEntry.fuel_amount_l), 0.0),
        )
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .filter(
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .one()
    )
    fuel_entry_count = int(fuel_stats[0] or 0)
    total_fuel_liters = float(fuel_stats[1] or 0.0)

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
        **group_page_capabilities(db, user, group_id),
    }
