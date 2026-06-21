from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_active_group, require_role
from app.enums import Role
from app.models import Group
from app.services.audit_ui import audit_log_page_context
from app.templating import templates

router = APIRouter()


@router.get("/settings/audit")
async def audit_log_page(
    request: Request,
    db: Session = Depends(get_db),
    group: Group = Depends(get_active_group),
    _user=Depends(require_role(Role.admin.value)),
):
    ctx = audit_log_page_context(db, group.id)
    return templates.TemplateResponse(request, "audit_log.html", context=ctx)
