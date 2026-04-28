from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import set_session_cookie
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.responses import forbidden_response, not_found_response
from app.schemas import GroupCreate, first_validation_error_message
from app.services import groups as group_service
from app.services.invite_codes import InviteCodeGenerationError
from app.templating import templates

router = APIRouter()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _render_groups_with_error(
    request: Request,
    db: Session,
    user: User,
    active_group_id: int | None,
    error: str,
):
    context = group_service.user_groups_context(db, user, active_group_id)
    context["error"] = error
    return templates.TemplateResponse(request, "groups.html", context=context)


# ── Pages ────────────────────────────────────────────────────────────────────


@router.get("/groups")
async def groups_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_data = request.state.session_data
    context = group_service.user_groups_context(
        db, user, session_data.get("active_group_id")
    )
    return templates.TemplateResponse(request, "groups.html", context=context)


# ── Actions ──────────────────────────────────────────────────────────────────


@router.post("/groups/create")
async def create_group(
    request: Request,
    name: str = Form(""),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        group_data = GroupCreate(name=name)
    except ValidationError as exc:
        session_data = request.state.session_data
        return _render_groups_with_error(
            request, db, user,
            session_data.get("active_group_id"),
            first_validation_error_message(exc),
        )

    try:
        group = group_service.create_group(db, user, group_data)
    except InviteCodeGenerationError:
        session_data = request.state.session_data
        return _render_groups_with_error(
            request,
            db,
            user,
            session_data.get("active_group_id"),
            "Could not generate an invite code. Please try again.",
        )

    response = RedirectResponse(url="/groups", status_code=303)
    set_session_cookie(response, user.id, group.id)
    return response


@router.post("/groups/join")
async def join_group(
    request: Request,
    invite_code: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    session_data = request.state.session_data
    active_group_id = session_data.get("active_group_id")

    try:
        group = group_service.join_group_by_invite_code(db, user, invite_code)
    except group_service.GroupActionError as exc:
        return _render_groups_with_error(
            request, db, user, active_group_id,
            str(exc),
        )

    response = RedirectResponse(url="/groups", status_code=303)
    set_session_cookie(response, user.id, group.id)
    return response


@router.post("/groups/switch/{group_id}")
async def switch_group(
    request: Request,
    group_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    group = group_service.switchable_group_for_user(db, user, group_id)
    if not group:
        return forbidden_response()

    response = RedirectResponse(url="/dashboard", status_code=303)
    set_session_cookie(response, user.id, group.id)
    return response


@router.post("/groups/leave/{group_id}")
async def leave_group(
    request: Request,
    group_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        left = group_service.leave_group(db, user, group_id)
    except group_service.GroupActionError as exc:
        session_data = request.state.session_data
        return _render_groups_with_error(
            request, db, user,
            session_data.get("active_group_id"),
            str(exc),
        )
    if not left:
        return forbidden_response()

    session_data = request.state.session_data
    response = RedirectResponse(url="/groups", status_code=303)
    if session_data.get("active_group_id") == group_id:
        set_session_cookie(response, user.id, None)
    return response


@router.post("/groups/delete/{group_id}")
async def delete_group(
    request: Request,
    group_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        group = group_service.soft_delete_group_as_admin(db, user, group_id)
    except PermissionError:
        return forbidden_response()

    if not group:
        return not_found_response()

    session_data = request.state.session_data
    response = RedirectResponse(url="/groups", status_code=303)
    if session_data.get("active_group_id") == group_id:
        set_session_cookie(response, user.id, None)
    return response
