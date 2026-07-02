from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import clear_session_cookie
from app.database import get_db
from app.dependencies import get_current_user
from app.flash import set_flash
from app.models import User
from app.responses import not_found_response
from app.schemas import PasswordChange, UserUpdate, first_validation_error_message
from app.services import profile as profile_service
from app.services.sessions import (
    list_active_sessions,
    revoke_all_user_sessions,
    revoke_session,
)
from app.templating import templates

router = APIRouter()


def _profile_context(
    request: Request,
    db: Session,
    user: User,
    **extra,
) -> dict:
    return {
        "sessions": list_active_sessions(db, user.id),
        "current_session_id": request.state.session_data.get("session_id"),
        **extra,
    }


@router.get("/profile")
async def profile_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "profile.html",
        context=_profile_context(request, db, user),
    )


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
            context=_profile_context(
                request,
                db,
                user,
                profile_error=first_validation_error_message(exc),
            ),
        )

    err = profile_service.update_user_profile(db, user, data)
    if err:
        return templates.TemplateResponse(
            request,
            "profile.html",
            context=_profile_context(request, db, user, profile_error=err),
        )

    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(response, "Profil aktualisiert", category="success")
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
            context=_profile_context(
                request,
                db,
                user,
                password_error=first_validation_error_message(exc),
            ),
        )

    err = profile_service.change_user_password(db, user, data)
    if err:
        return templates.TemplateResponse(
            request,
            "profile.html",
            context=_profile_context(request, db, user, password_error=err),
        )

    current_session_id = request.state.session_data.get("session_id")
    revoke_all_user_sessions(db, user.id, except_session_id=current_session_id)
    db.commit()

    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(response, "Passwort geändert", category="success")
    return response


@router.post("/profile/sessions/{session_id}/revoke")
async def revoke_profile_session(
    session_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    sessions = list_active_sessions(db, user.id)
    if not any(session.id == session_id for session in sessions):
        return not_found_response()

    revoke_session(db, session_id)
    db.commit()

    if request.state.session_data.get("session_id") == session_id:
        response = RedirectResponse(url="/login", status_code=303)
        clear_session_cookie(response)
        return response

    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(response, "Sitzung beendet.", category="success")
    return response


@router.post("/profile/sessions/revoke-all")
async def revoke_all_profile_sessions(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    current_session_id = request.state.session_data.get("session_id")
    revoke_all_user_sessions(db, user.id, except_session_id=current_session_id)
    db.commit()
    response = RedirectResponse(url="/profile", status_code=303)
    set_flash(response, "Alle anderen Geräte abgemeldet.", category="success")
    return response


@router.get("/profile/export/data.json")
async def export_personal_data(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = profile_service.export_user_personal_data(db, user)
    return JSONResponse(
        payload,
        headers={
            "Content-Disposition": 'attachment; filename="tankly-my-data.json"',
        },
    )


@router.post("/profile/delete-account")
async def delete_account(
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    err = profile_service.delete_user_account(db, user, password)
    if err:
        return templates.TemplateResponse(
            request,
            "profile.html",
            context=_profile_context(request, db, user, delete_error=err),
        )

    response = RedirectResponse(url="/login", status_code=303)
    clear_session_cookie(response)
    set_flash(response, "Dein Konto wurde gelöscht.", category="success")
    return response
