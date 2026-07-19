"""Fuel entry listing and mutations for the active group."""

from sqlalchemy.orm import Session, joinedload

from app.enums import FillSource, VehicleType
from app.models import FuelEntry, StorageTank, User, Vehicle
from app.schemas import FuelEntryCreate, FuelEntryUpdate
from app.services.membership import group_page_capabilities
from app.services.storage_tanks import (
    get_active_storage_tank_in_group,
    list_storage_tanks_for_fuel_form,
    list_storage_tanks_for_group,
)
from app.services.tank_ledger import (
    soft_delete_vehicle_withdrawals_for_fuel_entry,
    sync_vehicle_withdrawal_for_fuel_entry,
)
from app.time_utils import utc_now


def list_fuel_entries_for_group(db: Session, group_id: int) -> list[FuelEntry]:
    """List entries for the group, excluding soft-deleted entries and entries for soft-deleted vehicles."""
    return (
        db.query(FuelEntry)
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .options(
            joinedload(FuelEntry.vehicle),
            joinedload(FuelEntry.user),
            joinedload(FuelEntry.fuel_tank),
        )
        .filter(
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(FuelEntry.entry_date.desc(), FuelEntry.id.desc())
        .all()
    )


def get_active_fuel_entry_in_group(
    db: Session, entry_id: int, group_id: int
) -> FuelEntry | None:
    """Active entry in the group with a non-deleted vehicle (matches dashboard scope)."""
    return (
        db.query(FuelEntry)
        .join(Vehicle, Vehicle.id == FuelEntry.vehicle_id)
        .options(joinedload(FuelEntry.vehicle))
        .filter(
            FuelEntry.id == entry_id,
            FuelEntry.group_id == group_id,
            FuelEntry.deleted_at == None,  # noqa: E711
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def fuel_entries_page_context(db: Session, user: User, group_id: int) -> dict:
    entries = list_fuel_entries_for_group(db, group_id)
    return {
        "entries": entries,
        **group_page_capabilities(db, user, group_id),
    }


def fuel_entry_form_context(db: Session, group_id: int) -> dict:
    return {
        "storage_tanks": list_storage_tanks_for_fuel_form(db, group_id),
    }


def validate_adblue_for_vehicle(
    vehicle: Vehicle, adblue_amount_l: float | None
) -> None:
    if adblue_amount_l is not None and vehicle.vtype != VehicleType.tractor.value:
        raise ValueError("AdBlue ist nur für Traktoren möglich.")


def _fill_source_value(fill_source: FillSource | str) -> str:
    if isinstance(fill_source, FillSource):
        return fill_source.value
    return fill_source


def resolve_farm_tank(
    db: Session,
    group_id: int,
    vehicle: Vehicle,
    fill_source: FillSource | str,
    fuel_tank_id: int | None,
) -> StorageTank | None:
    fs = _fill_source_value(fill_source)
    if fs == FillSource.external.value:
        if fuel_tank_id is not None:
            raise ValueError("Externe Tankstelle erfordert keinen Hof-Tank.")
        return None

    resolved_tank_id = fuel_tank_id
    if resolved_tank_id is None:
        matching = [
            t
            for t in list_storage_tanks_for_group(db, group_id)
            if t.fuel_type == vehicle.fuel_type
        ]
        if len(matching) == 1:
            resolved_tank_id = matching[0].id
        else:
            raise ValueError("Bitte einen Hof-Tank auswählen.")

    tank = get_active_storage_tank_in_group(db, resolved_tank_id, group_id)
    if not tank:
        raise ValueError("Bitte einen gültigen Hof-Tank aus dieser Gruppe wählen.")
    if tank.fuel_type != vehicle.fuel_type:
        raise ValueError("Kraftstofftyp des Tanks passt nicht zum Fahrzeug.")
    return tank


def create_fuel_entry(
    db: Session,
    user_id: int,
    group_id: int,
    vehicle: Vehicle,
    data: FuelEntryCreate,
) -> FuelEntry:
    assert vehicle.group_id == group_id
    validate_adblue_for_vehicle(vehicle, data.adblue_amount_l)
    tank = resolve_farm_tank(db, group_id, vehicle, data.fill_source, data.fuel_tank_id)
    fill_source = _fill_source_value(data.fill_source)
    entry = FuelEntry(
        vehicle_id=vehicle.id,
        group_id=group_id,
        user_id=user_id,
        fuel_amount_l=data.fuel_amount_l,
        usage_reading=data.usage_reading,
        full_tank=data.full_tank,
        total_cost_eur=data.total_cost_eur,
        adblue_amount_l=data.adblue_amount_l,
        fill_source=fill_source,
        fuel_tank_id=tank.id if tank else None,
        entry_date=data.entry_date,
        notes=data.notes,
    )
    db.add(entry)
    db.flush()
    sync_vehicle_withdrawal_for_fuel_entry(db, user_id, group_id, entry, tank)
    db.commit()
    db.refresh(entry)
    return entry


def apply_fuel_entry_update(
    db: Session,
    entry: FuelEntry,
    data: FuelEntryUpdate,
    *,
    vehicle: Vehicle,
    user_id: int,
    group_id: int,
) -> None:
    dumped = data.model_dump(exclude_unset=True)
    if "adblue_amount_l" in dumped:
        validate_adblue_for_vehicle(vehicle, dumped["adblue_amount_l"])
    for name, value in dumped.items():
        if name == "fill_source" and value is not None:
            setattr(entry, name, _fill_source_value(value))
        else:
            setattr(entry, name, value)

    fill_source = entry.fill_source
    fuel_tank_id = entry.fuel_tank_id
    if "fill_source" in dumped or "fuel_tank_id" in dumped:
        if fill_source == FillSource.external.value:
            tank = None
        else:
            tank = resolve_farm_tank(db, group_id, vehicle, fill_source, fuel_tank_id)
    else:
        tank = (
            resolve_farm_tank(db, group_id, vehicle, fill_source, fuel_tank_id)
            if fill_source == FillSource.farm.value
            else None
        )

    entry.updated_at = utc_now()
    db.flush()
    sync_vehicle_withdrawal_for_fuel_entry(db, user_id, group_id, entry, tank)
    db.commit()
    db.refresh(entry)


def soft_delete_fuel_entry(db: Session, entry: FuelEntry) -> None:
    soft_delete_vehicle_withdrawals_for_fuel_entry(db, entry.id)
    entry.deleted_at = utc_now()
    db.commit()
    db.refresh(entry)
