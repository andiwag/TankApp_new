"""Tests for self-hosted vendor assets."""


class TestVendorAssets:
    async def test_alpine_js_accessible(self, client):
        response = await client.get("/static/vendor/alpine.min.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]

    async def test_tailwind_js_accessible(self, client):
        response = await client.get("/static/vendor/tailwindcss.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]

    async def test_chart_js_accessible(self, client):
        response = await client.get("/static/vendor/chart.umd.min.js")
        assert response.status_code == 200
        assert "javascript" in response.headers["content-type"]

    async def test_login_page_uses_self_hosted_scripts(self, client):
        response = await client.get("/login")
        assert response.status_code == 200
        assert "/static/vendor/tailwindcss.js" in response.text
        assert "/static/vendor/alpine.min.js" in response.text
        assert "cdn.tailwindcss.com" not in response.text
        assert "cdn.jsdelivr.net" not in response.text
