from app.config import Settings


def test_default_settings():
    s = Settings(
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="testkey",
        _env_file=None,
    )
    assert s.DATABASE_URL == "sqlite:///./test.db"
    assert s.TEST_DATABASE_URL == ""
    assert s.SESSION_COOKIE_NAME == "tankly_session"
    assert s.ENV == "development"
    assert s.is_production is False


def test_test_database_url_can_be_configured_separately():
    s = Settings(
        DATABASE_URL="postgresql://tankly:local@localhost/tankly_dev",
        TEST_DATABASE_URL="postgresql://tankly:local@localhost/tankly_test",
        _env_file=None,
    )

    assert s.DATABASE_URL.endswith("/tankly_dev")
    assert s.TEST_DATABASE_URL.endswith("/tankly_test")


def test_production_flag():
    s = Settings(
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="testkey",
        ENV="production",
        CRON_SECRET="cron-secret",
        SINGLE_WORKER_MODE=True,
        _env_file=None,
    )
    assert s.is_production is True
