import builtins
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.csrf import CsrfTokenMiddleware, validate_csrf
from app.database import check_database_connection
from app.error_pages import (
    api_error_response,
    error_page_response,
    http_exception_response,
    wants_html_response,
)
from app.flash import FlashMiddleware
from app.logging_config import configure_logging
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.session_cookie import StaleActiveGroupMiddleware
from app.responses import forbidden_response

logger = logging.getLogger(__name__)


def _init_sentry() -> None:
    if not settings.SENTRY_DSN:
        return
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENV,
        traces_sample_rate=0.0,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(json_logs=settings.is_production)
    _init_sentry()
    if (
        settings.is_production
        and not settings.REDIS_URL
        and settings.SINGLE_WORKER_MODE
    ):
        logger.warning(
            "SINGLE_WORKER_MODE is enabled; in-memory rate limits are not "
            "shared across replicas."
        )
    yield


app = FastAPI(
    title="TankApp",
    version="0.1.0",
    dependencies=[Depends(validate_csrf)],
    lifespan=lifespan,
)

_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

if settings.allowed_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(FlashMiddleware)
app.add_middleware(CsrfTokenMiddleware)
app.add_middleware(StaleActiveGroupMiddleware)


# ── Exception handlers ───────────────────────────────────────────────────────

from app.dependencies import (  # noqa: E402
    InsufficientRoleException,
    NoActiveGroupException,
    NotAuthenticatedException,
)


@app.exception_handler(NotAuthenticatedException)
async def not_authenticated_handler(request, exc):
    return RedirectResponse(url="/login", status_code=303)


@app.exception_handler(NoActiveGroupException)
async def no_active_group_handler(request, exc):
    return RedirectResponse(url="/groups", status_code=303)


@app.exception_handler(InsufficientRoleException)
async def insufficient_role_handler(request, exc):
    return forbidden_response()


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    return http_exception_response(request, exc)


def _root_cause(exc: BaseException) -> BaseException:
    group_type = getattr(builtins, "BaseExceptionGroup", None)
    if group_type is None:
        return exc
    while isinstance(exc, group_type) and exc.exceptions:
        exc = exc.exceptions[0]
    return exc


async def _handle_unhandled_error(request: Request, exc: BaseException):
    exc = _root_cause(exc)
    if not isinstance(exc, Exception):
        raise exc
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    if wants_html_response(request):
        return error_page_response(
            request,
            status_code=500,
            title="Something went wrong",
            message=(
                "An unexpected error occurred. Please try again. "
                "If the problem persists, contact support."
            ),
            detail=str(exc),
        )
    return api_error_response(500, "internal_server_error")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    return await _handle_unhandled_error(request, exc)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Liveness probe — process is up."""
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness_check() -> JSONResponse:
    """Readiness probe — database is reachable."""
    if check_database_connection():
        return JSONResponse({"status": "ready"})
    return JSONResponse({"status": "unavailable"}, status_code=503)


# ── Routes ───────────────────────────────────────────────────────────────────

from app.routes.analytics import router as analytics_router  # noqa: E402
from app.routes.audit_log import router as audit_log_router  # noqa: E402
from app.routes.auth import router as auth_router  # noqa: E402
from app.routes.cron import router as cron_router  # noqa: E402
from app.routes.dashboard import router as dashboard_router  # noqa: E402
from app.routes.export import router as export_router  # noqa: E402
from app.routes.fuel_entries import router as fuel_entries_router  # noqa: E402
from app.routes.group_settings import router as group_settings_router  # noqa: E402
from app.routes.groups import router as groups_router  # noqa: E402
from app.routes.maintenance import router as maintenance_router  # noqa: E402
from app.routes.marketing import router as marketing_router  # noqa: E402
from app.routes.profile import router as profile_router  # noqa: E402
from app.routes.summary import router as summary_router  # noqa: E402
from app.routes.vehicles import router as vehicles_router  # noqa: E402

app.include_router(marketing_router)
app.include_router(auth_router)
app.include_router(groups_router)
app.include_router(group_settings_router)
app.include_router(dashboard_router)
app.include_router(summary_router)
app.include_router(profile_router)
app.include_router(vehicles_router)
app.include_router(fuel_entries_router)
app.include_router(maintenance_router)
app.include_router(analytics_router)
app.include_router(export_router)
app.include_router(audit_log_router)
app.include_router(cron_router)
