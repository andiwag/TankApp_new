"""Small helpers for converting HTML form strings before Pydantic validation."""

from datetime import date


def parse_int(value: str, field_label: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{field_label} muss ausgewählt werden") from exc


def parse_float(value: str, field_label: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"{field_label} muss eine Zahl sein") from exc


def parse_date(value: str, field_label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_label} muss ein gültiges Datum sein") from exc


def parse_bool(value: str) -> bool:
    return value in ("1", "on", "true", "yes")


def parse_optional_float(value: str, field_label: str) -> float | None:
    stripped = value.strip()
    if not stripped:
        return None
    parsed = parse_float(stripped, field_label)
    if parsed < 0:
        raise ValueError(f"{field_label} darf nicht negativ sein")
    return parsed


def parse_optional_date(value: str, field_label: str) -> date | None:
    stripped = value.strip()
    if not stripped:
        return None
    return parse_date(stripped, field_label)
