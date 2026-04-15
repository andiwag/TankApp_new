from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.flash import set_flash
from app.main import templates
from app.models import User
from app.schemas import PasswordChange, UserUpdate, first_validation_error_message
from app.services import profile as profile_service

router = APIRouter()


@router.get("/profile")
async def profile_page(
    request: Request,
    _user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(request, "profile.html", context={})


@router.post("/profile")
async def profile_update(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = UserUpdate(name=name, email=email)
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "profile.html",
            context={"profile_error": first_validation_error_message(exc)},
        )

    err = profile_service.update_user_profile(db, user, data)
    if err:
        return templates.TemplateResponse(
            request, "profile.html", context={"profile_error": err},
        )

    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(response, "Profile updated", category="success")
    return response


@router.post("/profile/change-password")
async def profile_change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = PasswordChange(
            current_password=current_password,
            new_password=new_password,
            new_password_confirm=new_password_confirm,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request,
            "profile.html",
            context={"password_error": first_validation_error_message(exc)},
        )

    err = profile_service.change_user_password(db, user, data)
    if err:
        return templates.TemplateResponse(
            request, "profile.html", context={"password_error": err},
        )

    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(response, "Password changed", category="success")
    return response
