"""Simple battery models for propulsion operating points."""

from __future__ import annotations

from dataclasses import dataclass
from math import inf
from typing import Sequence

import numpy as np

from ac_design_toolbox.propulsion.units import (
    QuantityInput,
    coerce_fraction,
    coerce_optional_quantity,
    coerce_quantity,
    require_finite_scalar,
)


GENERIC_LIPO_SOC: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
GENERIC_LIPO_CELL_VOLTAGE: tuple[float, ...] = (3.30, 3.45, 3.60, 3.70, 3.75, 3.80, 3.85, 3.92, 4.00, 4.10, 4.20)
GENERIC_LIION_SOC: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
GENERIC_LIION_CELL_VOLTAGE: tuple[float, ...] = (3.00, 3.35, 3.50, 3.60, 3.67, 3.72, 3.78, 3.85, 3.95, 4.08, 4.20)
_SUPPORTED_CHEMISTRIES = {"constant", "generic_lipo", "generic_liion", "custom"}


@dataclass(frozen=True)
class BatteryOperatingPoint:
    """Resolved battery state for one propulsion current draw.

    Stored units are V, A, W, and hours. Positive current means discharge from
    the pack to the propulsion system.
    """

    nominal_voltage: float
    open_circuit_voltage: float
    terminal_voltage: float
    current: float
    power: float
    soc: float | None
    estimated_runtime_hours: float | None
    is_within_limits: bool
    limit_notes: tuple[str, ...]


@dataclass(frozen=True)
class BatteryPack:
    """Thevenin-equivalent battery pack with optional SOC-dependent OCV.

    Constant-voltage behavior is the default and remains backward compatible:
    without ``soc`` or with ``chemistry="constant"``, open-circuit voltage is
    simply ``nominal_voltage``. Generic LiPo and Li-ion curves add first-order
    open-circuit-voltage variation with SOC before the existing internal
    resistance sag is applied.

    Default OCV-SOC curves are approximate first-order placeholders. Replace
    with manufacturer or measured cell data for validation-quality predictions.
    This model does not perform SOC time integration, temperature dependence,
    degradation, or advanced equivalent-circuit dynamics.
    """

    nominal_voltage: QuantityInput
    internal_resistance: QuantityInput = 0.0
    capacity: QuantityInput | None = None
    max_current: QuantityInput | None = None
    soc: float | None = None
    chemistry: str = "constant"
    n_series: int | None = None
    ocv_soc_curve: tuple[Sequence[float], Sequence[QuantityInput]] | None = None
    mass: QuantityInput | None = None
    specific_energy: QuantityInput | None = None
    name: str = ""

    def __post_init__(self) -> None:
        """Normalize pack quantities and validate optional limits."""
        nominal_voltage = coerce_quantity("nominal_voltage", self.nominal_voltage, "v", "voltage")
        if nominal_voltage <= 0.0:
            raise ValueError("nominal_voltage must be positive.")
        object.__setattr__(self, "nominal_voltage", nominal_voltage)

        internal_resistance = coerce_quantity("internal_resistance", self.internal_resistance, "ohm", "resistance")
        if internal_resistance < 0.0:
            raise ValueError("internal_resistance must be non-negative.")
        object.__setattr__(self, "internal_resistance", internal_resistance)

        capacity = coerce_optional_quantity("capacity", self.capacity, "ah", "capacity")
        if capacity is not None and capacity <= 0.0:
            raise ValueError("capacity must be positive when provided.")
        object.__setattr__(self, "capacity", capacity)

        max_current = coerce_optional_quantity("max_current", self.max_current, "a", "current")
        if max_current is not None and max_current <= 0.0:
            raise ValueError("max_current must be positive when provided.")
        object.__setattr__(self, "max_current", max_current)

        soc = None if self.soc is None else coerce_fraction("soc", self.soc)
        object.__setattr__(self, "soc", soc)

        chemistry = str(self.chemistry).strip().lower()
        if chemistry not in _SUPPORTED_CHEMISTRIES:
            supported = ", ".join(sorted(_SUPPORTED_CHEMISTRIES))
            raise ValueError(f"chemistry must be one of: {supported}.")
        if chemistry != "custom" and self.ocv_soc_curve is not None:
            raise ValueError("ocv_soc_curve is only used with chemistry='custom'.")
        if chemistry == "custom" and self.ocv_soc_curve is None:
            raise ValueError("chemistry='custom' requires ocv_soc_curve.")
        object.__setattr__(self, "chemistry", chemistry)

        n_series = self.n_series
        if n_series is not None:
            if isinstance(n_series, bool) or int(n_series) != n_series or n_series <= 0:
                raise ValueError("n_series must be a positive integer when provided.")
            object.__setattr__(self, "n_series", int(n_series))
        elif chemistry in {"generic_lipo", "generic_liion"}:
            # Generic chemistry curves are per-cell; infer a practical series
            # count from nominal pack voltage only when the caller omits it.
            nominal_cell_voltage = 3.7 if chemistry == "generic_lipo" else 3.6
            inferred_n_series = max(1, round(nominal_voltage / nominal_cell_voltage))
            object.__setattr__(self, "n_series", inferred_n_series)

        if self.ocv_soc_curve is not None:
            object.__setattr__(self, "ocv_soc_curve", _validate_ocv_soc_curve(self.ocv_soc_curve))

        mass = coerce_optional_quantity("mass", self.mass, "kg", "mass")
        if mass is not None and mass <= 0.0:
            raise ValueError("mass must be positive when provided.")
        object.__setattr__(self, "mass", mass)

        specific_energy = coerce_optional_quantity("specific_energy", self.specific_energy, "wh_kg", "specific_energy")
        if specific_energy is not None and specific_energy <= 0.0:
            raise ValueError("specific_energy must be positive when provided.")
        object.__setattr__(self, "specific_energy", specific_energy)

        object.__setattr__(self, "name", str(self.name))

    @property
    def energy_capacity(self) -> float | None:
        """Return nominal pack energy capacity in Wh when capacity is known."""
        if self.capacity is None:
            return None
        return self.capacity * self.nominal_voltage

    @property
    def mass_kg(self) -> float | None:
        """Return direct or specific-energy-derived pack mass in kg."""
        if self.mass is not None:
            return self.mass
        if self.specific_energy is None or self.energy_capacity is None:
            return None
        return self.energy_capacity / self.specific_energy

    def open_circuit_voltage(self, soc: float | None = None) -> float:
        """Return pack open-circuit voltage before internal-resistance sag."""
        effective_soc = self.soc if soc is None else coerce_fraction("soc", soc)
        if self.chemistry == "constant" or effective_soc is None:
            return self.nominal_voltage

        if self.chemistry == "generic_lipo":
            cell_voltage = float(np.interp(effective_soc, GENERIC_LIPO_SOC, GENERIC_LIPO_CELL_VOLTAGE))
            return self._series_count_for_cell_curve() * cell_voltage

        if self.chemistry == "generic_liion":
            cell_voltage = float(np.interp(effective_soc, GENERIC_LIION_SOC, GENERIC_LIION_CELL_VOLTAGE))
            return self._series_count_for_cell_curve() * cell_voltage

        soc_values, pack_voltage_values = self.ocv_soc_curve or ((), ())
        return float(np.interp(effective_soc, soc_values, pack_voltage_values))

    def terminal_voltage(self, current: QuantityInput, soc: float | None = None) -> float:
        """Return pack terminal voltage after OCV lookup and resistance sag."""
        current_a = coerce_quantity("current", current, "a", "current")
        return self.open_circuit_voltage(soc) - current_a * self.internal_resistance

    def power_out(self, current: QuantityInput, soc: float | None = None) -> float:
        """Return battery terminal power delivered at the requested current."""
        current_a = coerce_quantity("current", current, "a", "current")
        return self.terminal_voltage(current_a, soc) * current_a

    def estimate_runtime_hours(self, current: QuantityInput) -> float | None:
        """Return ideal full-capacity runtime at the requested current."""
        if self.capacity is None:
            return None

        current_a = coerce_quantity("current", current, "a", "current")
        if current_a == 0.0:
            return inf
        if current_a < 0.0:
            return None
        return self.capacity / current_a

    def evaluate(self, current: QuantityInput, soc: float | None = None) -> BatteryOperatingPoint:
        """Return the battery operating point and simple limit diagnostics."""
        current_a = coerce_quantity("current", current, "a", "current")
        effective_soc = self.soc if soc is None else coerce_fraction("soc", soc)
        open_circuit_voltage = self.open_circuit_voltage(effective_soc)
        terminal_voltage = open_circuit_voltage - current_a * self.internal_resistance
        power = terminal_voltage * current_a
        notes: list[str] = []

        if current_a < 0.0:
            notes.append("Battery current is negative; charging behavior is outside this discharge model.")
        if terminal_voltage <= 0.0:
            notes.append("Battery terminal voltage is non-positive at this current.")
        if self.max_current is not None and abs(current_a) > self.max_current:
            notes.append(f"Battery current {abs(current_a):.3g} A exceeds max_current {self.max_current:.3g} A.")

        return BatteryOperatingPoint(
            nominal_voltage=self.nominal_voltage,
            open_circuit_voltage=open_circuit_voltage,
            terminal_voltage=terminal_voltage,
            current=current_a,
            power=power,
            soc=effective_soc,
            estimated_runtime_hours=self.estimate_runtime_hours(current_a),
            is_within_limits=not notes,
            limit_notes=tuple(notes),
        )

    def _series_count_for_cell_curve(self) -> int:
        """Return validated series-cell count for generic per-cell curves."""
        if self.n_series is None:
            raise ValueError("n_series is required for cell-level OCV-SOC curves.")
        return self.n_series


def _validate_ocv_soc_curve(curve: tuple[Sequence[float], Sequence[QuantityInput]]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Validate and normalize a custom pack-level OCV-SOC curve.

    Custom curve voltages are pack open-circuit voltages in V. Provide
    manufacturer or measured data here for validation-quality predictions.
    """
    if not isinstance(curve, (tuple, list)) or len(curve) != 2:
        raise TypeError("ocv_soc_curve must be a 2-item tuple/list: (soc_values, voltage_values).")

    soc_values_raw, voltage_values_raw = curve
    soc_values = tuple(coerce_fraction("ocv_soc_curve soc", value) for value in soc_values_raw)
    voltage_values = tuple(coerce_quantity("ocv_soc_curve voltage", value, "v", "voltage") for value in voltage_values_raw)

    if len(soc_values) != len(voltage_values):
        raise ValueError("ocv_soc_curve SOC and voltage arrays must have the same length.")
    if len(soc_values) < 2:
        raise ValueError("ocv_soc_curve requires at least two points.")
    if any(value <= 0.0 for value in voltage_values):
        raise ValueError("ocv_soc_curve voltages must be positive.")
    if any(next_value <= value for value, next_value in zip(soc_values, soc_values[1:])):
        raise ValueError("ocv_soc_curve SOC values must be strictly increasing.")
    if soc_values[0] > 0.0 or soc_values[-1] < 1.0:
        raise ValueError("ocv_soc_curve must cover the full SOC interval [0, 1].")

    return soc_values, voltage_values


__all__ = [
    "BatteryOperatingPoint",
    "BatteryPack",
    "GENERIC_LIION_CELL_VOLTAGE",
    "GENERIC_LIION_SOC",
    "GENERIC_LIPO_CELL_VOLTAGE",
    "GENERIC_LIPO_SOC",
]
