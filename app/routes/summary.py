from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group
from app.main import templates
from app.models import Group
from app.services.summary import get_summary_context

router = APIRouter()


@router.get("/summary")
async def summary_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    ctx = get_summary_context(db, group.id)
    return templates.TemplateResponse(request, "summary.html", context=ctx)
