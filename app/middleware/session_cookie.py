"""Middleware that refreshes the session cookie when active group membership is stale."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings
from app.services.sessions import refresh_session_cookie


def _response_sets_session_cookie(response: Response) -> bool:
    prefix = f"{settings.SESSION_COOKIE_NAME}="
    for key, value in response.raw_headers:
        if key.lower() == b"set-cookie" and value.decode("latin-1").startswith(prefix):
            return True
    return False


class StaleActiveGroupMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        session_data = getattr(request.state, "session_data", None)
        user = getattr(request.state, "user", None)
        session_id = session_data.get("session_id") if session_data else None
        if not user or not session_id or _response_sets_session_cookie(response):
            return response

        if getattr(request.state, "persist_active_group", False):
            refresh_session_cookie(
                response,
                user.id,
                session_data.get("active_group_id"),
                session_id=session_id,
                platform_view=False,
            )
        elif getattr(request.state, "clear_stale_active_group", False):
            refresh_session_cookie(
                response,
                user.id,
                None,
                session_id=session_id,
                platform_view=False,
            )
        elif getattr(request.state, "clear_invalid_platform_view", False):
            refresh_session_cookie(
                response,
                user.id,
                session_data.get("active_group_id"),
                session_id=session_id,
                platform_view=False,
            )
        return response
