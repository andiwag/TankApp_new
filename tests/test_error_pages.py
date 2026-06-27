"""Tests for global error handling."""

from unittest.mock import patch

from starlette.exceptions import HTTPException as StarletteHTTPException

from app.error_pages import _client_safe_http_detail


class TestErrorPages:
    async def test_unhandled_error_returns_friendly_html_on_login(
        self, client, create_test_user
    ):
        create_test_user(email="err@farm.com", password="secret123")

        with patch(
            "app.routes.auth.start_user_session",
            side_effect=RuntimeError("database unavailable"),
        ):
            response = await client.post(
                "/login",
                data={"email": "err@farm.com", "password": "secret123"},
                headers={"Accept": "text/html"},
            )

        assert response.status_code == 500
        assert "Something went wrong" in response.text
        assert "TankApp" in response.text
        assert "database unavailable" in response.text

    async def test_unhandled_error_returns_json_when_client_expects_json(
        self, client, create_test_user
    ):
        create_test_user(email="json@farm.com", password="secret123")

        with patch(
            "app.routes.auth.start_user_session",
            side_effect=RuntimeError("database unavailable"),
        ):
            response = await client.post(
                "/login",
                data={"email": "json@farm.com", "password": "secret123"},
                headers={"Accept": "application/json"},
            )

        assert response.status_code == 500
        assert response.json() == {"error": "internal_server_error"}

    async def test_unknown_route_returns_friendly_html_404(self, client):
        response = await client.get(
            "/this-page-does-not-exist",
            headers={"Accept": "text/html"},
        )

        assert response.status_code == 404
        assert "Page not found" in response.text

    def test_http_500_detail_hidden_in_production(self, monkeypatch):
        monkeypatch.setattr("app.error_pages.settings.ENV", "production")

        exc = StarletteHTTPException(
            status_code=500, detail="database connection leaked"
        )

        assert _client_safe_http_detail(exc) is None

        exc_403 = StarletteHTTPException(status_code=403, detail="Admins only")
        assert _client_safe_http_detail(exc_403) == "Admins only"
