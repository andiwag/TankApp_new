from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import settings

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["registration_invite_required"] = (
    lambda: settings.registration_invite_required
)
