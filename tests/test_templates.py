"""Tests for Phase 6: Base Template & Layout."""

import json

import pytest

FLASH_COOKIE_NAME = "tankapp_flash"


class TestBaseTemplateIncludes:
    @pytest.mark.asyncio
    async def test_base_template_includes_tailwind(self, client):
        response = await client.get("/login")
        assert response.status_code == 200
        assert "tailwindcss" in response.text

    @pytest.mark.asyncio
    async def test_base_template_includes_alpine(self, client):
        response = await client.get("/login")
        assert response.status_code == 200
        assert "alpinejs" in response.text or "alpine" in response.text


class TestLoginPageFields:
    @pytest.mark.asyncio
    async def test_login_page_has_email_and_password_fields(self, client):
        response = await client.get("/login")
        assert response.status_code == 200
        html = response.text
        assert 'name="email"' in html
        assert 'name="password"' in html
        assert 'type="email"' in html
        assert 'type="password"' in html


class TestRegisterPageFields:
    @pytest.mark.asyncio
    async def test_register_page_has_name_email_password_fields(self, client):
        response = await client.get("/register")
        assert response.status_code == 200
        html = response.text
        assert 'name="name"' in html
        assert 'name="email"' in html
        assert 'name="password"' in html
        assert 'name="password_confirm"' in html


class TestAuthenticatedPageElements:
    @pytest.mark.asyncio
    async def test_authenticated_page_shows_user_name(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user(name="Alice Farmer")
        auth_cookie(client, user.id)
        response = await client.get("/groups")
        assert response.status_code == 200
        assert "Alice Farmer" in response.text

    @pytest.mark.asyncio
    async def test_authenticated_page_shows_active_group(
        self, client, create_test_user, create_test_group, create_test_user_group, auth_cookie
    ):
        user = create_test_user()
        group = create_test_group(name="Green Farm", created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)
        response = await client.get("/groups")
        assert response.status_code == 200
        assert "Green Farm" in response.text

    @pytest.mark.asyncio
    async def test_authenticated_page_has_logout_button(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)
        response = await client.get("/groups")
        assert response.status_code == 200
        assert "/logout" in response.text


class TestFlashMessages:
    @pytest.mark.asyncio
    async def test_flash_message_displayed_after_redirect(self, client):
        client.cookies.set(
            FLASH_COOKIE_NAME,
            json.dumps({"message": "Operation successful", "category": "success"}),
        )
        response = await client.get("/login")
        assert response.status_code == 200
        assert "Operation successful" in response.text
