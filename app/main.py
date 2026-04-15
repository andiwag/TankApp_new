from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.flash import FlashMiddleware

app = FastAPI(title="TankApp", version="0.1.0")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

_static_dir = Path(__file__).parent / "static"
_static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")

app.add_middleware(FlashMiddleware)


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
    return Response("Forbidden", status_code=403)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


# ── Routes ───────────────────────────────────────────────────────────────────

from app.routes.auth import router as auth_router  # noqa: E402
from app.routes.dashboard import router as dashboard_router  # noqa: E402
from app.routes.groups import router as groups_router  # noqa: E402
from app.routes.fuel_entries import router as fuel_entries_router  # noqa: E402
from app.routes.vehicles import router as vehicles_router  # noqa: E402

app.include_router(auth_router)
app.include_router(groups_router)
app.include_router(dashboard_router)
app.include_router(vehicles_router)
app.include_router(fuel_entries_router)
