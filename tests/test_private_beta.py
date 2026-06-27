"""Tests for private beta registration gating."""


class TestRegistrationInviteCode:
    async def test_register_without_invite_when_not_required(self, client):
        response = await client.post(
            "/register",
            data={
                "name": "Beta User",
                "email": "open@farm.com",
                "password": "secret123",
                "password_confirm": "secret123",
            },
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/groups"

    async def test_register_requires_invite_code_when_configured(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(
            "app.config.settings.REGISTRATION_INVITE_CODE", "farm-beta-42"
        )

        response = await client.post(
            "/register",
            data={
                "name": "Blocked User",
                "email": "blocked@farm.com",
                "password": "secret123",
                "password_confirm": "secret123",
            },
        )

        assert response.status_code == 200
        assert "Invalid invite code" in response.text

    async def test_register_with_valid_invite_code(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.REGISTRATION_INVITE_CODE", "farm-beta-42"
        )

        response = await client.post(
            "/register",
            data={
                "invite_code": "farm-beta-42",
                "name": "Invited User",
                "email": "invited@farm.com",
                "password": "secret123",
                "password_confirm": "secret123",
            },
        )

        assert response.status_code == 303
        assert response.headers["location"] == "/groups"

    async def test_register_accepts_invite_code_with_surrounding_whitespace(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(
            "app.config.settings.REGISTRATION_INVITE_CODE", "farm-beta-42"
        )

        response = await client.post(
            "/register",
            data={
                "invite_code": "  farm-beta-42  ",
                "name": "Padded User",
                "email": "padded@farm.com",
                "password": "secret123",
                "password_confirm": "secret123",
            },
        )

        assert response.status_code == 303

    async def test_whitespace_only_invite_code_env_treated_as_open_registration(
        self, client, monkeypatch
    ):
        monkeypatch.setattr("app.config.settings.REGISTRATION_INVITE_CODE", "   ")

        response = await client.get("/register")

        assert response.status_code == 200
        assert 'name="invite_code"' not in response.text

    async def test_invalid_invite_rate_limited_per_host(self, client, monkeypatch):
        from app.rate_limit import InMemoryRateLimiter

        monkeypatch.setattr(
            "app.config.settings.REGISTRATION_INVITE_CODE", "farm-beta-42"
        )
        monkeypatch.setattr(
            "app.routes.auth.register_invite_rate_limiter",
            InMemoryRateLimiter(max_attempts=2, window_seconds=60),
        )

        for index in range(2):
            response = await client.post(
                "/register",
                data={
                    "invite_code": "wrong-code",
                    "name": f"User {index}",
                    "email": f"user{index}@farm.com",
                    "password": "secret123",
                    "password_confirm": "secret123",
                },
            )
            assert response.status_code == 200
            assert "Invalid invite code" in response.text

        response = await client.post(
            "/register",
            data={
                "invite_code": "wrong-code",
                "name": "Blocked User",
                "email": "blocked2@farm.com",
                "password": "secret123",
                "password_confirm": "secret123",
            },
        )

        assert response.status_code == 429
        assert "Too many attempts" in response.text

    async def test_register_page_shows_invite_field_when_configured(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(
            "app.config.settings.REGISTRATION_INVITE_CODE", "farm-beta-42"
        )

        response = await client.get("/register")

        assert response.status_code == 200
        assert 'name="invite_code"' in response.text

    async def test_robots_txt_disallows_crawling_in_private_beta(
        self, client, monkeypatch
    ):
        monkeypatch.setattr(
            "app.config.settings.REGISTRATION_INVITE_CODE", "farm-beta-42"
        )

        response = await client.get("/robots.txt")

        assert response.status_code == 200
        assert "Disallow: /" in response.text

    async def test_robots_txt_allows_crawling_when_open(self, client):
        response = await client.get("/robots.txt")

        assert response.status_code == 200
        assert "Allow: /" in response.text

    async def test_landing_has_noindex_when_private_beta(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.config.settings.REGISTRATION_INVITE_CODE", "farm-beta-42"
        )

        response = await client.get("/")

        assert response.status_code == 200
        assert 'content="noindex, nofollow"' in response.text
