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
        subject=f"{PRODUCT_NAME} – Passwort zurücksetzen",
        recipients=[to_email],
        body=(
            f"Nutze den folgenden Link, um dein {PRODUCT_NAME}-Passwort zurückzusetzen. "
            "Er ist 1 Stunde gültig.\n\n"
            f"{reset_url}\n"
        ),
        subtype=MessageType.plain,
    )
    try:
        await FastMail(_mail_connection()).send_message(message)
    except Exception:
        logger.exception("Failed to send password reset email to %s", to_email)


async def send_payment_failed_email(to_email: str, *, billing_url: str) -> None:
    message = MessageSchema(
        subject=f"{PRODUCT_NAME} – Zahlung fehlgeschlagen",
        recipients=[to_email],
        body=(
            f"Die letzte Zahlung für dein {PRODUCT_NAME}-Abo konnte nicht eingezogen werden.\n\n"
            "Bitte aktualisiere deine Zahlungsmethode, damit dein Tarif aktiv bleibt:\n"
            f"{billing_url}\n"
        ),
        subtype=MessageType.plain,
    )
    try:
        await FastMail(_mail_connection()).send_message(message)
    except Exception:
        logger.exception("Failed to send payment-failed email to %s", to_email)


async def send_service_reminder_email(
    to_email: str,
    *,
    vehicle_name: str,
    description: str,
    due_detail: str,
) -> None:
    message = MessageSchema(
        subject=f"{PRODUCT_NAME} – Servicehinweis: {vehicle_name}",
        recipients=[to_email],
        body=(
            f"Servicehinweis für {vehicle_name}.\n\n"
            f"Aufgabe: {description}\n"
            f"Fällig: {due_detail}\n\n"
            f"Melde dich bei {PRODUCT_NAME} an, um Wartungseinträge zu prüfen."
        ),
        subtype=MessageType.plain,
    )
    await FastMail(_mail_connection()).send_message(message)
