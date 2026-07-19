"""Tests for Phase 7: Dashboard."""

import re
from datetime import date

import pytest
from app.models import FuelEntry, Vehicle
from app.time_utils import utc_now

from tests.helpers import parse_display_number


def _stat(html: str, stat_id: str) -> int:
    m = re.search(rf'id="{re.escape(stat_id)}">([\d.,]+)</', html)
    assert m is not None, f"missing {stat_id} in response"
    return int(parse_display_number(m.group(1)))


def _stat_float(html: str, stat_id: str) -> float:
    m = re.search(rf'id="{re.escape(stat_id)}">([\d.,]+)</', html)
    assert m is not None, f"missing {stat_id} in response"
    return parse_display_number(m.group(1))


class TestDashboardAuth:
    async def test_dashboard_requires_auth(self, client):
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"

    async def test_dashboard_requires_active_group(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id, active_group_id=None)
        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"


class TestDashboardStats:
    async def test_dashboard_shows_vehicle_count(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        create_test_vehicle(group_id=group.id, name="T1")
        create_test_vehicle(group_id=group.id, name="T2")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat(response.text, "stat-vehicles") == 2

    async def test_dashboard_shows_entry_count(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=40.0
        )
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=30.0
        )
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat(response.text, "stat-entries") == 2

    async def test_dashboard_shows_total_liters(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=25.5
        )
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=10.0
        )
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat_float(response.text, "stat-liters") == pytest.approx(35.5)

    async def test_dashboard_shows_recent_entries(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id, name="Alpha Tractor")
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=20.0,
            entry_date=date(2024, 1, 1),
        )
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=45.0,
            entry_date=date(2024, 6, 1),
        )
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        assert "Alpha Tractor" in html
        assert "45" in html and "20" in html
        assert "recent-fuel-entries" in html

    async def test_dashboard_promotes_fuel_entry_for_contributors(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="contributor")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")

        assert response.status_code == 200
        assert 'href="/fuel/new"' in response.text
        assert "Tankvorgang erfassen" in response.text

    async def test_dashboard_scoped_to_active_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
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
        create_test_user_group(user.id, g_b.id, role="admin")

        va = create_test_vehicle(group_id=g_a.id, name="A1")
        create_test_vehicle(group_id=g_a.id, name="A2")
        vb = create_test_vehicle(group_id=g_b.id, name="B1")

        create_test_fuel_entry(
            vehicle_id=va.id, group_id=g_a.id, user_id=user.id, fuel_amount_l=10.0
        )
        create_test_fuel_entry(
            vehicle_id=vb.id, group_id=g_b.id, user_id=user.id, fuel_amount_l=99.0
        )

        auth_cookie(client, user.id, g_a.id)
        r_a = await client.get("/dashboard")
        assert r_a.status_code == 200
        assert _stat(r_a.text, "stat-vehicles") == 2
        assert _stat(r_a.text, "stat-entries") == 1
        assert _stat_float(r_a.text, "stat-liters") == pytest.approx(10.0)

        await client.post(f"/groups/switch/{g_b.id}", follow_redirects=False)
        r_b = await client.get("/dashboard")
        assert r_b.status_code == 200
        assert _stat(r_b.text, "stat-vehicles") == 1
        assert _stat(r_b.text, "stat-entries") == 1
        assert _stat_float(r_b.text, "stat-liters") == pytest.approx(99.0)

    async def test_dashboard_excludes_soft_deleted_vehicles(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        create_test_vehicle(group_id=group.id, name="Active")
        v_del = create_test_vehicle(group_id=group.id, name="Gone")

        db.query(Vehicle).filter(Vehicle.id == v_del.id).update(
            {"deleted_at": utc_now()}
        )
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat(response.text, "stat-vehicles") == 1

    async def test_dashboard_excludes_soft_deleted_entries(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
        db,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        v = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=10.0
        )
        e_del = create_test_fuel_entry(
            vehicle_id=v.id, group_id=group.id, user_id=user.id, fuel_amount_l=50.0
        )
        db.query(FuelEntry).filter(FuelEntry.id == e_del.id).update(
            {"deleted_at": utc_now()}
        )
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat(response.text, "stat-entries") == 1
        assert _stat_float(response.text, "stat-liters") == pytest.approx(10.0)

    async def test_dashboard_empty_group_shows_zeros(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat(response.text, "stat-vehicles") == 0
        assert _stat(response.text, "stat-entries") == 0
        assert _stat_float(response.text, "stat-liters") == pytest.approx(0.0)


class TestDashboardTankStock:
    async def test_dashboard_shows_tank_stock_when_tanks_exist(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        create_test_storage_tank(
            group_id=group.id, name="Diesel Hof", opening_balance_l=250.0
        )
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")

        assert response.status_code == 200
        html = response.text
        assert 'id="tank-stock"' in html
        assert "Diesel Hof" in html
        assert "250" in html

    async def test_dashboard_negative_stock_shows_warning(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_storage_tank,
        auth_cookie,
        db,
    ):
        from app.schemas import TankExternalWithdrawalCreate
        from app.services.tank_ledger import post_external_withdrawal

        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=10.0)
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
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")

        assert response.status_code == 200
        assert "negative-stock-warning" in response.text

    async def test_dashboard_no_tanks_hides_stock_section(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")

        assert response.status_code == 200
        assert 'id="tank-stock"' not in response.text
