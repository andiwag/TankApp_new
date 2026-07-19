"""Summary statistics for the active group (fuel per vehicle, monthly totals, D-004)."""

import calendar
from collections import defaultdict
from datetime import date

from sqlalchemy.orm import Session

from app.models import FuelEntry, Vehicle
from app.services.consumption import (
    average_consumption_for_vehicle,
    consumption_unit_label,
)
from app.services.fuel_queries import active_fuel_entries_for_group


def _today() -> date:
    """Test seam for `date.today()` (avoid patching the `date` constructor)."""
    return date.today()


def _last_12_month_keys(anchor: date) -> list[tuple[int, int]]:
    """Chronological list of (year, month) covering the 12 months ending at ``anchor``'s month."""
    y, m = anchor.year, anchor.month
    raw: list[tuple[int, int]] = []
    for _ in range(12):
        raw.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(raw))


def get_summary_context(db: Session, group_id: int, today: date | None = None) -> dict:
    """Build template context for the summary page."""
    anchor = today if today is not None else _today()
    month_keys = _last_12_month_keys(anchor)
    first_month = month_keys[0]

    vehicles = (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(Vehicle.name.asc())
        .all()
    )

    entries = active_fuel_entries_for_group(db, group_id).all()

    by_vehicle: dict[int, list[FuelEntry]] = defaultdict(list)
    for e in entries:
        by_vehicle[e.vehicle_id].append(e)

    vehicle_rows: list[dict] = []
    for v in vehicles:
        ves = by_vehicle.get(v.id, [])
        total_liters = sum(e.fuel_amount_l for e in ves)
        total_adblue = sum(e.adblue_amount_l or 0.0 for e in ves)
        entry_count = len(ves)
        pairs = [(e.usage_reading, e.fuel_amount_l, e.full_tank) for e in ves]
        avg = average_consumption_for_vehicle(v.usage_unit, pairs)
        unit_label = consumption_unit_label(v.usage_unit)
        total_cost = sum(e.total_cost_eur or 0.0 for e in ves)
        vehicle_rows.append(
            {
                "vehicle_id": v.id,
                "name": v.name,
                "total_liters": total_liters,
                "total_adblue_l": total_adblue if total_adblue > 0 else None,
                "total_cost_eur": total_cost if total_cost > 0 else None,
                "entry_count": entry_count,
                "avg_consumption": avg,
                "consumption_unit_label": unit_label,
            }
        )

    month_totals: dict[tuple[int, int], float] = {k: 0.0 for k in month_keys}
    month_costs: dict[tuple[int, int], float] = {k: 0.0 for k in month_keys}
    start_floor = date(first_month[0], first_month[1], 1)

    for e in entries:
        ed = e.entry_date
        if ed < start_floor:
            continue
        key = (ed.year, ed.month)
        if key not in month_totals:
            continue
        month_totals[key] += e.fuel_amount_l
        if e.total_cost_eur is not None:
            month_costs[key] += e.total_cost_eur

    monthly_rows = [
        {
            "key": k,
            "year": k[0],
            "month": k[1],
            "label": f"{calendar.month_abbr[k[1]]} {k[0]}",
            "liters": month_totals[k],
            "cost_eur": month_costs[k] if month_costs[k] > 0 else None,
        }
        for k in month_keys
    ]

    total_group_cost = sum(e.total_cost_eur or 0.0 for e in entries)
    total_group_adblue = sum(e.adblue_amount_l or 0.0 for e in entries)

    show_empty_state = len(vehicles) == 0

    return {
        "vehicle_rows": vehicle_rows,
        "monthly_rows": monthly_rows,
        "total_group_cost_eur": total_group_cost if total_group_cost > 0 else None,
        "total_group_adblue_l": total_group_adblue if total_group_adblue > 0 else None,
        "show_empty_state": show_empty_state,
    }
