"""Vehicle listing and mutations for the active group."""

from sqlalchemy.orm import Session

from app.models import User, Vehicle
from app.schemas import VehicleCreate, VehicleUpdate
from app.services.membership import group_page_capabilities
from app.services.mobile_stats import vehicle_mobile_stats
from app.time_utils import utc_now


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
    return {
        "vehicles": vehicles,
        "vehicle_stats": vehicle_mobile_stats(db, group_id, vehicles),
        **group_page_capabilities(db, user, group_id),
    }


def create_vehicle(db: Session, group_id: int, data: VehicleCreate) -> Vehicle:
    vehicle = Vehicle(
        group_id=group_id,
        name=data.name,
        vtype=data.vtype.value,
        fuel_type=data.fuel_type.value,
    )
    db.add(vehicle)
    db.flush()
    return vehicle


def apply_vehicle_update(db: Session, vehicle: Vehicle, data: VehicleUpdate) -> None:
    if data.name is not None:
        vehicle.name = data.name
    if data.fuel_type is not None:
        vehicle.fuel_type = data.fuel_type.value
    vehicle.updated_at = utc_now()
    db.commit()
    db.refresh(vehicle)


def soft_delete_vehicle(db: Session, vehicle: Vehicle) -> None:
    vehicle.deleted_at = utc_now()
    db.flush()
