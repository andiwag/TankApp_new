"""Tests for mobile layout optimizations (phases 1–6)."""

from pathlib import Path

from tests.test_platform_admin import _login_as, _set_platform_admins


class TestPhase1Guardrails:
    def test_app_css_has_overflow_x_clip(self):
        css = Path("app/static/app.css").read_text(encoding="utf-8")
        assert "overflow-x: clip" in css

    async def test_base_template_links_app_css_v10(self, client):
        response = await client.get("/login")
        assert response.status_code == 200
        assert "/static/app.css?v=12" in response.text

    async def test_main_content_wrapper_has_min_w_0(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert 'class="w-full min-w-0' in response.text or "min-w-0 flex-1 flex-col" in response.text


class TestPhase2ShellLayout:
    async def test_bottom_nav_uses_stacked_labels(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "flex-1 flex-col items-center" in response.text
        assert "Dashboard" in response.text
        assert "t-mobile-bottom-nav" in response.text

    async def test_page_header_uses_responsive_heading_classes(self, client, auth_group):
        auth_group()
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "text-2xl" in response.text
        assert "sm:text-[28px]" in response.text


class TestPhase3ListAndDashboard:
    async def test_fuel_list_item_stacks_actions_on_mobile(
        self, client, auth_group, create_test_vehicle, create_test_fuel_entry
    ):
        user, group = auth_group(role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Mobile Tractor")
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            fuel_amount_l=50.0,
            usage_reading=1000.0,
        )
        response = await client.get("/fuel")
        assert response.status_code == 200
        assert "sm:grid sm:grid-cols-[auto_minmax(0,1fr)_auto]" in response.text

    async def test_maintenance_list_item_stacks_actions_on_mobile(
        self, client, auth_group, create_test_vehicle, db, set_group_tier
    ):
        from datetime import date

        from app.models import MaintenanceLog

        user, group = auth_group(role="admin")
        set_group_tier(group.id, "pro")
        vehicle = create_test_vehicle(group_id=group.id, name="Service Tractor")
        db.add(
            MaintenanceLog(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                description="Oil change",
                service_date=date.today(),
            )
        )
        db.commit()
        response = await client.get("/maintenance")
        assert response.status_code == 200
        assert "sm:grid sm:grid-cols-[auto_minmax(0,1fr)_auto]" in response.text

    async def test_dashboard_hides_quick_actions_below_sm(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "hidden sm:flex" in response.text

    async def test_dashboard_fuel_card_has_no_unconditional_min_width(
        self, client, auth_group
    ):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert ' flex min-w-[280px]' not in response.text
        assert "xl:min-w-[280px]" in response.text

    async def test_kpi_card_uses_responsive_value_typography(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "text-2xl" in response.text
        assert "sm:text-[32px]" in response.text

    async def test_vehicle_card_stacks_actions_on_mobile(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group(role="admin")
        create_test_vehicle(group_id=group.id, name="Stack Test Tractor")
        response = await client.get("/vehicles")
        assert response.status_code == 200
        assert "max-sm:flex-col" in response.text


class TestPhase4Tables:
    def test_app_css_has_compact_table_cells(self):
        css = Path("app/static/app.css").read_text(encoding="utf-8")
        assert "max-width: 639px" in css
        assert ".t-data-table th" in css

    async def test_summary_tables_use_contained_scroll_wrapper(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group()
        create_test_vehicle(group_id=group.id, name="Summary Tractor")
        response = await client.get("/summary")
        assert response.status_code == 200
        assert "-mx-4 sm:mx-0" in response.text
        assert "t-table-scroll" in response.text
        assert "min-w-[480px]" in response.text

    async def test_platform_farms_table_has_overflow_container(
        self, client, create_test_user, create_test_group, auth_cookie, monkeypatch
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        create_test_group(name="Mobile Farm", invite_code="FARM-MOB01")
        _login_as(client, create_test_user, auth_cookie)
        response = await client.get("/platform/farms?status=all")
        assert response.status_code == 200
        assert "t-table-scroll" in response.text
        assert "min-w-[480px]" in response.text


class TestPhase5FormsSettings:
    async def test_group_settings_member_form_stacks_on_mobile(
        self, client, auth_group, create_test_user, create_test_user_group
    ):
        _, group = auth_group(role="admin")
        member = create_test_user(email="member@farm.test", name="Member User")
        create_test_user_group(member.id, group.id, role="contributor")
        response = await client.get("/settings/group")
        assert response.status_code == 200
        assert "flex w-full flex-col gap-2 sm:flex-row" in response.text

    def test_invite_code_has_overflow_protection(self):
        css = Path("app/static/app.css").read_text(encoding="utf-8")
        assert "max-width: 399px" in css
        assert ".t-invite-code" in css

    async def test_fuel_entry_form_footer_clears_bottom_nav(self, client, auth_group):
        auth_group(role="admin")
        response = await client.get("/fuel/new")
        assert response.status_code == 200
        assert "sticky bottom-24" in response.text
        assert "-mx-1" not in response.text

    async def test_group_card_stacks_actions_on_mobile(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group_a = create_test_group(name="Farm A", invite_code="FARM-MOB02", created_by=user.id)
        group_b = create_test_group(name="Farm B", invite_code="FARM-MOB03", created_by=user.id)
        create_test_user_group(user.id, group_a.id, role="admin")
        create_test_user_group(user.id, group_b.id, role="admin")
        auth_cookie(client, user.id, group_a.id)
        response = await client.get("/groups")
        assert response.status_code == 200
        assert "max-sm:flex-col" in response.text


class TestPhase6Marketing:
    async def test_landing_viewport_meta_present(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert 'name="viewport"' in response.text
        assert "width=device-width" in response.text

    async def test_landing_pricing_grid_stacks_on_small_screens(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert 'id="pricing"' in response.text
        assert "grid-cols-1 gap-6 sm:grid-cols-2 md:grid-cols-3" in response.text
