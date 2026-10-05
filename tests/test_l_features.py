"""Tests for L effort features: maintenance logs, service reminders, session revocation."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from app.auth import SESSION_ABSOLUTE_MAX_AGE, SESSION_IDLE_MAX_AGE
from app.config import settings
from app.models import AuditLog, MaintenanceLog, UserSession
from app.services.reminders import list_due_email_reminders, list_group_reminders
from app.services.sessions import (
    create_user_session,
    get_active_session,
    revoke_session,
    slide_session_expiry,
)
from app.time_utils import UTC, utc_now

from tests.conftest import create_authenticated_group


class TestMaintenanceLogs:
    async def test_list_maintenance_requires_auth(self, client):
        response = await client.get("/maintenance", follow_redirects=False)
        assert response.status_code == 303

    async def test_create_maintenance_log(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
        set_group_tier,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        set_group_tier(group.id, "pro")
        vehicle = create_test_vehicle(group_id=group.id)
        response = await client.post(
            "/maintenance/new",
            data={
                "vehicle_id": str(vehicle.id),
                "service_date": date.today().isoformat(),
                "description": "Oil change",
                "usage_reading": "1500",
                "cost_eur": "120",
                "next_service_date": (date.today() + timedelta(days=90)).isoformat(),
                "next_service_usage": "2000",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        log = db.query(MaintenanceLog).one()
        assert log.description == "Oil change"
        assert log.cost_eur == pytest.approx(120.0)
        audit = db.query(AuditLog).filter(AuditLog.action == "maintenance.create").one()
        assert audit.entity_id == log.id

    async def test_reader_cannot_create_maintenance(
        self, client, auth_group, set_group_tier
    ):
        _, group = auth_group(role="reader")
        set_group_tier(group.id, "pro")
        response = await client.get("/maintenance/new", follow_redirects=False)
        assert response.status_code == 403

    async def test_edit_maintenance_rejects_invalid_next_service_date(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
        set_group_tier,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
            role="contributor",
        )
        set_group_tier(group.id, "pro")
        vehicle = create_test_vehicle(group_id=group.id)
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            service_date=date.today(),
            description="Service",
        )
        db.add(log)
        db.commit()

        response = await client.post(
            f"/maintenance/{log.id}/edit",
            data={
                "service_date": date.today().isoformat(),
                "description": "Service",
                "next_service_date": (date.today() - timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == 200
        assert (
            "Nächstes Servicedatum muss am oder nach dem Servicedatum liegen"
            in response.text
        )


class TestServiceReminders:
    def test_list_group_reminders_overdue_by_date(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, name="Tractor")
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            service_date=date.today() - timedelta(days=30),
            description="Annual service",
            next_service_date=date.today() - timedelta(days=1),
        )
        db.add(log)
        db.commit()

        reminders = list_group_reminders(db, group.id)
        assert len(reminders) == 1
        assert reminders[0]["status"] == "overdue"
        assert reminders[0]["vehicle_name"] == "Tractor"

    def test_list_due_email_reminders_skips_already_sent(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            service_date=date.today() - timedelta(days=10),
            description="Filter change",
            next_service_date=date.today(),
            reminder_sent_at=utc_now(),
        )
        db.add(log)
        db.commit()
        assert list_due_email_reminders(db) == []

    async def test_cron_requires_secret(self, client):
        response = await client.post("/cron/service-reminders")
        assert response.status_code == 403

    async def test_cron_sends_reminders_with_bearer_token(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
    ):
        admin = create_test_user(email="admin@farm.com")
        group = create_test_group(created_by=admin.id)
        create_test_user_group(admin.id, group.id, role="admin")
        vehicle = create_test_vehicle(group_id=group.id, name="Combine")
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=admin.id,
            service_date=date.today() - timedelta(days=5),
            description="Hydraulic check",
            next_service_date=date.today() + timedelta(days=2),
        )
        db.add(log)
        db.commit()

        with (
            patch.object(settings, "CRON_SECRET", "test-cron-secret"),
            patch.object(settings, "MAIL_USERNAME", "user"),
            patch.object(settings, "MAIL_PASSWORD", "pass"),
            patch.object(settings, "MAIL_SERVER", "smtp.example.com"),
            patch(
                "app.routes.cron.send_service_reminder_email",
                new_callable=AsyncMock,
            ) as mock_send,
        ):
            response = await client.post(
                "/cron/service-reminders",
                headers={"Authorization": "Bearer test-cron-secret"},
            )

        assert response.status_code == 200
        assert response.json()["sent"] == 1
        mock_send.assert_awaited_once()
        db.refresh(log)
        assert log.reminder_sent_at is not None


def _as_utc(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class TestSessionLifetime:
    def test_new_session_idles_out_after_thirty_days(self, db, create_test_user):
        user = create_test_user()
        before = utc_now()
        session_id = create_user_session(db, user.id)
        db.commit()

        session = db.query(UserSession).filter(UserSession.id == session_id).one()
        lifetime = _as_utc(session.expires_at) - before
        assert timedelta(seconds=SESSION_IDLE_MAX_AGE - 5) <= lifetime
        assert lifetime <= timedelta(seconds=SESSION_IDLE_MAX_AGE + 5)

    def test_session_past_absolute_lifetime_is_inactive(self, db, create_test_user):
        user = create_test_user()
        session_id = create_user_session(db, user.id)
        session = db.query(UserSession).filter(UserSession.id == session_id).one()
        session.created_at = utc_now() - timedelta(
            seconds=SESSION_ABSOLUTE_MAX_AGE + 60
        )
        session.expires_at = utc_now() + timedelta(days=1)
        db.commit()

        assert get_active_session(db, session_id) is None

    def test_slide_extends_idle_deadline_up_to_absolute_cap(self, db, create_test_user):
        user = create_test_user()
        session_id = create_user_session(db, user.id)
        session = db.query(UserSession).filter(UserSession.id == session_id).one()
        created_at = utc_now() - timedelta(days=80)
        session.created_at = created_at
        session.expires_at = utc_now() + timedelta(days=1)
        db.commit()

        assert slide_session_expiry(db, session) is True
        db.refresh(session)
        assert _as_utc(session.expires_at) - _as_utc(session.created_at) == timedelta(
            seconds=SESSION_ABSOLUTE_MAX_AGE
        )

    def test_slide_leaves_a_fresh_deadline_unchanged(self, db, create_test_user):
        user = create_test_user()
        session_id = create_user_session(db, user.id)
        db.commit()
        session = db.query(UserSession).filter(UserSession.id == session_id).one()
        original_expiry = session.expires_at

        assert slide_session_expiry(db, session) is False
        db.refresh(session)
        assert session.expires_at == original_expiry

    async def test_authenticated_request_slides_idle_deadline(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        session = db.query(UserSession).one()
        session.created_at = utc_now() - timedelta(days=10)
        session.expires_at = utc_now() + timedelta(days=1)
        db.commit()

        response = await client.get("/profile")
        assert response.status_code == 200

        db.expire_all()
        session = db.query(UserSession).one()
        remaining = _as_utc(session.expires_at) - utc_now()
        assert remaining > timedelta(days=29)


class TestSessionRevocation:
    def test_revoked_session_is_invalid(self, db, create_test_user):
        user = create_test_user()
        from app.services.sessions import create_user_session

        session_id = create_user_session(db, user.id)
        db.commit()
        assert get_active_session(db, session_id) is not None
        revoke_session(db, session_id)
        db.commit()
        assert get_active_session(db, session_id) is None

    async def test_logout_revokes_session(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        session_count = db.query(UserSession).count()
        assert session_count == 1

        response = await client.post("/logout", follow_redirects=False)
        assert response.status_code == 303

        session = db.query(UserSession).one()
        assert session.revoked_at is not None

    async def test_revoked_session_cannot_access_protected_route(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        session = db.query(UserSession).one()
        revoke_session(db, session.id)
        db.commit()

        response = await client.get("/profile", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"

    async def test_profile_lists_active_sessions(self, client, auth_group):
        auth_group()
        response = await client.get("/profile")
        assert response.status_code == 200
        assert "Aktive Sitzungen" in response.text
        assert "dieses gerät" in response.text.lower()

    async def test_dashboard_shows_service_reminders(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        vehicle = create_test_vehicle(group_id=group.id, name="Due Tractor")
        db.add(
            MaintenanceLog(
                vehicle_id=vehicle.id,
                group_id=group.id,
                user_id=user.id,
                service_date=date.today() - timedelta(days=30),
                description="Greasing",
                next_service_date=date.today() + timedelta(days=5),
            )
        )
        db.commit()

        response = await client.get("/dashboard")
        assert response.status_code == 200
        assert "Wartungen" in response.text
        assert "Due Tractor" in response.text
