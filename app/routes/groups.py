import secrets
import string
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.auth import set_session_cookie
from app.database import get_db
from app.dependencies import get_current_user
from app.enums import Role
from app.main import templates
from app.models import Group, User, UserGroup
from app.schemas import GroupCreate, first_validation_error_message

router = APIRouter()

_INVITE_CODE_CHARS = string.ascii_uppercase + string.digits
_INVITE_CODE_LENGTH = 5
_INVITE_CODE_PREFIX = "FARM-"
_MAX_INVITE_CODE_RETRIES = 10


# ── Helpers ──────────────────────────────────────────────────────────────────


def _generate_invite_code() -> str:
    suffix = "".join(
        secrets.choice(_INVITE_CODE_CHARS) for _ in range(_INVITE_CODE_LENGTH)
    )
    return f"{_INVITE_CODE_PREFIX}{suffix}"


def _generate_unique_invite_code(db: Session) -> str:
    for _ in range(_MAX_INVITE_CODE_RETRIES):
        code = _generate_invite_code()
        existing = db.query(Group).filter(Group.invite_code == code).first()
        if not existing:
            return code
    raise RuntimeError("Failed to generate unique invite code")


def _user_groups_context(
    db: Session, user: User, active_group_id: int | None
) -> dict:
    rows = (
        db.query(Group, UserGroup.role)
        .join(UserGroup, UserGroup.group_id == Group.id)
        .filter(
            UserGroup.user_id == user.id,
            Group.deleted_at == None,  # noqa: E711
        )
        .all()
    )
    return {
        "groups": [{"group": g, "role": r} for g, r in rows],
        "active_group_id": active_group_id,
    }


def _render_groups_with_error(
    request: Request,
    db: Session,
    user: User,
    active_group_id: int | None,
    error: str,
):
    context = _user_groups_context(db, user, active_group_id)
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
    context = _user_groups_context(db, user, session_data.get("active_group_id"))
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

    invite_code = _generate_unique_invite_code(db)

    group = Group(
        name=group_data.name,
        invite_code=invite_code,
        created_by=user.id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)

    db.add(UserGroup(user_id=user.id, group_id=group.id, role=Role.admin.value))
    db.commit()

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

    group = db.query(Group).filter(
        Group.invite_code == invite_code,
        Group.deleted_at == None,  # noqa: E711
    ).first()

    if not group:
        return _render_groups_with_error(
            request, db, user, active_group_id,
            "Invalid invite code",
        )

    existing = db.query(UserGroup).filter(
        UserGroup.user_id == user.id,
        UserGroup.group_id == group.id,
    ).first()

    if existing:
        return _render_groups_with_error(
            request, db, user, active_group_id,
            "You are already a member of this group",
        )

    db.add(UserGroup(
        user_id=user.id,
        group_id=group.id,
        role=Role.contributor.value,
    ))
    db.commit()

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
    membership = db.query(UserGroup).filter(
        UserGroup.user_id == user.id,
        UserGroup.group_id == group_id,
    ).first()

    if not membership:
        return Response("Forbidden", status_code=403)

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at == None,  # noqa: E711
    ).first()

    if not group:
        return Response("Forbidden", status_code=403)

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
    membership = db.query(UserGroup).filter(
        UserGroup.user_id == user.id,
        UserGroup.group_id == group_id,
    ).first()

    if not membership:
        return Response("Forbidden", status_code=403)

    if membership.role == Role.admin.value:
        admin_count = db.query(UserGroup).filter(
            UserGroup.group_id == group_id,
            UserGroup.role == Role.admin.value,
        ).count()
        if admin_count <= 1:
            session_data = request.state.session_data
            return _render_groups_with_error(
                request, db, user,
                session_data.get("active_group_id"),
                "You cannot leave as the sole admin. Promote another admin first.",
            )

    db.delete(membership)
    db.commit()

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
    membership = db.query(UserGroup).filter(
        UserGroup.user_id == user.id,
        UserGroup.group_id == group_id,
    ).first()

    if not membership or membership.role != Role.admin.value:
        return Response("Forbidden", status_code=403)

    group = db.query(Group).filter(
        Group.id == group_id,
        Group.deleted_at == None,  # noqa: E711
    ).first()

    if not group:
        return Response("Not found", status_code=404)

    group.deleted_at = datetime.now(timezone.utc)
    db.commit()

    session_data = request.state.session_data
    response = RedirectResponse(url="/groups", status_code=303)
    if session_data.get("active_group_id") == group_id:
        set_session_cookie(response, user.id, None)
    return response
