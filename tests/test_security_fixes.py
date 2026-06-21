"""Tests for security hardening fixes."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from app.auth import create_session_cookie
from app.config import Settings, settings
from app.models import MaintenanceLog
from app.services.export import fuel_entries_csv, vehicles_csv
from app.services.reminders import (
    list_due_email_reminders,
    release_reminder_claim,
    try_claim_reminder_send,
)
from app.services.sessions import create_user_session
from pydantic import ValidationError


class TestActiveGroupMembership:
    async def test_removed_member_cannot_read_fuel_list(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        auth_cookie,
        db,
    ):
        admin = create_test_user(email="admin@farm.com")
        group = create_test_group(created_by=admin.id)
        create_test_user_group(admin.id, group.id, role="admin")
        member = create_test_user(email="member@farm.com")
        create_test_user_group(member.id, group.id, role="contributor")
        create_test_vehicle(group_id=group.id)

        auth_cookie(client, member.id, group.id)
        assert (await client.get("/fuel")).status_code == 200

        from app.models import UserGroup

        db.query(UserGroup).filter(
            UserGroup.user_id == member.id,
            UserGroup.group_id == group.id,
        ).delete()
        db.commit()

        response = await client.get("/fuel", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"

    async def test_removed_member_cannot_export_csv(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        admin = create_test_user(email="admin@farm.com")
        group = create_test_group(created_by=admin.id)
        create_test_user_group(admin.id, group.id, role="admin")
        member = create_test_user(email="exporter@farm.com")
        create_test_user_group(member.id, group.id, role="reader")

        auth_cookie(client, member.id, group.id)
        from app.models import UserGroup

        db.query(UserGroup).filter(
            UserGroup.user_id == member.id, UserGroup.group_id == group.id
        ).delete()
        db.commit()

        response = await client.get("/export/fuel-entries.csv", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"

    async def test_removed_member_does_not_see_stale_group_in_nav(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        admin = create_test_user(email="admin@farm.com")
        group = create_test_group(created_by=admin.id, name="Removed Farm")
        create_test_user_group(admin.id, group.id, role="admin")
        member = create_test_user(email="member@farm.com")
        create_test_user_group(member.id, group.id, role="contributor")

        auth_cookie(client, member.id, group.id)
        assert "Removed Farm" in (await client.get("/profile")).text

        from app.models import UserGroup

        db.query(UserGroup).filter(
            UserGroup.user_id == member.id,
            UserGroup.group_id == group.id,
        ).delete()
        db.commit()

        response = await client.get("/profile")
        assert response.status_code == 200
        assert "Removed Farm" not in response.text

    async def test_removed_member_cookie_clears_stale_active_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        admin = create_test_user(email="admin@farm.com")
        group = create_test_group(created_by=admin.id, name="Stale Cookie Farm")
        create_test_user_group(admin.id, group.id, role="admin")
        member = create_test_user(email="member@farm.com")
        create_test_user_group(member.id, group.id, role="contributor")

        auth_cookie(client, member.id, group.id)

        from app.models import UserGroup

        db.query(UserGroup).filter(
            UserGroup.user_id == member.id,
            UserGroup.group_id == group.id,
        ).delete()
        db.commit()

        response = await client.get("/groups")
        assert response.status_code == 200

        from app.auth import decode_session_cookie

        cookie_value = response.cookies.get(settings.SESSION_COOKIE_NAME)
        assert cookie_value is not None
        data = decode_session_cookie(cookie_value)
        assert data is not None
        assert data.get("active_group_id") is None


class TestSessionUserBinding:
    async def test_cookie_user_id_must_match_session_user(
        self, client, create_test_user, db
    ):
        user_a = create_test_user(email="a@farm.com")
        user_b = create_test_user(email="b@farm.com")
        session_id = create_user_session(db, user_a.id)
        db.commit()

        mismatched_cookie = create_session_cookie(
            user_b.id, None, session_id=session_id
        )
        client.cookies.set(settings.SESSION_COOKIE_NAME, mismatched_cookie)

        response = await client.get("/profile", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"


class TestReminderEmailReliability:
    def test_usage_only_reminder_included_in_email_queue(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        vehicle = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            usage_reading=950.0,
            notes=None,
        )
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            service_date=date.today() - timedelta(days=10),
            description="Belt replacement",
            next_service_usage=1000.0,
        )
        db.add(log)
        db.commit()

        due = list_due_email_reminders(db)
        assert len(due) == 1
        assert "due at 1000.0" in due[0][2]

    async def test_cron_releases_claim_when_email_fails(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
    ):
        from app.config import settings

        admin = create_test_user(email="admin@farm.com")
        group = create_test_group(created_by=admin.id)
        create_test_user_group(admin.id, group.id, role="admin")
        vehicle = create_test_vehicle(group_id=group.id)
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=admin.id,
            service_date=date.today() - timedelta(days=3),
            description="Failed send",
            next_service_date=date.today(),
        )
        db.add(log)
        db.commit()

        with (
            patch.object(settings, "CRON_SECRET", "cron-secret"),
            patch.object(settings, "MAIL_USERNAME", "user"),
            patch.object(settings, "MAIL_PASSWORD", "pass"),
            patch.object(settings, "MAIL_SERVER", "smtp.example.com"),
            patch(
                "app.routes.cron.send_service_reminder_email",
                new_callable=AsyncMock,
                side_effect=RuntimeError("smtp down"),
            ),
        ):
            response = await client.post(
                "/cron/service-reminders",
                headers={"Authorization": "Bearer cron-secret"},
            )

        assert response.status_code == 200
        db.refresh(log)
        assert log.reminder_sent_at is None

    async def test_cron_keeps_claim_when_some_emails_succeed(
        self,
        client,
        db,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
    ):
        from app.config import settings

        admin_a = create_test_user(email="admin-a@farm.com")
        admin_b = create_test_user(email="admin-b@farm.com")
        group = create_test_group(created_by=admin_a.id)
        create_test_user_group(admin_a.id, group.id, role="admin")
        create_test_user_group(admin_b.id, group.id, role="admin")
        vehicle = create_test_vehicle(group_id=group.id)
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=admin_a.id,
            service_date=date.today() - timedelta(days=3),
            description="Partial send",
            next_service_date=date.today(),
        )
        db.add(log)
        db.commit()

        async def _send(email, **kwargs):
            if email == "admin-b@farm.com":
                raise RuntimeError("smtp down")

        with (
            patch.object(settings, "CRON_SECRET", "cron-secret"),
            patch.object(settings, "MAIL_USERNAME", "user"),
            patch.object(settings, "MAIL_PASSWORD", "pass"),
            patch.object(settings, "MAIL_SERVER", "smtp.example.com"),
            patch(
                "app.routes.cron.send_service_reminder_email",
                new_callable=AsyncMock,
                side_effect=_send,
            ),
        ):
            response = await client.post(
                "/cron/service-reminders",
                headers={"Authorization": "Bearer cron-secret"},
            )

        assert response.status_code == 200
        db.refresh(log)
        assert log.reminder_sent_at is not None

    def test_try_claim_prevents_double_processing(
        self, db, create_test_user, create_test_group, create_test_vehicle
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        log = MaintenanceLog(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            service_date=date.today(),
            description="Claim test",
            next_service_date=date.today(),
        )
        db.add(log)
        db.commit()

        assert try_claim_reminder_send(db, log.id) is not None
        assert try_claim_reminder_send(db, log.id) is None

        release_reminder_claim(db, log.id)
        assert try_claim_reminder_send(db, log.id) is not None


class TestCsvInjection:
    def test_vehicle_name_formula_prefix_is_escaped(
        self, db, create_test_group, create_test_vehicle
    ):
        group = create_test_group()
        create_test_vehicle(group_id=group.id, name="=CMD()")
        content = vehicles_csv(db, group.id)
        assert "'=CMD()" in content

    def test_fuel_entry_notes_formula_prefix_is_escaped(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_fuel_entry,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
            notes="=1+1",
        )
        content = fuel_entries_csv(db, group.id)
        assert "'=1+1" in content


class TestProductionSecrets:
    def test_default_secret_key_rejected_in_production(self):
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            Settings(
                DATABASE_URL="sqlite:///./test.db",
                ENV="production",
                SECRET_KEY="supersecretkey",
                CRON_SECRET="cron-secret",
                REDIS_URL="redis://localhost:6379/0",
                _env_file=None,
            )

    def test_custom_secret_key_allowed_in_production(self):
        settings = Settings(
            DATABASE_URL="sqlite:///./test.db",
            ENV="production",
            SECRET_KEY="a-unique-production-secret",
            CRON_SECRET="cron-secret",
            REDIS_URL="redis://localhost:6379/0",
            _env_file=None,
        )
        assert settings.is_production is True

    def test_production_requires_cron_secret(self):
        with pytest.raises(ValidationError, match="CRON_SECRET"):
            Settings(
                DATABASE_URL="sqlite:///./test.db",
                ENV="production",
                SECRET_KEY="a-unique-production-secret",
                REDIS_URL="redis://localhost:6379/0",
                CRON_SECRET="",
                _env_file=None,
            )
