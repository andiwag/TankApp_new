from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.branding import LOGO_STATIC_PATH, PRODUCT_DOMAIN, PRODUCT_NAME, PRODUCT_URL
from app.config import settings
from app.display_labels import (
    fuel_type_label,
    role_label,
    tank_movement_type_label,
    usage_unit_label,
    vehicle_type_label,
)
from app.formatting import format_date_de, format_datetime_de, format_number_de

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["product_name"] = lambda: PRODUCT_NAME
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
