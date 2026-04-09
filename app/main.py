from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates

app = FastAPI(title="TankApp", version="0.1.0")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


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


# ── Routes ───────────────────────────────────────────────────────────────────

from app.routes.auth import router as auth_router  # noqa: E402

app.include_router(auth_router)
