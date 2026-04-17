"""Very small command-line helper for mission unit conversions.

Usage
-----
python examples/mission_unit_convert.py 30 m_s kts
python examples/mission_unit_convert.py 500 ft/min m_s
python examples/mission_unit_convert.py 25 sqft m2
python examples/mission_unit_convert.py 30 lbm kg
python examples/mission_unit_convert.py 30 lbf n
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ac_design_toolbox.mission.units import convert_value, normalize_unit

LB_ALIASES = {"lb", "lbs", "pound", "pounds"}
MASS_UNITS = {"kg", "lbm"}
FORCE_UNITS = {"n", "lbf"}


def _normalize_if_supported(unit: str) -> str | None:
    """Return a canonical unit when supported, otherwise ``None``."""
    try:
        return normalize_unit(unit)
    except ValueError:
        return None


def _lb_note(raw_unit: str, canonical_unit: str | None) -> str | None:
    """Return a note when the user typed an ambiguous pound-mass alias."""
    if raw_unit.strip().lower() in LB_ALIASES and canonical_unit == "lbm":
        return "Note: plain 'lb' is interpreted as 'lbm' (mass). Use 'lbf' for force."

    return None


def _friendly_lb_error(raw_from_unit: str, raw_to_unit: str, value: float) -> str | None:
    """Return a friendlier message for common lb/lbm/lbf confusion cases."""
    canonical_from = _normalize_if_supported(raw_from_unit)
    canonical_to = _normalize_if_supported(raw_to_unit)

    if canonical_from is None or canonical_to is None:
        return None

    messages: list[str] = []
    from_note = _lb_note(raw_from_unit, canonical_from)
    to_note = _lb_note(raw_to_unit, canonical_to)
    if from_note is not None:
        messages.append(from_note)
    if to_note is not None and to_note not in messages:
        messages.append(to_note)

    if canonical_from in MASS_UNITS and canonical_to in FORCE_UNITS:
        messages.append(
            "Mass-to-force is not treated as a pure unit conversion here, so that request is rejected."
        )
        messages.append(f"If you meant force/weight, try: python mission_unit_convert.py {value:g} lbf {canonical_to}")
        messages.append(f"If you meant mass, try: python mission_unit_convert.py {value:g} lbm kg")
    elif canonical_from in FORCE_UNITS and canonical_to in MASS_UNITS:
        messages.append(
            "Force-to-mass is not treated as a pure unit conversion here, so that request is rejected."
        )
        messages.append(f"If you meant force, try: python mission_unit_convert.py {value:g} {canonical_from} lbf")
        messages.append(f"If you meant mass, try: python mission_unit_convert.py {value:g} lbm {canonical_to}")

    if not messages:
        return None

    return "\n".join(messages)


def main() -> int:
    """Convert one mission-boundary quantity between supported units."""
    if len(sys.argv) != 4:
        print("Usage: python examples/mission_unit_convert.py <value> <from_unit> <to_unit>")
        return 1

    value = float(sys.argv[1])
    raw_from_unit = sys.argv[2]
    raw_to_unit = sys.argv[3]

    try:
        converted_value = convert_value(value, raw_from_unit, raw_to_unit)
        canonical_from = normalize_unit(raw_from_unit)
        canonical_to = normalize_unit(raw_to_unit)
    except ValueError as exc:
        print(exc)
        friendly_message = _friendly_lb_error(raw_from_unit, raw_to_unit, value)
        if friendly_message is not None:
            print(friendly_message)
        return 1

    print(f"{value} {canonical_from} = {converted_value} {canonical_to}")

    note = _lb_note(raw_from_unit, canonical_from)
    if note is not None:
        print(note)

    note = _lb_note(raw_to_unit, canonical_to)
    if note is not None:
        print(note)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
