"""Legal entity details for Impressum, Datenschutz, and AGB."""

from dataclasses import dataclass

from app.branding import PRODUCT_DOMAIN, PRODUCT_NAME
from app.config import settings


@dataclass(frozen=True)
class CompanyInfo:
    legal_name: str
    street: str
    city: str
    email: str
    phone: str
    uid: str
    company_register: str
    register_court: str
    trade_authority: str
    jurisdiction: str
    hosting_provider: str
    mail_provider: str


def company_info() -> CompanyInfo:
    return CompanyInfo(
        legal_name=settings.COMPANY_LEGAL_NAME.strip(),
        street=settings.COMPANY_STREET.strip(),
        city=settings.COMPANY_CITY.strip(),
        email=settings.COMPANY_EMAIL.strip() or f"info@{PRODUCT_DOMAIN}",
        phone=settings.COMPANY_PHONE.strip(),
        uid=settings.COMPANY_UID.strip(),
        company_register=settings.COMPANY_REGISTER.strip(),
        register_court=settings.COMPANY_REGISTER_COURT.strip(),
        trade_authority=settings.COMPANY_TRADE_AUTHORITY.strip(),
        jurisdiction=settings.COMPANY_JURISDICTION.strip() or "Wien",
        hosting_provider=settings.HOSTING_PROVIDER.strip() or "Northflank",
        mail_provider=settings.MAIL_PROVIDER.strip() or "Brevo",
    )


def legal_pages_ready() -> bool:
    info = company_info()
    return bool(info.legal_name and info.street and info.city and info.email)


def company_display_name() -> str:
    info = company_info()
    return info.legal_name or PRODUCT_NAME
