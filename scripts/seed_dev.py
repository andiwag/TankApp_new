"""Seed the local development database with realistic demo data.

The dataset is deterministic (Random(42)) and designed so consumption,
tank stock, and fleet stats line up with Tankly's calculation rules:
full-tank anchors only, AdBlue ignored in consumption, external
withdrawals affect stock but not fleet liters.
"""

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
from app.enums import FillSource, FuelType, Role, VehicleType  # noqa: E402
from app.models import (  # noqa: E402
    AuditLog,
    FuelEntry,
    Group,
    GroupSubscription,
    MaintenanceLog,
    StorageTank,
    TankLedgerEntry,
    User,
    UserGroup,
    UserSession,
    Vehicle,
)
from app.schemas import (  # noqa: E402
    FuelEntryCreate,
    StorageTankCreate,
    TankAdjustmentCreate,
    TankDeliveryCreate,
    TankExternalWithdrawalCreate,
)
from app.services.billing.subscriptions import ensure_group_subscription  # noqa: E402
from app.services.consumption import average_consumption_for_vehicle  # noqa: E402
from app.services.fuel_entries import create_fuel_entry  # noqa: E402
from app.services.storage_tanks import create_storage_tank  # noqa: E402
from app.services.tank_ledger import (  # noqa: E402
    current_stock_l,
    post_adjustment,
    post_delivery,
    post_external_withdrawal,
)
from sqlalchemy.orm import Session  # noqa: E402

DEMO_ADMIN_EMAIL = "demo@tankly.local"
DEMO_CONTRIBUTOR_EMAIL = "maria@tankly.local"
DEMO_READER_EMAIL = "leser@tankly.local"
DEMO_PASSWORD = "Demo1234!"
DEMO_GROUP_NAME = "Hof Winkling"
DEMO_INVITE_CODE = "TANKLY-DEMO"

DEMO_EMAILS = (DEMO_ADMIN_EMAIL, DEMO_CONTRIBUTOR_EMAIL, DEMO_READER_EMAIL)

# Known Audi segments: 40 L / 500 km * 100 = 8.0 L/100 km each → avg 8.0
AUDI_EXPECTED_L_PER_100KM = 8.0
# Tractor full fills: 80 L / 20 h = 4.0 L/h each → avg 4.0
TRACTOR_EXPECTED_L_PER_H = 4.0


def demo_exists(db: Session) -> bool:
    return db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).first() is not None


def clear_demo_data(db: Session) -> None:
    group = db.query(Group).filter(Group.invite_code == DEMO_INVITE_CODE).first()
    if group:
        db.query(AuditLog).filter(AuditLog.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(TankLedgerEntry).filter(TankLedgerEntry.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(FuelEntry).filter(FuelEntry.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(MaintenanceLog).filter(MaintenanceLog.group_id == group.id).delete(
            synchronize_session=False
        )
        db.query(StorageTank).filter(StorageTank.group_id == group.id).delete(
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
        db.query(TankLedgerEntry).filter(TankLedgerEntry.user_id == user.id).delete(
            synchronize_session=False
        )
        db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(
            synchronize_session=False
        )
        db.delete(user)

    db.commit()


def _add_fuel(
    db: Session,
    *,
    vehicle: Vehicle,
    user_id: int,
    group_id: int,
    liters: float,
    reading: float,
    entry_date: date,
    full_tank: bool = True,
    fill_source: FillSource = FillSource.external,
    fuel_tank_id: int | None = None,
    cost_eur: float | None = None,
    adblue_l: float | None = None,
    notes: str | None = None,
) -> FuelEntry:
    return create_fuel_entry(
        db,
        user_id,
        group_id,
        vehicle,
        FuelEntryCreate(
            vehicle_id=vehicle.id,
            fuel_amount_l=liters,
            usage_reading=reading,
            entry_date=entry_date,
            full_tank=full_tank,
            total_cost_eur=cost_eur,
            adblue_amount_l=adblue_l,
            fill_source=fill_source,
            fuel_tank_id=fuel_tank_id,
            notes=notes,
        ),
    )


def _seed_audi_history(
    db: Session,
    *,
    vehicle: Vehicle,
    admin_id: int,
    contributor_id: int,
    group_id: int,
    petrol_tank_id: int,
    today: date,
) -> None:
    """Deterministic 8.0 L/100 km average with farm/external mix and a partial fill."""
    # Anchor + three equal full segments at 8.0 L/100 km
    fills = [
        # (days_ago, reading, liters, full, source, user, cost, notes)
        (200, 80000.0, 48.0, True, FillSource.external, admin_id, 78.0, None),
        (170, 80500.0, 40.0, True, FillSource.farm, admin_id, None, "Hof-Tank Benzin"),
        (140, 81000.0, 40.0, True, FillSource.external, contributor_id, 66.4, None),
        (110, 81500.0, 40.0, True, FillSource.farm, admin_id, None, None),
        # Partial mid-cycle (ignored as consumption anchor)
        (95, 81750.0, 22.0, False, FillSource.external, contributor_id, 36.0, "Teilfüllung"),
        # Next full still measured from 81500 → 82000 (40 L / 500 km)
        (80, 82000.0, 40.0, True, FillSource.farm, admin_id, None, None),
        (50, 82500.0, 40.0, True, FillSource.external, admin_id, 67.2, None),
        (20, 83000.0, 40.0, True, FillSource.farm, contributor_id, None, None),
        (5, 83500.0, 40.0, True, FillSource.external, admin_id, 68.0, None),
    ]
    for days_ago, reading, liters, full, source, user_id, cost, notes in fills:
        _add_fuel(
            db,
            vehicle=vehicle,
            user_id=user_id,
            group_id=group_id,
            liters=liters,
            reading=reading,
            entry_date=today - timedelta(days=days_ago),
            full_tank=full,
            fill_source=source,
            fuel_tank_id=petrol_tank_id if source == FillSource.farm else None,
            cost_eur=cost,
            notes=notes,
        )


def _seed_golf_history(
    db: Session,
    *,
    vehicle: Vehicle,
    user_id: int,
    group_id: int,
    petrol_tank_id: int,
    today: date,
    rng: random.Random,
) -> None:
    reading = 45200.0
    for index in range(12):
        days_ago = (12 - index) * 16 + rng.randint(0, 2)
        reading = round(reading + rng.uniform(380, 480), 1)
        liters = round(rng.uniform(38, 48), 1)
        farm = index % 3 == 0
        _add_fuel(
            db,
            vehicle=vehicle,
            user_id=user_id,
            group_id=group_id,
            liters=liters,
            reading=reading,
            entry_date=today - timedelta(days=days_ago),
            full_tank=True,
            fill_source=FillSource.farm if farm else FillSource.external,
            fuel_tank_id=petrol_tank_id if farm else None,
            cost_eur=None if farm else round(liters * rng.uniform(1.55, 1.68), 2),
        )


def _seed_motorcycle_history(
    db: Session,
    *,
    vehicle: Vehicle,
    user_id: int,
    group_id: int,
    today: date,
) -> None:
    # 5.0 L/100 km segments
    fills = [
        (90, 12000.0, 12.0),
        (60, 12400.0, 20.0),  # 20/400*100 = 5.0
        (30, 12800.0, 20.0),
        (7, 13200.0, 20.0),
    ]
    for days_ago, reading, liters in fills:
        _add_fuel(
            db,
            vehicle=vehicle,
            user_id=user_id,
            group_id=group_id,
            liters=liters,
            reading=reading,
            entry_date=today - timedelta(days=days_ago),
            full_tank=True,
            fill_source=FillSource.external,
            cost_eur=round(liters * 1.72, 2),
        )


def _seed_tractor_history(
    db: Session,
    *,
    vehicle: Vehicle,
    admin_id: int,
    contributor_id: int,
    group_id: int,
    diesel_tank_id: int,
    today: date,
) -> None:
    """4.0 L/h average with AdBlue on farm fills."""
    fills = [
        # days, hours, liters, full, farm, user, adblue
        (150, 1200.0, 70.0, True, True, admin_id, 8.0),
        (120, 1220.0, 80.0, True, True, admin_id, 10.0),  # 80/20 = 4.0
        (100, 1230.0, 25.0, False, False, contributor_id, None),  # partial external
        (90, 1240.0, 80.0, True, True, admin_id, 9.5),
        (60, 1260.0, 80.0, True, True, contributor_id, 11.0),
        (35, 1280.0, 80.0, True, False, admin_id, None),
        (15, 1300.0, 80.0, True, True, admin_id, 10.0),
        (3, 1320.0, 80.0, True, True, admin_id, 12.0),
    ]
    for days_ago, hours, liters, full, farm, user_id, adblue in fills:
        _add_fuel(
            db,
            vehicle=vehicle,
            user_id=user_id,
            group_id=group_id,
            liters=liters,
            reading=hours,
            entry_date=today - timedelta(days=days_ago),
            full_tank=full,
            fill_source=FillSource.farm if farm else FillSource.external,
            fuel_tank_id=diesel_tank_id if farm else None,
            cost_eur=None if farm else round(liters * 1.42, 2),
            adblue_l=adblue,
            notes="Hof Diesel + AdBlue" if farm and adblue else None,
        )


def _seed_machine_history(
    db: Session,
    *,
    vehicle: Vehicle,
    user_id: int,
    group_id: int,
    diesel_tank_id: int,
    today: date,
) -> None:
    # 12 L/h segments
    fills = [
        (100, 400.0, 40.0),
        (70, 410.0, 120.0),  # 120/10 = 12
        (40, 420.0, 120.0),
        (10, 430.0, 120.0),
    ]
    for days_ago, hours, liters in fills:
        _add_fuel(
            db,
            vehicle=vehicle,
            user_id=user_id,
            group_id=group_id,
            liters=liters,
            reading=hours,
            entry_date=today - timedelta(days=days_ago),
            full_tank=True,
            fill_source=FillSource.farm,
            fuel_tank_id=diesel_tank_id,
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
    today = date.today()
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
    reader = User(
        email=DEMO_READER_EMAIL,
        name="Leo Leser",
        password_hash=password_hash,
    )
    db.add_all([admin, contributor, reader])
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
    sub.tier = "farm"
    group.subscription_tier = "farm"
    db.flush()

    db.add_all(
        [
            UserGroup(user_id=admin.id, group_id=group.id, role=Role.admin.value),
            UserGroup(
                user_id=contributor.id,
                group_id=group.id,
                role=Role.contributor.value,
            ),
            UserGroup(user_id=reader.id, group_id=group.id, role=Role.reader.value),
        ]
    )
    db.flush()

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
    bike = Vehicle(
        group_id=group.id,
        name="KTM 390",
        vtype=VehicleType.motorcycle.value,
        fuel_type=FuelType.petrol.value,
    )
    tractor = Vehicle(
        group_id=group.id,
        name="Fendt 724",
        vtype=VehicleType.tractor.value,
        fuel_type=FuelType.diesel.value,
    )
    press = Vehicle(
        group_id=group.id,
        name="Claas Quadrant",
        vtype=VehicleType.machine.value,
        fuel_type=FuelType.diesel.value,
    )
    db.add_all([audi, golf, bike, tractor, press])
    db.flush()

    diesel_tank = create_storage_tank(
        db,
        group.id,
        StorageTankCreate(
            name="Diesel Haupttank",
            fuel_type=FuelType.diesel,
            capacity_l=8000.0,
            opening_balance_l=2200.0,
            notes="Hofzapfsäule Diesel",
        ),
    )
    petrol_tank = create_storage_tank(
        db,
        group.id,
        StorageTankCreate(
            name="Benzin Tank",
            fuel_type=FuelType.petrol,
            capacity_l=1000.0,
            opening_balance_l=480.0,
            notes="Kleiner Benzin-Vorrat",
        ),
    )

    post_delivery(
        db,
        admin.id,
        group.id,
        diesel_tank,
        TankDeliveryCreate(
            amount_l=2500.0,
            entry_date=today - timedelta(days=160),
            total_cost_eur=3375.0,
            notes="Herbstlieferung Lagerhaus",
        ),
    )
    post_delivery(
        db,
        admin.id,
        group.id,
        petrol_tank,
        TankDeliveryCreate(
            amount_l=600.0,
            entry_date=today - timedelta(days=150),
            total_cost_eur=990.0,
            notes="Benzin Auffüllung",
        ),
    )
    post_delivery(
        db,
        admin.id,
        group.id,
        diesel_tank,
        TankDeliveryCreate(
            amount_l=1800.0,
            entry_date=today - timedelta(days=45),
            total_cost_eur=2520.0,
            notes="Frühjahrsfüllung",
        ),
    )
    post_adjustment(
        db,
        admin.id,
        group.id,
        diesel_tank,
        TankAdjustmentCreate(
            amount_l=-35.0,
            entry_date=today - timedelta(days=30),
            notes="Messkorrektur Peilstab vs. Zähler",
        ),
    )
    post_external_withdrawal(
        db,
        admin.id,
        group.id,
        diesel_tank,
        TankExternalWithdrawalCreate(
            amount_l=120.0,
            entry_date=today - timedelta(days=25),
            recipient_name="Nachbar Kreuzmayr",
            total_cost_eur=168.0,
            notes="Hilfe bei der Ernte",
        ),
    )
    post_external_withdrawal(
        db,
        contributor.id,
        group.id,
        petrol_tank,
        TankExternalWithdrawalCreate(
            amount_l=25.0,
            entry_date=today - timedelta(days=12),
            recipient_name="Firma Huber Bau",
            notes="Kurzfristige Abgabe",
        ),
    )

    _seed_audi_history(
        db,
        vehicle=audi,
        admin_id=admin.id,
        contributor_id=contributor.id,
        group_id=group.id,
        petrol_tank_id=petrol_tank.id,
        today=today,
    )
    _seed_golf_history(
        db,
        vehicle=golf,
        user_id=contributor.id,
        group_id=group.id,
        petrol_tank_id=petrol_tank.id,
        today=today,
        rng=rng,
    )
    _seed_motorcycle_history(
        db,
        vehicle=bike,
        user_id=admin.id,
        group_id=group.id,
        today=today,
    )
    _seed_tractor_history(
        db,
        vehicle=tractor,
        admin_id=admin.id,
        contributor_id=contributor.id,
        group_id=group.id,
        diesel_tank_id=diesel_tank.id,
        today=today,
    )
    _seed_machine_history(
        db,
        vehicle=press,
        user_id=admin.id,
        group_id=group.id,
        diesel_tank_id=diesel_tank.id,
        today=today,
    )

    db.add_all(
        [
            MaintenanceLog(
                vehicle_id=audi.id,
                group_id=group.id,
                user_id=admin.id,
                service_date=today - timedelta(days=90),
                description="Ölwechsel",
                cost_eur=89.0,
                usage_reading=80950.0,
                next_service_date=today + timedelta(days=12),
            ),
            MaintenanceLog(
                vehicle_id=golf.id,
                group_id=group.id,
                user_id=admin.id,
                service_date=today - timedelta(days=120),
                description="Inspektion",
                cost_eur=249.0,
                usage_reading=45200.0,
                next_service_date=today + timedelta(days=75),
            ),
            MaintenanceLog(
                vehicle_id=tractor.id,
                group_id=group.id,
                user_id=admin.id,
                service_date=today - timedelta(days=60),
                description="Filterwechsel",
                cost_eur=156.0,
                usage_reading=1180.0,
                next_service_usage=1370.0,
            ),
            MaintenanceLog(
                vehicle_id=bike.id,
                group_id=group.id,
                user_id=contributor.id,
                service_date=today - timedelta(days=40),
                description="Kette und Reifen",
                cost_eur=210.0,
                usage_reading=12100.0,
                next_service_date=today + timedelta(days=140),
            ),
            MaintenanceLog(
                vehicle_id=press.id,
                group_id=group.id,
                user_id=admin.id,
                service_date=today - timedelta(days=20),
                description="Schmierstellen und Bindfaden",
                cost_eur=75.0,
                usage_reading=415.0,
                next_service_usage=450.0,
            ),
        ]
    )
    db.commit()

    fuel_count = db.query(FuelEntry).filter(FuelEntry.group_id == group.id).count()
    vehicle_count = db.query(Vehicle).filter(Vehicle.group_id == group.id).count()
    tank_count = db.query(StorageTank).filter(StorageTank.group_id == group.id).count()
    ledger_count = (
        db.query(TankLedgerEntry).filter(TankLedgerEntry.group_id == group.id).count()
    )
    farm_fills = (
        db.query(FuelEntry)
        .filter(
            FuelEntry.group_id == group.id,
            FuelEntry.fill_source == FillSource.farm.value,
        )
        .count()
    )
    adblue_fills = (
        db.query(FuelEntry)
        .filter(
            FuelEntry.group_id == group.id,
            FuelEntry.adblue_amount_l.isnot(None),
        )
        .count()
    )
    diesel_stock = current_stock_l(db, diesel_tank)
    petrol_stock = current_stock_l(db, petrol_tank)

    audi_entries = (
        db.query(FuelEntry)
        .filter(FuelEntry.vehicle_id == audi.id, FuelEntry.deleted_at.is_(None))
        .all()
    )
    audi_avg = average_consumption_for_vehicle(
        "km",
        [(e.usage_reading, e.fuel_amount_l, e.full_tank) for e in audi_entries],
    )
    tractor_entries = (
        db.query(FuelEntry)
        .filter(FuelEntry.vehicle_id == tractor.id, FuelEntry.deleted_at.is_(None))
        .all()
    )
    tractor_avg = average_consumption_for_vehicle(
        "hours",
        [(e.usage_reading, e.fuel_amount_l, e.full_tank) for e in tractor_entries],
    )

    return {
        "created": True,
        "admin_email": DEMO_ADMIN_EMAIL,
        "contributor_email": DEMO_CONTRIBUTOR_EMAIL,
        "reader_email": DEMO_READER_EMAIL,
        "password": DEMO_PASSWORD,
        "group_name": DEMO_GROUP_NAME,
        "invite_code": DEMO_INVITE_CODE,
        "vehicles": vehicle_count,
        "fuel_entries": fuel_count,
        "storage_tanks": tank_count,
        "ledger_entries": ledger_count,
        "farm_fills": farm_fills,
        "adblue_fills": adblue_fills,
        "diesel_stock_l": diesel_stock,
        "diesel_capacity_l": diesel_tank.capacity_l,
        "petrol_stock_l": petrol_stock,
        "petrol_capacity_l": petrol_tank.capacity_l,
        "audi_avg_l_per_100km": audi_avg,
        "tractor_avg_l_per_h": tractor_avg,
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
            print(f"  Betrieb:        {result['group_name']}")
            print(f"  Fahrzeuge:      {result['vehicles']}")
            print(f"  Tankungen:      {result['fuel_entries']}")
            print(f"  Hof-Tanks:      {result['storage_tanks']}")
            print(f"  Ledger:         {result['ledger_entries']}")
            print(f"  Hof-Tankungen:  {result['farm_fills']}")
            print(f"  AdBlue-Einträge:{result['adblue_fills']}")
            print(f"  Diesel Bestand: {result['diesel_stock_l']:.1f} L")
            print(f"  Benzin Bestand: {result['petrol_stock_l']:.1f} L")
            if result.get("audi_avg_l_per_100km") is not None:
                print(
                    f"  Audi Verbr.:    {result['audi_avg_l_per_100km']:.2f} L/100 km"
                )
            if result.get("tractor_avg_l_per_h") is not None:
                print(f"  Fendt Verbr.:   {result['tractor_avg_l_per_h']:.2f} L/h")
        else:
            print("Demo data already present (use --reset to recreate).")

        print()
        print("Login:")
        print(f"  Admin:     {result['admin_email']} / {result['password']}")
        if result.get("contributor_email"):
            print(
                f"  Beitrag:   {result['contributor_email']} / {result['password']}"
            )
        if result.get("reader_email"):
            print(f"  Leser:     {result['reader_email']} / {result['password']}")
        print("  URL:       http://127.0.0.1:8000/login")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
