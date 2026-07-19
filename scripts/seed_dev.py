"""Seed the local development database with realistic demo data."""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.auth import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.enums import FuelType, Role, VehicleType  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    FuelEntry,
    Group,
    GroupSubscription,
    MaintenanceLog,
    User,
    UserGroup,
    UserSession,
    Vehicle,
)
from app.services.billing.subscriptions import ensure_group_subscription  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

DEMO_ADMIN_EMAIL = "demo@tankly.local"
DEMO_CONTRIBUTOR_EMAIL = "maria@tankly.local"
DEMO_PASSWORD = "Demo1234!"
DEMO_GROUP_NAME = "Hof Winkling"
DEMO_INVITE_CODE = "TANKLY-DEMO"

DEMO_EMAILS = (DEMO_ADMIN_EMAIL, DEMO_CONTRIBUTOR_EMAIL)


def demo_exists(db: Session) -> bool:
    return (
        db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).first() is not None
    )


def clear_demo_data(db: Session) -> None:
    group = db.query(Group).filter(Group.invite_code == DEMO_INVITE_CODE).first()
    if group:
        db.query(AuditLog).filter(AuditLog.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(FuelEntry).filter(FuelEntry.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(MaintenanceLog).filter(MaintenanceLog.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(Vehicle).filter(Vehicle.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(UserGroup).filter(UserGroup.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(GroupSubscription).filter(
            GroupSubscription.group_id == group.id
        ).delete(synchronize_session=False)
        db.delete(group)
        db.flush()

    for email in DEMO_EMAILS:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            continue
        db.query(UserSession).filter(UserSession.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(UserGroup).filter(UserGroup.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(FuelEntry).filter(FuelEntry.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(MaintenanceLog).filter(MaintenanceLog.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(
            synchronize_session=False
        )
        db.delete(user)

    db.commit()


def _add_fuel_history(
    db: Session,
    *,
    vehicle: Vehicle,
    group_id: int,
    user_id: int,
    start_reading: float,
    start_date: date,
    fill_count: int,
    rng: random.Random,
) -> None:
    reading = start_reading
    anchor = date.today()
    for index in range(fill_count):
        days_back = (fill_count - index) * 14 + rng.randint(0, 4)
        entry_date = anchor - timedelta(days=days_back)
        if entry_date < start_date:
            continue
        distance = rng.uniform(420, 620)
        liters = round(rng.uniform(42, 56), 1)
        reading = round(reading + distance, 1)
        price_per_liter = rng.uniform(1.52, 1.68)
        db.add(
            FuelEntry(
                vehicle_id=vehicle.id,
                group_id=group_id,
                user_id=user_id,
                fuel_amount_l=liters,
                usage_reading=reading,
                full_tank=True,
                total_cost_eur=round(liters * price_per_liter, 2),
                entry_date=entry_date,
            )
        )


def seed_demo_data(db: Session) -> dict:
    """Insert demo farm data. Idempotent when demo user already exists."""
    if demo_exists(db):
        return {
            "created": False,
            "admin_email": DEMO_ADMIN_EMAIL,
            "password": DEMO_PASSWORD,
            "group_name": DEMO_GROUP_NAME,
        }

    rng = random.Random(42)
    password_hash = hash_password(DEMO_PASSWORD)

    admin = User(
        email=DEMO_ADMIN_EMAIL,
        name="Andreas Wagner",
        password_hash=password_hash,
    )
    contributor = User(
        email=DEMO_CONTRIBUTOR_EMAIL,
        name="Maria Huber",
        password_hash=password_hash,
    )
    db.add_all([admin, contributor])
    db.flush()

    group = Group(
        name=DEMO_GROUP_NAME,
        invite_code=DEMO_INVITE_CODE,
        created_by=admin.id,
    )
    db.add(group)
    db.flush()
    ensure_group_subscription(db, group.id)
    sub = (
        db.query(GroupSubscription)
        .filter(GroupSubscription.group_id == group.id)
        .one()
    )
    sub.tier = "pro"
    group.subscription_tier = "pro"
    db.flush()

    db.add_all(
        [
            UserGroup(user_id=admin.id, group_id=group.id, role=Role.admin.value),
            UserGroup(
                user_id=contributor.id,
                group_id=group.id,
                role=Role.contributor.value,
            ),
        ]
    )

    audi = Vehicle(
        group_id=group.id,
        name="Audi A4",
        vtype=VehicleType.car.value,
        fuel_type=FuelType.petrol.value,
    )
    golf = Vehicle(
        group_id=group.id,
        name="VW Golf",
        vtype=VehicleType.car.value,
        fuel_type=FuelType.petrol.value,
    )
    tractor = Vehicle(
        group_id=group.id,
        name="Fendt 724",
        vtype=VehicleType.tractor.value,
        fuel_type=FuelType.diesel.value,
    )
    db.add_all([audi, golf, tractor])
    db.flush()

    history_start = date.today() - timedelta(days=210)
    _add_fuel_history(
        db,
        vehicle=audi,
        group_id=group.id,
        user_id=admin.id,
        start_reading=81200.0,
        start_date=history_start,
        fill_count=14,
        rng=rng,
    )
    _add_fuel_history(
        db,
        vehicle=golf,
        group_id=group.id,
        user_id=contributor.id,
        start_reading=45800.0,
        start_date=history_start,
        fill_count=11,
        rng=rng,
    )

    tractor_hours = 1240.0
    for index in range(8):
        entry_date = date.today() - timedelta(days=24 * (index + 1))
        liters = round(rng.uniform(75, 95), 1)
        tractor_hours = round(tractor_hours + rng.uniform(18, 28), 1)
        db.add(
            FuelEntry(
                vehicle_id=tractor.id,
                group_id=group.id,
                user_id=admin.id,
                fuel_amount_l=liters,
                usage_reading=tractor_hours,
                full_tank=True,
                total_cost_eur=round(liters * rng.uniform(1.35, 1.48), 2),
                entry_date=entry_date,
            )
        )

    db.add_all(
        [
            MaintenanceLog(
                vehicle_id=audi.id,
                group_id=group.id,
                user_id=admin.id,
                service_date=date.today() - timedelta(days=90),
                description="Ölwechsel",
                cost_eur=89.0,
                usage_reading=80950.0,
                next_service_date=date.today() + timedelta(days=12),
            ),
            MaintenanceLog(
                vehicle_id=golf.id,
                group_id=group.id,
                user_id=admin.id,
                service_date=date.today() - timedelta(days=120),
                description="Inspektion",
                cost_eur=249.0,
                usage_reading=45200.0,
                next_service_date=date.today() + timedelta(days=75),
            ),
            MaintenanceLog(
                vehicle_id=tractor.id,
                group_id=group.id,
                user_id=admin.id,
                service_date=date.today() - timedelta(days=60),
                description="Filterwechsel",
                cost_eur=156.0,
                usage_reading=1180.0,
                next_service_usage=tractor_hours + 50,
            ),
        ]
    )

    db.commit()

    fuel_count = (
        db.query(FuelEntry).filter(FuelEntry.group_id == group.id).count()
    )
    vehicle_count = db.query(Vehicle).filter(Vehicle.group_id == group.id).count()

    return {
        "created": True,
        "admin_email": DEMO_ADMIN_EMAIL,
        "contributor_email": DEMO_CONTRIBUTOR_EMAIL,
        "password": DEMO_PASSWORD,
        "group_name": DEMO_GROUP_NAME,
        "invite_code": DEMO_INVITE_CODE,
        "vehicles": vehicle_count,
        "fuel_entries": fuel_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seed Tankly dev database with realistic demo data."
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Remove existing demo data before seeding.",
    )
    args = parser.parse_args()

    if settings.ENV == "production":
        print("Refusing to seed: ENV=production", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        if args.reset:
            clear_demo_data(db)
            print("Removed existing demo data.")

        result = seed_demo_data(db)
        if result["created"]:
            print("Demo data created.")
            print(f"  Betrieb:   {result['group_name']}")
            print(f"  Fahrzeuge: {result['vehicles']}")
            print(f"  Tankungen: {result['fuel_entries']}")
        else:
            print("Demo data already present (use --reset to recreate).")

        print()
        print("Login:")
        print(f"  E-Mail:    {result['admin_email']}")
        print(f"  Passwort:  {result['password']}")
        print("  URL:       http://127.0.0.1:8000/login")
        if result.get("contributor_email"):
            print(f"  Mitbearbeiter: {result['contributor_email']} (same password)")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
