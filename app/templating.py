from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.branding import PRODUCT_DOMAIN, PRODUCT_NAME, PRODUCT_URL
from app.config import settings

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["product_name"] = lambda: PRODUCT_NAME
templates.env.globals["product_domain"] = lambda: PRODUCT_DOMAIN
templates.env.globals["product_url"] = lambda: PRODUCT_URL
templates.env.globals["registration_invite_required"] = (
    lambda: settings.registration_invite_required
)
