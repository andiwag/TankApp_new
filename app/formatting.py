"""German locale display formatting for dates and numbers."""

from datetime import date, datetime


def format_date_de(value: date) -> str:
    return value.strftime("%d.%m.%Y")


def format_datetime_de(value: datetime) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def format_number_de(value: float, decimals: int = 1) -> str:
    formatted = f"{value:,.{decimals}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
