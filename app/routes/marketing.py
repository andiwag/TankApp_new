"""Public marketing pages (landing, legal)."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.dependencies import get_optional_current_user
from app.models import User
from app.templating import templates

router = APIRouter()


@router.get("/")
async def landing_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_optional_current_user),
):
    if user is not None:
        if request.state.active_group:
            return RedirectResponse(url="/dashboard", status_code=303)
        return RedirectResponse(url="/groups", status_code=303)

    return templates.TemplateResponse(request, "landing.html")


@router.get("/impressum")
async def impressum_page(
    request: Request,
    _user: User | None = Depends(get_optional_current_user),
):
    return templates.TemplateResponse(request, "legal/impressum.html")


@router.get("/datenschutz")
async def privacy_page(
    request: Request,
    _user: User | None = Depends(get_optional_current_user),
):
    return templates.TemplateResponse(request, "legal/privacy.html")


@router.get("/agb")
async def terms_page(
    request: Request,
    _user: User | None = Depends(get_optional_current_user),
):
    return templates.TemplateResponse(request, "legal/terms.html")


@router.get("/robots.txt", include_in_schema=False)
async def robots_txt() -> PlainTextResponse:
    if settings.registration_invite_required:
        body = "User-agent: *\nDisallow: /\n"
    else:
        body = "User-agent: *\nAllow: /\n"
    return PlainTextResponse(body, media_type="text/plain")
