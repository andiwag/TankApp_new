"""German display labels for enum values shown in the UI."""

VEHICLE_TYPE_LABELS: dict[str, str] = {
    "car": "Auto",
    "motorcycle": "Motorrad",
    "tractor": "Traktor",
    "machine": "Maschine",
}

FUEL_TYPE_LABELS: dict[str, str] = {
    "diesel": "Diesel",
    "petrol": "Benzin",
}

ROLE_LABELS: dict[str, str] = {
    "admin": "Admin",
    "contributor": "Bearbeiter",
    "reader": "Leser",
}

USAGE_UNIT_LABELS: dict[str, str] = {
    "km": "km",
    "hours": "h",
}


def vehicle_type_label(value: str) -> str:
    return VEHICLE_TYPE_LABELS.get(value, value)


def fuel_type_label(value: str) -> str:
    return FUEL_TYPE_LABELS.get(value, value)


def role_label(value: str) -> str:
    return ROLE_LABELS.get(value, value)


def usage_unit_label(value: str) -> str:
    return USAGE_UNIT_LABELS.get(value, value)
