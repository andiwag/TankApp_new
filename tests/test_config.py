from app.config import Settings


def test_default_settings():
    s = Settings(
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="testkey",
        _env_file=None,
    )
    assert s.DATABASE_URL == "sqlite:///./test.db"
    assert s.SESSION_COOKIE_NAME == "tankapp_session"
    assert s.ENV == "development"
    assert s.is_production is False


def test_production_flag():
    s = Settings(
        DATABASE_URL="sqlite:///./test.db",
        SECRET_KEY="testkey",
        ENV="production",
        _env_file=None,
    )
    assert s.is_production is True
