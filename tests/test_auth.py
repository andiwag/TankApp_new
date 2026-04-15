"""Tests for Phase 3: Authentication (Register, Login, Logout)."""

import time
from datetime import datetime, timezone
from unittest.mock import patch

from fastapi import Depends

from app.auth import (
    create_password_reset_token,
    create_session_cookie,
    decode_password_reset_token,
    decode_session_cookie,
    hash_password,
    verify_password,
)
from app.config import settings
from app.dependencies import get_current_user, require_role
from app.main import app
from app.models import User, UserGroup


# ── Test-only routes for dependency testing ──────────────────────────────────


@app.get("/test/protected")
async def _test_protected_route(user: User = Depends(get_current_user)):
    return {"user_id": user.id, "name": user.name}


@app.get("/test/admin-only")
async def _test_admin_route(user: User = Depends(require_role("admin"))):
    return {"user_id": user.id}


@app.get("/test/contributor-min")
async def _test_contributor_route(user: User = Depends(require_role("contributor"))):
    return {"user_id": user.id}


# ── Unit tests: password hashing ─────────────────────────────────────────────


class TestPasswordHashing:
    def test_hash_password_returns_bcrypt_hash(self):
        hashed = hash_password("mysecret123")
        assert hashed.startswith("$2b$")
        assert hashed != "mysecret123"

    def test_verify_password_correct(self):
        hashed = hash_password("mysecret123")
        assert verify_password("mysecret123", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("mysecret123")
        assert verify_password("wrongpassword", hashed) is False


# ── Unit tests: session cookies ──────────────────────────────────────────────


class TestSessionCookie:
    def test_create_session_cookie_returns_string(self):
        cookie = create_session_cookie(user_id=1, active_group_id=2)
        assert isinstance(cookie, str)
        assert len(cookie) > 0

    def test_decode_session_cookie_valid(self):
        cookie = create_session_cookie(user_id=42, active_group_id=7)
        data = decode_session_cookie(cookie)
        assert data is not None
        assert data["user_id"] == 42
        assert data["active_group_id"] == 7

    def test_decode_session_cookie_tampered_returns_none(self):
        cookie = create_session_cookie(user_id=1, active_group_id=2)
        tampered = cookie[:-5] + "XXXXX"
        assert decode_session_cookie(tampered) is None

    def test_decode_session_cookie_expired_returns_none(self):
        cookie = create_session_cookie(user_id=1, active_group_id=None)
        time.sleep(1.1)
        with patch("app.auth.SESSION_MAX_AGE", 0):
            assert decode_session_cookie(cookie) is None


# ── Integration tests: login route ───────────────────────────────────────────


class TestLoginRoute:
    async def test_get_login_page_returns_200(self, client):
        response = await client.get("/login")
        assert response.status_code == 200

    async def test_login_valid_redirects_to_dashboard(self, client, create_test_user):
        create_test_user(password="secret1234")
        response = await client.post(
            "/login",
            data={"email": "test@example.com", "password": "secret1234"},
        )
        assert response.status_code == 303
        assert "/dashboard" in response.headers["location"]

    async def test_login_invalid_email_shows_error(self, client):
        response = await client.post(
            "/login",
            data={"email": "nonexistent@example.com", "password": "secret1234"},
        )
        assert response.status_code == 200
        assert "invalid" in response.text.lower()

    async def test_login_invalid_password_shows_error(self, client, create_test_user):
        create_test_user(password="secret1234")
        response = await client.post(
            "/login",
            data={"email": "test@example.com", "password": "wrongpassword"},
        )
        assert response.status_code == 200
        assert "invalid" in response.text.lower()

    async def test_login_sets_session_cookie(self, client, create_test_user):
        create_test_user(password="secret1234")
        response = await client.post(
            "/login",
            data={"email": "test@example.com", "password": "secret1234"},
        )
        assert settings.SESSION_COOKIE_NAME in response.cookies

    async def test_login_soft_deleted_user_fails(self, client, create_test_user, db):
        user = create_test_user(password="secret1234")
        user.deleted_at = datetime.now(timezone.utc)
        db.commit()

        response = await client.post(
            "/login",
            data={"email": "test@example.com", "password": "secret1234"},
        )
        assert response.status_code == 200
        assert "invalid" in response.text.lower()


# ── Integration tests: register route ────────────────────────────────────────


class TestRegisterRoute:
    async def test_get_register_page_returns_200(self, client):
        response = await client.get("/register")
        assert response.status_code == 200

    async def test_register_valid_creates_user_and_redirects(self, client, db):
        response = await client.post(
            "/register",
            data={
                "name": "Alice",
                "email": "alice@farm.com",
                "password": "secret1234",
                "password_confirm": "secret1234",
            },
        )
        assert response.status_code == 303

        user = db.query(User).filter(User.email == "alice@farm.com").first()
        assert user is not None
        assert user.name == "Alice"
        assert user.password_hash != "secret1234"

    async def test_register_duplicate_email_shows_error(
        self, client, create_test_user
    ):
        create_test_user(email="alice@farm.com")
        response = await client.post(
            "/register",
            data={
                "name": "Alice 2",
                "email": "alice@farm.com",
                "password": "secret1234",
                "password_confirm": "secret1234",
            },
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "email" in body or "already" in body

    async def test_register_password_mismatch_shows_error(self, client):
        response = await client.post(
            "/register",
            data={
                "name": "Alice",
                "email": "alice@farm.com",
                "password": "secret1234",
                "password_confirm": "different1",
            },
        )
        assert response.status_code == 200
        assert "password" in response.text.lower()

    async def test_register_sets_session_cookie(self, client):
        response = await client.post(
            "/register",
            data={
                "name": "Bob",
                "email": "bob@farm.com",
                "password": "secret1234",
                "password_confirm": "secret1234",
            },
        )
        assert settings.SESSION_COOKIE_NAME in response.cookies


# ── Integration tests: logout route ──────────────────────────────────────────


class TestLogoutRoute:
    async def test_logout_clears_cookie(self, client, create_test_user, auth_cookie):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.post("/logout")
        cookie_header = response.headers.get("set-cookie", "")
        assert settings.SESSION_COOKIE_NAME in cookie_header
        assert 'Max-Age=0' in cookie_header or '""' in cookie_header

    async def test_logout_redirects_to_login(self, client, create_test_user, auth_cookie):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.post("/logout")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


# ── Integration tests: protected routes ──────────────────────────────────────


class TestProtectedRoutes:
    async def test_protected_route_without_session_redirects_to_login(self, client):
        response = await client.get("/test/protected")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    async def test_protected_route_with_valid_session_succeeds(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.get("/test/protected")
        assert response.status_code == 200
        assert response.json()["user_id"] == user.id

    async def test_protected_route_with_tampered_cookie_redirects(self, client):
        client.cookies.set(settings.SESSION_COOKIE_NAME, "tampered_value_xyz")
        response = await client.get("/test/protected")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"


# ── Dependency tests ─────────────────────────────────────────────────────────


class TestDependencies:
    async def test_get_current_user_with_valid_session(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.get("/test/protected")
        assert response.status_code == 200
        assert response.json()["user_id"] == user.id

    async def test_get_current_user_without_session_redirects(self, client):
        response = await client.get("/test/protected")
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

    async def test_require_role_admin_allows_admin(
        self, client, create_test_user, create_test_group, db, auth_cookie
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        db.add(UserGroup(user_id=user.id, group_id=group.id, role="admin"))
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/test/admin-only")
        assert response.status_code == 200

    async def test_require_role_admin_blocks_contributor(
        self, client, create_test_user, create_test_group, db, auth_cookie
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        db.add(UserGroup(user_id=user.id, group_id=group.id, role="contributor"))
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/test/admin-only")
        assert response.status_code == 403

    async def test_require_role_admin_blocks_reader(
        self, client, create_test_user, create_test_group, db, auth_cookie
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        db.add(UserGroup(user_id=user.id, group_id=group.id, role="reader"))
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/test/admin-only")
        assert response.status_code == 403

    async def test_require_role_contributor_allows_admin(
        self, client, create_test_user, create_test_group, db, auth_cookie
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        db.add(UserGroup(user_id=user.id, group_id=group.id, role="admin"))
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/test/contributor-min")
        assert response.status_code == 200

    async def test_require_role_contributor_allows_contributor(
        self, client, create_test_user, create_test_group, db, auth_cookie
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        db.add(UserGroup(user_id=user.id, group_id=group.id, role="contributor"))
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/test/contributor-min")
        assert response.status_code == 200

    async def test_require_role_contributor_blocks_reader(
        self, client, create_test_user, create_test_group, db, auth_cookie
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        db.add(UserGroup(user_id=user.id, group_id=group.id, role="reader"))
        db.commit()
        auth_cookie(client, user.id, group.id)

        response = await client.get("/test/contributor-min")
        assert response.status_code == 403


# ── Integration tests: forgot password route ─────────────────────────────────


class TestForgotPasswordRoute:
    async def test_get_forgot_password_page_returns_200(self, client):
        response = await client.get("/forgot-password")
        assert response.status_code == 200

    async def test_forgot_password_existing_email_succeeds(
        self, client, create_test_user
    ):
        create_test_user(email="alice@farm.com", password="secret1234")
        response = await client.post(
            "/forgot-password", data={"email": "alice@farm.com"}
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "reset" in body or "sent" in body

    async def test_forgot_password_nonexistent_email_succeeds_silently(self, client):
        response = await client.post(
            "/forgot-password", data={"email": "nobody@example.com"}
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "reset" in body or "sent" in body

    async def test_forgot_password_generates_token(self, client, create_test_user):
        user = create_test_user(email="alice@farm.com", password="secret1234")
        with patch("app.routes.auth._deliver_reset_token") as mock_deliver:
            response = await client.post(
                "/forgot-password", data={"email": "alice@farm.com"}
            )
        assert response.status_code == 200
        mock_deliver.assert_called_once()
        email_arg, token_arg = mock_deliver.call_args[0]
        assert email_arg == "alice@farm.com"
        data = decode_password_reset_token(token_arg)
        assert data is not None
        assert data["user_id"] == user.id


# ── Integration tests: reset password route ──────────────────────────────────


class TestResetPasswordRoute:
    async def test_get_reset_password_page_valid_token_returns_200(
        self, client, create_test_user
    ):
        user = create_test_user(password="secret1234")
        token = create_password_reset_token(user.id, user.password_hash)
        response = await client.get(f"/reset-password/{token}")
        assert response.status_code == 200
        assert "new_password" in response.text

    async def test_get_reset_password_page_invalid_token_shows_error(self, client):
        response = await client.get("/reset-password/invalid_token_xyz")
        assert response.status_code == 200
        body = response.text.lower()
        assert "invalid" in body or "expired" in body

    async def test_get_reset_password_page_expired_token_shows_error(
        self, client, create_test_user
    ):
        user = create_test_user(password="secret1234")
        token = create_password_reset_token(user.id, user.password_hash)
        time.sleep(1.1)
        with patch("app.auth.RESET_TOKEN_MAX_AGE", 0):
            response = await client.get(f"/reset-password/{token}")
        assert response.status_code == 200
        body = response.text.lower()
        assert "invalid" in body or "expired" in body

    async def test_reset_password_valid_token_changes_password(
        self, client, create_test_user
    ):
        user = create_test_user(password="secret1234")
        token = create_password_reset_token(user.id, user.password_hash)
        response = await client.post(
            f"/reset-password/{token}",
            data={
                "new_password": "newsecret1234",
                "new_password_confirm": "newsecret1234",
            },
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/login"

        login_response = await client.post(
            "/login",
            data={"email": "test@example.com", "password": "newsecret1234"},
        )
        assert login_response.status_code == 303
        assert "/dashboard" in login_response.headers["location"]

    async def test_reset_password_invalid_token_fails(self, client):
        response = await client.post(
            "/reset-password/invalid_token_xyz",
            data={
                "new_password": "newsecret1234",
                "new_password_confirm": "newsecret1234",
            },
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "invalid" in body or "expired" in body

    async def test_reset_password_expired_token_fails(
        self, client, create_test_user
    ):
        user = create_test_user(password="secret1234")
        token = create_password_reset_token(user.id, user.password_hash)
        time.sleep(1.1)
        with patch("app.auth.RESET_TOKEN_MAX_AGE", 0):
            response = await client.post(
                f"/reset-password/{token}",
                data={
                    "new_password": "newsecret1234",
                    "new_password_confirm": "newsecret1234",
                },
            )
        assert response.status_code == 200
        body = response.text.lower()
        assert "invalid" in body or "expired" in body

    async def test_reset_password_password_mismatch_shows_error(
        self, client, create_test_user
    ):
        user = create_test_user(password="secret1234")
        token = create_password_reset_token(user.id, user.password_hash)
        response = await client.post(
            f"/reset-password/{token}",
            data={
                "new_password": "newsecret1234",
                "new_password_confirm": "different1234",
            },
        )
        assert response.status_code == 200
        assert "password" in response.text.lower()

    async def test_reset_password_used_token_cannot_reuse(
        self, client, create_test_user
    ):
        user = create_test_user(password="secret1234")
        token = create_password_reset_token(user.id, user.password_hash)

        response = await client.post(
            f"/reset-password/{token}",
            data={
                "new_password": "newsecret1234",
                "new_password_confirm": "newsecret1234",
            },
        )
        assert response.status_code == 303

        response = await client.post(
            f"/reset-password/{token}",
            data={
                "new_password": "anotherpw1234",
                "new_password_confirm": "anotherpw1234",
            },
        )
        assert response.status_code == 200
        body = response.text.lower()
        assert "invalid" in body or "expired" in body
