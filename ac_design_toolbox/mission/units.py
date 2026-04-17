"""Small explicit units helpers for the mission public boundary.

The mission package accepts a limited set of Aviary-style quantity inputs at
its public dataclass boundaries. Values are normalized immediately into
documented computational units so the runtime mission math can stay on plain
floats without carrying unit wrapper objects through the solver paths.
"""

from __future__ import annotations

from math import isfinite
from typing import Final

QuantityScalar = float | int
QuantityPair = tuple[QuantityScalar, str] | list[QuantityScalar | str]
QuantityInput = QuantityScalar | QuantityPair

_UNIT_ALIASES: Final[dict[str, str]] = {
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "ft": "ft",
    "foot": "ft",
    "feet": "ft",
    "m_s": "m_s",
    "m/s": "m_s",
    "meter_per_second": "m_s",
    "meters_per_second": "m_s",
    "metre_per_second": "m_s",
    "metres_per_second": "m_s",
    "ft_s": "ft_s",
    "ft/s": "ft_s",
    "foot_per_second": "ft_s",
    "feet_per_second": "ft_s",
    "kts": "kts",
    "kt": "kts",
    "knot": "kts",
    "knots": "kts",
    "ft_min": "ft_min",
    "ft/min": "ft_min",
    "foot_per_minute": "ft_min",
    "feet_per_minute": "ft_min",
    "m2": "m2",
    "m^2": "m2",
    "square_meter": "m2",
    "square_meters": "m2",
    "square_metre": "m2",
    "square_metres": "m2",
    "ft2": "ft2",
    "ft^2": "ft2",
    "sqft": "ft2",
    "square_foot": "ft2",
    "square_feet": "ft2",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "lbm": "lbm",
    "lb": "lbm",
    "lbs": "lbm",
    "pound": "lbm",
    "pounds": "lbm",
    "n": "n",
    "newton": "n",
    "newtons": "n",
    "lbf": "lbf",
    "w": "w",
    "watt": "w",
    "watts": "w",
    "deg": "deg",
    "degree": "deg",
    "degrees": "deg",
    "s": "s",
    "sec": "s",
    "second": "s",
    "seconds": "s",
    "min": "min",
    "minute": "min",
    "minutes": "min",
    "hr": "hr",
    "hrs": "hr",
    "hour": "hr",
    "hours": "hr",
    "pa": "pa",
    "pascal": "pa",
    "pascals": "pa",
    "kg_m3": "kg_m3",
    "kg/m3": "kg_m3",
    "kg/m^3": "kg_m3",
    "degf": "degF",
    "deg_f": "degF",
    "degfahrenheit": "degF",
    "degc": "degC",
    "deg_c": "degC",
    "degcelsius": "degC",
}

_FAMILY_FACTORS_TO_SI: Final[dict[str, dict[str, float]]] = {
    "length": {
        "m": 1.0,
        "ft": 0.3048,
    },
    "speed": {
        "m_s": 1.0,
        "ft_s": 0.3048,
        "kts": 0.5144444444444445,
    },
    "rate": {
        "m_s": 1.0,
        "ft_s": 0.3048,
        "ft_min": 0.3048 / 60.0,
    },
    "area": {
        "m2": 1.0,
        "ft2": 0.09290304,
    },
    "mass": {
        "kg": 1.0,
        "lbm": 0.45359237,
    },
    "force": {
        "n": 1.0,
        "lbf": 4.4482216152605,
    },
    "power": {
        "w": 1.0,
    },
    "angle": {
        "deg": 1.0,
    },
    "time": {
        "s": 1.0,
        "min": 60.0,
        "hr": 3600.0,
    },
    "pressure": {
        "pa": 1.0,
    },
    "density": {
        "kg_m3": 1.0,
    },
    "temperature_delta": {
        "degF": 5.0 / 9.0,
        "degC": 1.0,
    },
}

def _require_finite_scalar(name: str, value: QuantityScalar) -> float:
    """Return a finite float scalar for unit conversion and validation."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a scalar number.")

    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")

    return scalar_value


def normalize_unit(unit: str) -> str:
    """Return the canonical spelling for a supported unit string."""
    if not isinstance(unit, str):
        raise TypeError("unit must be a string.")

    stripped_unit = unit.strip()
    if not stripped_unit:
        raise ValueError("unit must be a non-empty string.")

    canonical_unit = _UNIT_ALIASES.get(stripped_unit.lower())
    if canonical_unit is None:
        raise ValueError(f"Unsupported unit {unit!r}.")

    return canonical_unit


def convert_value(value: float, from_unit: str, to_unit: str) -> float:
    """Convert a finite scalar between two supported units in the same family."""
    scalar_value = _require_finite_scalar("value", value)
    normalized_from = normalize_unit(from_unit)
    normalized_to = normalize_unit(to_unit)

    for family_units in _FAMILY_FACTORS_TO_SI.values():
        if normalized_from in family_units and normalized_to in family_units:
            from_factor = family_units[normalized_from]
            to_factor = family_units[normalized_to]
            return scalar_value * from_factor / to_factor

    raise ValueError(f"Cannot convert from {normalized_from!r} to {normalized_to!r}.")


def _require_supported_family(family: str) -> dict[str, float]:
    """Return the explicit conversion table for a supported unit family."""
    try:
        return _FAMILY_FACTORS_TO_SI[family]
    except KeyError as exc:
        raise ValueError(f"Unsupported unit family {family!r}.") from exc


def _supported_units_text(family: str) -> str:
    """Return a stable human-readable list of supported units for one family."""
    return ", ".join(_require_supported_family(family))


def _coerce_quantity_pair(name: str, value: QuantityInput) -> tuple[float, str]:
    """Return the scalar value and normalized unit from a 2-item quantity pair."""
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{name} must be a scalar or a 2-item (value, unit) tuple/list.")

    if len(value) != 2:
        raise TypeError(f"{name} quantity inputs must have exactly two items: [value, unit].")

    scalar_value = _require_finite_scalar(name, value[0])
    unit = value[1]
    if not isinstance(unit, str):
        raise TypeError(f"{name} unit must be a string.")

    return scalar_value, normalize_unit(unit)


def coerce_quantity(name: str, value: QuantityInput, canonical_unit: str, family: str) -> float:
    """Normalize a required public quantity into its canonical computational unit."""
    normalized_canonical_unit = normalize_unit(canonical_unit)
    supported_units = _require_supported_family(family)
    if normalized_canonical_unit not in supported_units:
        raise ValueError(f"Canonical unit {normalized_canonical_unit!r} is invalid for family {family!r}.")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _require_finite_scalar(name, value)

    scalar_value, normalized_input_unit = _coerce_quantity_pair(name, value)
    if normalized_input_unit not in supported_units:
        supported = _supported_units_text(family)
        raise ValueError(f"{name} does not accept unit {normalized_input_unit!r}. Supported units: {supported}.")

    from_factor = supported_units[normalized_input_unit]
    to_factor = supported_units[normalized_canonical_unit]
    return scalar_value * from_factor / to_factor


def coerce_optional_quantity(
    name: str,
    value: QuantityInput | None,
    canonical_unit: str,
    family: str,
) -> float | None:
    """Normalize an optional public quantity into its canonical computational unit."""
    if value is None:
        return None

    return coerce_quantity(name, value, canonical_unit, family)


__all__ = [
    "QuantityInput",
    "coerce_optional_quantity",
    "coerce_quantity",
    "convert_value",
    "normalize_unit",
]
