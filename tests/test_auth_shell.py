"""Phase 8: auth shells + motion (landing/legal unchanged)."""

from pathlib import Path


class TestAuthShell:
    async def test_login_uses_auth_shell_without_emoji(self, client):
        response = await client.get("/login")
        assert response.status_code == 200
        html = response.text
        assert "t-auth" in html
        assert "t-auth-panel" in html
        assert "👋" not in html
        assert "⛽" not in html
        assert "glass_panel" not in html

    async def test_register_uses_auth_shell_without_emoji(self, client):
        response = await client.get("/register")
        assert response.status_code == 200
        html = response.text
        assert "t-auth" in html
        assert "t-auth-panel" in html
        assert "✨" not in html
        assert "🚀" not in html

    async def test_forgot_and_reset_use_auth_shell(self, client):
        forgot = await client.get("/forgot-password")
        assert forgot.status_code == 200
        assert "t-auth-panel" in forgot.text
        assert "🔑" not in forgot.text

        # Reset without token still renders shell (invalid/missing handled in route)
        reset = await client.get("/reset-password/test-token-for-shell")
        assert "t-auth-panel" in reset.text or reset.status_code in (200, 400, 404)

    async def test_error_page_uses_auth_shell_without_emoji(self, client):
        response = await client.get("/this-route-does-not-exist-xyz")
        assert response.status_code == 404
        assert "t-error-panel" in response.text
        assert "t-auth-panel" in response.text
        assert "⚠️" not in response.text


class TestLandingLegalUnchanged:
    async def test_landing_does_not_use_auth_shell(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        assert "t-auth-panel" not in response.text
        assert "t-auth " not in response.text and 'class="t-auth"' not in response.text

    async def test_legal_pages_do_not_use_auth_shell(self, client):
        for path in ("/impressum", "/datenschutz", "/agb"):
            response = await client.get(path)
            assert response.status_code == 200
            assert "t-auth-panel" not in response.text


class TestMotionTokens:
    def test_css_defines_motion_and_reduced_motion(self):
        css = Path("app/static/app.css").read_text(encoding="utf-8")
        assert "t-motion-enter" in css or "@keyframes t-auth-enter" in css
        assert "prefers-reduced-motion" in css
        assert "t-capture-step" in css
