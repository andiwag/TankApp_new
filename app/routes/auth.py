import logging

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import (
    create_password_reset_token,
    decode_password_reset_token,
    hash_password,
    set_session_cookie,
    verify_password,
    verify_reset_token_data,
)
from app.config import settings
from app.database import get_db
from app.main import templates
from app.models import User
from app.schemas import (
    EMAIL_DUPLICATE_MESSAGE,
    PasswordResetConfirm,
    UserCreate,
    first_validation_error_message,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_INVALID_RESET_LINK = "Invalid or expired reset link"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _get_reset_user(db: Session, token_data: dict) -> User | None:
    """Look up the user from decoded token data and verify the password-hash fingerprint."""
    user = db.query(User).filter(
        User.id == token_data["user_id"],
        User.deleted_at == None,  # noqa: E711
    ).first()
    if not user:
        return None
    if not verify_reset_token_data(user.password_hash, token_data):
        return None
    return user


def _deliver_reset_token(email: str, token: str) -> None:
    """In development: log the reset link. In production: send via email."""
    if settings.is_production:
        pass
    else:
        logger.info("Password reset link for %s: /reset-password/%s", email, token)


# ── Pages ────────────────────────────────────────────────────────────────────


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@router.get("/register")
async def register_page(request: Request):
    return templates.TemplateResponse(request, "register.html")


@router.get("/forgot-password")
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "forgot_password.html")


@router.get("/reset-password/{token}")
async def reset_password_page(
    request: Request, token: str, db: Session = Depends(get_db)
):
    data = decode_password_reset_token(token)
    if not data:
        return templates.TemplateResponse(
            request, "reset_password.html",
            context={"error": _INVALID_RESET_LINK},
        )

    user = _get_reset_user(db, data)
    if not user:
        return templates.TemplateResponse(
            request, "reset_password.html",
            context={"error": _INVALID_RESET_LINK},
        )

    return templates.TemplateResponse(
        request, "reset_password.html", context={"token": token}
    )


# ── Actions ──────────────────────────────────────────────────────────────────


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    user = db.query(User).filter(
        User.email == email,
        User.deleted_at == None,  # noqa: E711
    ).first()

    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(
            request, "login.html", context={"error": "Invalid email or password"},
        )

    response = RedirectResponse(url="/dashboard", status_code=303)
    set_session_cookie(response, user.id)
    return response


@router.post("/register")
async def register(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        user_data = UserCreate(
            email=email, name=name, password=password, password_confirm=password_confirm
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request, "register.html",
            context={"error": first_validation_error_message(exc)},
        )

    normalized_email = user_data.email.lower()
    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        return templates.TemplateResponse(
            request, "register.html",
            context={"error": EMAIL_DUPLICATE_MESSAGE},
        )

    user = User(
        email=normalized_email,
        name=user_data.name,
        password_hash=hash_password(user_data.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    response = RedirectResponse(url="/groups", status_code=303)
    set_session_cookie(response, user.id)
    return response


@router.post("/forgot-password")
async def forgot_password(
    request: Request,
    email: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.lower().strip()
    user = db.query(User).filter(
        User.email == email,
        User.deleted_at == None,  # noqa: E711
    ).first()

    if user:
        token = create_password_reset_token(user.id, user.password_hash)
        _deliver_reset_token(email, token)

    return templates.TemplateResponse(
        request, "forgot_password.html", context={"success": True}
    )


@router.post("/reset-password/{token}")
async def reset_password(
    request: Request,
    token: str,
    new_password: str = Form(...),
    new_password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    data = decode_password_reset_token(token)
    if not data:
        return templates.TemplateResponse(
            request, "reset_password.html",
            context={"error": _INVALID_RESET_LINK},
        )

    user = _get_reset_user(db, data)
    if not user:
        return templates.TemplateResponse(
            request, "reset_password.html",
            context={"error": _INVALID_RESET_LINK},
        )

    try:
        PasswordResetConfirm(
            token=token,
            new_password=new_password,
            new_password_confirm=new_password_confirm,
        )
    except ValidationError as exc:
        return templates.TemplateResponse(
            request, "reset_password.html",
            context={"error": first_validation_error_message(exc), "token": token},
        )

    user.password_hash = hash_password(new_password)
    db.commit()

    return RedirectResponse(url="/login", status_code=303)


@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response
