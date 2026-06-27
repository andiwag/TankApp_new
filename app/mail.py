import logging

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

from app.branding import PRODUCT_NAME
from app.config import settings

logger = logging.getLogger(__name__)


def _mail_connection() -> ConnectionConfig:
    return ConnectionConfig(
        MAIL_USERNAME=settings.MAIL_USERNAME,
        MAIL_PASSWORD=settings.MAIL_PASSWORD,
        MAIL_FROM=settings.MAIL_FROM,
        MAIL_PORT=settings.MAIL_PORT,
        MAIL_SERVER=settings.MAIL_SERVER,
        MAIL_STARTTLS=settings.MAIL_STARTTLS,
        MAIL_SSL_TLS=False,
        USE_CREDENTIALS=True,
    )


async def send_password_reset_email(to_email: str, reset_url: str) -> None:
    message = MessageSchema(
        subject=f"{PRODUCT_NAME} password reset",
        recipients=[to_email],
        body=(
            f"Use the link below to reset your {PRODUCT_NAME} password. "
            "It is valid for 1 hour.\n\n"
            f"{reset_url}\n"
        ),
        subtype=MessageType.plain,
    )
    try:
        await FastMail(_mail_connection()).send_message(message)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)


async def send_service_reminder_email(
    to_email: str,
    *,
    vehicle_name: str,
    description: str,
    due_detail: str,
) -> None:
    message = MessageSchema(
        subject=f"{PRODUCT_NAME} service reminder: {vehicle_name}",
        recipients=[to_email],
        body=(
            f"Service reminder for {vehicle_name}.\n\n"
            f"Task: {description}\n"
            f"Due: {due_detail}\n\n"
            f"Log in to {PRODUCT_NAME} to review maintenance records."
        ),
        subtype=MessageType.plain,
    )
    await FastMail(_mail_connection()).send_message(message)
