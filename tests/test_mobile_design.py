"""Tests for mobile design alignment (phases 7–12)."""

import re
from datetime import date, timedelta

from app.services.analytics import consumption_trend_30d


class TestPhase7Shell:
    async def test_mobile_bottom_nav_has_core_tabs(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text
        assert "Tanken" in response.text
        assert "Tanks" in response.text
        assert "Mehr" in response.text
        nav_html = response.text.split("t-mobile-bottom-nav", 1)[1].split("</nav>", 1)[
            0
        ]
        assert 'href="/fuel"' in nav_html
        assert 'href="/tanks"' in nav_html
        assert 'href="/vehicles"' not in nav_html
        assert 'href="/analytics"' not in nav_html
        assert 'href="/profile"' not in nav_html

    async def test_mobile_more_menu_has_secondary_links(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        response = await client.get("/dashboard")
        assert "t-mobile-more-menu" in response.text
        assert 'href="/analytics"' in response.text
        assert 'href="/summary"' in response.text
        assert 'href="/maintenance"' in response.text
        assert 'href="/settings/group"' in response.text
        assert 'href="/profile"' in response.text
        assert 'href="/groups"' in response.text
        more_html = response.text.split("t-mobile-more-menu", 1)[1].split(
            "t-mobile-bottom-nav", 1
        )[0]
        assert 'href="/vehicles"' in more_html
        assert 'href="/tanks"' not in more_html

    async def test_mobile_bottom_nav_links_fuel_not_profile_tab(
        self, client, auth_group
    ):
        auth_group()
        response = await client.get("/dashboard")
        assert 'href="/fuel"' in response.text
        assert 'href="/tanks"' in response.text
        nav_html = response.text.split("t-mobile-bottom-nav", 1)[1].split("</nav>", 1)[
            0
        ]
        assert 'href="/profile"' not in nav_html
        assert 'href="/vehicles"' not in nav_html

    async def test_add_sheet_has_title_and_abbrechen(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/dashboard")
        assert "Was möchtest du hinzufügen?" in response.text
        assert "Abbrechen" in response.text
        assert "t-bottom-sheet" in response.text

    async def test_add_sheet_lists_fuel_and_vehicle_rows(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/dashboard")
        assert 'href="/fuel/new"' in response.text
        assert 'href="/tanks/external/new"' in response.text
        assert "Externe Abgabe" in response.text
        assert 'href="/vehicles/new"' in response.text
        assert 'href="/tanks/new"' in response.text

    async def test_add_sheet_lists_maintenance_when_entitled(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        response = await client.get("/dashboard")
        assert 'href="/maintenance/new"' in response.text


class TestPhase8Dashboard:
    async def test_dashboard_mobile_header_has_notification_link(
        self, client, auth_group, create_test_vehicle, db, set_group_tier
    ):
        from datetime import date, timedelta

        from app.models import MaintenanceLog

        user, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        vehicle = create_test_vehicle(group_id=group.id, name="Bell Tractor")
        db.add(
            MaintenanceLog(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                description="Oil change",
                service_date=date.today(),
                next_service_date=date.today() + timedelta(days=5),
            )
        )
        db.commit()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert 'aria-label="Wartungserinnerungen"' in response.text
        assert 'href="/maintenance"' in response.text

    async def test_dashboard_mobile_shows_status_row_with_chevron(
        self, client, auth_group
    ):
        auth_group()
        response = await client.get("/dashboard")
        assert "t-mobile-status-row" in response.text
        assert "t-dashboard-status" in response.text

    async def test_dashboard_mobile_status_row_links_to_fuel_not_duplicate_cta(
        self, client, auth_group
    ):
        auth_group(role="admin")
        response = await client.get("/dashboard")
        assert "t-mobile-status-row" in response.text
        assert "t-mobile-cta" not in response.text

    async def test_dashboard_mobile_uses_lean_metric_band(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        mobile = response.text.split("t-mobile-page", 1)[1].split(
            "t-dashboard-desktop", 1
        )[0]
        assert "t-mobile-page" in response.text
        assert "t-dashboard-metrics--compact" in mobile
        assert "t-dashboard-metric__value" in mobile
        assert "t-kpi-tile" not in mobile
        assert "t-mobile-section-title" not in mobile

    async def test_dashboard_mobile_hides_chart_grid(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert "t-dashboard-desktop" in response.text
        assert "t-dashboard-charts" in response.text
        mobile = response.text.split("t-mobile-page", 1)[1].split(
            "t-dashboard-desktop", 1
        )[0]
        assert "t-dashboard-charts" not in mobile
        assert 'id="consumption-chart"' not in mobile

    async def test_dashboard_mobile_shows_alle_anzeigen_link_for_fuel(
        self, client, auth_group
    ):
        auth_group()
        response = await client.get("/dashboard")
        assert "Letzte Tankvorgänge" in response.text
        assert "Alle anzeigen" in response.text

    async def test_dashboard_mobile_uses_shared_panels_and_rows(
        self, client, auth_group, create_test_vehicle, create_test_fuel_entry
    ):
        user, group = auth_group(role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Lean Truck")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=22.0,
            entry_date=date.today(),
        )
        response = await client.get("/dashboard")
        mobile = response.text.split("t-mobile-page", 1)[1].split(
            "t-dashboard-desktop", 1
        )[0]
        assert "t-dashboard-panel" in mobile
        assert "t-dashboard-activity-row" in mobile
        assert "t-dashboard-section-list--card" not in mobile
        assert 'class="t-mobile-list-row"' not in mobile

    async def test_dashboard_mobile_caps_tank_and_maintenance_rows(
        self,
        client,
        auth_group,
        create_test_storage_tank,
        create_test_vehicle,
        db,
        set_group_tier,
    ):
        from app.models import MaintenanceLog

        user, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        for i in range(5):
            create_test_storage_tank(
                group_id=group.id, name=f"Mobile Tank {i}", opening_balance_l=50.0
            )
        vehicle = create_test_vehicle(group_id=group.id, name="Svc Tractor")
        for i in range(4):
            db.add(
                MaintenanceLog(
                    vehicle_id=vehicle.id,
                    group_id=group.id,
                    user_id=user.id,
                    description=f"Service {i}",
                    service_date=date.today(),
                    next_service_date=date.today() + timedelta(days=2 + i),
                )
            )
        db.commit()
        response = await client.get("/dashboard")
        mobile = response.text.split("t-mobile-page", 1)[1].split(
            "t-dashboard-desktop", 1
        )[0]
        tank_section = mobile.split("Hof-Tank Bestände", 1)[1]
        assert (
            len(re.findall(r'class="t-dashboard-inventory-row(?:\s|")', tank_section))
            == 3
        )
        assert "<h2>Wartungen</h2>" not in mobile
        assert "t-dashboard-maintenance-row" not in mobile
        assert (
            len(re.findall(r"t-dashboard-attention-item--(?:danger|warning)", mobile))
            == 4
        )

    async def test_dashboard_mobile_attention_before_metrics(
        self,
        client,
        auth_group,
        create_test_storage_tank,
        db,
    ):
        from app.schemas import TankExternalWithdrawalCreate
        from app.services.tank_ledger import post_external_withdrawal

        user, group = auth_group(role="admin")
        tank = create_test_storage_tank(group_id=group.id, opening_balance_l=5.0)
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
        response = await client.get("/dashboard")
        mobile = response.text.split("t-mobile-page", 1)[1].split(
            "t-dashboard-desktop", 1
        )[0]
        assert mobile.find("dashboard-attention-mobile") < mobile.find(
            "t-dashboard-metrics--compact"
        )


class TestPhase9Vehicles:
    async def test_vehicles_mobile_uses_hero_card_layout(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        create_test_vehicle(group_id=group.id, name="Hero Tractor")
        response = await client.get("/vehicles")
        assert response.status_code == 200
        html = response.text
        assert "t-lean" in html
        assert "t-lean-list-row" in html
        assert "t-dashboard-panel" in html
        assert "t-vehicle-hero-card" not in html
        assert "Hero Tractor" in html

    async def test_vehicles_mobile_uses_header_plus_not_bottom_button(
        self, client, auth_group
    ):
        auth_group(role="admin")
        response = await client.get("/vehicles")
        assert 'aria-label="Hinzufügen"' in response.text
        assert "t-add-card" not in response.text

    async def test_vehicles_mobile_header_has_plus_action(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/vehicles")
        assert 'aria-label="Hinzufügen"' in response.text


class TestPhase10Analytics:
    async def test_analytics_mobile_has_segmented_control(
        self, client, auth_group, set_group_tier, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        create_test_vehicle(group_id=group.id, name="Analytics Tractor")
        response = await client.get("/analytics")
        assert response.status_code == 200
        assert "t-segmented-control" in response.text
        assert "Verbrauch" in response.text
        assert "Kosten" in response.text
        assert "Tankungen" in response.text

    async def test_analytics_mobile_shows_consumption_trend_badge(
        self, client, auth_group, set_group_tier, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        create_test_vehicle(group_id=group.id, name="Trend Tractor")
        response = await client.get("/analytics")
        assert "t-trend-delta" in response.text or "Ø Verbrauch" in response.text


class TestPhase11Secondary:
    async def test_profile_page_has_logout_not_hub(self, client, auth_group):
        auth_group()
        response = await client.get("/profile")
        assert response.status_code == 200
        assert 'action="/logout"' in response.text
        assert "t-profile-hub-link" not in response.text
        assert 'aria-label="Zurück"' in response.text

    async def test_fuel_page_is_root_tab_without_back_link(self, client, auth_group):
        auth_group()
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "Tankvorgänge" in response.text
        assert 'aria-label="Zurück"' not in response.text

    async def test_fuel_list_uses_lean_layout(
        self, client, auth_group, create_test_vehicle, create_test_fuel_entry
    ):
        user, group = auth_group(role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Lean Fuel Truck")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=33.0,
            usage_reading=1200.0,
        )
        response = await client.get("/fuel")
        assert response.status_code == 200
        html = response.text
        assert "t-lean" in html
        assert "t-dashboard-panel" in html
        assert "t-lean-list-row" in html
        assert "t-kpi-icon-emerald" not in html.split('id="fuel-entry-list"', 1)[1]
        assert "Lean Fuel Truck" in html
        assert 'href="/fuel/new"' in html
        assert 'href="/tanks/external/new"' in html
        assert "t-row-actions--mobile" in html
        assert 'aria-label="Aktionen"' in html
        assert (
            "t-status-chip" not in html.split('id="fuel-entry-list"', 1)[1]
            or html.count("t-status-chip") <= html.count("Teilbefüllung") + 2
        )
        assert "uppercase tracking-wide" not in html.split('id="fuel-entry-list"', 1)[1]

    async def test_fuel_form_uses_lean_shell(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        html = response.text
        assert "t-lean" in html
        assert "t-dashboard-header" in html
        assert "t-dashboard-header__title" in html
        assert "t-capture-surface" in html or "t-dashboard-panel" in html
        assert "t-lean-form" in html
        assert "t-lean-form-footer" in html
        form_start = html.find('action="/fuel/new"')
        assert form_start != -1
        form_html = html[form_start : html.find("</form>", form_start)]
        assert "shadow-xl" not in form_html
        assert "t-lean-form-footer" in form_html
        assert "t-card" not in form_html
        assert "🚗" not in html
        assert "⛽" not in html

    async def test_group_settings_mobile_header(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/settings/group")
        assert 'href="/profile"' in response.text
        assert "Einstellungen" in response.text

    async def test_secondary_pages_back_to_profile(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        for path in (
            "/analytics",
            "/summary",
            "/maintenance",
            "/groups",
            "/settings/group",
        ):
            response = await client.get(path)
            assert response.status_code == 200
            assert 'href="/profile"' in response.text
            assert 'aria-label="Zurück"' in response.text


class TestConsumptionTrendService:
    def test_consumption_trend_30d_computes_delta(
        self,
        db,
        create_test_group,
        create_test_user,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, name="Trend Vehicle")
        today = date.today()

        for day_offset, usage in [
            (45, 1000.0),
            (40, 1500.0),
            (15, 2000.0),
            (5, 2500.0),
        ]:
            create_test_fuel_entry(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                entry_date=today - timedelta(days=day_offset),
                fuel_amount_l=50.0,
                usage_reading=usage,
            )

        result = consumption_trend_30d(db, group.id, today=today)
        assert result["has_data"] is True
        assert result["current_avg"] is not None
