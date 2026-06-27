import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.branding import FLASH_COOKIE_DEFAULT
from app.config import settings

FLASH_COOKIE_NAME = FLASH_COOKIE_DEFAULT


def _flash_cookie_kwargs() -> dict:
    return {
        "httponly": True,
        "samesite": "lax",
        "secure": settings.is_production,
    }


def set_flash(response: Response, message: str, category: str = "success") -> None:
    response.set_cookie(
        FLASH_COOKIE_NAME,
        json.dumps({"message": message, "category": category}),
        max_age=60,
        **_flash_cookie_kwargs(),
    )


def _read_flash(request: Request) -> dict | None:
    cookie = request.cookies.get(FLASH_COOKIE_NAME)
    if not cookie:
        return None
    try:
        return json.loads(cookie)
    except (json.JSONDecodeError, ValueError):
        return None


class FlashMiddleware(BaseHTTPMiddleware):
    """Reads flash cookie into request.state and initializes nav context defaults."""

    async def dispatch(self, request: Request, call_next):
        request.state.flash = _read_flash(request)
        request.state.user = None
        request.state.active_group = None
        response = await call_next(request)
        if request.state.flash:
            response.delete_cookie(FLASH_COOKIE_NAME, **_flash_cookie_kwargs())
        return response
