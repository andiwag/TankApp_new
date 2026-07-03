from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.audit import log_event
from app.database import get_db
from app.dependencies import require_platform_admin
from app.models import Group, User
from app.responses import not_found_response
from app.services import platform_admin as platform_service
from app.services.sessions import refresh_session_cookie
from app.templating import templates

router = APIRouter(prefix="/platform", tags=["platform"])


@router.get("")
async def platform_root(
    user: User = Depends(require_platform_admin),
):
    return RedirectResponse(url="/platform/farms", status_code=303)


@router.get("/farms")
async def platform_farms_page(
    request: Request,
    status: str = Query("active"),
    q: str | None = Query(None),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if status not in ("active", "deleted", "all"):
        status = "active"
    context = platform_service.farms_page_context(db, status=status, search=q)
    return templates.TemplateResponse(
        request,
        "platform_farms.html",
        context=context,
    )


@router.get("/farms/{group_id}")
async def platform_farm_detail_page(
    request: Request,
    group_id: int,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    context = platform_service.farm_detail_context(db, group_id)
    if context is None:
        return not_found_response()

    log_event(
        db,
        group_id=group_id,
        user_id=user.id,
        action="platform.farm.detail",
        entity_type="group",
        entity_id=group_id,
    )
    db.commit()

    return templates.TemplateResponse(
        request,
        "platform_farm_detail.html",
        context=context,
    )


@router.post("/farms/{group_id}/enter")
async def platform_enter_farm_view(
    request: Request,
    group_id: int,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        return not_found_response()

    session_data = request.state.session_data
    response = RedirectResponse(url="/dashboard", status_code=303)
    refresh_session_cookie(
        response,
        user.id,
        group.id,
        session_id=session_data["session_id"],
        platform_view=True,
        platform_view_group_id=group.id,
    )
    log_event(
        db,
        group_id=group.id,
        user_id=user.id,
        action="platform.farm.enter",
        entity_type="group",
        entity_id=group.id,
    )
    db.commit()
    return response


@router.post("/exit-view")
async def platform_exit_farm_view(
    request: Request,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    session_data = request.state.session_data
    exit_group_id = session_data.get("platform_view_group_id")
    if exit_group_id:
        log_event(
            db,
            group_id=exit_group_id,
            user_id=user.id,
            action="platform.farm.exit",
            entity_type="group",
            entity_id=exit_group_id,
        )
        db.commit()

    response = RedirectResponse(url="/platform/farms", status_code=303)
    refresh_session_cookie(
        response,
        user.id,
        None,
        session_id=session_data["session_id"],
        platform_view=False,
    )
    return response


@router.get("/users")
async def platform_users_page(
    request: Request,
    q: str | None = Query(None),
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    if q and q.strip():
        log_event(
            db,
            group_id=None,
            user_id=user.id,
            action="platform.user.search",
            entity_type="user",
            entity_id=0,
        )
        db.commit()

    context = platform_service.users_page_context(db, q)
    return templates.TemplateResponse(
        request,
        "platform_users.html",
        context=context,
    )


@router.get("/users/{user_id}")
async def platform_user_detail_page(
    request: Request,
    user_id: int,
    user: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
):
    context = platform_service.user_detail_context(db, user_id)
    if context is None:
        return not_found_response()

    log_event(
        db,
        group_id=None,
        user_id=user.id,
        action="platform.user.detail",
        entity_type="user",
        entity_id=user_id,
    )
    db.commit()

    return templates.TemplateResponse(
        request,
        "platform_user_detail.html",
        context=context,
    )
