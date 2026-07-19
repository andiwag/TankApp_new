"""Tests for ledger edit/delete routes and tank delete guards."""

import csv
import io
from datetime import date

import pytest
from app.enums import FillSource
from app.models import StorageTank, TankLedgerEntry
from app.schemas import (
    FuelEntryCreate,
    TankDeliveryCreate,
    TankExternalWithdrawalCreate,
)
from app.services.export import tank_ledger_csv
from app.services.fuel_entries import create_fuel_entry
from app.services.storage_tanks import tank_has_active_farm_fuel_entries
from app.services.tank_ledger import (
    apply_ledger_entry_update,
    current_stock_l,
    get_active_ledger_entry_in_group,
    post_delivery,
    post_external_withdrawal,
)
from app.time_utils import utc_now

from tests.conftest import create_authenticated_group


class TestLedgerEditDelete:
    def test_update_delivery_changes_stock(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=0.0)
        post_delivery(
            db,
            user.id,
            group.id,
            tank,
            TankDeliveryCreate(amount_l=50.0, entry_date=date.today()),
        )
        ledger = db.query(TankLedgerEntry).one()
        apply_ledger_entry_update(
            db,
            ledger,
            TankDeliveryCreate(amount_l=80.0, entry_date=date.today()),
        )
        assert current_stock_l(db, tank) == pytest.approx(80.0)

    def test_update_external_withdrawal_changes_stock(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=100.0)
        post_external_withdrawal(
            db,
            user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=20.0,
                entry_date=date.today(),
                recipient_name="Nachbar",
            ),
        )
        ledger = db.query(TankLedgerEntry).one()
        apply_ledger_entry_update(
            db,
            ledger,
            TankExternalWithdrawalCreate(
                amount_l=35.0,
                entry_date=date.today(),
                recipient_name="Nachbar",
            ),
        )
        assert current_stock_l(db, tank) == pytest.approx(65.0)

    def test_vehicle_withdrawal_ledger_not_editable(
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
        create_fuel_entry(
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
        ledger = db.query(TankLedgerEntry).one()
        with pytest.raises(ValueError, match="Tankvorgang"):
            apply_ledger_entry_update(
                db,
                ledger,
                TankDeliveryCreate(amount_l=5.0, entry_date=date.today()),
            )

    def test_get_active_ledger_entry_scoped_to_group(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        g_a = create_test_group(name="A", invite_code="FARM-AAA02", created_by=user.id)
        g_b = create_test_group(name="B", invite_code="FARM-BBB02", created_by=user.id)
        tank = create_test_storage_tank(group_id=g_b.id)
        post_delivery(
            db,
            user.id,
            g_b.id,
            tank,
            TankDeliveryCreate(amount_l=10.0, entry_date=date.today()),
        )
        ledger = db.query(TankLedgerEntry).one()
        assert get_active_ledger_entry_in_group(db, ledger.id, g_a.id) is None
        assert get_active_ledger_entry_in_group(db, ledger.id, g_b.id) is not None

    async def test_ledger_edit_via_post(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
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
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=0.0)
        post_delivery(
            db,
            _user.id,
            group.id,
            tank,
            TankDeliveryCreate(amount_l=40.0, entry_date=date.today()),
        )
        ledger = db.query(TankLedgerEntry).one()
        response = await client.post(
            f"/tanks/ledger/{ledger.id}/edit",
            data={
                "amount_l": "75",
                "entry_date": date.today().isoformat(),
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert current_stock_l(db, tank) == pytest.approx(75.0)

    async def test_ledger_delete_requires_admin(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="contributor")
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=50.0)
        auth_cookie(client, user.id, group.id)
        post_external_withdrawal(
            db,
            user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=10.0,
                entry_date=date.today(),
                recipient_name="Gast",
            ),
        )
        ledger = db.query(TankLedgerEntry).one()
        response = await client.post(
            f"/tanks/ledger/{ledger.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_ledger_delete_restores_stock(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        _user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="admin",
        )
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=60.0)
        post_external_withdrawal(
            db,
            _user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=15.0,
                entry_date=date.today(),
                recipient_name="Gast",
            ),
        )
        ledger = db.query(TankLedgerEntry).one()
        response = await client.post(
            f"/tanks/ledger/{ledger.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert current_stock_l(db, tank) == pytest.approx(60.0)

    async def test_vehicle_withdrawal_ledger_edit_blocked_in_ui(
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
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=100.0)
        create_fuel_entry(
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
        ledger = db.query(TankLedgerEntry).one()
        auth_cookie(client, user.id, group.id)
        response = await client.get(f"/tanks/ledger/{ledger.id}/edit")
        assert response.status_code == 200
        assert "Tankvorgang bearbeiten" in response.text


class TestTankDeleteGuard:
    def test_tank_has_active_farm_fuel_entries(
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
        tank = create_test_storage_tank(group_id=group.id)
        assert tank_has_active_farm_fuel_entries(db, tank.id) is False
        create_fuel_entry(
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
        assert tank_has_active_farm_fuel_entries(db, tank.id) is True

    async def test_tank_delete_blocked_when_farm_fuel_entries_exist(
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
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        vehicle = create_test_vehicle(group_id=group.id)
        tank = create_test_storage_tank(group_id=group.id)
        create_fuel_entry(
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
        auth_cookie(client, user.id, group.id)
        response = await client.post(
            f"/tanks/{tank.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert (
            db.query(StorageTank)
            .filter(StorageTank.id == tank.id, StorageTank.deleted_at == None)  # noqa: E711
            .count()
            == 1
        )

    async def test_tank_delete_allowed_without_farm_fuel_entries(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        tank = create_test_storage_tank(group_id=group.id)
        auth_cookie(client, user.id, group.id)
        response = await client.post(
            f"/tanks/{tank.id}/delete",
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.refresh(tank)
        assert tank.deleted_at is not None


class TestTankLedgerExportDeletedTank:
    def test_export_includes_ledger_for_soft_deleted_tank(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(
            group_id=group.id, name="Removed Tank", opening_balance_l=0.0
        )
        post_delivery(
            db,
            user.id,
            group.id,
            tank,
            TankDeliveryCreate(amount_l=55.0, entry_date=date(2025, 3, 1)),
        )
        tank.deleted_at = utc_now()
        db.commit()

        rows = list(csv.reader(io.StringIO(tank_ledger_csv(db, group.id))))
        assert len(rows) == 2
        assert rows[1][1] == "Removed Tank"
        assert rows[1][3] == "55.0"
