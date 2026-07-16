from datetime import date

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group
from app.models import Group
from app.services.dashboard import get_dashboard_context
from app.services.reminders import list_group_reminders
from app.templating import templates

router = APIRouter()


@router.get("/dashboard")
async def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
):
    ctx = get_dashboard_context(db, request.state.user, group.id)
    reminders = list_group_reminders(db, group.id)
    today = date.today()
    for reminder in reminders:
        next_date = reminder.get("next_service_date")
        reminder["days_until"] = (next_date - today).days if next_date else None
    ctx["service_reminders"] = reminders
    return templates.TemplateResponse(request, "dashboard.html", context=ctx)
