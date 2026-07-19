"""Tank inventory ledger: stock calculation and movements."""

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.enums import TankMovementType
from app.models import StorageTank, TankLedgerEntry
from app.schemas import (
    TankAdjustmentCreate,
    TankDeliveryCreate,
    TankExternalWithdrawalCreate,
)
from app.time_utils import utc_now


def _validate_tank_group(tank: StorageTank, group_id: int) -> None:
    if tank.group_id != group_id:
        raise ValueError("Tank gehört nicht zu dieser Gruppe.")


def current_stock_l(db: Session, tank: StorageTank) -> float:
    total = (
        db.query(func.coalesce(func.sum(TankLedgerEntry.amount_l), 0.0))
        .filter(
            TankLedgerEntry.tank_id == tank.id,
            TankLedgerEntry.deleted_at == None,  # noqa: E711
        )
        .scalar()
    )
    return tank.opening_balance_l + float(total)


def current_stock_by_tanks(db: Session, tanks: list[StorageTank]) -> dict[int, float]:
    if not tanks:
        return {}
    tank_ids = [tank.id for tank in tanks]
    ledger_totals = dict(
        db.query(
            TankLedgerEntry.tank_id,
            func.coalesce(func.sum(TankLedgerEntry.amount_l), 0.0),
        )
        .filter(
            TankLedgerEntry.tank_id.in_(tank_ids),
            TankLedgerEntry.deleted_at == None,  # noqa: E711
        )
        .group_by(TankLedgerEntry.tank_id)
        .all()
    )
    return {
        tank.id: tank.opening_balance_l + float(ledger_totals.get(tank.id, 0.0))
        for tank in tanks
    }


def list_ledger_entries_for_tank(db: Session, tank_id: int) -> list[TankLedgerEntry]:
    return (
        db.query(TankLedgerEntry)
        .options(joinedload(TankLedgerEntry.user))
        .filter(
            TankLedgerEntry.tank_id == tank_id,
            TankLedgerEntry.deleted_at == None,  # noqa: E711
        )
        .order_by(TankLedgerEntry.entry_date.desc(), TankLedgerEntry.id.desc())
        .all()
    )


def list_ledger_entries_for_group(db: Session, group_id: int) -> list[TankLedgerEntry]:
    return (
        db.query(TankLedgerEntry)
        .join(StorageTank, StorageTank.id == TankLedgerEntry.tank_id)
        .options(
            joinedload(TankLedgerEntry.user),
            joinedload(TankLedgerEntry.tank),
        )
        .filter(
            TankLedgerEntry.group_id == group_id,
            TankLedgerEntry.deleted_at == None,  # noqa: E711
        )
        .order_by(TankLedgerEntry.entry_date.desc(), TankLedgerEntry.id.desc())
        .all()
    )


def get_active_ledger_entry_in_group(
    db: Session, ledger_id: int, group_id: int
) -> TankLedgerEntry | None:
    return (
        db.query(TankLedgerEntry)
        .options(joinedload(TankLedgerEntry.tank))
        .filter(
            TankLedgerEntry.id == ledger_id,
            TankLedgerEntry.group_id == group_id,
            TankLedgerEntry.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def apply_ledger_entry_update(
    db: Session,
    entry: TankLedgerEntry,
    data: TankDeliveryCreate | TankExternalWithdrawalCreate | TankAdjustmentCreate,
) -> None:
    if entry.movement_type == TankMovementType.vehicle_withdrawal.value:
        raise ValueError("Fahrzeugentnahmen bitte über den Tankvorgang bearbeiten.")

    if entry.movement_type == TankMovementType.delivery.value:
        if not isinstance(data, TankDeliveryCreate):
            raise ValueError("Ungültige Daten für Lieferung.")
        entry.amount_l = data.amount_l
        entry.entry_date = data.entry_date
        entry.total_cost_eur = data.total_cost_eur
        entry.notes = data.notes
    elif entry.movement_type == TankMovementType.external_withdrawal.value:
        if not isinstance(data, TankExternalWithdrawalCreate):
            raise ValueError("Ungültige Daten für externe Abgabe.")
        entry.amount_l = -data.amount_l
        entry.entry_date = data.entry_date
        entry.recipient_name = data.recipient_name
        entry.total_cost_eur = data.total_cost_eur
        entry.notes = data.notes
    elif entry.movement_type == TankMovementType.adjustment.value:
        if not isinstance(data, TankAdjustmentCreate):
            raise ValueError("Ungültige Daten für Bestandskorrektur.")
        entry.amount_l = data.amount_l
        entry.entry_date = data.entry_date
        entry.notes = data.notes
    else:
        raise ValueError("Unbekannte Bewegungsart.")

    entry.updated_at = utc_now()
    db.commit()
    db.refresh(entry)


def post_delivery(
    db: Session,
    user_id: int,
    group_id: int,
    tank: StorageTank,
    data: TankDeliveryCreate,
) -> TankLedgerEntry:
    _validate_tank_group(tank, group_id)
    entry = TankLedgerEntry(
        tank_id=tank.id,
        group_id=group_id,
        user_id=user_id,
        movement_type=TankMovementType.delivery.value,
        amount_l=data.amount_l,
        entry_date=data.entry_date,
        total_cost_eur=data.total_cost_eur,
        notes=data.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def post_adjustment(
    db: Session,
    user_id: int,
    group_id: int,
    tank: StorageTank,
    data: TankAdjustmentCreate,
) -> TankLedgerEntry:
    _validate_tank_group(tank, group_id)
    entry = TankLedgerEntry(
        tank_id=tank.id,
        group_id=group_id,
        user_id=user_id,
        movement_type=TankMovementType.adjustment.value,
        amount_l=data.amount_l,
        entry_date=data.entry_date,
        notes=data.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def post_external_withdrawal(
    db: Session,
    user_id: int,
    group_id: int,
    tank: StorageTank,
    data: TankExternalWithdrawalCreate,
) -> TankLedgerEntry:
    _validate_tank_group(tank, group_id)
    entry = TankLedgerEntry(
        tank_id=tank.id,
        group_id=group_id,
        user_id=user_id,
        movement_type=TankMovementType.external_withdrawal.value,
        amount_l=-data.amount_l,
        entry_date=data.entry_date,
        recipient_name=data.recipient_name,
        total_cost_eur=data.total_cost_eur,
        notes=data.notes,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def soft_delete_ledger_entry(db: Session, entry: TankLedgerEntry) -> None:
    entry.deleted_at = utc_now()
    db.commit()
    db.refresh(entry)


def get_active_vehicle_withdrawal_for_fuel_entry(
    db: Session, fuel_entry_id: int
) -> TankLedgerEntry | None:
    return _get_vehicle_withdrawal_for_fuel_entry(db, fuel_entry_id, active_only=True)


def _get_vehicle_withdrawal_for_fuel_entry(
    db: Session, fuel_entry_id: int, *, active_only: bool
) -> TankLedgerEntry | None:
    query = db.query(TankLedgerEntry).filter(
        TankLedgerEntry.fuel_entry_id == fuel_entry_id,
        TankLedgerEntry.movement_type == TankMovementType.vehicle_withdrawal.value,
    )
    if active_only:
        query = query.filter(TankLedgerEntry.deleted_at == None)  # noqa: E711
    return query.first()


def sync_vehicle_withdrawal_for_fuel_entry(
    db: Session,
    user_id: int,
    group_id: int,
    entry,
    tank: StorageTank | None,
) -> None:
    """Create, update, or soft-delete the ledger row for a farm fuel fill."""
    from app.enums import FillSource

    existing = get_active_vehicle_withdrawal_for_fuel_entry(db, entry.id)
    if entry.fill_source != FillSource.farm.value:
        if existing:
            existing.deleted_at = utc_now()
            existing.updated_at = utc_now()
        entry.fuel_tank_id = None
        return

    if tank is None:
        raise ValueError("Bitte einen gültigen Hof-Tank aus dieser Gruppe wählen.")

    _validate_tank_group(tank, group_id)
    amount = -entry.fuel_amount_l
    entry.fuel_tank_id = tank.id

    linked = existing or _get_vehicle_withdrawal_for_fuel_entry(
        db, entry.id, active_only=False
    )
    if linked:
        linked.deleted_at = None
        linked.tank_id = tank.id
        linked.group_id = group_id
        linked.amount_l = amount
        linked.entry_date = entry.entry_date
        linked.updated_at = utc_now()
        return

    db.add(
        TankLedgerEntry(
            tank_id=tank.id,
            group_id=group_id,
            user_id=user_id,
            movement_type=TankMovementType.vehicle_withdrawal.value,
            amount_l=amount,
            entry_date=entry.entry_date,
            fuel_entry_id=entry.id,
        )
    )


def soft_delete_vehicle_withdrawals_for_fuel_entry(
    db: Session, fuel_entry_id: int
) -> None:
    existing = get_active_vehicle_withdrawal_for_fuel_entry(db, fuel_entry_id)
    if existing:
        existing.deleted_at = utc_now()
        existing.updated_at = utc_now()
