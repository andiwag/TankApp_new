"""Tests for Phase 22: Platform admin (Phase 1 — read-only operator dashboard)."""

from datetime import datetime

from app.auth import decode_session_cookie
from app.config import settings
from app.models import AuditLog, User

from tests.conftest import create_authenticated_group


def _set_platform_admins(monkeypatch, *emails: str) -> None:
    monkeypatch.setattr(
        "app.config.settings.PLATFORM_ADMIN_EMAILS",
        ",".join(emails),
    )


def _login_as(
    client,
    create_test_user,
    auth_cookie,
    *,
    email: str = "ops@tankly.test",
    name: str = "Platform Operator",
    active_group_id: int | None = None,
) -> User:
    user = create_test_user(email=email, name=name)
    auth_cookie(client, user.id, active_group_id)
    return user


class TestPlatformAccessControl:
    async def test_platform_routes_require_auth(self, client):
        for path in ("/platform", "/platform/farms", "/platform/users"):
            response = await client.get(path, follow_redirects=False)
            assert response.status_code == 303
            assert response.headers.get("location") == "/login"

    async def test_platform_routes_require_platform_admin_email(
        self, client, create_test_user, auth_cookie, monkeypatch
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        response = await client.get("/platform/farms")
        assert response.status_code == 200

    async def test_non_allowlisted_user_gets_403_on_platform(
        self, client, create_test_user, auth_cookie, monkeypatch
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        _login_as(client, create_test_user, auth_cookie, email="customer@farm.com")
        response = await client.get("/platform/farms")
        assert response.status_code == 403

    async def test_empty_platform_admin_emails_disables_all_platform_access(
        self, client, create_test_user, auth_cookie, monkeypatch
    ):
        _set_platform_admins(monkeypatch)
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        response = await client.get("/platform/farms")
        assert response.status_code == 403

    async def test_platform_root_redirects_to_farms(
        self, client, create_test_user, auth_cookie, monkeypatch
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        response = await client.get("/platform", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/platform/farms"


class TestPlatformFarmList:
    async def test_platform_farm_list_includes_all_groups_not_just_membership(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        admin = create_test_user(email="member@farm.com")
        visible = create_test_group(name="Member Farm", invite_code="FARM-MEM01")
        create_test_user_group(admin.id, visible.id, role="admin")
        create_test_group(name="Other Farm", invite_code="FARM-OTH01")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get("/platform/farms?status=all")
        assert response.status_code == 200
        assert "Member Farm" in response.text
        assert "Other Farm" in response.text

    async def test_platform_farm_list_shows_member_and_vehicle_counts(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        owner = create_test_user(email="owner@farm.com")
        group = create_test_group(name="Counted Farm", invite_code="FARM-CNT01")
        create_test_user_group(owner.id, group.id, role="admin")
        contributor = create_test_user(email="contrib@farm.com")
        create_test_user_group(contributor.id, group.id, role="contributor")
        create_test_vehicle(group_id=group.id, name="Tractor A")
        create_test_vehicle(group_id=group.id, name="Tractor B")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get("/platform/farms?status=all")
        assert response.status_code == 200
        assert "Counted Farm" in response.text
        assert 'data-member-count="2"' in response.text
        assert 'data-vehicle-count="2"' in response.text

    async def test_platform_farm_list_masks_invite_code(
        self,
        client,
        create_test_group,
        create_test_user,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        create_test_group(name="Secret Farm", invite_code="FARM-SECR1")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get("/platform/farms?status=all")
        assert response.status_code == 200
        assert "FARM-SECR1" not in response.text
        assert "FARM-•••••" in response.text

    async def test_platform_farm_list_includes_soft_deleted_when_filtered(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        create_test_group(name="Active Farm", invite_code="FARM-ACT01")
        deleted = create_test_group(name="Deleted Farm", invite_code="FARM-DEL01")
        deleted.deleted_at = datetime.utcnow()
        db.commit()
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        active_only = await client.get("/platform/farms")
        assert active_only.status_code == 200
        assert "Active Farm" in active_only.text
        assert "Deleted Farm" not in active_only.text

        deleted_only = await client.get("/platform/farms?status=deleted")
        assert deleted_only.status_code == 200
        assert "Deleted Farm" in deleted_only.text
        assert "Active Farm" not in deleted_only.text


class TestPlatformFarmDetail:
    async def test_platform_farm_detail_shows_members_and_roles(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        admin = create_test_user(email="admin@farm.com", name="Admin Person")
        group = create_test_group(name="Detail Farm", invite_code="FARM-DTL01")
        create_test_user_group(admin.id, group.id, role="admin")
        reader = create_test_user(email="reader@farm.com", name="Reader Person")
        create_test_user_group(reader.id, group.id, role="reader")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get(f"/platform/farms/{group.id}")
        assert response.status_code == 200
        assert "Detail Farm" in response.text
        assert "FARM-DTL01" in response.text
        assert "admin@farm.com" in response.text
        assert "reader@farm.com" in response.text
        assert 'data-member-role="admin"' in response.text
        assert 'data-member-role="reader"' in response.text

    async def test_platform_farm_detail_logs_audit_event(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        group = create_test_group(name="Audit Farm", invite_code="FARM-AUD01")
        operator = _login_as(
            client, create_test_user, auth_cookie, email="ops@tankly.test"
        )

        response = await client.get(f"/platform/farms/{group.id}")
        assert response.status_code == 200

        log = db.query(AuditLog).filter(AuditLog.action == "platform.farm.detail").one()
        assert log.group_id == group.id
        assert log.user_id == operator.id
        assert log.entity_type == "group"
        assert log.entity_id == group.id

    async def test_platform_farm_detail_not_found(
        self,
        client,
        create_test_user,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        response = await client.get("/platform/farms/99999")
        assert response.status_code == 404


class TestPlatformUsers:
    async def test_platform_user_search_by_email(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        user = create_test_user(email="findme@farm.com", name="Find Me")
        group = create_test_group(name="Search Farm", invite_code="FARM-SRC01")
        create_test_user_group(user.id, group.id, role="contributor")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get("/platform/users?q=findme@farm")
        assert response.status_code == 200
        assert "findme@farm.com" in response.text
        assert "Search Farm" in response.text

    async def test_platform_user_search_logs_audit_when_query_present(
        self,
        client,
        db,
        create_test_user,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        create_test_user(email="search@farm.com")
        operator = _login_as(
            client, create_test_user, auth_cookie, email="ops@tankly.test"
        )

        response = await client.get("/platform/users?q=search@farm")
        assert response.status_code == 200

        log = db.query(AuditLog).filter(AuditLog.action == "platform.user.search").one()
        assert log.group_id is None
        assert log.user_id == operator.id
        assert log.entity_type == "user"
        assert log.entity_id == 0

    async def test_platform_user_detail_lists_farm_memberships(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        user = create_test_user(email="member@farm.com", name="Member User")
        farm_a = create_test_group(name="Farm Alpha", invite_code="FARM-ALP01")
        farm_b = create_test_group(name="Farm Beta", invite_code="FARM-BET01")
        create_test_user_group(user.id, farm_a.id, role="admin")
        create_test_user_group(user.id, farm_b.id, role="reader")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get(f"/platform/users/{user.id}")
        assert response.status_code == 200
        assert "member@farm.com" in response.text
        assert "Farm Alpha" in response.text
        assert "Farm Beta" in response.text
        assert "password" not in response.text.lower()
        assert "hashed_pw" not in response.text

    async def test_normal_user_cannot_access_other_group_via_platform_routes(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="admin",
        )
        other = create_test_group(name="Hidden Farm", invite_code="FARM-HID01")

        response = await client.get(f"/platform/farms/{other.id}")
        assert response.status_code == 403


class TestPlatformAdminConfig:
    def test_platform_admin_emails_parsed_case_insensitive(self):
        from app.config import Settings

        s = Settings(
            DATABASE_URL="sqlite:///./test.db",
            SECRET_KEY="testkey",
            PLATFORM_ADMIN_EMAILS="  Ops@Example.com , CO@Example.com  ",
            _env_file=None,
        )
        assert s.platform_admin_emails == frozenset(
            {"ops@example.com", "co@example.com"}
        )

    def test_empty_platform_admin_emails_returns_empty_frozenset(self):
        from app.config import Settings

        s = Settings(
            DATABASE_URL="sqlite:///./test.db",
            SECRET_KEY="testkey",
            PLATFORM_ADMIN_EMAILS="  ",
            _env_file=None,
        )
        assert s.platform_admin_emails == frozenset()


class TestPlatformSupportView:
    async def test_non_operator_cannot_enter_support_view(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="admin",
        )
        target = create_test_group(name="Target Farm", invite_code="FARM-TGT01")

        response = await client.post(f"/platform/farms/{target.id}/enter")
        assert response.status_code == 403

    async def test_platform_enter_sets_platform_view_cookie(
        self,
        client,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Target Farm", invite_code="FARM-TGT02")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.post(
            f"/platform/farms/{target.id}/enter", follow_redirects=False
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/dashboard"

        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        data = decode_session_cookie(cookie)
        assert data is not None
        assert data["platform_view"] is True
        assert data["platform_view_group_id"] == target.id
        assert data["active_group_id"] == target.id

    async def test_platform_enter_allows_dashboard_without_membership(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Customer Farm", invite_code="FARM-CUS01")
        create_test_vehicle(group_id=target.id, name="Customer Tractor")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        enter = await client.post(f"/platform/farms/{target.id}/enter")
        assert enter.status_code == 303

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "Customer Farm" in response.text
        assert "Support view" in response.text

    async def test_platform_view_blocks_vehicle_create_post(
        self,
        client,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Locked Farm", invite_code="FARM-LOC01")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        await client.post(f"/platform/farms/{target.id}/enter")

        response = await client.post(
            "/vehicles/new",
            data={
                "name": "Blocked Tractor",
                "vtype": "tractor",
                "fuel_type": "diesel",
            },
        )
        assert response.status_code == 403

    async def test_platform_view_blocks_group_settings_post(
        self,
        client,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Settings Farm", invite_code="FARM-SET01")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        await client.post(f"/platform/farms/{target.id}/enter")

        response = await client.post("/settings/group/regenerate-code")
        assert response.status_code == 403

    async def test_platform_view_blocks_export_csv_get(
        self,
        client,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Export Farm", invite_code="FARM-EXP01")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        await client.post(f"/platform/farms/{target.id}/enter")

        response = await client.get("/export/vehicles.csv")
        assert response.status_code == 403

    async def test_platform_view_cannot_access_settings_audit_get(
        self,
        client,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Audit Farm", invite_code="FARM-AUD02")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        await client.post(f"/platform/farms/{target.id}/enter")

        response = await client.get("/settings/audit")
        assert response.status_code == 403

    async def test_platform_exit_clears_platform_view(
        self,
        client,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Exit Farm", invite_code="FARM-EXT01")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        await client.post(f"/platform/farms/{target.id}/enter")

        response = await client.post("/platform/exit-view", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/platform/farms"

        cookie = response.cookies[settings.SESSION_COOKIE_NAME]
        data = decode_session_cookie(cookie)
        assert data is not None
        assert "platform_view" not in data
        assert data.get("active_group_id") is None

    async def test_platform_enter_logs_audit_event(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Enter Audit Farm", invite_code="FARM-ENT01")
        operator = _login_as(
            client, create_test_user, auth_cookie, email="ops@tankly.test"
        )

        response = await client.post(f"/platform/farms/{target.id}/enter")
        assert response.status_code == 303

        log = db.query(AuditLog).filter(AuditLog.action == "platform.farm.enter").one()
        assert log.group_id == target.id
        assert log.user_id == operator.id
        assert log.entity_type == "group"
        assert log.entity_id == target.id

    async def test_platform_admin_without_view_cannot_open_arbitrary_dashboard(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Remote Farm", invite_code="FARM-REM01")
        create_test_vehicle(group_id=target.id, name="Remote Tractor")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get("/dashboard", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"

    async def test_platform_view_allows_vehicles_list_get(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        target = create_test_group(name="Browse Farm", invite_code="FARM-BRW01")
        create_test_vehicle(group_id=target.id, name="Visible Tractor")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")
        await client.post(f"/platform/farms/{target.id}/enter")

        response = await client.get("/vehicles")
        assert response.status_code == 200
        assert "Visible Tractor" in response.text

    async def test_stale_platform_view_cookie_cleared_when_demoted_but_still_member(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        monkeypatch,
    ):
        operator_email = "ops@tankly.test"
        _set_platform_admins(monkeypatch, operator_email)
        operator = create_test_user(email=operator_email)
        group = create_test_group(name="Member Farm", invite_code="FARM-MEM02")
        create_test_user_group(operator.id, group.id, role="contributor")
        auth_cookie(client, operator.id, group.id)

        await client.post(f"/platform/farms/{group.id}/enter")
        _set_platform_admins(monkeypatch)

        dashboard = await client.get("/dashboard")
        assert dashboard.status_code == 200

        cookie = dashboard.cookies[settings.SESSION_COOKIE_NAME]
        data = decode_session_cookie(cookie)
        assert data is not None
        assert "platform_view" not in data
        assert data["active_group_id"] == group.id

        create = await client.post(
            "/vehicles/new",
            data={
                "name": "Allowed Tractor",
                "vtype": "tractor",
                "fuel_type": "diesel",
            },
        )
        assert create.status_code == 303


class TestPartnerTierGrant:
    async def test_grant_partner_requires_platform_admin(
        self,
        client,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        group = create_test_group(name="Grant Farm", invite_code="FARM-PRT01")
        _login_as(client, create_test_user, auth_cookie, email="user@farm.com")

        response = await client.post(
            f"/platform/farms/{group.id}/grant-partner",
            follow_redirects=False,
        )
        assert response.status_code == 403

    async def test_grant_partner_sets_tier_and_audit(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        from app.enums import SubscriptionTier
        from app.models import GroupSubscription
        from app.services.entitlements import (
            can_add_vehicle,
            effective_tier,
            tier_has_feature,
            vehicle_limit_for_tier,
        )

        _set_platform_admins(monkeypatch, "ops@tankly.test")
        group = create_test_group(name="Partner Farm", invite_code="FARM-PRT02")
        operator = _login_as(
            client, create_test_user, auth_cookie, email="ops@tankly.test"
        )

        response = await client.post(
            f"/platform/farms/{group.id}/grant-partner",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == f"/platform/farms/{group.id}"

        db.expire_all()
        sub = (
            db.query(GroupSubscription)
            .filter(GroupSubscription.group_id == group.id)
            .one()
        )
        assert sub.tier == SubscriptionTier.partner.value
        assert sub.status == "active"
        assert sub.stripe_subscription_id is None
        assert group.subscription_tier == SubscriptionTier.partner.value
        assert effective_tier(db, group.id) == SubscriptionTier.partner.value
        assert vehicle_limit_for_tier(SubscriptionTier.partner.value) is None
        assert tier_has_feature(SubscriptionTier.partner.value, "analytics") is True
        assert can_add_vehicle(db, group.id) is True

        log = (
            db.query(AuditLog)
            .filter(AuditLog.action == "platform.billing.grant_partner")
            .one()
        )
        assert log.group_id == group.id
        assert log.user_id == operator.id

        detail = await client.get(f"/platform/farms/{group.id}")
        assert detail.status_code == 200
        assert "partner" in detail.text.lower()
        assert "revoke-partner" in detail.text

    async def test_revoke_partner_resets_to_free(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
        set_group_tier,
    ):
        from app.enums import SubscriptionTier
        from app.models import GroupSubscription
        from app.services.entitlements import effective_tier

        _set_platform_admins(monkeypatch, "ops@tankly.test")
        group = create_test_group(name="Revoke Farm", invite_code="FARM-PRT03")
        set_group_tier(group.id, SubscriptionTier.partner.value)
        operator = _login_as(
            client, create_test_user, auth_cookie, email="ops@tankly.test"
        )

        response = await client.post(
            f"/platform/farms/{group.id}/revoke-partner",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == f"/platform/farms/{group.id}"

        db.expire_all()
        sub = (
            db.query(GroupSubscription)
            .filter(GroupSubscription.group_id == group.id)
            .one()
        )
        assert sub.tier == SubscriptionTier.free.value
        assert effective_tier(db, group.id) == SubscriptionTier.free.value
        assert group.subscription_tier == SubscriptionTier.free.value

        log = (
            db.query(AuditLog)
            .filter(AuditLog.action == "platform.billing.revoke_partner")
            .one()
        )
        assert log.user_id == operator.id
        assert log.group_id == group.id

        detail = await client.get(f"/platform/farms/{group.id}")
        assert "grant-partner" in detail.text

    async def test_grant_partner_blocked_when_stripe_subscription_exists(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        from app.enums import SubscriptionTier
        from app.flash import FLASH_COOKIE_NAME
        from app.models import GroupSubscription

        _set_platform_admins(monkeypatch, "ops@tankly.test")
        group = create_test_group(name="Stripe Farm", invite_code="FARM-PRT04")
        db.add(
            GroupSubscription(
                group_id=group.id,
                tier=SubscriptionTier.pro.value,
                status="active",
                stripe_subscription_id="sub_existing",
                stripe_customer_id="cus_existing",
            )
        )
        group.subscription_tier = SubscriptionTier.pro.value
        db.commit()
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.post(
            f"/platform/farms/{group.id}/grant-partner",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == f"/platform/farms/{group.id}"
        assert FLASH_COOKIE_NAME in response.cookies

        db.expire_all()
        sub = (
            db.query(GroupSubscription)
            .filter(GroupSubscription.group_id == group.id)
            .one()
        )
        assert sub.tier == SubscriptionTier.pro.value
        assert sub.stripe_subscription_id == "sub_existing"
        assert (
            db.query(AuditLog)
            .filter(AuditLog.action == "platform.billing.grant_partner")
            .count()
            == 0
        )

    async def test_grant_partner_idempotent_when_already_partner(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
        set_group_tier,
    ):
        from app.enums import SubscriptionTier

        _set_platform_admins(monkeypatch, "ops@tankly.test")
        group = create_test_group(name="Already Partner", invite_code="FARM-PRT05")
        set_group_tier(group.id, SubscriptionTier.partner.value)
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.post(
            f"/platform/farms/{group.id}/grant-partner",
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert (
            db.query(AuditLog)
            .filter(AuditLog.action == "platform.billing.grant_partner")
            .count()
            == 0
        )

    async def test_grant_partner_missing_group_returns_404(
        self,
        client,
        create_test_user,
        auth_cookie,
        monkeypatch,
    ):
        _set_platform_admins(monkeypatch, "ops@tankly.test")
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.post(
            "/platform/farms/99999/grant-partner",
            follow_redirects=False,
        )
        assert response.status_code == 404

    async def test_farm_detail_hides_grant_when_stripe_subscription_present(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        auth_cookie,
        monkeypatch,
    ):
        from app.enums import SubscriptionTier
        from app.models import GroupSubscription

        _set_platform_admins(monkeypatch, "ops@tankly.test")
        group = create_test_group(name="Stripe Detail", invite_code="FARM-PRT06")
        db.add(
            GroupSubscription(
                group_id=group.id,
                tier=SubscriptionTier.pro.value,
                status="active",
                stripe_subscription_id="sub_detail",
            )
        )
        group.subscription_tier = SubscriptionTier.pro.value
        db.commit()
        _login_as(client, create_test_user, auth_cookie, email="ops@tankly.test")

        response = await client.get(f"/platform/farms/{group.id}")
        assert response.status_code == 200
        assert "grant-partner" not in response.text
        assert "Stripe-Abo" in response.text
