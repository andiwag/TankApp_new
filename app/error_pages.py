"""User-facing error page helpers."""

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.templating import templates

_API_PREFIXES = ("/health", "/cron/")


def wants_html_response(request: Request) -> bool:
    path = request.url.path
    if path.startswith(_API_PREFIXES):
        return False
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return False
    return True


def error_page_response(
    request: Request,
    *,
    status_code: int,
    title: str,
    message: str,
    detail: str | None = None,
) -> Response:
    return templates.TemplateResponse(
        request,
        "error.html",
        context={
            "status_code": status_code,
            "title": title,
            "message": message,
            "detail": detail if not settings.is_production else None,
        },
        status_code=status_code,
    )


def api_error_response(status_code: int, error: str) -> JSONResponse:
    return JSONResponse({"error": error}, status_code=status_code)


_HTTP_MESSAGES: dict[int, tuple[str, str]] = {
    403: ("Access denied", "You do not have permission to view this page."),
    404: ("Page not found", "The page you requested does not exist."),
    429: ("Too many requests", "Please wait a moment and try again."),
}


def _client_safe_http_detail(exc: StarletteHTTPException) -> str | None:
    if not isinstance(exc.detail, str) or not exc.detail or exc.status_code == 404:
        return None
    if exc.status_code >= 500 and settings.is_production:
        return None
    return exc.detail


def http_exception_response(request: Request, exc: StarletteHTTPException) -> Response:
    if wants_html_response(request):
        title, message = _HTTP_MESSAGES.get(
            exc.status_code,
            ("Request error", "Something went wrong with your request."),
        )
        detail = _client_safe_http_detail(exc)
        if detail:
            message = detail
        return error_page_response(
            request,
            status_code=exc.status_code,
            title=title,
            message=message,
        )

    detail = exc.detail
    if not isinstance(detail, str):
        detail = "request_error"
    if exc.status_code >= 500 and settings.is_production:
        detail = "internal_server_error"
    return JSONResponse({"detail": detail}, status_code=exc.status_code)
