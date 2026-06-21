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
        if not getattr(request.state, "clear_stale_active_group", False):
            return response

        session_data = getattr(request.state, "session_data", None)
        user = getattr(request.state, "user", None)
        session_id = session_data.get("session_id") if session_data else None
        if user and session_id:
            refresh_session_cookie(
                response,
                user.id,
                None,
                session_id=session_id,
            )
        return response
