"""Billing-related email notifications."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.mail import send_payment_failed_email
from app.services.membership import list_group_admin_users

logger = logging.getLogger(__name__)


def _billing_settings_url() -> str:
    base = settings.BASE_URL.strip() or "http://localhost:8000"
    return f"{base.rstrip('/')}/settings/billing"


async def notify_group_payment_failed(db: Session, group_id: int) -> None:
    if not settings.mail_configured:
        logger.warning(
            "Mail not configured; skipping payment-failed notification for group %s",
            group_id,
        )
        return

    admins = list_group_admin_users(db, group_id)
    emails = [admin.email for admin in admins if admin.email]
    if not emails:
        return

    billing_url = _billing_settings_url()
    for email in emails:
        await send_payment_failed_email(email, billing_url=billing_url)
