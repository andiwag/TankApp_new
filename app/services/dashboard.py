"""Dashboard statistics for the active group."""

from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from app.models import FuelEntry, User, Vehicle
from app.services.consumption import (
    average_consumption_for_vehicle,
    consumption_unit_label,
)
from app.services.fuel_queries import active_fuel_entries_for_group
from app.services.membership import group_page_capabilities
from app.services.storage_tanks import list_storage_tanks_for_group
from app.services.tank_ledger import current_stock_by_tanks

RECENT_FUEL_ENTRIES_LIMIT = 5
VEHICLES_PREVIEW_LIMIT = 4
CONSUMPTION_CHART_DAYS = 30
COST_CHART_MONTHS = 6

MONTH_LABELS_DE = (
    "",
    "Jan",
    "Feb",
    "Mär",
    "Apr",
    "Mai",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Okt",
    "Nov",
    "Dez",
)


def _today() -> date:
    return date.today()


def dashboard_greeting(*, today: date | None = None) -> str:
    from datetime import datetime

    hour = datetime.now().hour
    if hour < 11:
        return "Guten Morgen"
    if hour < 18:
        return "Guten Tag"
    return "Guten Abend"


def _first_name(full_name: str) -> str:
    return full_name.strip().split()[0] if full_name.strip() else full_name


def _month_start(anchor: date) -> date:
    return date(anchor.year, anchor.month, 1)


def _last_n_month_keys(anchor: date, months: int) -> list[tuple[int, int]]:
    y, m = anchor.year, anchor.month
    raw: list[tuple[int, int]] = []
    for _ in range(months):
        raw.append((y, m))
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(raw))


def _month_label_de(key: tuple[int, int]) -> str:
    return MONTH_LABELS_DE[key[1]]


def _cost_chart_from_rows(
    rows: list[tuple[date, float | None]],
    *,
    anchor: date,
    months: int = COST_CHART_MONTHS,
) -> list[dict]:
    month_keys = _last_n_month_keys(anchor, months)
    totals = {key: 0.0 for key in month_keys}
    for entry_date, cost in rows:
        key = (entry_date.year, entry_date.month)
        if key not in totals or cost is None:
            continue
        totals[key] += float(cost)
    return [
        {
            "label": _month_label_de(key),
            "cost_eur": round(totals[key], 2),
        }
        for key in month_keys
    ]


def _consumption_by_entry_id(entries: list[FuelEntry]) -> dict[int, float]:
    by_vehicle: dict[int, list[FuelEntry]] = defaultdict(list)
    for entry in entries:
        by_vehicle[entry.vehicle_id].append(entry)

    consumption: dict[int, float] = {}
    for vehicle_entries in by_vehicle.values():
        vehicle = vehicle_entries[0].vehicle
        sorted_entries = sorted(
            vehicle_entries, key=lambda row: (row.entry_date, row.id)
        )
        previous_full: FuelEntry | None = None
        for entry in sorted_entries:
            if not entry.full_tank:
                continue
            if previous_full is not None:
                value = average_consumption_for_vehicle(
                    vehicle.usage_unit,
                    [
                        (
                            previous_full.usage_reading,
                            previous_full.fuel_amount_l,
                            previous_full.full_tank,
                        ),
                        (entry.usage_reading, entry.fuel_amount_l, entry.full_tank),
                    ],
                )
                if value is not None:
                    consumption[entry.id] = round(value, 1)
            previous_full = entry
    return consumption


def _consumption_chart(
    consumption_by_entry: dict[int, float],
    entries: list[FuelEntry],
    *,
    today: date,
    days: int = CONSUMPTION_CHART_DAYS,
) -> list[dict]:
    start = today - timedelta(days=days - 1)
    by_date: dict[date, list[float]] = defaultdict(list)
    for entry in entries:
        if entry.entry_date < start or entry.entry_date > today:
            continue
        value = consumption_by_entry.get(entry.id)
        if value is None:
            continue
        by_date[entry.entry_date].append(value)

    points: list[dict] = []
    for day in sorted(by_date):
        values = by_date[day]
        points.append(
            {
                "date": day.isoformat(),
                "label": f"{day.day}. {MONTH_LABELS_DE[day.month]}",
                "consumption": round(sum(values) / len(values), 1),
            }
        )
    return points


def _recent_entry_rows(
    entries: list[FuelEntry], consumption_by_entry: dict[int, float]
) -> list[dict]:
    rows: list[dict] = []
    for entry in entries:
        consumption = consumption_by_entry.get(entry.id)
        rows.append(
            {
                "entry": entry,
                "consumption": consumption,
                "consumption_label": consumption_unit_label(entry.vehicle.usage_unit)
                if consumption is not None
                else None,
            }
        )
    return rows


def get_dashboard_context(
    db: Session,
    user: User,
    group_id: int,
    *,
    today: date | None = None,
) -> dict:
    anchor = today if today is not None else _today()
    month_start = _month_start(anchor)
    consumption_start = anchor - timedelta(days=CONSUMPTION_CHART_DAYS - 1)
    cost_month_keys = _last_n_month_keys(anchor, COST_CHART_MONTHS)
    cost_start = date(cost_month_keys[0][0], cost_month_keys[0][1], 1)
    range_start = min(month_start, consumption_start, cost_start)

    vehicles = (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(Vehicle.name.asc())
        .all()
    )
    vehicle_count = len(vehicles)
    vehicles_preview = vehicles[:VEHICLES_PREVIEW_LIMIT]

    ranged_rows = (
        active_fuel_entries_for_group(db, group_id)
        .filter(FuelEntry.entry_date >= range_start, FuelEntry.entry_date <= anchor)
        .with_entities(
            FuelEntry.entry_date,
            FuelEntry.fuel_amount_l,
            FuelEntry.total_cost_eur,
        )
        .all()
    )
    month_rows = [row for row in ranged_rows if month_start <= row[0] <= anchor]
    month_fuel_count = len(month_rows)
    month_cost_eur = float(sum(row[2] or 0.0 for row in month_rows))
    cost_rows = [(row[0], row[2]) for row in ranged_rows if row[0] >= cost_start]
    today_fuel_count = sum(1 for row in ranged_rows if row[0] == anchor)
    cost_chart = _cost_chart_from_rows(cost_rows, anchor=anchor)

    all_entries = (
        active_fuel_entries_for_group(db, group_id)
        .options(joinedload(FuelEntry.vehicle))
        .order_by(FuelEntry.entry_date.asc(), FuelEntry.id.asc())
        .all()
    )
    consumption_by_entry = _consumption_by_entry_id(all_entries)
    consumption_chart = _consumption_chart(
        consumption_by_entry, all_entries, today=anchor
    )

    recent_fuel_entries = list(reversed(all_entries))[:RECENT_FUEL_ENTRIES_LIMIT]
    recent_entry_rows = _recent_entry_rows(recent_fuel_entries, consumption_by_entry)

    tanks = list_storage_tanks_for_group(db, group_id)
    stock_by_tank_id = current_stock_by_tanks(db, tanks)
    tank_stock_rows = [
        {
            "tank": tank,
            "current_stock_l": stock_by_tank_id[tank.id],
            "negative_stock": stock_by_tank_id[tank.id] < 0,
        }
        for tank in tanks
    ]

    return {
        "vehicle_count": vehicle_count,
        "month_fuel_count": month_fuel_count,
        "month_cost_eur": month_cost_eur,
        "today_fuel_count": today_fuel_count,
        "recent_fuel_entries": recent_fuel_entries,
        "recent_entry_rows": recent_entry_rows,
        "consumption_chart": consumption_chart,
        "cost_chart": cost_chart,
        "vehicles_preview": vehicles_preview,
        "greeting": dashboard_greeting(today=anchor),
        "user_first_name": _first_name(user.name),
        "tank_stock_rows": tank_stock_rows,
        **group_page_capabilities(db, user, group_id),
    }
