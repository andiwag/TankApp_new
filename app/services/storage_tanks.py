"""Storage tank listing and mutations for the active group."""

from sqlalchemy.orm import Session

from app.enums import FillSource
from app.models import FuelEntry, StorageTank, User
from app.schemas import StorageTankCreate, StorageTankUpdate
from app.services.membership import group_page_capabilities
from app.services.tank_ledger import current_stock_l
from app.time_utils import utc_now


def list_storage_tanks_for_group(db: Session, group_id: int) -> list[StorageTank]:
    return (
        db.query(StorageTank)
        .filter(
            StorageTank.group_id == group_id,
            StorageTank.deleted_at == None,  # noqa: E711
        )
        .order_by(StorageTank.name.asc())
        .all()
    )


def get_active_storage_tank_in_group(
    db: Session, tank_id: int, group_id: int
) -> StorageTank | None:
    return (
        db.query(StorageTank)
        .filter(
            StorageTank.id == tank_id,
            StorageTank.group_id == group_id,
            StorageTank.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def list_storage_tanks_for_fuel_form(db: Session, group_id: int) -> list[dict]:
    """Active tanks with stock for the fuel entry form dropdown."""
    tanks = list_storage_tanks_for_group(db, group_id)
    return [
        {
            "id": tank.id,
            "name": tank.name,
            "fuel_type": tank.fuel_type,
            "current_stock_l": current_stock_l(db, tank),
        }
        for tank in tanks
    ]


def tanks_page_context(db: Session, user: User, group_id: int) -> dict:
    tanks = list_storage_tanks_for_group(db, group_id)
    tank_rows = [
        {
            "tank": tank,
            "current_stock_l": current_stock_l(db, tank),
        }
        for tank in tanks
    ]
    return {
        "tank_rows": tank_rows,
        **group_page_capabilities(db, user, group_id),
    }


def tank_detail_context(
    db: Session, user: User, group_id: int, tank: StorageTank
) -> dict:
    from app.services.tank_ledger import list_ledger_entries_for_tank

    stock = current_stock_l(db, tank)
    return {
        "tank": tank,
        "current_stock_l": stock,
        "negative_stock": stock < 0,
        "ledger_entries": list_ledger_entries_for_tank(db, tank.id),
        **group_page_capabilities(db, user, group_id),
    }


def create_storage_tank(
    db: Session, group_id: int, data: StorageTankCreate
) -> StorageTank:
    tank = StorageTank(
        group_id=group_id,
        name=data.name,
        fuel_type=data.fuel_type.value,
        capacity_l=data.capacity_l,
        opening_balance_l=data.opening_balance_l,
        notes=data.notes,
    )
    db.add(tank)
    db.commit()
    db.refresh(tank)
    return tank


def apply_storage_tank_update(
    db: Session, tank: StorageTank, data: StorageTankUpdate
) -> None:
    for name, value in data.model_dump(exclude_unset=True).items():
        setattr(tank, name, value)
    tank.updated_at = utc_now()
    db.commit()
    db.refresh(tank)


def tank_has_active_farm_fuel_entries(db: Session, tank_id: int) -> bool:
    return (
        db.query(FuelEntry)
        .filter(
            FuelEntry.fuel_tank_id == tank_id,
            FuelEntry.fill_source == FillSource.farm.value,
            FuelEntry.deleted_at == None,  # noqa: E711
        )
        .count()
        > 0
    )


def soft_delete_storage_tank(db: Session, tank: StorageTank) -> None:
    if tank_has_active_farm_fuel_entries(db, tank.id):
        raise ValueError(
            "Tank kann nicht entfernt werden — es gibt noch aktive Hof-Tank-Tankvorgänge."
        )
    tank.deleted_at = utc_now()
    db.commit()
    db.refresh(tank)
