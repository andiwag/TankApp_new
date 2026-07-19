from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.branding import (
    LOGO_STATIC_PATH,
    PRODUCT_DOMAIN,
    PRODUCT_NAME,
    PRODUCT_URL,
    PRODUCT_VERSION,
)
from app.company import company_display_name, company_info, legal_pages_ready
from app.config import settings
from app.dependencies import ROLE_HIERARCHY
from app.display_labels import (
    fuel_type_label,
    role_label,
    tank_movement_type_label,
    usage_unit_label,
    vehicle_type_label,
)
from app.enums import Role
from app.formatting import format_date_de, format_datetime_de, format_number_de

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def user_can_edit(request) -> bool:
    if getattr(request.state, "platform_view", False):
        return False
    role = getattr(request.state, "user_role", None)
    if not role:
        return False
    return ROLE_HIERARCHY.get(role, 0) >= ROLE_HIERARCHY[Role.contributor.value]


def group_feature_enabled(request, feature: str) -> bool:
    if feature == "maintenance":
        return bool(getattr(request.state, "can_maintenance", False))
    if feature == "analytics":
        return bool(getattr(request.state, "can_analytics", False))
    return False


templates.env.globals["user_can_edit"] = user_can_edit
templates.env.globals["group_feature_enabled"] = group_feature_enabled
templates.env.globals["product_name"] = lambda: PRODUCT_NAME
templates.env.globals["product_version"] = lambda: PRODUCT_VERSION
templates.env.globals["product_logo_url"] = lambda: LOGO_STATIC_PATH
templates.env.globals["format_date"] = format_date_de
templates.env.globals["format_datetime"] = format_datetime_de
templates.env.globals["format_number"] = format_number_de
templates.env.globals["vehicle_type_label"] = vehicle_type_label
templates.env.globals["fuel_type_label"] = fuel_type_label
templates.env.globals["role_label"] = role_label
templates.env.globals["usage_unit_label"] = usage_unit_label
templates.env.globals["tank_movement_type_label"] = tank_movement_type_label
templates.env.globals["product_domain"] = lambda: PRODUCT_DOMAIN
templates.env.globals["product_url"] = lambda: PRODUCT_URL
templates.env.globals["registration_invite_required"] = lambda: (
    settings.registration_invite_required
)
templates.env.globals["company_info"] = company_info
templates.env.globals["company_display_name"] = company_display_name
templates.env.globals["legal_pages_ready"] = legal_pages_ready
templates.env.globals["stripe_enabled"] = lambda: settings.stripe_enabled
templates.env.globals["stripe_checkout_available"] = lambda: (
    settings.stripe_checkout_available
)
templates.env.globals["stripe_trial_days"] = lambda: settings.STRIPE_TRIAL_DAYS
