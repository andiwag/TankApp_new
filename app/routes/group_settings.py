from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.dependencies import get_active_group, require_role
from app.enums import Role
from app.flash import set_flash
from app.models import Group
from app.responses import not_found_response
from app.services import group_settings as settings_service
from app.services.invite_codes import InviteCodeGenerationError
from app.templating import templates

router = APIRouter()


def _settings_response(
    request: Request,
    db: Session,
    group: Group,
    *,
    error: str | None = None,
):
    context = settings_service.group_settings_context(db, request.state.user, group)
    context["error"] = error
    return templates.TemplateResponse(
        request,
        "group_settings.html",
        context=context,
    )


@router.get("/settings/group")
async def group_settings_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    return _settings_response(request, db, group)


@router.post("/settings/group/regenerate-code")
async def regenerate_invite_code_post(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.admin.value)),
):
    try:
        settings_service.regenerate_group_invite_code(db, group)
    except InviteCodeGenerationError:
        return _settings_response(
            request,
            db,
            group,
            error="Einladungscode konnte nicht erzeugt werden. Bitte erneut versuchen.",
        )
    response = RedirectResponse(url="/settings/group", status_code=303)
    set_flash(response, "Einladungscode neu erzeugt.")
    return response


@router.post("/settings/group/members/{user_id}/role")
async def change_member_role_post(
    request: Request,
    user_id: int,
    role: str = Form(""),
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    admin=Depends(require_role(Role.admin.value)),
):
    try:
        changed = settings_service.change_member_role(
            db,
            group_id=group.id,
            actor_user_id=admin.id,
            member_user_id=user_id,
            role=role,
        )
    except (PermissionError, ValueError) as exc:
        return _settings_response(request, db, group, error=str(exc))

    if not changed:
        return not_found_response()

    response = RedirectResponse(url="/settings/group", status_code=303)
    log_event(
        db,
        group.id,
        admin.id,
        "member.role_change",
        "user_group",
        user_id,
    )
    db.commit()
    set_flash(response, "Mitgliedsrolle aktualisiert.")
    return response


@router.post("/settings/group/members/{user_id}/remove")
async def remove_member_post(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    admin=Depends(require_role(Role.admin.value)),
):
    try:
        removed = settings_service.remove_member(
            db,
            group_id=group.id,
            actor_user_id=admin.id,
            member_user_id=user_id,
        )
    except PermissionError as exc:
        return _settings_response(request, db, group, error=str(exc))

    if not removed:
        return not_found_response()

    response = RedirectResponse(url="/settings/group", status_code=303)
    log_event(
        db,
        group.id,
        admin.id,
        "member.remove",
        "user_group",
        user_id,
    )
    db.commit()
    set_flash(response, "Mitglied entfernt.")
    return response
