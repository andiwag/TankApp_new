"""Marketing page helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.config import settings

if TYPE_CHECKING:
    from app.models import User


def landing_pricing_ctas(*, trial_days: int | None = None) -> dict[str, dict[str, str]]:
    days = trial_days if trial_days is not None else settings.STRIPE_TRIAL_DAYS
    pro_label = (
        f"{days} Tage Pro testen"
        if settings.stripe_enabled and days > 0
        else "Pro testen"
    )
    return {
        "free": {"href": "/register", "label": "Kostenlos starten"},
        "pro": {"href": "/register", "label": pro_label},
        "farm": {"href": "/register", "label": "Farm wählen"},
    }


def pricing_upgrade_href(user: User | None, *, is_group_admin: bool = False) -> str:
    if user is None:
        return "/register"
    if is_group_admin:
        return "/settings/billing"
    return "/groups"
