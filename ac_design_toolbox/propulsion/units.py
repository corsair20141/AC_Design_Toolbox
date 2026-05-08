"""Small explicit unit helpers for electric-propulsion public boundaries.

The propulsion package accepts a limited set of quantity inputs at its public
dataclass and function boundaries. Values are normalized immediately into the
documented computational units so motor-prop matching can use plain floats.
"""

from __future__ import annotations

from math import isfinite, pi
from typing import Final

QuantityScalar = float | int
QuantityPair = tuple[QuantityScalar, str] | list[QuantityScalar | str]
QuantityInput = QuantityScalar | QuantityPair

_UNIT_ALIASES: Final[dict[str, str]] = {
    "v": "v",
    "volt": "v",
    "volts": "v",
    "a": "a",
    "amp": "a",
    "amps": "a",
    "ampere": "a",
    "amperes": "a",
    "ah": "ah",
    "amp_hour": "ah",
    "amp_hours": "ah",
    "ampere_hour": "ah",
    "ampere_hours": "ah",
    "ohm": "ohm",
    "ohms": "ohm",
    "omega": "ohm",
    "n_m": "n_m",
    "n*m": "n_m",
    "nm": "n_m",
    "newton_meter": "n_m",
    "newton_meters": "n_m",
    "rad_s": "rad_s",
    "rad/s": "rad_s",
    "radian_per_second": "rad_s",
    "radians_per_second": "rad_s",
    "rpm": "rpm",
    "rev_min": "rpm",
    "rev/min": "rpm",
    "revolution_per_minute": "rpm",
    "revolutions_per_minute": "rpm",
    "n": "n",
    "newton": "n",
    "newtons": "n",
    "w": "w",
    "watt": "w",
    "watts": "w",
    "wh": "wh",
    "whr": "wh",
    "watt_hour": "wh",
    "watt_hours": "wh",
    "kwh": "kwh",
    "kwhr": "kwh",
    "kilowatt_hour": "kwh",
    "kilowatt_hours": "kwh",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "lb": "lbm",
    "lbs": "lbm",
    "lbm": "lbm",
    "pound": "lbm",
    "pounds": "lbm",
    "wh_kg": "wh_kg",
    "wh/kg": "wh_kg",
    "watt_hour_per_kg": "wh_kg",
    "watt_hours_per_kg": "wh_kg",
    "wh_lbm": "wh_lbm",
    "wh/lbm": "wh_lbm",
    "wh/lb": "wh_lbm",
    "watt_hour_per_lbm": "wh_lbm",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "in": "in",
    "inch": "in",
    "inches": "in",
    "m_s": "m_s",
    "m/s": "m_s",
    "meter_per_second": "m_s",
    "meters_per_second": "m_s",
    "metre_per_second": "m_s",
    "metres_per_second": "m_s",
    "kg_m3": "kg_m3",
    "kg/m3": "kg_m3",
    "kg/m^3": "kg_m3",
    "rad_s_v": "rad_s_v",
    "rad/s/v": "rad_s_v",
    "rad_s_per_v": "rad_s_v",
    "rad/s/volt": "rad_s_v",
    "radian_per_second_per_volt": "rad_s_v",
    "radians_per_second_per_volt": "rad_s_v",
    "rpm_v": "rpm_v",
    "rpm/v": "rpm_v",
    "rpm_per_v": "rpm_v",
    "rpm/volt": "rpm_v",
    "rev_min_v": "rpm_v",
    "rev/min/v": "rpm_v",
}

_FAMILY_FACTORS_TO_CANONICAL: Final[dict[str, dict[str, float]]] = {
    "voltage": {"v": 1.0},
    "current": {"a": 1.0},
    "capacity": {"ah": 1.0},
    "resistance": {"ohm": 1.0},
    "torque": {"n_m": 1.0},
    "angular_speed": {"rad_s": 1.0, "rpm": pi / 30.0},
    "rotational_speed": {"rpm": 1.0, "rad_s": 30.0 / pi},
    "force": {"n": 1.0},
    "power": {"w": 1.0},
    "energy": {"wh": 1.0, "kwh": 1000.0},
    "mass": {"kg": 1.0, "lbm": 0.45359237},
    "specific_energy": {"wh_kg": 1.0, "wh_lbm": 1.0 / 0.45359237},
    "length": {"m": 1.0, "in": 0.0254},
    "speed": {"m_s": 1.0},
    "density": {"kg_m3": 1.0},
    "speed_constant": {"rad_s_v": 1.0, "rpm_v": pi / 30.0},
}


def require_finite_scalar(name: str, value: QuantityScalar) -> float:
    """Return a finite float scalar for validation and unit conversion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a scalar number.")

    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")

    return scalar_value


def normalize_unit(unit: str) -> str:
    """Return the canonical spelling for a supported propulsion unit string."""
    if not isinstance(unit, str):
        raise TypeError("unit must be a string.")

    normalized = unit.strip().lower().replace(" ", "_").replace("-", "_")
    if not normalized:
        raise ValueError("unit must be a non-empty string.")

    canonical_unit = _UNIT_ALIASES.get(normalized)
    if canonical_unit is None:
        raise ValueError(f"Unsupported unit {unit!r}.")

    return canonical_unit


def _require_supported_family(family: str) -> dict[str, float]:
    """Return the explicit conversion table for a supported unit family."""
    try:
        return _FAMILY_FACTORS_TO_CANONICAL[family]
    except KeyError as exc:
        raise ValueError(f"Unsupported unit family {family!r}.") from exc


def _coerce_quantity_pair(name: str, value: QuantityInput) -> tuple[float, str]:
    """Return the scalar value and normalized unit from a 2-item quantity pair."""
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{name} must be a scalar or a 2-item (value, unit) tuple/list.")

    if len(value) != 2:
        raise TypeError(f"{name} quantity inputs must have exactly two items: [value, unit].")

    scalar_value = require_finite_scalar(name, value[0])
    unit = value[1]
    if not isinstance(unit, str):
        raise TypeError(f"{name} unit must be a string.")

    return scalar_value, normalize_unit(unit)


def coerce_quantity(name: str, value: QuantityInput, canonical_unit: str, family: str) -> float:
    """Normalize a required quantity into the requested canonical unit."""
    supported_units = _require_supported_family(family)
    normalized_canonical = normalize_unit(canonical_unit)
    if normalized_canonical not in supported_units:
        raise ValueError(f"Canonical unit {normalized_canonical!r} is invalid for family {family!r}.")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return require_finite_scalar(name, value)

    scalar_value, normalized_input = _coerce_quantity_pair(name, value)
    if normalized_input not in supported_units:
        supported = ", ".join(supported_units)
        raise ValueError(f"{name} does not accept unit {normalized_input!r}. Supported units: {supported}.")

    from_factor = supported_units[normalized_input]
    to_factor = supported_units[normalized_canonical]
    return scalar_value * from_factor / to_factor


def coerce_optional_quantity(
    name: str,
    value: QuantityInput | None,
    canonical_unit: str,
    family: str,
) -> float | None:
    """Normalize an optional quantity into the requested canonical unit."""
    if value is None:
        return None

    return coerce_quantity(name, value, canonical_unit, family)


def coerce_fraction(name: str, value: float) -> float:
    """Return a finite fraction in the closed interval [0, 1]."""
    scalar_value = require_finite_scalar(name, value)
    if scalar_value < 0.0 or scalar_value > 1.0:
        raise ValueError(f"{name} must lie in [0, 1].")
    return scalar_value


def convert_value(value: QuantityScalar, from_unit: str, to_unit: str) -> float:
    """Convert a finite scalar between two supported units in the same family."""
    scalar_value = require_finite_scalar("value", value)
    normalized_from = normalize_unit(from_unit)
    normalized_to = normalize_unit(to_unit)

    for family_units in _FAMILY_FACTORS_TO_CANONICAL.values():
        if normalized_from in family_units and normalized_to in family_units:
            return scalar_value * family_units[normalized_from] / family_units[normalized_to]

    raise ValueError(f"Cannot convert from {normalized_from!r} to {normalized_to!r}.")


def rotational_speed_to_angular_speed(rotational_speed: QuantityInput) -> float:
    """Return angular speed in rad/s from a rotational-speed quantity.

    Bare scalars are interpreted as rpm because rotational speed is an
    input/output convenience in this package. Use ``(value, "rad/s")`` when
    the caller already has angular speed.
    """
    if isinstance(rotational_speed, (int, float)) and not isinstance(rotational_speed, bool):
        return require_finite_scalar("rotational_speed", rotational_speed) * pi / 30.0

    return coerce_quantity("rotational_speed", rotational_speed, "rad_s", "angular_speed")


def angular_speed_to_rotational_speed(angular_speed: QuantityInput) -> float:
    """Return rotational speed in rpm from an angular-speed quantity.

    Bare scalars are interpreted as rad/s because this helper converts from the
    internal angular-speed representation.
    """
    if isinstance(angular_speed, (int, float)) and not isinstance(angular_speed, bool):
        return require_finite_scalar("angular_speed", angular_speed) * 30.0 / pi

    return coerce_quantity("angular_speed", angular_speed, "rpm", "rotational_speed")


__all__ = [
    "QuantityInput",
    "angular_speed_to_rotational_speed",
    "coerce_fraction",
    "coerce_optional_quantity",
    "coerce_quantity",
    "convert_value",
    "normalize_unit",
    "require_finite_scalar",
    "rotational_speed_to_angular_speed",
]
