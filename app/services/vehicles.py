"""Vehicle listing and mutations for the active group."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.dependencies import ROLE_HIERARCHY
from app.enums import Role
from app.models import User, UserGroup, Vehicle
from app.schemas import VehicleCreate, VehicleUpdate


def list_vehicles_for_group(db: Session, group_id: int) -> list[Vehicle]:
    return (
        db.query(Vehicle)
        .filter(
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .order_by(Vehicle.name.asc())
        .all()
    )


def get_active_vehicle_in_group(
    db: Session, vehicle_id: int, group_id: int
) -> Vehicle | None:
    return (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.group_id == group_id,
            Vehicle.deleted_at == None,  # noqa: E711
        )
        .first()
    )


def vehicles_page_context(db: Session, user: User, group_id: int) -> dict:
    vehicles = list_vehicles_for_group(db, group_id)
    ug = (
        db.query(UserGroup)
        .filter(
            UserGroup.user_id == user.id,
            UserGroup.group_id == group_id,
        )
        .first()
    )
    can_edit = bool(
        ug and ROLE_HIERARCHY.get(ug.role, 0) >= ROLE_HIERARCHY[Role.contributor.value]
    )
    can_delete = bool(ug and ug.role == Role.admin.value)
    return {
        "vehicles": vehicles,
        "can_edit": can_edit,
        "can_delete": can_delete,
    }


def create_vehicle(db: Session, group_id: int, data: VehicleCreate) -> Vehicle:
    vehicle = Vehicle(
        group_id=group_id,
        name=data.name,
        vtype=data.vtype.value,
        fuel_type=data.fuel_type.value,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


def apply_vehicle_update(db: Session, vehicle: Vehicle, data: VehicleUpdate) -> None:
    if data.name is not None:
        vehicle.name = data.name
    if data.fuel_type is not None:
        vehicle.fuel_type = data.fuel_type.value
    vehicle.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(vehicle)


def soft_delete_vehicle(db: Session, vehicle: Vehicle) -> None:
    vehicle.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(vehicle)
