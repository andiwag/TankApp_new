"""CSV export for group data."""

import csv
import io

from sqlalchemy.orm import Session

from app.services import fuel_entries as fuel_entry_service
from app.services import vehicles as vehicle_service

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_csv_cell(value: object) -> object:
    if not isinstance(value, str) or not value:
        return value
    if value[0] in _FORMULA_PREFIXES:
        return f"'{value}"
    return value


def _csv_string(rows: list[list[object]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue()


def fuel_entries_csv(db: Session, group_id: int) -> str:
    entries = fuel_entry_service.list_fuel_entries_for_group(db, group_id)
    rows: list[list[object]] = [
        [
            "date",
            "vehicle",
            "fuel_liters",
            "usage_reading",
            "full_tank",
            "total_cost_eur",
            "logged_by",
            "notes",
        ]
    ]
    for entry in entries:
        rows.append(
            [
                entry.entry_date.isoformat(),
                _safe_csv_cell(entry.vehicle.name),
                entry.fuel_amount_l,
                entry.usage_reading,
                entry.full_tank,
                entry.total_cost_eur if entry.total_cost_eur is not None else "",
                _safe_csv_cell(entry.user.name),
                _safe_csv_cell(entry.notes or ""),
            ]
        )
    return _csv_string(rows)


def vehicles_csv(db: Session, group_id: int) -> str:
    vehicles = vehicle_service.list_vehicles_for_group(db, group_id)
    rows: list[list[object]] = [
        ["name", "type", "usage_unit", "fuel_type", "created_at"]
    ]
    for vehicle in vehicles:
        rows.append(
            [
                _safe_csv_cell(vehicle.name),
                vehicle.vtype,
                vehicle.usage_unit,
                vehicle.fuel_type,
                vehicle.created_at.date().isoformat(),
            ]
        )
    return _csv_string(rows)
