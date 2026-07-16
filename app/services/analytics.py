"""Analytics dashboard context (charts built on summary data)."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.models import FuelEntry, Vehicle
from app.services import dashboard as dashboard_service
from app.services.consumption import (
    average_consumption_for_vehicle,
    consumption_unit_label,
)
from app.services.fuel_queries import active_fuel_entries_for_group
from app.services.summary import _last_12_month_keys, _today, get_summary_context

TREND_WINDOW_DAYS = 30


def _consumption_values_in_window(
    consumption_by_entry: dict[int, float],
    entries: list[FuelEntry],
    *,
    start: date,
    end: date,
    vehicle_id: int | None = None,
) -> list[float]:
    values: list[float] = []
    for entry in entries:
        if vehicle_id is not None and entry.vehicle_id != vehicle_id:
            continue
        if entry.entry_date < start or entry.entry_date > end:
            continue
        value = consumption_by_entry.get(entry.id)
        if value is not None:
            values.append(value)
    return values


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def consumption_trend_30d(
    db: Session,
    group_id: int,
    *,
    today: date | None = None,
    vehicle_id: int | None = None,
) -> dict:
    anchor = today if today is not None else _today()
    current_start = anchor - timedelta(days=TREND_WINDOW_DAYS - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=TREND_WINDOW_DAYS - 1)

    entries = (
        active_fuel_entries_for_group(db, group_id)
        .options(joinedload(FuelEntry.vehicle))
        .order_by(FuelEntry.entry_date.asc(), FuelEntry.id.asc())
        .all()
    )
    consumption_by_entry = dashboard_service._consumption_by_entry_id(entries)

    current_avg = _average(
        _consumption_values_in_window(
            consumption_by_entry,
            entries,
            start=current_start,
            end=anchor,
            vehicle_id=vehicle_id,
        )
    )
    previous_avg = _average(
        _consumption_values_in_window(
            consumption_by_entry,
            entries,
            start=previous_start,
            end=previous_end,
            vehicle_id=vehicle_id,
        )
    )
    delta = None
    if current_avg is not None and previous_avg is not None:
        delta = round(current_avg - previous_avg, 1)

    unit_label = "L/100 km"
    if vehicle_id is not None:
        vehicle = next((row.vehicle for row in entries if row.vehicle_id == vehicle_id), None)
        if vehicle is not None:
            unit_label = consumption_unit_label(vehicle.usage_unit)
    elif entries:
        unit_label = consumption_unit_label(entries[0].vehicle.usage_unit)

    return {
        "current_avg": round(current_avg, 1) if current_avg is not None else None,
        "previous_avg": round(previous_avg, 1) if previous_avg is not None else None,
        "delta": delta,
        "unit_label": unit_label,
        "has_data": current_avg is not None,
    }


def cost_trend_30d(
    db: Session,
    group_id: int,
    *,
    today: date | None = None,
) -> dict:
    anchor = today if today is not None else _today()
    current_start = anchor - timedelta(days=TREND_WINDOW_DAYS - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=TREND_WINDOW_DAYS - 1)

    rows = (
        active_fuel_entries_for_group(db, group_id)
        .filter(
            FuelEntry.entry_date >= previous_start,
            FuelEntry.entry_date <= anchor,
        )
        .with_entities(FuelEntry.entry_date, FuelEntry.total_cost_eur)
        .all()
    )
    current_total = sum(
        float(cost or 0.0)
        for entry_date, cost in rows
        if current_start <= entry_date <= anchor
    )
    previous_total = sum(
        float(cost or 0.0)
        for entry_date, cost in rows
        if previous_start <= entry_date <= previous_end
    )
    delta = round(current_total - previous_total, 2) if previous_total > 0 else None
    return {
        "current_total": round(current_total, 2),
        "previous_total": round(previous_total, 2),
        "delta": delta,
        "has_data": current_total > 0 or previous_total > 0,
    }


def vehicle_consumption_breakdown(
    db: Session,
    group_id: int,
    *,
    today: date | None = None,
) -> list[dict]:
    anchor = today if today is not None else _today()
    vehicles = (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(Vehicle.name.asc())
        .all()
    )
    entries = (
        active_fuel_entries_for_group(db, group_id)
        .options(joinedload(FuelEntry.vehicle))
        .order_by(FuelEntry.entry_date.asc(), FuelEntry.id.asc())
        .all()
    )
    by_vehicle: dict[int, list[FuelEntry]] = defaultdict(list)
    for entry in entries:
        by_vehicle[entry.vehicle_id].append(entry)

    breakdown: list[dict] = []
    for vehicle in vehicles:
        pairs = [
            (row.usage_reading, row.fuel_amount_l, row.full_tank)
            for row in sorted(
                by_vehicle.get(vehicle.id, []), key=lambda item: (item.entry_date, item.id)
            )
        ]
        avg = average_consumption_for_vehicle(vehicle.usage_unit, pairs)
        trend = consumption_trend_30d(
            db, group_id, today=anchor, vehicle_id=vehicle.id
        )
        if avg is None and not trend["has_data"]:
            continue
        breakdown.append(
            {
                "vehicle_id": vehicle.id,
                "name": vehicle.name,
                "consumption": round(avg, 1) if avg is not None else None,
                "unit_label": consumption_unit_label(vehicle.usage_unit),
                "delta": trend["delta"],
            }
        )
    return breakdown


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
    total_12_month_cost = round(sum(row["cost_eur"] or 0.0 for row in monthly_chart), 2)
    top_vehicle = max(vehicle_chart, key=lambda row: row["liters"], default=None)
    peak_month = max(monthly_chart, key=lambda row: row["liters"], default=None)

    consumption_trend = consumption_trend_30d(db, group_id, today=anchor)
    cost_trend = cost_trend_30d(db, group_id, today=anchor)
    vehicle_breakdown = vehicle_consumption_breakdown(db, group_id, today=anchor)

    all_entries = (
        active_fuel_entries_for_group(db, group_id)
        .options(joinedload(FuelEntry.vehicle))
        .order_by(FuelEntry.entry_date.asc(), FuelEntry.id.asc())
        .all()
    )
    consumption_by_entry = dashboard_service._consumption_by_entry_id(all_entries)
    mobile_consumption_chart = dashboard_service._consumption_chart(
        consumption_by_entry, all_entries, today=anchor, days=TREND_WINDOW_DAYS
    )
    month_start = date(anchor.year, anchor.month, 1)
    month_fuel_count = (
        active_fuel_entries_for_group(db, group_id)
        .filter(
            FuelEntry.entry_date >= month_start,
            FuelEntry.entry_date <= anchor,
        )
        .count()
    )
    current_month_liters = monthly_chart[-1]["liters"] if monthly_chart else 0.0

    return {
        **summary,
        "vehicle_chart": vehicle_chart,
        "monthly_chart": monthly_chart,
        "has_cost_data": has_cost_data,
        "total_12_month_liters": total_12_month_liters,
        "total_12_month_cost": total_12_month_cost if total_12_month_cost > 0 else None,
        "top_vehicle": top_vehicle,
        "peak_month": peak_month,
        "consumption_trend": consumption_trend,
        "cost_trend": cost_trend,
        "vehicle_breakdown": vehicle_breakdown,
        "mobile_consumption_chart": mobile_consumption_chart,
        "month_fuel_count": month_fuel_count,
        "current_month_liters": round(current_month_liters, 2),
    }
