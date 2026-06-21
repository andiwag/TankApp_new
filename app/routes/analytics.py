from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group
from app.models import Group
from app.services.analytics import get_analytics_context
from app.templating import templates

router = APIRouter()


@router.get("/analytics")
async def analytics_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    ctx = get_analytics_context(db, group.id)
    return templates.TemplateResponse(request, "analytics.html", context=ctx)
