"""Tests for Phase 10: User Profile Management."""

from app.auth import verify_password
from app.models import User


class TestProfilePage:
    async def test_get_profile_page_returns_200(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.get("/profile")
        assert response.status_code == 200

    async def test_get_profile_shows_current_name_and_email(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user(email="farmer@example.com", name="Pat Farmer")
        auth_cookie(client, user.id)
        response = await client.get("/profile")
        assert response.status_code == 200
        assert "Pat Farmer" in response.text
        assert "farmer@example.com" in response.text

    async def test_update_profile_requires_auth(self, client):
        response = await client.get("/profile", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"


class TestProfileUpdate:
    async def test_update_profile_name(self, client, create_test_user, auth_cookie, db):
        user = create_test_user(name="Old Name")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile",
            data={"name": "New Name", "email": user.email},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/profile"
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert u.name == "New Name"
        assert u.email == user.email

    async def test_update_profile_email(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(email="old@example.com")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile",
            data={"name": user.name, "email": "new@example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert u.email == "new@example.com"

    async def test_update_profile_duplicate_email_fails(
        self, client, create_test_user, auth_cookie, db
    ):
        create_test_user(email="taken@example.com", name="Other")
        user = create_test_user(email="mine@example.com", name="Me", password="pw")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile",
            data={"name": user.name, "email": "taken@example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "bereits verwendet" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert u.email == "mine@example.com"


class TestProfilePassword:
    async def test_change_password_valid(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(password="oldpass12")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile/change-password",
            data={
                "current_password": "oldpass12",
                "new_password": "newpass12x",
                "new_password_confirm": "newpass12x",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/profile"
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert verify_password("newpass12x", u.password_hash)

    async def test_change_password_wrong_current_password_fails(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(password="correct12")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile/change-password",
            data={
                "current_password": "wrongpass12",
                "new_password": "newpass12x",
                "new_password_confirm": "newpass12x",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "aktuelles passwort" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert verify_password("correct12", u.password_hash)

    async def test_change_password_mismatch_confirmation_fails(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(password="correct12")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile/change-password",
            data={
                "current_password": "correct12",
                "new_password": "newpass12x",
                "new_password_confirm": "newpass12y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "stimmen nicht" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert verify_password("correct12", u.password_hash)

    async def test_change_password_short_password_fails(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(password="correct12")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile/change-password",
            data={
                "current_password": "correct12",
                "new_password": "short",
                "new_password_confirm": "short",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "mindestens" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert verify_password("correct12", u.password_hash)

    async def test_change_password_requires_auth(self, client):
        response = await client.post(
            "/profile/change-password",
            data={
                "current_password": "x",
                "new_password": "newpass12x",
                "new_password_confirm": "newpass12x",
            },
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"


class TestProfileDataExport:
    async def test_export_personal_data_returns_json(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user(email="export@example.com", name="Export User")
        group = create_test_group(created_by=user.id, name="Export Farm")
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/profile/export/data.json")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/json")
        data = response.json()
        assert data["profile"]["email"] == "export@example.com"
        assert data["profile"]["name"] == "Export User"
        assert len(data["group_memberships"]) == 1
        assert data["group_memberships"][0]["group_name"] == "Export Farm"

    def test_export_personal_data_includes_fuel_and_tank_ledger_fields(
        self,
        db,
        create_test_user,
        create_test_group,
        create_test_vehicle,
        create_test_storage_tank,
    ):
        from datetime import date

        from app.enums import FillSource
        from app.schemas import FuelEntryCreate, TankExternalWithdrawalCreate
        from app.services.fuel_entries import create_fuel_entry
        from app.services.profile import export_user_personal_data
        from app.services.tank_ledger import post_external_withdrawal

        user = create_test_user()
        group = create_test_group(created_by=user.id)
        vehicle = create_test_vehicle(group_id=group.id, vtype="tractor")
        tank = create_test_storage_tank(
            group_id=group.id, name="Hof Diesel", opening_balance_l=200.0
        )
        create_fuel_entry(
            db,
            user.id,
            group.id,
            vehicle,
            FuelEntryCreate(
                vehicle_id=vehicle.id,
                fuel_amount_l=30.0,
                usage_reading=100.0,
                entry_date=date(2025, 5, 1),
                fill_source=FillSource.farm,
                fuel_tank_id=tank.id,
                adblue_amount_l=5.0,
            ),
        )
        post_external_withdrawal(
            db,
            user.id,
            group.id,
            tank,
            TankExternalWithdrawalCreate(
                amount_l=12.0,
                entry_date=date(2025, 5, 2),
                recipient_name="Nachbar",
            ),
        )

        data = export_user_personal_data(db, user)

        assert len(data["fuel_entries"]) == 1
        fuel = data["fuel_entries"][0]
        assert fuel["fill_source"] == "farm"
        assert fuel["fuel_tank_name"] == "Hof Diesel"
        assert fuel["adblue_amount_l"] == 5.0

        assert len(data["tank_ledger_entries"]) == 2
        types = {row["movement_type"] for row in data["tank_ledger_entries"]}
        assert types == {"vehicle_withdrawal", "external_withdrawal"}
        external = next(
            r
            for r in data["tank_ledger_entries"]
            if r["movement_type"] == "external_withdrawal"
        )
        assert external["recipient_name"] == "Nachbar"
        assert external["tank_name"] == "Hof Diesel"

    async def test_export_requires_auth(self, client):
        response = await client.get("/profile/export/data.json", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"


class TestProfileDeleteAccount:
    async def test_delete_account_success(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(email="delete@example.com", password="deletepass1")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile/delete-account",
            data={"password": "deletepass1"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert u.deleted_at is not None
        assert u.email == f"deleted-{user.id}@deleted.tankly.invalid"
        assert u.name == "Deleted user"

    async def test_delete_account_wrong_password_fails(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(email="keep@example.com", password="correctpass1")
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile/delete-account",
            data={"password": "wrongpass12"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "aktuelles passwort" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert u.deleted_at is None

    async def test_delete_account_blocked_as_sole_admin(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        user = create_test_user(email="admin@example.com", password="adminpass12")
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)
        response = await client.post(
            "/profile/delete-account",
            data={"password": "adminpass12"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "alleinige admin" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert u.deleted_at is None

    async def test_deleted_user_cannot_login(
        self, client, create_test_user, auth_cookie, db
    ):
        user = create_test_user(email="gone@example.com", password="gonepass12")
        auth_cookie(client, user.id)
        await client.post(
            "/profile/delete-account",
            data={"password": "gonepass12"},
            follow_redirects=False,
        )
        response = await client.post(
            "/login",
            data={"email": "gone@example.com", "password": "gonepass12"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "ungültig" in response.text.lower()

    async def test_delete_allowed_when_co_admin_exists(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
        db,
    ):
        admin_a = create_test_user(email="admin-a@example.com", password="adminpass12")
        admin_b = create_test_user(email="admin-b@example.com")
        group = create_test_group(created_by=admin_a.id)
        create_test_user_group(admin_a.id, group.id, role="admin")
        create_test_user_group(admin_b.id, group.id, role="admin")
        auth_cookie(client, admin_a.id, group.id)

        response = await client.post(
            "/profile/delete-account",
            data={"password": "adminpass12"},
            follow_redirects=False,
        )
        assert response.status_code == 303
        db.expire_all()
        u = db.query(User).filter(User.id == admin_a.id).first()
        assert u.deleted_at is not None


class TestProfileErrorContext:
    async def test_profile_validation_error_still_shows_sessions(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile",
            data={"name": user.name, "email": "not-an-email"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "Aktive Sitzungen" in response.text
