"""Regression tests for redesigned UI affordances and permissions."""


class TestDashboardAffordances:
    async def test_dashboard_uses_prominent_brand_logo(self, client, auth_group):
        auth_group()
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "t-brand-img--lg" in response.text

    async def test_reader_sees_csv_export_on_dashboard(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="reader")
        set_group_tier(group.id, "pro")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "/export/fuel-entries.csv" in response.text
        assert "CSV exportieren" in response.text

    async def test_free_tier_hides_csv_export_on_dashboard(
        self, client, auth_group, db
    ):
        from app.enums import SubscriptionTier

        from tests.test_billing import _ensure_subscription

        _, group = auth_group(role="reader")
        _ensure_subscription(db, group.id, tier=SubscriptionTier.free.value)
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "/export/fuel-entries.csv" not in response.text

    async def test_reader_does_not_see_create_quick_actions_on_dashboard(
        self, client, auth_group
    ):
        auth_group(role="reader")
        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert 'href="/fuel/new"' not in response.text


class TestNavigationAffordances:
    async def test_desktop_nav_includes_summary_link(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(name="Green Farm", created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/dashboard")

        assert response.status_code == 200
        assert 'href="/summary"' in response.text
        assert "Zusammenfassung" in response.text

    async def test_mobile_profile_includes_logout(self, client, auth_group):
        auth_group(role="contributor")
        response = await client.get("/profile")
        assert response.status_code == 200
        assert 'action="/logout"' in response.text


class TestReaderPermissionAffordances:
    async def test_reader_vehicle_card_has_no_quick_create_links(
        self, client, auth_group, create_test_vehicle
    ):
        _, group = auth_group(role="reader")
        create_test_vehicle(group_id=group.id, name="Reader Tractor")

        response = await client.get("/vehicles")

        assert response.status_code == 200
        assert "Reader Tractor" in response.text
        assert 'href="/fuel/new"' not in response.text
        assert 'href="/maintenance/new"' not in response.text

    async def test_analytics_empty_state_hides_vehicle_create_for_reader(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="reader")
        set_group_tier(group.id, "pro")
        response = await client.get("/analytics")
        assert response.status_code == 200
        assert 'href="/vehicles/new"' not in response.text


class TestPlatformUiAffordances:
    async def test_platform_farms_has_search_and_status_filters(
        self, client, create_test_user, auth_cookie, monkeypatch
    ):
        from tests.test_platform_admin import _login_as, _set_platform_admins

        _set_platform_admins(monkeypatch, "ops@tankly.test")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get("/platform/farms?status=all")

        assert response.status_code == 200
        assert 'action="/platform/farms"' in response.text
        assert 'name="q"' in response.text
        assert "status=active" in response.text
        assert "status=deleted" in response.text

    async def test_platform_farm_detail_has_support_view_form(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        from tests.test_platform_admin import _login_as, _set_platform_admins

        _set_platform_admins(monkeypatch, "ops@tankly.test")
        admin = create_test_user(email="admin@farm.com", name="Admin Farmer")
        group = create_test_group(name="Detail Farm", invite_code="FARM-DTL01")
        create_test_user_group(admin.id, group.id, role="admin")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get(f"/platform/farms/{group.id}")

        assert response.status_code == 200
        assert "FARM-DTL01" in response.text
        assert f'action="/platform/farms/{group.id}/enter"' in response.text
        assert 'name="csrf_token"' in response.text
        assert 'data-member-role="admin"' in response.text


class TestMarketingUiAffordances:
    async def test_landing_has_features_and_pricing_anchors(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert 'id="features"' in response.text
        assert 'id="pricing"' in response.text
        assert "/register" in response.text
        assert "/login" in response.text
