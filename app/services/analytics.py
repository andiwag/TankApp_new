"""Analytics dashboard context (charts built on summary data)."""

from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.models import FuelEntry
from app.services.fuel_queries import active_fuel_entries_for_group
from app.services.summary import _last_12_month_keys, _today, get_summary_context


def get_analytics_context(
    db: Session, group_id: int, today: date | None = None
) -> dict:
    anchor = today if today is not None else _today()
    month_keys = _last_12_month_keys(anchor)
    first_month = month_keys[0]
    start_floor = date(first_month[0], first_month[1], 1)

    summary = get_summary_context(db, group_id, today=anchor)
    entries = (
        active_fuel_entries_for_group(db, group_id)
        .options(joinedload(FuelEntry.vehicle))
        .all()
    )
    period_entries = [e for e in entries if e.entry_date >= start_floor]

    liters_by_vehicle: dict[int, float] = defaultdict(float)
    names_by_vehicle: dict[int, str] = {}
    for entry in period_entries:
        liters_by_vehicle[entry.vehicle_id] += entry.fuel_amount_l
        names_by_vehicle[entry.vehicle_id] = entry.vehicle.name

    vehicle_chart = [
        {"name": names_by_vehicle[vehicle_id], "liters": round(liters, 2)}
        for vehicle_id, liters in sorted(
            liters_by_vehicle.items(), key=lambda item: names_by_vehicle[item[0]]
        )
        if liters > 0
    ]
    monthly_chart = [
        {
            "label": row["label"],
            "liters": round(row["liters"], 2),
            "cost_eur": round(row["cost_eur"], 2) if row["cost_eur"] else None,
        }
        for row in summary["monthly_rows"]
    ]
    has_cost_data = any(row["cost_eur"] for row in summary["monthly_rows"])

    return {
        **summary,
        "vehicle_chart": vehicle_chart,
        "monthly_chart": monthly_chart,
        "has_cost_data": has_cost_data,
    }
