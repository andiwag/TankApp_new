from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_entitlement
from app.models import Group
from app.services.analytics import get_analytics_context
from app.services.membership import group_page_capabilities
from app.templating import templates

router = APIRouter()


@router.get("/analytics")
async def analytics_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(require_entitlement("analytics")),
):
    ctx = get_analytics_context(db, group.id)
    ctx.update(group_page_capabilities(db, request.state.user, group.id))
    return templates.TemplateResponse(request, "analytics.html", context=ctx)
