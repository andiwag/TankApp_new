from io import BytesIO
from urllib.parse import urlsplit

import segno

from app.config import settings

_QR_CONFIGURATION_ERROR = "BASE_URL must be a configured HTTP(S) origin."


class QrConfigurationError(ValueError):
    pass


class QrGenerationError(RuntimeError):
    pass


def validate_qr_configuration() -> None:
    base_url = settings.BASE_URL.strip().rstrip("/")
    if any(character.isspace() or ord(character) < 32 for character in base_url):
        raise QrConfigurationError(_QR_CONFIGURATION_ERROR)

    try:
        parsed = urlsplit(base_url)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as exc:
        raise QrConfigurationError(_QR_CONFIGURATION_ERROR) from exc

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or hostname is None
        or (port is not None and port < 1)
        or (parsed.netloc.endswith(":") and port is None)
        or parsed.path
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or (settings.is_production and parsed.scheme != "https")
    ):
        raise QrConfigurationError(_QR_CONFIGURATION_ERROR)


def vehicle_quick_capture_url(group_id: int, vehicle_id: int) -> str:
    base_url = settings.BASE_URL.strip().rstrip("/")
    validate_qr_configuration()
    return f"{base_url}/fuel/quick/{group_id}/{vehicle_id}"


def vehicle_qr_svg(group_id: int, vehicle_id: int) -> str:
    url = vehicle_quick_capture_url(group_id, vehicle_id)
    try:
        code = segno.make_qr(url, error="M")
        svg = BytesIO()
        code.save(svg, kind="svg", scale=6, border=4, xmldecl=False)
        return svg.getvalue().decode("utf-8")
    except segno.DataOverflowError as exc:
        raise QrGenerationError(
            "The configured BASE_URL is too long for a vehicle QR code."
        ) from exc
