"""Tests for mobile design alignment (phases 7–12)."""

from datetime import date, timedelta

from app.services.analytics import consumption_trend_30d


class TestPhase7Shell:
    async def test_mobile_bottom_nav_has_core_tabs(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "Dashboard" in response.text
        assert "Tanken" in response.text
        assert "Fahrzeuge" in response.text
        assert "Mehr" in response.text
        nav_html = response.text.split("t-mobile-bottom-nav", 1)[1].split("</nav>", 1)[0]
        assert 'href="/fuel"' in nav_html
        assert 'href="/analytics"' not in nav_html
        assert 'href="/profile"' not in nav_html

    async def test_mobile_more_menu_has_secondary_links(self, client, auth_group, set_group_tier):
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

    async def test_mobile_bottom_nav_links_fuel_not_profile_tab(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert 'href="/fuel"' in response.text
        assert 'href="/vehicles"' in response.text
        nav_html = response.text.split("t-mobile-bottom-nav", 1)[1].split("</nav>", 1)[0]
        assert 'href="/profile"' not in nav_html

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
        assert 'href="/vehicles/new"' in response.text

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

    async def test_dashboard_mobile_shows_status_row_with_chevron(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert "t-mobile-status-row" in response.text

    async def test_dashboard_mobile_status_row_links_to_fuel_not_duplicate_cta(
        self, client, auth_group
    ):
        auth_group(role="admin")
        response = await client.get("/dashboard")
        assert "t-mobile-status-row" in response.text
        assert "t-mobile-cta" not in response.text

    async def test_dashboard_mobile_shows_ueberblick_section(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert "Überblick" in response.text
        assert "t-mobile-page" in response.text

    async def test_dashboard_mobile_hides_chart_grid(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert "hidden lg:block space-y-5" in response.text
        assert "dashboard-grid" in response.text

    async def test_dashboard_mobile_shows_alle_anzeigen_link_for_fuel(
        self, client, auth_group
    ):
        auth_group()
        response = await client.get("/dashboard")
        assert "Letzte Tankvorgänge" in response.text
        assert "Alle anzeigen" in response.text


class TestPhase9Vehicles:
    async def test_vehicles_mobile_uses_hero_card_layout(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        create_test_vehicle(group_id=group.id, name="Hero Tractor")
        response = await client.get("/vehicles")
        assert response.status_code == 200
        assert "t-vehicle-hero-card" in response.text
        assert "Hero Tractor" in response.text

    async def test_vehicles_mobile_uses_header_plus_not_bottom_button(self, client, auth_group):
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
        assert "t-trend-chip" in response.text or "Ø Verbrauch" in response.text


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

    async def test_group_settings_mobile_header(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/settings/group")
        assert 'href="/profile"' in response.text
        assert "Einstellungen" in response.text

    async def test_secondary_pages_back_to_profile(self, client, auth_group, set_group_tier):
        _, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        for path in ("/analytics", "/summary", "/maintenance", "/groups", "/settings/group"):
            response = await client.get(path)
            assert response.status_code == 200
            assert 'href="/profile"' in response.text
            assert 'aria-label="Zurück"' in response.text


class TestConsumptionTrendService:
    def test_consumption_trend_30d_computes_delta(
        self, db, create_test_group, create_test_user, create_test_vehicle, create_test_fuel_entry
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, name="Trend Vehicle")
        today = date.today()

        for day_offset, usage in [(45, 1000.0), (40, 1500.0), (15, 2000.0), (5, 2500.0)]:
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
