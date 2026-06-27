"""CSRF configuration, validation dependency, and template token middleware."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, Request, Response
from fastapi_csrf_protect import CsrfProtect
from fastapi_csrf_protect.exceptions import CsrfProtectError
from itsdangerous import BadData, SignatureExpired, URLSafeTimedSerializer
from starlette.middleware.base import BaseHTTPMiddleware

from app.branding import CSRF_COOKIE_DEFAULT
from app.config import settings

CSRF_COOKIE_NAME = CSRF_COOKIE_DEFAULT
CSRF_FIELD_NAME = "csrf_token"
CSRF_MAX_AGE = 3600
UNSAFE_METHODS = {"DELETE", "PATCH", "POST", "PUT"}


@CsrfProtect.load_config
def get_csrf_config() -> list[tuple[str, object]]:
    return [
        ("secret_key", settings.SECRET_KEY),
        ("cookie_key", CSRF_COOKIE_NAME),
        ("cookie_samesite", "lax"),
        ("cookie_secure", settings.is_production),
        ("httponly", True),
        ("max_age", CSRF_MAX_AGE),
        ("token_location", "body"),
        ("token_key", CSRF_FIELD_NAME),
    ]


def create_csrf_tokens() -> tuple[str, str]:
    return CsrfProtect().generate_csrf_tokens()


def csrf_token_from_signed_cookie(signed_token: str | None) -> str | None:
    if not signed_token:
        return None
    serializer = URLSafeTimedSerializer(
        settings.SECRET_KEY,
        salt="fastapi-csrf-token",
    )
    try:
        token = serializer.loads(signed_token, max_age=CSRF_MAX_AGE)
    except (BadData, SignatureExpired):
        return None
    return token if isinstance(token, str) else None


async def validate_csrf(
    request: Request,
    csrf_protect: CsrfProtect = Depends(),
) -> None:
    if request.url.path.startswith("/cron/"):
        return
    if request.method.upper() not in UNSAFE_METHODS:
        return
    try:
        await csrf_protect.validate_csrf(request)
    except CsrfProtectError as exc:
        raise HTTPException(status_code=403, detail="CSRF validation failed") from exc


class CsrfTokenMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        signed_token = request.cookies.get(CSRF_COOKIE_NAME)
        token = csrf_token_from_signed_cookie(signed_token)
        should_set_cookie = token is None
        if token is None:
            token, signed_token = create_csrf_tokens()
        request.state.csrf_token = token
        response = await call_next(request)
        if should_set_cookie:
            CsrfProtect().set_csrf_cookie(signed_token, response)
        return response
