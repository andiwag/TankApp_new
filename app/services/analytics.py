"""Analytics dashboard context (charts built on summary data)."""

from collections import defaultdict
from datetime import date

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import FuelEntry, Vehicle
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
    vehicle_liter_rows = (
        active_fuel_entries_for_group(db, group_id)
        .filter(FuelEntry.entry_date >= start_floor)
        .with_entities(
            FuelEntry.vehicle_id,
            Vehicle.name,
            func.sum(FuelEntry.fuel_amount_l).label("liters"),
        )
        .group_by(FuelEntry.vehicle_id, Vehicle.name)
        .order_by(Vehicle.name.asc())
        .all()
    )

    liters_by_vehicle: dict[int, float] = defaultdict(float)
    names_by_vehicle: dict[int, str] = {}
    for vehicle_id, vehicle_name, liters in vehicle_liter_rows:
        liters_by_vehicle[vehicle_id] += float(liters or 0.0)
        names_by_vehicle[vehicle_id] = vehicle_name

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
    total_12_month_liters = round(sum(row["liters"] for row in monthly_chart), 2)
    total_12_month_cost = round(
        sum(row["cost_eur"] or 0.0 for row in monthly_chart), 2
    )
    top_vehicle = max(vehicle_chart, key=lambda row: row["liters"], default=None)
    peak_month = max(monthly_chart, key=lambda row: row["liters"], default=None)

    return {
        **summary,
        "vehicle_chart": vehicle_chart,
        "monthly_chart": monthly_chart,
        "has_cost_data": has_cost_data,
        "total_12_month_liters": total_12_month_liters,
        "total_12_month_cost": total_12_month_cost if total_12_month_cost > 0 else None,
        "top_vehicle": top_vehicle,
        "peak_month": peak_month,
    }
