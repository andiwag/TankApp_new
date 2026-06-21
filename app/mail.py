import logging

from fastapi_mail import ConnectionConfig, FastMail, MessageSchema, MessageType

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
        subject="TankApp password reset",
        recipients=[to_email],
        body=(
            "Use the link below to reset your TankApp password. "
            "It is valid for 1 hour.\n\n"
            f"{reset_url}\n"
        ),
        subtype=MessageType.plain,
    )
    try:
        await FastMail(_mail_connection()).send_message(message)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)
