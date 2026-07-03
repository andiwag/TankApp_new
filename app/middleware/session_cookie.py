"""Middleware that refreshes the session cookie when active group membership is stale."""

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.services.sessions import refresh_session_cookie


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
        if not user or not session_id:
            return response

        if getattr(request.state, "clear_stale_active_group", False):
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
