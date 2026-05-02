"""Aircraft electrical-energy component primitives.

This module owns non-solar aircraft energy definitions that can be reused by
mission tools without importing mission propagation, solar geometry, or Dash
apps. Public quantity fields accept bare values in the documented canonical
unit or ``(value, "unit")`` pairs, then store plain floats for downstream math.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping
import warnings


QuantityScalar = float | int
QuantityPair = tuple[QuantityScalar, str] | list[QuantityScalar | str]
QuantityInput = QuantityScalar | QuantityPair

_KG_PER_LBM = 0.45359237
_M2_PER_FT2 = 0.09290304

_UNIT_ALIASES: dict[str, str] = {
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "lb": "lbm",
    "lbs": "lbm",
    "lbm": "lbm",
    "pound": "lbm",
    "pounds": "lbm",
    "w": "w",
    "watt": "w",
    "watts": "w",
    "kw": "kw",
    "kilowatt": "kw",
    "kilowatts": "kw",
    "wh": "wh",
    "whr": "wh",
    "watt_hour": "wh",
    "watt_hours": "wh",
    "kwh": "kwh",
    "kwhr": "kwh",
    "kilowatt_hour": "kwh",
    "kilowatt_hours": "kwh",
    "v": "v",
    "volt": "v",
    "volts": "v",
    "a": "a",
    "amp": "a",
    "amps": "a",
    "ampere": "a",
    "amperes": "a",
    "m2": "m2",
    "m^2": "m2",
    "sqm": "m2",
    "square_meter": "m2",
    "square_meters": "m2",
    "ft2": "ft2",
    "ft^2": "ft2",
    "sqft": "ft2",
    "square_foot": "ft2",
    "square_feet": "ft2",
    "wh_kg": "wh_kg",
    "wh/kg": "wh_kg",
    "watt_hour_per_kg": "wh_kg",
    "watt_hours_per_kg": "wh_kg",
    "wh_lbm": "wh_lbm",
    "wh/lbm": "wh_lbm",
    "wh/lb": "wh_lbm",
    "watt_hour_per_lbm": "wh_lbm",
    "kg_m2": "kg_m2",
    "kg/m2": "kg_m2",
    "kg/m^2": "kg_m2",
    "lbm_ft2": "lbm_ft2",
    "lbm/ft2": "lbm_ft2",
    "lb/ft2": "lbm_ft2",
}

_FAMILY_FACTORS_TO_CANONICAL: dict[str, dict[str, float]] = {
    "mass": {"kg": 1.0, "lbm": _KG_PER_LBM},
    "power": {"w": 1.0, "kw": 1000.0},
    "energy": {"wh": 1.0, "kwh": 1000.0},
    "voltage": {"v": 1.0},
    "current": {"a": 1.0},
    "area": {"m2": 1.0, "ft2": _M2_PER_FT2},
    "specific_energy": {"wh_kg": 1.0, "wh_lbm": 1.0 / _KG_PER_LBM},
    "areal_density": {"kg_m2": 1.0, "lbm_ft2": _KG_PER_LBM / _M2_PER_FT2},
}


class EnergyLimitWarning(UserWarning):
    """Warning emitted when an energy component exceeds an optional limit."""


def _require_finite_scalar(name: str, value: Any) -> float:
    """Return a finite scalar float for validation and unit conversion."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a scalar number.")
    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")
    return scalar_value


def _normalize_unit(unit: str) -> str:
    """Return the canonical spelling for a supported energy unit."""
    if not isinstance(unit, str):
        raise TypeError("unit must be a string.")
    normalized = unit.strip().lower().replace(" ", "_").replace("-", "_")
    if normalized not in _UNIT_ALIASES:
        raise ValueError(f"Unsupported unit {unit!r}.")
    return _UNIT_ALIASES[normalized]


def _coerce_quantity(name: str, value: QuantityInput, canonical_unit: str, family: str) -> float:
    """Normalize a public quantity into the requested canonical unit."""
    family_units = _FAMILY_FACTORS_TO_CANONICAL[family]
    normalized_canonical = _normalize_unit(canonical_unit)
    if normalized_canonical not in family_units:
        raise ValueError(f"Canonical unit {canonical_unit!r} is not valid for {family}.")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return _require_finite_scalar(name, value)

    if not isinstance(value, (tuple, list)) or len(value) != 2:
        raise TypeError(f"{name} must be a scalar or a 2-item (value, unit) tuple/list.")

    scalar_value = _require_finite_scalar(name, value[0])
    normalized_input = _normalize_unit(str(value[1]))
    if normalized_input not in family_units:
        supported = ", ".join(family_units)
        raise ValueError(f"{name} does not accept unit {normalized_input!r}. Supported units: {supported}.")

    return scalar_value * family_units[normalized_input] / family_units[normalized_canonical]


def _coerce_optional_quantity(
    name: str,
    value: QuantityInput | None,
    canonical_unit: str,
    family: str,
) -> float | None:
    """Normalize an optional public quantity into the requested canonical unit."""
    if value is None:
        return None
    return _coerce_quantity(name, value, canonical_unit, family)


def _coerce_fraction(name: str, value: float) -> float:
    """Return a finite fraction in the closed interval [0, 1]."""
    scalar_value = _require_finite_scalar(name, value)
    if scalar_value < 0.0 or scalar_value > 1.0:
        raise ValueError(f"{name} must lie in [0, 1].")
    return scalar_value


def _freeze_mapping(mapping: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return an immutable shallow copy of a metadata mapping."""
    return MappingProxyType(dict(mapping))


@dataclass(frozen=True)
class EnergyLimitViolation:
    """One exceeded optional component limit."""

    component: str
    limit_name: str
    value: float
    limit: float
    unit: str
    margin: float
    message: str

    def to_dict(self) -> dict[str, object]:
        """Serialize the violation for result summaries or MDO constraints."""
        return {
            "component": self.component,
            "limit_name": self.limit_name,
            "value": self.value,
            "limit": self.limit,
            "unit": self.unit,
            "margin": self.margin,
            "message": self.message,
        }


@dataclass(frozen=True)
class MassItem:
    """Named component mass contribution used by aircraft mass buildup."""

    name: str
    mass: QuantityInput
    category: str = "misc"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize mass and metadata."""
        name = str(self.name).strip()
        if not name:
            raise ValueError("MassItem.name must be non-empty.")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "category", str(self.category or "misc"))

        mass_kg = _coerce_quantity("mass", self.mass, "kg", "mass")
        if mass_kg < 0.0:
            raise ValueError("mass must be non-negative.")
        object.__setattr__(self, "mass", mass_kg)
        object.__setattr__(self, "metadata", _freeze_mapping(self.metadata))

    def to_dict(self) -> dict[str, object]:
        """Serialize this mass contribution."""
        return {
            "name": self.name,
            "category": self.category,
            "mass": self.mass,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class BatteryPowerLimitResult:
    """Battery limit checks for one signed battery-bus power sample."""

    battery_power: float
    battery_current: float
    feasible: bool
    violations: tuple[EnergyLimitViolation, ...]


@dataclass(frozen=True)
class BatteryPackConfig:
    """Energy-bucket battery model with optional power and current limits.

    Stored units are Wh, V, A, W, kg, and Wh/kg. ``energy_capacity`` is stored
    in Wh. Positive battery-bus power means discharge to serve aircraft loads;
    negative power means charging.
    """

    energy_capacity: QuantityInput
    nominal_voltage: QuantityInput
    initial_soc: float = 1.0
    usable_soc_min: float = 0.0
    usable_soc_max: float = 1.0
    charge_efficiency: float = 1.0
    discharge_efficiency: float = 1.0
    max_charge_power: QuantityInput | None = None
    max_discharge_power: QuantityInput | None = None
    max_charge_current: QuantityInput | None = None
    max_discharge_current: QuantityInput | None = None
    mass: QuantityInput | None = None
    specific_energy: QuantityInput | None = None

    def __post_init__(self) -> None:
        """Normalize quantities and validate the energy bucket."""
        energy_capacity_wh = _coerce_quantity(
            "energy_capacity",
            self.energy_capacity,
            "wh",
            "energy",
        )
        if energy_capacity_wh <= 0.0:
            raise ValueError("energy_capacity must be positive.")
        object.__setattr__(self, "energy_capacity", energy_capacity_wh)

        nominal_voltage_v = _coerce_quantity("nominal_voltage", self.nominal_voltage, "v", "voltage")
        if nominal_voltage_v <= 0.0:
            raise ValueError("nominal_voltage must be positive.")
        object.__setattr__(self, "nominal_voltage", nominal_voltage_v)

        usable_soc_min = _coerce_fraction("usable_soc_min", self.usable_soc_min)
        usable_soc_max = _coerce_fraction("usable_soc_max", self.usable_soc_max)
        if usable_soc_min > usable_soc_max:
            raise ValueError("usable_soc_min must be <= usable_soc_max.")
        object.__setattr__(self, "usable_soc_min", usable_soc_min)
        object.__setattr__(self, "usable_soc_max", usable_soc_max)

        initial_soc = _coerce_fraction("initial_soc", self.initial_soc)
        if initial_soc < usable_soc_min or initial_soc > usable_soc_max:
            raise ValueError("initial_soc must lie within the usable SOC bounds.")
        object.__setattr__(self, "initial_soc", initial_soc)

        for field_name in ("charge_efficiency", "discharge_efficiency"):
            efficiency = _coerce_fraction(field_name, getattr(self, field_name))
            if efficiency <= 0.0:
                raise ValueError(f"{field_name} must be > 0.")
            object.__setattr__(self, field_name, efficiency)

        for field_name in ("max_charge_power", "max_discharge_power"):
            value = _coerce_optional_quantity(field_name, getattr(self, field_name), "w", "power")
            if value is not None and value <= 0.0:
                raise ValueError(f"{field_name} must be positive when provided.")
            object.__setattr__(self, field_name, value)

        for field_name in ("max_charge_current", "max_discharge_current"):
            value = _coerce_optional_quantity(field_name, getattr(self, field_name), "a", "current")
            if value is not None and value <= 0.0:
                raise ValueError(f"{field_name} must be positive when provided.")
            object.__setattr__(self, field_name, value)

        mass_kg = _coerce_optional_quantity("mass", self.mass, "kg", "mass")
        specific_energy_wh_kg = _coerce_optional_quantity(
            "specific_energy",
            self.specific_energy,
            "wh_kg",
            "specific_energy",
        )
        if mass_kg is None and specific_energy_wh_kg is None:
            raise ValueError("BatteryPackConfig requires either mass or specific_energy.")
        if mass_kg is not None and mass_kg <= 0.0:
            raise ValueError("mass must be positive when provided.")
        if specific_energy_wh_kg is not None and specific_energy_wh_kg <= 0.0:
            raise ValueError("specific_energy must be positive when provided.")
        object.__setattr__(self, "mass", mass_kg)
        object.__setattr__(self, "specific_energy", specific_energy_wh_kg)

    @property
    def mass_kg(self) -> float:
        """Return explicit or specific-energy-derived battery mass."""
        if self.mass is not None:
            return self.mass
        if self.specific_energy is None:
            raise RuntimeError("Battery specific_energy was not initialized.")
        return self.energy_capacity / self.specific_energy

    @property
    def initial_energy_wh(self) -> float:
        """Return the initial stored battery energy."""
        return self.energy_capacity * self.initial_soc

    @property
    def usable_energy_min_wh(self) -> float:
        """Return the lower usable battery-energy bound."""
        return self.energy_capacity * self.usable_soc_min

    @property
    def usable_energy_max_wh(self) -> float:
        """Return the upper usable battery-energy bound."""
        return self.energy_capacity * self.usable_soc_max

    def apply_bus_power(self, energy_wh: float, battery_power: float, dt_seconds: float) -> float:
        """Advance stored energy for one interval using bus-side battery power."""
        current_energy = _require_finite_scalar("energy_wh", energy_wh)
        power_w = _require_finite_scalar("battery_power", battery_power)
        dt_s = _require_finite_scalar("dt_seconds", dt_seconds)
        if dt_s < 0.0:
            raise ValueError("dt_seconds must be non-negative.")

        if power_w >= 0.0:
            delta_wh = power_w * dt_s / 3600.0 / self.discharge_efficiency
            next_energy = current_energy - delta_wh
        else:
            delta_wh = (-power_w) * dt_s / 3600.0 * self.charge_efficiency
            next_energy = current_energy + delta_wh

        return max(0.0, min(self.energy_capacity, next_energy))

    def evaluate_power_limits(self, battery_power: QuantityInput) -> BatteryPowerLimitResult:
        """Check optional charge/discharge power and current limits."""
        power_w = _coerce_quantity("battery_power", battery_power, "w", "power")
        current_a = abs(power_w) / self.nominal_voltage
        violations: list[EnergyLimitViolation] = []

        if power_w >= 0.0:
            _append_power_violation(
                violations,
                component="battery",
                limit_name="max_discharge_power",
                value=power_w,
                limit=self.max_discharge_power,
                unit="w",
            )
            _append_power_violation(
                violations,
                component="battery",
                limit_name="max_discharge_current",
                value=current_a,
                limit=self.max_discharge_current,
                unit="a",
            )
        else:
            _append_power_violation(
                violations,
                component="battery",
                limit_name="max_charge_power",
                value=abs(power_w),
                limit=self.max_charge_power,
                unit="w",
            )
            _append_power_violation(
                violations,
                component="battery",
                limit_name="max_charge_current",
                value=current_a,
                limit=self.max_charge_current,
                unit="a",
            )

        return BatteryPowerLimitResult(
            battery_power=power_w,
            battery_current=current_a,
            feasible=len(violations) == 0,
            violations=tuple(violations),
        )


@dataclass(frozen=True)
class PropulsionElectricalConfig:
    """Electrical propulsion component limits and mass contribution."""

    name: str = "propulsion"
    mass: QuantityInput | None = None
    max_power: QuantityInput | None = None
    max_current: QuantityInput | None = None

    def __post_init__(self) -> None:
        """Normalize optional mass, power, and current limits."""
        name = str(self.name).strip() or "propulsion"
        object.__setattr__(self, "name", name)
        for field_name, canonical_unit, family in (
            ("mass", "kg", "mass"),
            ("max_power", "w", "power"),
            ("max_current", "a", "current"),
        ):
            value = _coerce_optional_quantity(field_name, getattr(self, field_name), canonical_unit, family)
            if value is not None and value <= 0.0:
                raise ValueError(f"{field_name} must be positive when provided.")
            object.__setattr__(self, field_name, value)

    def evaluate_power_limits(
        self,
        propulsion_electrical_power: QuantityInput,
        *,
        bus_voltage: QuantityInput,
    ) -> BatteryPowerLimitResult:
        """Check propulsion electrical power and current limits."""
        power_w = _coerce_quantity("propulsion_electrical_power", propulsion_electrical_power, "w", "power")
        voltage_v = _coerce_quantity("bus_voltage", bus_voltage, "v", "voltage")
        if power_w < 0.0:
            raise ValueError("propulsion_electrical_power must be non-negative.")
        if voltage_v <= 0.0:
            raise ValueError("bus_voltage must be positive.")

        current_a = power_w / voltage_v
        violations: list[EnergyLimitViolation] = []
        _append_power_violation(
            violations,
            component=self.name,
            limit_name="max_power",
            value=power_w,
            limit=self.max_power,
            unit="w",
        )
        _append_power_violation(
            violations,
            component=self.name,
            limit_name="max_current",
            value=current_a,
            limit=self.max_current,
            unit="a",
        )
        return BatteryPowerLimitResult(
            battery_power=power_w,
            battery_current=current_a,
            feasible=len(violations) == 0,
            violations=tuple(violations),
        )


@dataclass(frozen=True)
class ElectricalLoadConfig:
    """Reusable named non-propulsive electrical load definition."""

    name: str
    power: QuantityInput
    mass: QuantityInput | None = None
    category: str = "payload"

    def __post_init__(self) -> None:
        """Normalize load power and optional mass."""
        name = str(self.name).strip()
        if not name:
            raise ValueError("ElectricalLoadConfig.name must be non-empty.")
        object.__setattr__(self, "name", name)

        power_w = _coerce_quantity("power", self.power, "w", "power")
        if power_w < 0.0:
            raise ValueError("power must be non-negative.")
        object.__setattr__(self, "power", power_w)

        mass_kg = _coerce_optional_quantity("mass", self.mass, "kg", "mass")
        if mass_kg is not None and mass_kg < 0.0:
            raise ValueError("mass must be non-negative when provided.")
        object.__setattr__(self, "mass", mass_kg)
        object.__setattr__(self, "category", str(self.category or "payload"))

    def mass_item(self) -> MassItem | None:
        """Return this load's mass contribution when one was provided."""
        if self.mass is None:
            return None
        return MassItem(name=self.name, mass=self.mass, category=self.category)


@dataclass(frozen=True)
class AircraftEnergyConfig:
    """Non-solar aircraft energy-system parameters and mass buildup."""

    base_aircraft_mass: QuantityInput
    battery: BatteryPackConfig
    propulsion: PropulsionElectricalConfig = field(default_factory=PropulsionElectricalConfig)
    loads: tuple[ElectricalLoadConfig, ...] = ()
    extra_mass_items: tuple[MassItem, ...] = ()

    def __post_init__(self) -> None:
        """Normalize nested configs and validate unique load names."""
        base_mass_kg = _coerce_quantity("base_aircraft_mass", self.base_aircraft_mass, "kg", "mass")
        if base_mass_kg < 0.0:
            raise ValueError("base_aircraft_mass must be non-negative.")
        object.__setattr__(self, "base_aircraft_mass", base_mass_kg)

        if isinstance(self.battery, Mapping):
            object.__setattr__(self, "battery", BatteryPackConfig(**self.battery))
        if isinstance(self.propulsion, Mapping):
            object.__setattr__(self, "propulsion", PropulsionElectricalConfig(**self.propulsion))

        loads = tuple(
            load if isinstance(load, ElectricalLoadConfig) else ElectricalLoadConfig(**load)
            for load in self.loads
        )
        load_names = [load.name for load in loads]
        duplicates = sorted({name for name in load_names if load_names.count(name) > 1})
        if duplicates:
            raise ValueError(f"loads must have unique names. Duplicates: {duplicates}.")
        object.__setattr__(self, "loads", loads)

        extra_mass_items = tuple(
            item if isinstance(item, MassItem) else MassItem(**item)
            for item in self.extra_mass_items
        )
        object.__setattr__(self, "extra_mass_items", extra_mass_items)

    def load_by_name(self, name: str) -> ElectricalLoadConfig:
        """Return a configured electrical load by name."""
        normalized_name = str(name).strip()
        for load in self.loads:
            if load.name == normalized_name:
                return load
        raise KeyError(f"No electrical load is configured with name {normalized_name!r}.")

    def mass_items(self, external_mass_items: tuple[MassItem, ...] = ()) -> tuple[MassItem, ...]:
        """Return all named mass contributions, including optional external items."""
        items: list[MassItem] = [
            MassItem(name="base_aircraft", mass=self.base_aircraft_mass, category="airframe"),
            MassItem(name="battery", mass=self.battery.mass_kg, category="battery"),
        ]
        if self.propulsion.mass is not None:
            items.append(MassItem(name=self.propulsion.name, mass=self.propulsion.mass, category="propulsion"))
        for load in self.loads:
            load_mass = load.mass_item()
            if load_mass is not None:
                items.append(load_mass)
        items.extend(self.extra_mass_items)
        items.extend(external_mass_items)
        return tuple(items)

    def mass_breakdown(self, external_mass_items: tuple[MassItem, ...] = ()) -> dict[str, float]:
        """Return mass contribution totals by item name."""
        return {item.name: item.mass for item in self.mass_items(external_mass_items)}

    def category_mass_breakdown(self, external_mass_items: tuple[MassItem, ...] = ()) -> dict[str, float]:
        """Return mass contribution totals by component category."""
        totals: dict[str, float] = {}
        for item in self.mass_items(external_mass_items):
            totals[item.category] = totals.get(item.category, 0.0) + item.mass
        return totals

    def total_mass(self, external_mass_items: tuple[MassItem, ...] = ()) -> float:
        """Return total aircraft mass after configured and external items."""
        return sum(item.mass for item in self.mass_items(external_mass_items))

    def constant_load_power(self) -> float:
        """Return the sum of configured non-propulsive load powers."""
        return sum(load.power for load in self.loads)


def _append_power_violation(
    violations: list[EnergyLimitViolation],
    *,
    component: str,
    limit_name: str,
    value: float,
    limit: float | None,
    unit: str,
) -> None:
    """Append one violation when a value exceeds a configured positive limit."""
    if limit is None:
        return
    margin = float(limit) - float(value)
    if margin >= 0.0:
        return
    violations.append(
        EnergyLimitViolation(
            component=component,
            limit_name=limit_name,
            value=float(value),
            limit=float(limit),
            unit=unit,
            margin=margin,
            message=(
                f"{component} {limit_name} exceeded: "
                f"{float(value):.6g} {unit} > {float(limit):.6g} {unit}."
            ),
        )
    )


def warn_for_violations(violations: tuple[EnergyLimitViolation, ...] | list[EnergyLimitViolation]) -> None:
    """Emit one warning per unique exceeded component limit."""
    seen: set[tuple[str, str]] = set()
    for violation in violations:
        key = (violation.component, violation.limit_name)
        if key in seen:
            continue
        seen.add(key)
        warnings.warn(violation.message, EnergyLimitWarning, stacklevel=2)


__all__ = [
    "AircraftEnergyConfig",
    "BatteryPackConfig",
    "BatteryPowerLimitResult",
    "ElectricalLoadConfig",
    "EnergyLimitViolation",
    "EnergyLimitWarning",
    "MassItem",
    "PropulsionElectricalConfig",
    "QuantityInput",
    "warn_for_violations",
]
