from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group
from app.main import templates
from app.models import Group
from app.services.dashboard import get_dashboard_context

router = APIRouter()


@router.get("/dashboard")
async def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    ctx = get_dashboard_context(db, group.id)
    return templates.TemplateResponse(request, "dashboard.html", context=ctx)
