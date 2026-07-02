"""Shared helpers for parsing German-formatted numbers in HTML tests."""


def parse_display_number(value: str) -> float:
    stripped = value.strip()
    if "," in stripped:
        stripped = stripped.replace(".", "").replace(",", ".")
    return float(stripped)
