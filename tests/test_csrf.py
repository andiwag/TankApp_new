"""Tests for Phase 14: CSRF protection."""

import re
from contextlib import asynccontextmanager

from httpx import ASGITransport, AsyncClient

from app.auth import create_password_reset_token
from app.main import app
from tests.conftest import create_authenticated_group


_CSRF_RE = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
_POST_FORM_RE = re.compile(
    r"<form\b(?=[^>]*method=\"post\")[^>]*>.*?</form>",
    re.IGNORECASE | re.DOTALL,
)


@asynccontextmanager
async def _raw_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _csrf_token(response) -> str:
    match = _CSRF_RE.search(response.text)
    assert match is not None
    return match.group(1)


def _assert_all_post_forms_have_csrf(response) -> None:
    forms = _POST_FORM_RE.findall(response.text)
    assert forms
    for form in forms:
        assert 'name="csrf_token"' in form


def test_csrf_field_macro_is_defined():
    from pathlib import Path

    macros = Path("app/templates/_macros.html").read_text()
    assert "macro csrf_field" in macros


class TestCsrfRequests:
    async def test_post_without_csrf_token_rejected(self, create_test_user):
        create_test_user(password="secret1234")
        async with _raw_client() as client:
            response = await client.post(
                "/login",
                data={"email": "test@example.com", "password": "secret1234"},
            )
        assert response.status_code == 403

    async def test_post_with_valid_csrf_token_accepted(self, create_test_user):
        create_test_user(password="secret1234")
        async with _raw_client() as client:
            page = await client.get("/login")
            response = await client.post(
                "/login",
                data={
                    "email": "test@example.com",
                    "password": "secret1234",
                    "csrf_token": _csrf_token(page),
                },
            )
        assert response.status_code == 303

    async def test_post_with_invalid_csrf_token_rejected(self, create_test_user):
        create_test_user(password="secret1234")
        async with _raw_client() as client:
            await client.get("/login")
            response = await client.post(
                "/login",
                data={
                    "email": "test@example.com",
                    "password": "secret1234",
                    "csrf_token": "not-a-valid-token",
                },
            )
        assert response.status_code == 403

    async def test_stale_form_token_still_valid_after_second_get(self, create_test_user):
        create_test_user(password="secret1234")
        async with _raw_client() as client:
            first_page = await client.get("/login")
            first_token = _csrf_token(first_page)
            await client.get("/register")

            response = await client.post(
                "/login",
                data={
                    "email": "test@example.com",
                    "password": "secret1234",
                    "csrf_token": first_token,
                },
            )

        assert response.status_code == 303


class TestCsrfTemplateFields:
    async def test_csrf_token_present_in_all_forms(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        create_test_vehicle,
        create_test_fuel_entry,
        auth_cookie,
    ):
        user, group = create_authenticated_group(
            client,
            create_test_user,
            create_test_group,
            create_test_user_group,
            auth_cookie,
        )
        vehicle = create_test_vehicle(group_id=group.id)
        create_test_fuel_entry(
            vehicle_id=vehicle.id,
            group_id=group.id,
            user_id=user.id,
        )
        reset_token = create_password_reset_token(user.id, user.password_hash)

        pages = [
            "/login",
            "/register",
            "/forgot-password",
            f"/reset-password/{reset_token}",
            "/groups",
            "/vehicles",
            "/vehicles/new",
            f"/vehicles/{vehicle.id}/edit",
            "/fuel",
            "/fuel/new",
            "/profile",
            "/settings/group",
        ]

        for path in pages:
            response = await client.get(path)
            assert response.status_code == 200, path
            _assert_all_post_forms_have_csrf(response)
