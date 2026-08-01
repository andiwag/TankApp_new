"""Tests for Phase 7: Dashboard."""

import re
from datetime import date, timedelta

import pytest
from app.models import FuelEntry, Vehicle
from app.services.dashboard import get_dashboard_context
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

    async def test_dashboard_shows_month_entry_count(
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
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            entry_date=date.today(),
        )
        create_test_fuel_entry(
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=30.0,
            entry_date=date.today() - timedelta(days=40),
        )
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat(response.text, "stat-month-entries") == 1

    async def test_dashboard_shows_month_cost(
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
            vehicle_id=v.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=25.5,
            entry_date=date.today(),
        )
        entry = db.query(FuelEntry).one()
        entry.total_cost_eur = 56.4
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat_float(response.text, "stat-month-cost") == pytest.approx(56.4)

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
        assert "Tankvorgang" in response.text

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
        assert _stat(r_a.text, "stat-month-entries") == 1

        await client.post(f"/groups/switch/{g_b.id}", follow_redirects=False)
        r_b = await client.get("/dashboard")
        assert r_b.status_code == 200
        assert _stat(r_b.text, "stat-vehicles") == 1
        assert _stat(r_b.text, "stat-month-entries") == 1

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
        assert _stat(response.text, "stat-month-entries") == 1

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
        assert _stat(response.text, "stat-month-entries") == 0
        assert _stat_float(response.text, "stat-month-cost") == pytest.approx(0.0)


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


class TestDashboardContext:
    def test_dashboard_context_includes_greeting_and_charts(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user(name="Andreas Wagner")
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Audi A4")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=40.0,
            entry_date=date.today(),
        )

        ctx = get_dashboard_context(db, user, group.id)

        assert ctx["greeting"]
        assert ctx["today_fuel_count"] == 1
        assert ctx["month_fuel_count"] == 1
        assert ctx["vehicle_count"] == 1
        assert len(ctx["cost_chart"]) == 6
        assert isinstance(ctx["consumption_chart"], list)
        assert "vehicles_preview" not in ctx
        assert len(ctx["recent_entry_rows"]) == 1
        assert ctx["tank_stock_rows"] == []

    def test_dashboard_vehicle_count_excludes_deleted_without_preview(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        create_test_vehicle(group_id=group.id, name="Active")
        gone = create_test_vehicle(group_id=group.id, name="Gone")
        db.query(Vehicle).filter(Vehicle.id == gone.id).update(
            {"deleted_at": utc_now()}
        )
        db.commit()

        ctx = get_dashboard_context(db, user, group.id)

        assert ctx["vehicle_count"] == 1
        assert "vehicles_preview" not in ctx

    async def test_dashboard_shows_personalized_greeting(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user(name="Andreas Wagner")
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "Andreas" in response.text
        assert "dashboard-greeting" in response.text

    async def test_dashboard_includes_chart_canvases(
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
        create_test_vehicle(group_id=group.id)
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert 'id="consumption-chart"' in response.text
        assert 'id="cost-bar-chart"' in response.text
        assert 'id="dashboard-consumption-data"' in response.text
        assert 'id="dashboard-cost-data"' in response.text
        assert 'type="application/json"' in response.text
        assert "/static/vendor/chart.umd.min.js" in response.text
        assert "/static/dashboard.js" in response.text
        chart_pos = response.text.find("/static/vendor/chart.umd.min.js")
        dash_pos = response.text.find("/static/dashboard.js")
        assert chart_pos < dash_pos


class TestDashboardRedesignContracts:
    async def test_metric_ids_present_on_desktop_band(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        assert 'id="stat-vehicles"' in html
        assert 'id="stat-month-entries"' in html
        assert 'id="stat-month-cost"' in html
        assert 'id="stat-maintenance-due"' in html
        assert "t-dashboard-metrics" in html

    async def test_admin_sees_primary_fuel_action(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "t-dashboard-primary-action" in response.text
        assert 'href="/fuel/new"' in response.text
        assert "Tankvorgang erfassen" in response.text

    async def test_contributor_sees_primary_fuel_action(self, client, auth_group):
        auth_group(role="contributor")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "t-dashboard-primary-action" in response.text
        assert 'href="/fuel/new"' in response.text

    async def test_reader_has_no_new_links_but_keeps_export(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="reader")
        set_group_tier(group.id, "pro")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert 'href="/fuel/new"' not in response.text
        assert 'href="/vehicles/new"' not in response.text
        assert 'href="/maintenance/new"' not in response.text
        assert "t-dashboard-primary-action" not in response.text
        assert "/export/fuel-entries.csv" in response.text

    async def test_free_tier_hides_export_and_paid_dead_links(
        self, client, auth_group, db
    ):
        from app.enums import SubscriptionTier

        from tests.test_billing import _ensure_subscription

        _, group = auth_group(role="admin")
        _ensure_subscription(db, group.id, tier=SubscriptionTier.free.value)
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "/export/fuel-entries.csv" not in response.text

    async def test_no_attention_omits_attention_section(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert 'id="dashboard-attention"' not in response.text

    async def test_negative_stock_attention_is_danger_linked_to_tanks(
        self,
        client,
        auth_group,
        create_test_storage_tank,
        db,
    ):
        from app.schemas import TankExternalWithdrawalCreate
        from app.services.tank_ledger import post_external_withdrawal

        user, group = auth_group(role="admin")
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
        response = await client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        assert 'id="dashboard-attention"' in html
        assert "t-dashboard-attention-item--danger" in html
        assert "negative-stock-warning" in html
        attention = html.split('id="dashboard-attention"', 1)[1]
        assert 'href="/tanks"' in attention

    async def test_overdue_maintenance_attention_uses_danger(
        self, client, auth_group, create_test_vehicle, db, set_group_tier
    ):
        from app.models import MaintenanceLog

        user, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        vehicle = create_test_vehicle(group_id=group.id, name="Late Tractor")
        db.add(
            MaintenanceLog(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                description="Ölwechsel",
                service_date=date.today() - timedelta(days=60),
                next_service_date=date.today() - timedelta(days=3),
            )
        )
        db.commit()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        assert 'id="dashboard-attention"' in html
        assert "t-dashboard-attention-item--danger" in html
        assert "überfällig" in html

    async def test_attention_orders_negative_stock_before_overdue(
        self,
        client,
        auth_group,
        create_test_vehicle,
        create_test_storage_tank,
        db,
        set_group_tier,
    ):
        from app.models import MaintenanceLog
        from app.schemas import TankExternalWithdrawalCreate
        from app.services.tank_ledger import post_external_withdrawal

        user, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        tank = create_test_storage_tank(
            group_id=group.id, name="Neg Tank", opening_balance_l=5.0
        )
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
        vehicle = create_test_vehicle(group_id=group.id, name="Late Tractor")
        db.add(
            MaintenanceLog(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                description="Filter",
                service_date=date.today() - timedelta(days=40),
                next_service_date=date.today() - timedelta(days=1),
            )
        )
        db.commit()
        response = await client.get("/dashboard")
        html = response.text
        attention = html.split('id="dashboard-attention"', 1)[1]
        neg_pos = attention.find("Neg Tank")
        overdue_pos = attention.find("Filter")
        assert neg_pos != -1 and overdue_pos != -1
        assert neg_pos < overdue_pos

    async def test_empty_group_shows_zeros_and_empty_state(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert _stat(response.text, "stat-vehicles") == 0
        assert _stat(response.text, "stat-month-entries") == 0
        assert "Noch keine Tankvorgänge" in response.text

    async def test_action_menu_has_aria_and_permitted_actions(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        assert "t-dashboard-action-menu" in html
        assert 'aria-haspopup="menu"' in html
        assert "aria-expanded" in html
        assert "Weitere Aktionen" in html
        assert 'href="/maintenance/new"' in html
        assert 'href="/vehicles/new"' in html
        assert "/export/fuel-entries.csv" in html

    async def test_vehicle_preview_section_absent(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "vehicles_preview" not in response.text
        assert "Alle Fahrzeuge anzeigen" not in response.text

    async def test_chart_tabs_and_panels_present(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        assert 'role="tablist"' in html
        assert 'role="tab"' in html
        assert 'aria-controls="dashboard-chart-consumption"' in html
        assert 'aria-controls="dashboard-chart-cost"' in html
        assert 'id="dashboard-chart-consumption"' in html
        assert 'id="dashboard-chart-cost"' in html
        assert "Noch nicht genug Daten für Verbrauchstrend" in html

    async def test_inventory_caps_visible_rows(
        self, client, auth_group, create_test_storage_tank
    ):
        _, group = auth_group(role="admin")
        for i in range(6):
            create_test_storage_tank(
                group_id=group.id,
                name=f"Tank {i}",
                opening_balance_l=100.0 + i,
            )
        response = await client.get("/dashboard")
        assert response.status_code == 200
        html = response.text
        desktop = html.split('id="tank-stock"', 1)[1].split("</section>", 1)[0]
        assert (
            len(re.findall(r'class="t-dashboard-inventory-row(?:\s|")', desktop)) == 4
        )
        assert "weitere anzeigen" in desktop

    async def test_mobile_shows_three_recent_entries(
        self,
        client,
        auth_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user, group = auth_group(role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Fleet Truck")
        for offset in range(5):
            create_test_fuel_entry(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                fuel_amount_l=10.0 + offset,
                entry_date=date.today() - timedelta(days=offset),
            )
        response = await client.get("/dashboard")
        assert response.status_code == 200
        mobile = response.text.split("t-mobile-page", 1)[1].split(
            "t-dashboard-desktop", 1
        )[0]
        recent_section = mobile.split("Letzte Tankvorgänge", 1)[1]
        assert (
            len(re.findall(r'class="t-dashboard-activity-row(?:\s|")', recent_section))
            == 3
        )
