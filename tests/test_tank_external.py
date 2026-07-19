"""Tests for Phase 27: external withdrawals at farm tanks."""

from datetime import date

import pytest
from app.models import FuelEntry, TankLedgerEntry
from app.schemas import TankExternalWithdrawalCreate
from app.services.analytics import get_analytics_context
from app.services.dashboard import get_dashboard_context
from app.services.summary import get_summary_context
from app.services.tank_ledger import (
    current_stock_l,
    post_external_withdrawal,
    soft_delete_ledger_entry,
)
from pydantic import ValidationError

from tests.conftest import create_authenticated_group


class TestExternalWithdrawalService:
    def test_external_withdrawal_creates_ledger_not_fuel_entry(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id)
        post_external_withdrawal(
            db,
            user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=30.0,
                entry_date=date.today(),
                recipient_name="Kreuzmayr",
            ),
        )
        assert db.query(TankLedgerEntry).count() == 1
        assert db.query(FuelEntry).count() == 0
        entry = db.query(TankLedgerEntry).one()
        assert entry.movement_type == "external_withdrawal"
        assert entry.recipient_name == "Kreuzmayr"
        assert entry.amount_l == pytest.approx(-30.0)

    def test_external_withdrawal_requires_recipient_name(self):
        with pytest.raises(ValidationError):
            TankExternalWithdrawalCreate(
                amount_l=10.0,
                entry_date=date.today(),
                recipient_name="",
            )

    def test_external_withdrawal_reduces_tank_stock(
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
                amount_l=25.0,
                entry_date=date.today(),
                recipient_name="Nachbar",
            ),
        )
        assert current_stock_l(db, tank) == pytest.approx(75.0)

    def test_external_withdrawal_soft_delete_restores_stock(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_storage_tank,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=50.0)
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
        soft_delete_ledger_entry(db, ledger)
        assert current_stock_l(db, tank) == pytest.approx(50.0)


class TestExternalWithdrawalStatsIsolation:
    def test_external_withdrawal_excluded_from_dashboard_fuel_liters(
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
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=200.0)
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            usage_reading=100.0,
        )
        before = get_dashboard_context(db, user, group.id)
        post_external_withdrawal(
            db,
            user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=100.0,
                entry_date=date.today(),
                recipient_name="Kreuzmayr",
            ),
        )
        after = get_dashboard_context(db, user, group.id)
        assert after["total_fuel_liters"] == before["total_fuel_liters"]
        assert after["fuel_entry_count"] == before["fuel_entry_count"]

    def test_external_withdrawal_excluded_from_summary_vehicle_totals(
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
        vehicle = create_test_vehicle(group_id=group.id, name="Tractor")
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=500.0)
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=60.0,
            usage_reading=10.0,
        )
        before = get_summary_context(db, group.id, today=date.today())
        post_external_withdrawal(
            db,
            user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=200.0,
                entry_date=date.today(),
                recipient_name="Kreuzmayr",
            ),
        )
        after = get_summary_context(db, group.id, today=date.today())
        before_row = next(r for r in before["vehicle_rows"] if r["name"] == "Tractor")
        after_row = next(r for r in after["vehicle_rows"] if r["name"] == "Tractor")
        assert after_row["total_liters"] == before_row["total_liters"]

    def test_external_withdrawal_excluded_from_analytics(
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
        vehicle = create_test_vehicle(group_id=group.id, name="Combine")
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=300.0)
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=45.0,
            usage_reading=500.0,
            entry_date=date.today(),
        )
        before = get_analytics_context(db, group.id, today=date.today())
        post_external_withdrawal(
            db,
            user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=80.0,
                entry_date=date.today(),
                recipient_name="Kreuzmayr",
            ),
        )
        after = get_analytics_context(db, group.id, today=date.today())
        assert after["vehicle_chart"] == before["vehicle_chart"]


class TestExternalWithdrawalRoutes:
    async def test_external_withdrawal_via_post(
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
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=120.0)
        response = await client.post(
            f"/tanks/{tank.id}/external/new",
            data={
                "amount_l": "20",
                "entry_date": date.today().isoformat(),
                "recipient_name": "Kreuzmayr",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert current_stock_l(db, tank) == pytest.approx(100.0)
        entry = db.query(TankLedgerEntry).one()
        assert entry.recipient_name == "Kreuzmayr"

    async def test_external_withdrawal_other_group_tank_404(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
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
        tank_b = create_test_storage_tank(group_id=g_b.id)
        auth_cookie(client, user.id, g_a.id)
        response = await client.get(f"/tanks/{tank_b.id}/external/new")
        assert response.status_code == 404

    async def test_external_withdrawal_requires_recipient_name_via_post(
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
        tank = create_test_storage_tank(group_id=group.id)
        response = await client.post(
            f"/tanks/{tank.id}/external/new",
            data={
                "amount_l": "10",
                "entry_date": date.today().isoformat(),
                "recipient_name": "",
            },
        )
        assert response.status_code == 200
        assert "bg-red-50" in response.text
        assert db.query(TankLedgerEntry).count() == 0
