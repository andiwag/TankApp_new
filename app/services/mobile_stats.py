"""Mobile UI statistics (vehicle cards, maintenance countdown)."""

from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models import FuelEntry, Vehicle
from app.services.consumption import (
    average_consumption_for_vehicle,
    consumption_unit_label,
)
from app.services.fuel_queries import active_fuel_entries_for_group
from app.services.reminders import list_group_reminders


def _fuel_pairs_for_vehicle(entries: list[FuelEntry]) -> list[tuple[float, float, bool]]:
    return [
        (entry.usage_reading, entry.fuel_amount_l, entry.full_tank)
        for entry in sorted(entries, key=lambda row: (row.entry_date, row.id))
    ]


def _next_maintenance_days_by_vehicle(
    db: Session,
    group_id: int,
    *,
    today: date | None = None,
) -> dict[int, int | None]:
    anchor = today if today is not None else date.today()
    days_by_vehicle: dict[int, int | None] = {}
    for reminder in list_group_reminders(db, group_id, today=anchor):
        vehicle_id = reminder.get("vehicle_id")
        if vehicle_id is None:
            continue
        next_date = reminder.get("next_service_date")
        if next_date is None:
            continue
        days = (next_date - anchor).days
        existing = days_by_vehicle.get(vehicle_id)
        if existing is None or days < existing:
            days_by_vehicle[vehicle_id] = days
    return days_by_vehicle


def vehicle_mobile_stats(
    db: Session,
    group_id: int,
    vehicles: list[Vehicle],
    *,
    today: date | None = None,
) -> dict[int, dict]:
    """Per-vehicle stats for mobile hero cards."""
    if not vehicles:
        return {}

    entries = (
        active_fuel_entries_for_group(db, group_id)
        .options(joinedload(FuelEntry.vehicle))
        .order_by(FuelEntry.entry_date.asc(), FuelEntry.id.asc())
        .all()
    )
    by_vehicle: dict[int, list[FuelEntry]] = defaultdict(list)
    for entry in entries:
        by_vehicle[entry.vehicle_id].append(entry)

    maintenance_days = _next_maintenance_days_by_vehicle(db, group_id, today=today)
    stats: dict[int, dict] = {}
    for vehicle in vehicles:
        pairs = _fuel_pairs_for_vehicle(by_vehicle.get(vehicle.id, []))
        avg = average_consumption_for_vehicle(vehicle.usage_unit, pairs)
        stats[vehicle.id] = {
            "avg_consumption": round(avg, 1) if avg is not None else None,
            "consumption_label": consumption_unit_label(vehicle.usage_unit),
            "next_maintenance_days": maintenance_days.get(vehicle.id),
        }
    return stats
