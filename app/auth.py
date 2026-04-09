import bcrypt
from itsdangerous import URLSafeTimedSerializer

from app.config import settings

SESSION_MAX_AGE = 86400  # 24 hours
RESET_TOKEN_MAX_AGE = 3600  # 1 hour
_RESET_TOKEN_SALT = "password-reset"
_PASSWORD_HASH_PREFIX_LEN = 16

_serializer = URLSafeTimedSerializer(settings.SECRET_KEY)


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Session cookies ──────────────────────────────────────────────────────────


def create_session_cookie(user_id: int, active_group_id: int | None = None) -> str:
    return _serializer.dumps({"user_id": user_id, "active_group_id": active_group_id})


def decode_session_cookie(cookie_value: str) -> dict | None:
    try:
        return _serializer.loads(cookie_value, max_age=SESSION_MAX_AGE)
    except Exception:
        return None


# ── Password reset tokens ────────────────────────────────────────────────────


def create_password_reset_token(user_id: int, password_hash: str) -> str:
    """Create a signed token embedding the user ID and a password-hash fingerprint.

    The fingerprint invalidates the token automatically after a password change.
    """
    return _serializer.dumps(
        {"user_id": user_id, "ph": password_hash[:_PASSWORD_HASH_PREFIX_LEN]},
        salt=_RESET_TOKEN_SALT,
    )


def decode_password_reset_token(token: str) -> dict | None:
    try:
        return _serializer.loads(
            token, salt=_RESET_TOKEN_SALT, max_age=RESET_TOKEN_MAX_AGE
        )
    except Exception:
        return None


def verify_reset_token_data(password_hash: str, token_data: dict) -> bool:
    """Check that the password-hash fingerprint in the token still matches the user's current hash."""
    return password_hash[:_PASSWORD_HASH_PREFIX_LEN] == token_data.get("ph")
