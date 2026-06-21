"""Pure fuel consumption math (D-004). DB-agnostic."""

from app.enums import UsageUnit

FuelReading = tuple[float, float] | tuple[float, float, bool]


def _normalize_entry(entry: FuelReading) -> tuple[float, float, bool]:
    if len(entry) == 2:
        return (entry[0], entry[1], True)
    return entry


def average_consumption_for_vehicle(
    usage_unit: str,
    entries: list[FuelReading],
) -> float | None:
    """Return mean segment consumption, or None if there is no valid segment.

    Each entry is ``(usage_reading, fuel_amount_l)`` or
    ``(usage_reading, fuel_amount_l, full_tank)``. When ``full_tank`` is omitted it
    defaults to ``True``. Only full-tank fills anchor consumption segments.

    * ``km`` → liters / 100 km per segment, then arithmetic mean.
    * ``hours`` → liters / hour per segment, then arithmetic mean.
    """
    if not entries:
        return None

    sorted_e = sorted((_normalize_entry(e) for e in entries), key=lambda t: t[0])
    full_tank_readings = [(r, f) for r, f, ft in sorted_e if ft]
    segments: list[float] = []

    for i in range(1, len(full_tank_readings)):
        prev_reading, _ = full_tank_readings[i - 1]
        curr_reading, curr_fuel = full_tank_readings[i]
        delta = curr_reading - prev_reading
        if delta <= 0:
            continue

        if usage_unit == UsageUnit.km.value:
            segments.append(curr_fuel / delta * 100.0)
        elif usage_unit == UsageUnit.hours.value:
            segments.append(curr_fuel / delta)
        else:
            raise ValueError(f"Unknown usage_unit: {usage_unit!r}")

    if not segments:
        return None

    return sum(segments) / len(segments)


def consumption_unit_label(usage_unit: str) -> str:
    """Human-readable unit for average consumption (D-004). Unknown values → em dash."""
    if usage_unit == UsageUnit.km.value:
        return "L/100 km"
    if usage_unit == UsageUnit.hours.value:
        return "L/h"
    return "—"
