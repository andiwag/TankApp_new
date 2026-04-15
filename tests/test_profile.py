"""Tests for Phase 10: User Profile Management."""

import pytest

from app.auth import verify_password
from app.models import User


class TestProfilePage:
    @pytest.mark.asyncio
    async def test_get_profile_page_returns_200(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.get("/profile")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_profile_shows_current_name_and_email(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user(
            email="farmer@example.com", name="Pat Farmer"
        )
        auth_cookie(client, user.id)
        response = await client.get("/profile")
        assert response.status_code == 200
        assert "Pat Farmer" in response.text
        assert "farmer@example.com" in response.text

    @pytest.mark.asyncio
    async def test_update_profile_requires_auth(self, client):
        response = await client.get("/profile", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/login"


class TestProfileUpdate:
    @pytest.mark.asyncio
    async def test_update_profile_name(
        self, client, create_test_user, auth_cookie, db
    ):
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

    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
    async def test_update_profile_duplicate_email_fails(
        self, client, create_test_user, auth_cookie, db
    ):
        create_test_user(email="taken@example.com", name="Other")
        user = create_test_user(
            email="mine@example.com", name="Me", password="pw"
        )
        auth_cookie(client, user.id)
        response = await client.post(
            "/profile",
            data={"name": user.name, "email": "taken@example.com"},
            follow_redirects=False,
        )
        assert response.status_code == 200
        assert "already in use" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert u.email == "mine@example.com"


class TestProfilePassword:
    @pytest.mark.asyncio
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

    @pytest.mark.asyncio
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
        assert "current password is incorrect" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert verify_password("correct12", u.password_hash)

    @pytest.mark.asyncio
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
        assert "do not match" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert verify_password("correct12", u.password_hash)

    @pytest.mark.asyncio
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
        assert "at least" in response.text.lower()
        db.expire_all()
        u = db.query(User).filter(User.id == user.id).first()
        assert verify_password("correct12", u.password_hash)

    @pytest.mark.asyncio
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
