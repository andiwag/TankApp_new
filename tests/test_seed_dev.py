"""Tests for development database seeding."""

from datetime import date, timedelta

import pytest

from app.enums import FillSource, Role, VehicleType
from app.models import (
    FuelEntry,
    Group,
    MaintenanceLog,
    StorageTank,
    TankLedgerEntry,
    User,
    UserGroup,
    Vehicle,
)
from app.services.consumption import average_consumption_for_vehicle
from app.services.dashboard import get_dashboard_context
from app.services.summary import get_summary_context
from app.services.tank_ledger import current_stock_l
from scripts.seed_dev import (
    AUDI_EXPECTED_L_PER_100KM,
    DEMO_ADMIN_EMAIL,
    DEMO_CONTRIBUTOR_EMAIL,
    DEMO_INVITE_CODE,
    DEMO_READER_EMAIL,
    TRACTOR_EXPECTED_L_PER_H,
    clear_demo_data,
    demo_exists,
    seed_demo_data,
)


def _group(db) -> Group:
    return db.query(Group).filter(Group.invite_code == DEMO_INVITE_CODE).one()


def _vehicle(db, group_id: int, name: str) -> Vehicle:
    return (
        db.query(Vehicle)
        .filter(Vehicle.group_id == group_id, Vehicle.name == name)
        .one()
    )


def _active_entries(db, vehicle_id: int) -> list[FuelEntry]:
    return (
        db.query(FuelEntry)
        .filter(FuelEntry.vehicle_id == vehicle_id, FuelEntry.deleted_at.is_(None))
        .order_by(FuelEntry.usage_reading.asc())
        .all()
    )


class TestSeedDev:
    def test_seed_creates_realistic_demo_farm(self, db):
        result = seed_demo_data(db)

        assert result["created"] is True
        assert demo_exists(db)

        admin = db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).one()
        group = _group(db)
        vehicles = db.query(Vehicle).filter(Vehicle.group_id == group.id).all()
        entries = db.query(FuelEntry).filter(FuelEntry.group_id == group.id).all()
        maintenance = (
            db.query(MaintenanceLog).filter(MaintenanceLog.group_id == group.id).all()
        )
        tanks = db.query(StorageTank).filter(StorageTank.group_id == group.id).all()

        assert admin.name == "Andreas Wagner"
        assert len(vehicles) == 5
        assert len(entries) >= 35
        assert len(maintenance) == 5
        assert len(tanks) == 2
        assert any(entry.total_cost_eur for entry in entries)
        assert any(
            log.next_service_date
            and log.next_service_date <= date.today() + timedelta(days=30)
            for log in maintenance
        )
        assert result["storage_tanks"] == 2
        assert result["farm_fills"] >= 10
        assert result["adblue_fills"] >= 5
        assert result["diesel_stock_l"] > 0
        assert result["petrol_stock_l"] > 0

    def test_seed_covers_all_roles_and_vehicle_types(self, db):
        seed_demo_data(db)
        group = _group(db)

        roles = {
            ug.role
            for ug in db.query(UserGroup).filter(UserGroup.group_id == group.id).all()
        }
        assert roles == {Role.admin.value, Role.contributor.value, Role.reader.value}
        assert db.query(User).filter(User.email == DEMO_CONTRIBUTOR_EMAIL).one()
        assert db.query(User).filter(User.email == DEMO_READER_EMAIL).one()

        types = {
            v.vtype
            for v in db.query(Vehicle).filter(Vehicle.group_id == group.id).all()
        }
        assert types == {
            VehicleType.car.value,
            VehicleType.motorcycle.value,
            VehicleType.tractor.value,
            VehicleType.machine.value,
        }

    def test_seed_covers_tank_ledger_and_fill_features(self, db):
        seed_demo_data(db)
        group = _group(db)

        movements = {
            e.movement_type
            for e in db.query(TankLedgerEntry)
            .filter(
                TankLedgerEntry.group_id == group.id,
                TankLedgerEntry.deleted_at.is_(None),
            )
            .all()
        }
        assert "delivery" in movements
        assert "adjustment" in movements
        assert "external_withdrawal" in movements
        assert "vehicle_withdrawal" in movements

        entries = (
            db.query(FuelEntry)
            .filter(FuelEntry.group_id == group.id, FuelEntry.deleted_at.is_(None))
            .all()
        )
        assert any(e.fill_source == FillSource.farm.value for e in entries)
        assert any(e.fill_source == FillSource.external.value for e in entries)
        assert any(e.full_tank is False for e in entries)
        assert any(e.adblue_amount_l for e in entries)
        assert all(
            e.fuel_tank_id is not None
            for e in entries
            if e.fill_source == FillSource.farm.value
        )

    def test_seed_audi_consumption_is_exactly_eight(self, db):
        seed_demo_data(db)
        group = _group(db)
        audi = _vehicle(db, group.id, "Audi A4")
        entries = _active_entries(db, audi.id)

        avg = average_consumption_for_vehicle(
            "km",
            [(e.usage_reading, e.fuel_amount_l, e.full_tank) for e in entries],
        )
        assert avg == AUDI_EXPECTED_L_PER_100KM
        assert any(e.full_tank is False for e in entries)

    def test_seed_tractor_consumption_is_exactly_four(self, db):
        seed_demo_data(db)
        group = _group(db)
        tractor = _vehicle(db, group.id, "Fendt 724")
        entries = _active_entries(db, tractor.id)

        avg = average_consumption_for_vehicle(
            "hours",
            [(e.usage_reading, e.fuel_amount_l, e.full_tank) for e in entries],
        )
        assert avg == TRACTOR_EXPECTED_L_PER_H
        assert all(
            e.adblue_amount_l is None or e.fill_source == FillSource.farm.value
            for e in entries
        )

    def test_seed_tank_stock_matches_ledger_math(self, db):
        seed_demo_data(db)
        group = _group(db)
        tanks = db.query(StorageTank).filter(StorageTank.group_id == group.id).all()
        assert len(tanks) == 2

        for tank in tanks:
            ledger = (
                db.query(TankLedgerEntry)
                .filter(
                    TankLedgerEntry.tank_id == tank.id,
                    TankLedgerEntry.deleted_at.is_(None),
                )
                .all()
            )
            expected = tank.opening_balance_l + sum(e.amount_l for e in ledger)
            assert current_stock_l(db, tank) == pytest.approx(expected)
            assert expected > 0

            farm_liters = sum(
                e.fuel_amount_l
                for e in db.query(FuelEntry)
                .filter(
                    FuelEntry.fuel_tank_id == tank.id,
                    FuelEntry.fill_source == FillSource.farm.value,
                    FuelEntry.deleted_at.is_(None),
                )
                .all()
            )
            withdrawal_liters = -sum(
                e.amount_l for e in ledger if e.movement_type == "vehicle_withdrawal"
            )
            assert abs(farm_liters - withdrawal_liters) < 0.01

    def test_seed_external_withdrawal_not_in_fleet_fuel_total(self, db):
        seed_demo_data(db)
        group = _group(db)

        fleet_liters = sum(
            e.fuel_amount_l
            for e in db.query(FuelEntry)
            .filter(FuelEntry.group_id == group.id, FuelEntry.deleted_at.is_(None))
            .all()
        )
        external_stock_liters = -sum(
            e.amount_l
            for e in db.query(TankLedgerEntry)
            .filter(
                TankLedgerEntry.group_id == group.id,
                TankLedgerEntry.movement_type == "external_withdrawal",
                TankLedgerEntry.deleted_at.is_(None),
            )
            .all()
        )
        assert external_stock_liters > 0

        summary = get_summary_context(db, group.id)
        summary_liters = sum(row["total_liters"] for row in summary["vehicle_rows"])
        # Summary fleet liters come from fuel entries only — external tank
        # withdrawals must not inflate vehicle fuel totals.
        assert abs(summary_liters - fleet_liters) < 0.01
        assert summary_liters + external_stock_liters > summary_liters

    def test_seed_dashboard_and_summary_calculate_useful_stats(self, db):
        seed_demo_data(db)
        group = _group(db)
        admin = db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).one()

        dashboard = get_dashboard_context(db, admin, group.id)
        summary = get_summary_context(db, group.id)

        assert dashboard["vehicle_count"] == 5
        assert len(dashboard["recent_fuel_entries"]) > 0
        assert len(dashboard["tank_stock_rows"]) == 2
        assert all(row["current_stock_l"] > 0 for row in dashboard["tank_stock_rows"])
        assert sum(row["total_liters"] for row in summary["vehicle_rows"]) > 0
        assert len(summary["vehicle_rows"]) == 5
        assert any(row["avg_consumption"] for row in summary["vehicle_rows"])
        assert summary["total_group_adblue_l"] is not None
        assert summary["total_group_adblue_l"] > 0

        audi_row = next(
            row for row in summary["vehicle_rows"] if row["name"] == "Audi A4"
        )
        assert audi_row["avg_consumption"] == AUDI_EXPECTED_L_PER_100KM

        tractor_row = next(
            row for row in summary["vehicle_rows"] if row["name"] == "Fendt 724"
        )
        assert tractor_row["avg_consumption"] == TRACTOR_EXPECTED_L_PER_H

    def test_seed_is_idempotent(self, db):
        first = seed_demo_data(db)
        second = seed_demo_data(db)

        assert first["created"] is True
        assert second["created"] is False
        assert (
            db.query(FuelEntry)
            .join(Group, Group.id == FuelEntry.group_id)
            .filter(Group.invite_code == DEMO_INVITE_CODE)
            .count()
            == first["fuel_entries"]
        )

    def test_reset_clears_demo_data(self, db):
        seed_demo_data(db)
        clear_demo_data(db)

        assert demo_exists(db) is False
        assert (
            db.query(Group).filter(Group.invite_code == DEMO_INVITE_CODE).count() == 0
        )
        assert db.query(StorageTank).count() == 0
        assert db.query(TankLedgerEntry).count() == 0
        assert db.query(User).filter(User.email == DEMO_READER_EMAIL).count() == 0
