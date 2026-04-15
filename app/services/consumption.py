"""Pure fuel consumption math (D-004). DB-agnostic."""

from app.enums import UsageUnit


def average_consumption_for_vehicle(
    usage_unit: str,
    entries: list[tuple[float, float]],
) -> float | None:
    """Return mean segment consumption, or None if there is no valid segment.

    ``entries`` are ``(usage_reading, fuel_amount_l)`` for one vehicle (each fill).
    Rows are sorted by ``usage_reading`` internally.

    * ``km`` → liters / 100 km per segment, then arithmetic mean.
    * ``hours`` → liters / hour per segment, then arithmetic mean.

    Segments with a non-positive odometer/hour delta are skipped (duplicate or
    reversed readings).
    """
    if not entries:
        return None

    sorted_e = sorted(entries, key=lambda t: t[0])
    segments: list[float] = []

    for i in range(1, len(sorted_e)):
        prev_reading, _ = sorted_e[i - 1]
        curr_reading, curr_fuel = sorted_e[i]
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
