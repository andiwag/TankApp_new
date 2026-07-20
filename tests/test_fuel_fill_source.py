"""Tests for Phase 26: fill source and farm tank selection on fuel entries."""

import re
from datetime import date

import pytest
from app.enums import FillSource
from app.models import FuelEntry, TankLedgerEntry
from app.schemas import FuelEntryCreate, FuelEntryUpdate
from app.services.fuel_entries import (
    apply_fuel_entry_update,
    create_fuel_entry,
    soft_delete_fuel_entry,
)
from app.services.tank_ledger import current_stock_l

from tests.conftest import create_authenticated_group


def _fuel_post(
    vehicle_id: int,
    *,
    fill_source: str = "external",
    fuel_tank_id: str = "",
    fuel_amount_l: str = "50",
    usage_reading: str = "100",
    entry_date: str | None = None,
) -> dict:
    if entry_date is None:
        entry_date = date.today().isoformat()
    data = {
        "vehicle_id": str(vehicle_id),
        "fuel_amount_l": fuel_amount_l,
        "usage_reading": usage_reading,
        "entry_date": entry_date,
        "fill_source": fill_source,
    }
    if fuel_tank_id:
        data["fuel_tank_id"] = fuel_tank_id
    return data


class TestFillSourceService:
    def test_fuel_entry_default_fill_source_external(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        entry = create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=40.0,
                usage_reading=10.0,
                entry_date=date.today(),
            ),
        )
        assert entry.fill_source == FillSource.external.value
        assert entry.fuel_tank_id is None

    def test_fuel_entry_farm_fill_requires_tank_id(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, fuel_type="diesel")
        create_test_storage_tank(group_id=group.id, name="D1", fuel_type="diesel")
        create_test_storage_tank(group_id=group.id, name="D2", fuel_type="diesel")
        with pytest.raises(ValueError, match="Tank"):
            create_fuel_entry(
                db,
                user.id,
                group.id,
                vehicle,
                FuelEntryCreate(
                    vehicle_id=vehicle.id,
                    fuel_amount_l=40.0,
                    usage_reading=10.0,
                    entry_date=date.today(),
                    fill_source=FillSource.farm,
                ),
            )

    def test_fuel_entry_farm_fill_wrong_fuel_type_rejected(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(
            group_id=group.id, fuel_type="petrol", vtype="car"
        )
        diesel_tank = create_test_storage_tank(group_id=group.id, fuel_type="diesel")
        with pytest.raises(ValueError, match="Kraftstoff"):
            create_fuel_entry(
                db,
                user.id,
                group.id,
                vehicle,
                FuelEntryCreate(
                    vehicle_id=vehicle.id,
                    fuel_amount_l=30.0,
                    usage_reading=1000.0,
                    entry_date=date.today(),
                    fill_source=FillSource.farm,
                    fuel_tank_id=diesel_tank.id,
                ),
            )

    def test_fuel_entry_farm_fill_creates_vehicle_withdrawal_ledger(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=500.0)
        entry = create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=25.0,
                usage_reading=10.0,
                entry_date=date.today(),
                fill_source=FillSource.farm,
                fuel_tank_id=tank.id,
            ),
        )
        ledger = db.query(TankLedgerEntry).one()
        assert ledger.movement_type == "vehicle_withdrawal"
        assert ledger.fuel_entry_id == entry.id
        assert ledger.amount_l == pytest.approx(-25.0)

    def test_fuel_entry_external_fill_no_ledger_row(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        create_test_storage_tank(group_id=group.id)
        create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=25.0,
                usage_reading=10.0,
                entry_date=date.today(),
                fill_source=FillSource.external,
            ),
        )
        assert db.query(TankLedgerEntry).count() == 0

    def test_fuel_entry_farm_fill_deducts_correct_tank_stock(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=200.0)
        create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=30.0,
                usage_reading=10.0,
                entry_date=date.today(),
                fill_source=FillSource.farm,
                fuel_tank_id=tank.id,
            ),
        )
        assert current_stock_l(db, tank) == pytest.approx(170.0)

    def test_fuel_entry_update_liters_updates_ledger_amount(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=100.0)
        entry = create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=20.0,
            usage_reading=5.0,
        )
        entry.fill_source = FillSource.farm.value
        entry.fuel_tank_id = tank.id
        db.commit()
        apply_fuel_entry_update(
            db,
            entry,
            FuelEntryUpdate(fuel_amount_l=35.0),
            vehicle=vehicle,
            user_id=user.id,
            group_id=group.id,
        )
        ledger = db.query(TankLedgerEntry).one()
        assert ledger.amount_l == pytest.approx(-35.0)
        assert current_stock_l(db, tank) == pytest.approx(65.0)

    def test_fuel_entry_change_farm_to_external_removes_ledger(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=100.0)
        entry = create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=20.0,
                usage_reading=5.0,
                entry_date=date.today(),
                fill_source=FillSource.farm,
                fuel_tank_id=tank.id,
            ),
        )
        apply_fuel_entry_update(
            db,
            entry,
            FuelEntryUpdate(fill_source=FillSource.external, fuel_tank_id=None),
            vehicle=vehicle,
            user_id=user.id,
            group_id=group.id,
        )
        assert (
            db.query(TankLedgerEntry)
            .filter(
                TankLedgerEntry.deleted_at == None  # noqa: E711
            )
            .count()
            == 0
        )
        assert current_stock_l(db, tank) == pytest.approx(100.0)
        db.refresh(entry)
        assert entry.fill_source == FillSource.external.value

    def test_fuel_entry_farm_external_farm_reuses_ledger_row(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=100.0)
        entry = create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=20.0,
                usage_reading=1.0,
                entry_date=date.today(),
                fill_source=FillSource.farm,
                fuel_tank_id=tank.id,
            ),
        )
        original_ledger_id = db.query(TankLedgerEntry).one().id
        apply_fuel_entry_update(
            db,
            entry,
            FuelEntryUpdate(fill_source=FillSource.external, fuel_tank_id=None),
            vehicle=vehicle,
            user_id=user.id,
            group_id=group.id,
        )
        assert (
            db.query(TankLedgerEntry)
            .filter(
                TankLedgerEntry.deleted_at == None  # noqa: E711
            )
            .count()
            == 0
        )
        apply_fuel_entry_update(
            db,
            entry,
            FuelEntryUpdate(fill_source=FillSource.farm, fuel_tank_id=tank.id),
            vehicle=vehicle,
            user_id=user.id,
            group_id=group.id,
        )
        ledger_rows = db.query(TankLedgerEntry).all()
        assert len(ledger_rows) == 1
        assert ledger_rows[0].id == original_ledger_id
        assert ledger_rows[0].deleted_at is None
        assert current_stock_l(db, tank) == pytest.approx(80.0)

    def test_fuel_entry_change_external_to_farm_creates_ledger(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=80.0)
        entry = create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=15.0,
            usage_reading=5.0,
        )
        apply_fuel_entry_update(
            db,
            entry,
            FuelEntryUpdate(fill_source=FillSource.farm, fuel_tank_id=tank.id),
            vehicle=vehicle,
            user_id=user.id,
            group_id=group.id,
        )
        ledger = db.query(TankLedgerEntry).one()
        assert ledger.amount_l == pytest.approx(-15.0)
        assert current_stock_l(db, tank) == pytest.approx(65.0)

    def test_fuel_entry_delete_soft_deletes_linked_ledger(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=50.0)
        entry = create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=10.0,
                usage_reading=1.0,
                entry_date=date.today(),
                fill_source=FillSource.farm,
                fuel_tank_id=tank.id,
            ),
        )
        soft_delete_fuel_entry(db, entry)
        assert (
            db.query(TankLedgerEntry)
            .filter(
                TankLedgerEntry.deleted_at == None  # noqa: E711
            )
            .count()
            == 0
        )
        assert current_stock_l(db, tank) == pytest.approx(50.0)

    def test_existing_entries_without_fill_source_treated_as_external(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        entry = create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
        )
        assert entry.fill_source == FillSource.external.value


class TestFillSourceRoutes:
    async def test_fuel_entry_multiple_petrol_tanks_must_choose_tank(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        car = create_test_vehicle(group_id=group.id, vtype="car", fuel_type="petrol")
        create_test_storage_tank(group_id=group.id, name="B1", fuel_type="petrol")
        create_test_storage_tank(group_id=group.id, name="B2", fuel_type="petrol")
        response = await client.post(
            "/fuel/new",
            data=_fuel_post(car.id, fill_source="farm"),
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text
        assert db.query(FuelEntry).count() == 0

    async def test_fuel_entry_single_matching_tank_sync_logic_present(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        """One matching tank is auto-selected client-side via syncTankSelection."""
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        tank = create_test_storage_tank(
            group_id=group.id, name="Benzin Hof", fuel_type="petrol"
        )
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        assert 'id="storage-tanks-data"' in response.text
        assert f'"id": {tank.id}' in response.text or f'"id":{tank.id}' in response.text
        assert "Benzin Hof" in response.text
        assert "ids.length === 1" in response.text
        assert "syncTankSelection" in response.text
        assert f"selectedTankId: '{tank.id}'" not in response.text

    async def test_fuel_entry_farm_tank_other_group_rejected(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        g_a = create_test_group(
            name="Farm A", invite_code="FARM-AAAAA", created_by=user.id
        )
        g_b = create_test_group(
            name="Farm B", invite_code="FARM-BBBBB", created_by=user.id
        )
        create_test_user_group(user.id, g_a.id, role="admin")
        vehicle = create_test_vehicle(group_id=g_a.id, fuel_type="diesel")
        tank_b = create_test_storage_tank(group_id=g_b.id, fuel_type="diesel")
        auth_cookie(client, user.id, g_a.id)
        response = await client.post(
            "/fuel/new",
            data=_fuel_post(
                vehicle.id,
                fill_source="farm",
                fuel_tank_id=str(tank_b.id),
            ),
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text
        assert db.query(FuelEntry).count() == 0

    async def test_fuel_entry_form_tank_dropdown_lists_only_matching_fuel_type(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        create_test_vehicle(
            group_id=group.id, name="Auto", vtype="car", fuel_type="petrol"
        )
        create_test_storage_tank(
            group_id=group.id, name="Diesel Tank", fuel_type="diesel"
        )
        create_test_storage_tank(
            group_id=group.id, name="Petrol Tank", fuel_type="petrol"
        )
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        assert "Petrol Tank" in response.text
        assert "Diesel Tank" in response.text
        assert 'id="storage-tanks-data"' in response.text
        assert 'x-show="tankVisible' not in response.text
        assert "x-show='tankVisible" not in response.text

    async def test_fuel_entry_form_does_not_autoselect_single_mismatched_fuel_tank(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        create_test_vehicle(
            group_id=group.id, name="Auto", vtype="car", fuel_type="petrol"
        )
        tank = create_test_storage_tank(
            group_id=group.id, name="Only Diesel", fuel_type="diesel"
        )
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        assert "Only Diesel" in response.text
        assert f'"id": {tank.id}' in response.text or f'"id":{tank.id}' in response.text
        assert f"selectedTankId: '{tank.id}'" not in response.text
        assert (
            re.search(rf'<option[^>]*value="{tank.id}"[^>]*selected', response.text)
            is None
        )

    async def test_fuel_entry_farm_fill_via_post(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=100.0)
        response = await client.post(
            "/fuel/new",
            data=_fuel_post(
                vehicle.id,
                fill_source="farm",
                fuel_tank_id=str(tank.id),
                fuel_amount_l="25",
            ),
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert current_stock_l(db, tank) == pytest.approx(75.0)
