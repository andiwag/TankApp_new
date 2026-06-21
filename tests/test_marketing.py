"""Tests for public marketing pages."""


class TestLandingPage:
    async def test_landing_page_renders_for_anonymous_users(self, client):
        response = await client.get("/")
        assert response.status_code == 200
        html = response.text
        assert "Kraftstoff" in html
        assert "TankApp" in html
        assert "/register" in html
        assert 'id="pricing"' in html or 'id="features"' in html

    async def test_landing_redirects_authenticated_user_with_group(
        self,
        client,
        create_test_user,
        create_test_group,
        create_test_user_group,
        auth_cookie,
    ):
        user = create_test_user()
        group = create_test_group(created_by=user.id)
        create_test_user_group(user.id, group.id, role="admin")
        auth_cookie(client, user.id, group.id)

        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/dashboard"

    async def test_landing_redirects_authenticated_user_without_group(
        self, client, create_test_user, auth_cookie
    ):
        user = create_test_user()
        auth_cookie(client, user.id)

        response = await client.get("/", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers.get("location") == "/groups"

    async def test_landing_has_security_headers(self, client):
        response = await client.get("/")
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert "Content-Security-Policy" in response.headers


class TestLegalPages:
    async def test_impressum_page(self, client):
        response = await client.get("/impressum")
        assert response.status_code == 200
        assert "Impressum" in response.text

    async def test_privacy_page(self, client):
        response = await client.get("/datenschutz")
        assert response.status_code == 200
        assert "Datenschutz" in response.text

    async def test_terms_page(self, client):
        response = await client.get("/agb")
        assert response.status_code == 200
        assert "AGB" in response.text
