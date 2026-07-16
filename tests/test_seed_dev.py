"""Tests for development database seeding."""

from datetime import date, timedelta

from app.models import FuelEntry, Group, MaintenanceLog, User, Vehicle
from scripts.seed_dev import (
    DEMO_ADMIN_EMAIL,
    DEMO_INVITE_CODE,
    clear_demo_data,
    demo_exists,
    seed_demo_data,
)


class TestSeedDev:
    def test_seed_creates_realistic_demo_farm(self, db):
        result = seed_demo_data(db)

        assert result["created"] is True
        assert demo_exists(db)

        admin = db.query(User).filter(User.email == DEMO_ADMIN_EMAIL).one()
        group = db.query(Group).filter(Group.invite_code == DEMO_INVITE_CODE).one()
        vehicles = db.query(Vehicle).filter(Vehicle.group_id == group.id).all()
        entries = db.query(FuelEntry).filter(FuelEntry.group_id == group.id).all()
        maintenance = (
            db.query(MaintenanceLog).filter(MaintenanceLog.group_id == group.id).all()
        )

        assert admin.name == "Andreas Wagner"
        assert len(vehicles) == 3
        assert len(entries) >= 20
        assert len(maintenance) == 3
        assert any(entry.total_cost_eur for entry in entries)
        assert any(
            log.next_service_date and log.next_service_date <= date.today() + timedelta(days=30)
            for log in maintenance
        )

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
        assert db.query(Group).filter(Group.invite_code == DEMO_INVITE_CODE).count() == 0
