"""One-off import of logbuch CSV rows into a Tankly group.

Reads logbuch_daten-1.csv (or any CSV with tankly_vehicle column) and creates
fuel entries. Rows without tankly_vehicle (e.g. Kreuzmayr) are skipped.

Usage:
    set DATABASE_URL=postgresql://...
    python scripts/import_fuel_entries.py --group-id 1 --user-id 2 --dry-run
    python scripts/import_fuel_entries.py --group-id 1 --user-id 2

The logbuch CSV has liters only (no km/h readings). usage_reading is assigned
as a synthetic sequence per vehicle (1000, 2000, ...) so entries keep
chronological order; update real readings in the app later if needed.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

# Project root on sys.path for `app.*` imports when run as a script.
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.database import SessionLocal  # noqa: E402
from app.models import Group, User, Vehicle  # noqa: E402
from app.schemas import FuelEntryCreate  # noqa: E402
from app.services.fuel_entries import create_fuel_entry  # noqa: E402

# Fallback if tankly_vehicle column is missing (case-insensitive keys).
VEHICLE_ALIASES: dict[str, str] = {
    "fiat": "Fiat Doblo",
    "thomas": "Thomas",
    "steyr": "Steyr",
    "loder": "Loder",
    "michi": "Michi",
    "t6140": "New Holland T6.140",
}


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date: {value!r}")


def _resolve_vehicle_name(row: dict[str, str]) -> str | None:
    mapped = (row.get("tankly_vehicle") or "").strip()
    if mapped:
        return mapped
    raw = (row.get("Name/Fahrzeug") or row.get("vehicle") or "").strip()
    if not raw or raw.lower() == "kreuzmayr":
        return None
    return VEHICLE_ALIASES.get(raw.lower())


def _load_rows(csv_path: Path) -> list[dict[str, object]]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        raw_rows = list(csv.DictReader(handle))

    parsed: list[dict[str, object]] = []
    for index, row in enumerate(raw_rows, start=2):
        vehicle_name = _resolve_vehicle_name(row)
        if not vehicle_name:
            continue
        liters_raw = (row.get("Liter/Stunden") or row.get("fuel_liters") or "").strip()
        if not liters_raw:
            raise ValueError(f"Row {index}: missing fuel liters")
        parsed.append(
            {
                "line": index,
                "vehicle_name": vehicle_name,
                "entry_date": _parse_date(row["Datum"] if "Datum" in row else row["date"]),
                "fuel_liters": float(liters_raw.replace(",", ".")),
                "notes": (row.get("Anmerkung") or row.get("notes") or "").strip() or None,
            }
        )

    parsed.sort(key=lambda item: (item["vehicle_name"], item["entry_date"], item["line"]))
    counters: dict[str, int] = defaultdict(int)
    for item in parsed:
        counters[str(item["vehicle_name"])] += 1
        item["usage_reading"] = float(counters[str(item["vehicle_name"])] * 1000)
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description="Import logbuch CSV into Tankly fuel entries.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=_ROOT / "logbuch_daten-1.csv",
        help="Path to CSV (default: logbuch_daten-1.csv in project root)",
    )
    parser.add_argument("--group-id", type=int, required=True, help="Target Betrieb / group ID")
    parser.add_argument("--user-id", type=int, required=True, help="User ID to attribute entries to")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and print rows without writing to the database",
    )
    args = parser.parse_args()

    rows = _load_rows(args.csv)
    if not rows:
        print("No importable rows found.")
        return 1

    db = SessionLocal()
    try:
        group = (
            db.query(Group)
            .filter(Group.id == args.group_id, Group.deleted_at.is_(None))
            .first()
        )
        if not group:
            print(f"Group {args.group_id} not found.")
            return 1

        user = db.query(User).filter(User.id == args.user_id).first()
        if not user:
            print(f"User {args.user_id} not found.")
            return 1

        vehicles = {
            vehicle.name: vehicle
            for vehicle in db.query(Vehicle).filter(
                Vehicle.group_id == args.group_id,
                Vehicle.deleted_at.is_(None),
            )
        }

        missing = sorted({str(row["vehicle_name"]) for row in rows} - set(vehicles))
        if missing:
            print("These mapped vehicles are missing in the group:")
            for name in missing:
                print(f"  - {name}")
            print("\nExisting vehicles:", ", ".join(sorted(vehicles)) or "(none)")
            return 1

        created = 0
        for row in rows:
            vehicle = vehicles[str(row["vehicle_name"])]
            data = FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=float(row["fuel_liters"]),
                usage_reading=float(row["usage_reading"]),
                entry_date=row["entry_date"],  # type: ignore[arg-type]
                full_tank=True,
                notes=row["notes"],  # type: ignore[arg-type]
            )
            label = (
                f"Row {row['line']}: {data.entry_date} | {vehicle.name} | "
                f"{data.fuel_amount_l} L | reading {data.usage_reading}"
            )
            if args.dry_run:
                print(f"DRY RUN  {label}")
            else:
                create_fuel_entry(db, args.user_id, args.group_id, vehicle, data)
                print(f"IMPORTED {label}")
            created += 1

        print(
            f"\n{'Would import' if args.dry_run else 'Imported'} {created} entries "
            f"into group {args.group_id} ({group.name})."
        )
        if args.dry_run:
            print("Re-run without --dry-run to write to the database.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
