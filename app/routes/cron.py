import logging
import secrets

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.mail import send_service_reminder_email
from app.services.reminders import (
    list_due_email_reminders,
    release_reminder_claim,
    try_claim_reminder_send,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _cron_authorized(authorization: str | None) -> bool:
    if not settings.CRON_SECRET or not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    return secrets.compare_digest(token, settings.CRON_SECRET)


@router.post("/cron/service-reminders")
async def send_service_reminders_cron(
    db: Session = Depends(get_db),
    authorization: str | None = Header(None),
):
    if not _cron_authorized(authorization):
        return JSONResponse({"error": "forbidden"}, status_code=403)

    if not settings.mail_configured:
        logger.warning("Service reminder cron skipped: mail not configured")
        return {"sent": 0, "skipped": "mail_not_configured"}

    due = list_due_email_reminders(db)
    sent = 0
    processed = 0
    for log, admins, due_detail in due:
        claimed = try_claim_reminder_send(db, log.id)
        if not claimed:
            continue
        processed += 1
        successes = 0
        for admin in admins:
            try:
                await send_service_reminder_email(
                    admin.email,
                    vehicle_name=claimed.vehicle.name,
                    description=claimed.description,
                    due_detail=due_detail,
                )
                sent += 1
                successes += 1
            except Exception:
                logger.exception(
                    "Service reminder email failed for maintenance log %s to %s",
                    log.id,
                    admin.email,
                )
        if successes == 0:
            release_reminder_claim(db, log.id)

    return {"sent": sent, "logs": processed}
