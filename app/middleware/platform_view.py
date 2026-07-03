"""Block mutating requests while an operator is in platform support view."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.auth import decode_session_cookie
from app.config import settings
from app.database import SessionLocal, get_db
from app.dependencies import platform_view_is_valid
from app.models import User
from app.responses import forbidden_response
from app.services.sessions import get_active_session


def _platform_view_allows_request(path: str, method: str) -> bool:
    if method == "GET":
        return not path.startswith("/export/")
    if path == "/logout":
        return True
    if path == "/platform/exit-view":
        return True
    if path.startswith("/platform/farms/") and path.endswith("/enter"):
        return True
    return False


def _open_db_session(request: Request):
    override = request.app.dependency_overrides.get(get_db)
    if override is not None:
        return next(override()), True
    return SessionLocal(), True


def _cookie_has_active_platform_view(request: Request, data: dict) -> bool:
    session_id = data.get("session_id")
    user_id = data.get("user_id")
    if not session_id or not user_id:
        return False

    db, should_close = _open_db_session(request)
    try:
        session = get_active_session(db, session_id)
        if not session or session.user_id != user_id:
            return False
        user = (
            db.query(User)
            .filter(
                User.id == user_id,
                User.deleted_at == None,  # noqa: E711
            )
            .first()
        )
        if not user:
            return False
        return platform_view_is_valid(user, data)
    finally:
        if should_close:
            db.close()


class PlatformViewReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        cookie = request.cookies.get(settings.SESSION_COOKIE_NAME)
        if cookie:
            data = decode_session_cookie(cookie)
            if data and data.get("platform_view"):
                if _cookie_has_active_platform_view(request, data):
                    if not _platform_view_allows_request(
                        request.url.path, request.method.upper()
                    ):
                        return forbidden_response()
        return await call_next(request)
