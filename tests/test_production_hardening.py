"""Tests for A+ production hardening (headers, health, config guards)."""

import pytest
from app.config import Settings
from pydantic import ValidationError


def _production_settings(**overrides) -> Settings:
    values = {
        "DATABASE_URL": "sqlite:///./test.db",
        "ENV": "production",
        "SECRET_KEY": "unique-production-secret",
        "CRON_SECRET": "cron-secret-value",
        "REDIS_URL": "redis://localhost:6379/0",
        "_env_file": None,
    }
    values.update(overrides)
    return Settings(**values)


class TestProductionConfig:
    def test_production_requires_cron_secret(self):
        with pytest.raises(ValidationError, match="CRON_SECRET"):
            Settings(
                DATABASE_URL="sqlite:///./test.db",
                ENV="production",
                SECRET_KEY="unique-production-secret",
                REDIS_URL="redis://localhost:6379/0",
                CRON_SECRET="",
                _env_file=None,
            )

    def test_production_requires_redis_or_single_worker_mode(self):
        with pytest.raises(ValidationError, match="REDIS_URL"):
            Settings(
                DATABASE_URL="sqlite:///./test.db",
                ENV="production",
                SECRET_KEY="unique-production-secret",
                CRON_SECRET="cron-secret",
                SINGLE_WORKER_MODE=False,
                _env_file=None,
            )

    def test_single_worker_mode_allows_missing_redis(self):
        settings = _production_settings(
            REDIS_URL="",
            SINGLE_WORKER_MODE=True,
        )
        assert settings.SINGLE_WORKER_MODE is True

    def test_allowed_hosts_parsed_from_csv(self):
        settings = Settings(
            ALLOWED_HOSTS="app.example.com, *.code.run",
            _env_file=None,
        )
        assert settings.allowed_hosts == ["app.example.com", "*.code.run"]


class TestSecurityHeaders:
    async def test_security_headers_on_login_page(self, client):
        response = await client.get("/login")
        assert response.status_code == 200
        assert response.headers.get("X-Content-Type-Options") == "nosniff"
        assert response.headers.get("X-Frame-Options") == "DENY"
        assert (
            response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        )
        assert "Content-Security-Policy" in response.headers
        csp = response.headers["Content-Security-Policy"]
        assert "script-src 'self'" in csp
        assert "cdn.tailwindcss.com" not in csp
        assert "cdn.jsdelivr.net" not in csp
        assert "frame-ancestors 'none'" in csp

    async def test_hsts_not_set_in_development(self, client):
        response = await client.get("/login")
        assert "Strict-Transport-Security" not in response.headers


class TestHealthEndpoints:
    async def test_liveness(self, client):
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_readiness_when_database_up(self, client):
        response = await client.get("/health/ready")
        assert response.status_code == 200
        assert response.json() == {"status": "ready"}

    async def test_readiness_when_database_down(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.main.check_database_connection",
            lambda: False,
        )
        response = await client.get("/health/ready")
        assert response.status_code == 503
        assert response.json() == {"status": "unavailable"}
