"""Interpretable propeller models for motor-prop operating-point analysis."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi
from typing import Protocol, runtime_checkable

import numpy as np

from ac_design_toolbox.propulsion.units import (
    QuantityInput,
    coerce_quantity,
    require_finite_scalar,
    rotational_speed_to_angular_speed,
)


@dataclass(frozen=True)
class PropellerOperatingPoint:
    """Resolved propeller state at one airspeed and rotational speed.

    Stored units are m/s, rpm, rad/s, kg/m^3, m, N, N*m, and W. Coefficients
    use the standard nondimensional fixed-pitch propeller definitions.
    """

    airspeed: float
    rotational_speed: float
    angular_speed: float
    density: float
    diameter: float
    advance_ratio: float
    thrust: float
    torque: float
    shaft_power: float
    ct: float | None
    cp: float | None
    cq: float | None
    efficiency: float | None
    notes: tuple[str, ...] = ()


@runtime_checkable
class PropellerModel(Protocol):
    """Protocol for propeller models that evaluate one operating point."""

    diameter: float

    def evaluate(
        self,
        *,
        airspeed: QuantityInput,
        rotational_speed: QuantityInput,
        density: QuantityInput = 1.225,
    ) -> PropellerOperatingPoint:
        """Return propeller thrust, torque, power, and coefficients."""
        ...


def _require_positive(name: str, value: float) -> float:
    """Return a finite positive scalar."""
    scalar_value = require_finite_scalar(name, value)
    if scalar_value <= 0.0:
        raise ValueError(f"{name} must be positive.")
    return scalar_value


def _coerce_prop_inputs(
    *,
    airspeed: QuantityInput,
    rotational_speed: QuantityInput,
    density: QuantityInput,
    diameter: QuantityInput,
) -> tuple[float, float, float, float, float, float]:
    """Normalize repeated propeller inputs and return derived speed terms."""
    airspeed_m_s = coerce_quantity("airspeed", airspeed, "m_s", "speed")
    rotational_speed_rpm = coerce_quantity("rotational_speed", rotational_speed, "rpm", "rotational_speed")
    density_kg_m3 = coerce_quantity("density", density, "kg_m3", "density")
    diameter_m = coerce_quantity("diameter", diameter, "m", "length")

    if airspeed_m_s < 0.0:
        raise ValueError("airspeed must be non-negative.")
    if rotational_speed_rpm <= 0.0:
        raise ValueError("rotational_speed must be positive.")
    if density_kg_m3 <= 0.0:
        raise ValueError("density must be positive.")
    if diameter_m <= 0.0:
        raise ValueError("diameter must be positive.")

    angular_speed = rotational_speed_to_angular_speed(rotational_speed_rpm)
    revolutions_per_second = rotational_speed_rpm / 60.0
    advance_ratio = airspeed_m_s / (revolutions_per_second * diameter_m)
    return airspeed_m_s, rotational_speed_rpm, angular_speed, density_kg_m3, diameter_m, advance_ratio


def _result_from_coefficients(
    *,
    airspeed: float,
    rotational_speed: float,
    angular_speed: float,
    density: float,
    diameter: float,
    advance_ratio: float,
    ct: float,
    cp: float,
    notes: tuple[str, ...] = (),
) -> PropellerOperatingPoint:
    """Compute dimensional propeller outputs from nondimensional coefficients."""
    revolutions_per_second = rotational_speed / 60.0
    thrust = ct * density * revolutions_per_second**2 * diameter**4
    shaft_power = cp * density * revolutions_per_second**3 * diameter**5
    torque = shaft_power / angular_speed
    cq = cp / (2.0 * pi)
    efficiency = thrust * airspeed / shaft_power if shaft_power > 0.0 else None

    return PropellerOperatingPoint(
        airspeed=airspeed,
        rotational_speed=rotational_speed,
        angular_speed=angular_speed,
        density=density,
        diameter=diameter,
        advance_ratio=advance_ratio,
        thrust=thrust,
        torque=torque,
        shaft_power=shaft_power,
        ct=ct,
        cp=cp,
        cq=cq,
        efficiency=efficiency,
        notes=notes,
    )


@dataclass(frozen=True)
class CoefficientPropeller:
    """Fixed-coefficient propeller model for smoke tests and early estimates."""

    diameter: QuantityInput
    ct: float
    cp: float | None = None
    cq: float | None = None
    name: str = ""

    def __post_init__(self) -> None:
        """Normalize propeller geometry and coefficient inputs."""
        diameter = coerce_quantity("diameter", self.diameter, "m", "length")
        if diameter <= 0.0:
            raise ValueError("diameter must be positive.")
        object.__setattr__(self, "diameter", diameter)

        ct = require_finite_scalar("ct", self.ct)
        object.__setattr__(self, "ct", ct)

        cp = None if self.cp is None else require_finite_scalar("cp", self.cp)
        cq = None if self.cq is None else require_finite_scalar("cq", self.cq)
        if cp is None and cq is None:
            raise ValueError("CoefficientPropeller requires either cp or cq.")
        if cp is not None and cq is not None:
            expected_cp = 2.0 * pi * cq
            if abs(cp - expected_cp) > 1e-9:
                raise ValueError("cp and cq are inconsistent; cp must equal 2*pi*cq.")
        if cp is None and cq is not None:
            cp = 2.0 * pi * cq
        if cq is None and cp is not None:
            cq = cp / (2.0 * pi)

        object.__setattr__(self, "cp", cp)
        object.__setattr__(self, "cq", cq)
        object.__setattr__(self, "name", str(self.name))

    def evaluate(
        self,
        *,
        airspeed: QuantityInput,
        rotational_speed: QuantityInput,
        density: QuantityInput = 1.225,
    ) -> PropellerOperatingPoint:
        """Evaluate propeller loads using constant CT and CP/CQ."""
        airspeed_m_s, rotational_speed_rpm, angular_speed, density_kg_m3, diameter_m, advance_ratio = (
            _coerce_prop_inputs(
                airspeed=airspeed,
                rotational_speed=rotational_speed,
                density=density,
                diameter=self.diameter,
            )
        )
        return _result_from_coefficients(
            airspeed=airspeed_m_s,
            rotational_speed=rotational_speed_rpm,
            angular_speed=angular_speed,
            density=density_kg_m3,
            diameter=diameter_m,
            advance_ratio=advance_ratio,
            ct=self.ct,
            cp=float(self.cp),
        )


@dataclass(frozen=True)
class TabulatedPropeller:
    """Propeller model based on CT and CP tables versus advance ratio."""

    diameter: QuantityInput
    advance_ratio: tuple[float, ...]
    ct: tuple[float, ...]
    cp: tuple[float, ...]
    extrapolation_mode: str = "raise"
    name: str = ""
    source: str = ""

    def __post_init__(self) -> None:
        """Normalize table arrays, sort by advance ratio, and validate modes."""
        diameter = coerce_quantity("diameter", self.diameter, "m", "length")
        if diameter <= 0.0:
            raise ValueError("diameter must be positive.")
        object.__setattr__(self, "diameter", diameter)

        advance_ratio = np.asarray(self.advance_ratio, dtype=float)
        ct = np.asarray(self.ct, dtype=float)
        cp = np.asarray(self.cp, dtype=float)
        if advance_ratio.ndim != 1 or ct.ndim != 1 or cp.ndim != 1:
            raise ValueError("advance_ratio, ct, and cp must be one-dimensional.")
        if not (len(advance_ratio) == len(ct) == len(cp)):
            raise ValueError("advance_ratio, ct, and cp must have the same length.")
        if len(advance_ratio) < 2:
            raise ValueError("TabulatedPropeller requires at least two table rows.")
        if not (np.isfinite(advance_ratio).all() and np.isfinite(ct).all() and np.isfinite(cp).all()):
            raise ValueError("advance_ratio, ct, and cp must be finite.")

        sort_order = np.argsort(advance_ratio)
        advance_ratio = advance_ratio[sort_order]
        ct = ct[sort_order]
        cp = cp[sort_order]
        if np.any(np.diff(advance_ratio) <= 0.0):
            raise ValueError("advance_ratio values must be unique.")

        mode = str(self.extrapolation_mode).strip().lower()
        if mode not in {"raise", "clip", "linear"}:
            raise ValueError("extrapolation_mode must be 'raise', 'clip', or 'linear'.")

        object.__setattr__(self, "advance_ratio", tuple(float(value) for value in advance_ratio))
        object.__setattr__(self, "ct", tuple(float(value) for value in ct))
        object.__setattr__(self, "cp", tuple(float(value) for value in cp))
        object.__setattr__(self, "extrapolation_mode", mode)
        object.__setattr__(self, "name", str(self.name))
        object.__setattr__(self, "source", str(self.source))

    @classmethod
    def from_arrays(
        cls,
        *,
        diameter: QuantityInput,
        advance_ratio: list[float] | tuple[float, ...],
        ct: list[float] | tuple[float, ...],
        cp: list[float] | tuple[float, ...],
        extrapolation_mode: str = "raise",
        name: str = "",
        source: str = "",
    ) -> "TabulatedPropeller":
        """Build a table model from array-like coefficient data."""
        return cls(
            diameter=diameter,
            advance_ratio=tuple(advance_ratio),
            ct=tuple(ct),
            cp=tuple(cp),
            extrapolation_mode=extrapolation_mode,
            name=name,
            source=source,
        )

    @classmethod
    def from_dataframe(
        cls,
        data,
        *,
        diameter: QuantityInput,
        advance_ratio_column: str = "advance_ratio",
        ct_column: str = "ct",
        cp_column: str = "cp",
        extrapolation_mode: str = "raise",
        name: str = "",
        source: str = "",
    ) -> "TabulatedPropeller":
        """Build a table model from a dataframe-like or mapping object."""
        return cls.from_arrays(
            diameter=diameter,
            advance_ratio=list(data[advance_ratio_column]),
            ct=list(data[ct_column]),
            cp=list(data[cp_column]),
            extrapolation_mode=extrapolation_mode,
            name=name,
            source=source,
        )

    def coefficients_at(self, advance_ratio: float) -> tuple[float, float, tuple[str, ...]]:
        """Return CT, CP, and notes at one advance ratio."""
        query_j = require_finite_scalar("advance_ratio", advance_ratio)
        table_j = np.asarray(self.advance_ratio)
        table_ct = np.asarray(self.ct)
        table_cp = np.asarray(self.cp)
        notes: list[str] = []

        if table_j[0] <= query_j <= table_j[-1]:
            return (
                float(np.interp(query_j, table_j, table_ct)),
                float(np.interp(query_j, table_j, table_cp)),
                (),
            )

        if self.extrapolation_mode == "raise":
            raise ValueError(
                f"advance_ratio {query_j:.6g} is outside table range "
                f"[{table_j[0]:.6g}, {table_j[-1]:.6g}]."
            )

        if self.extrapolation_mode == "clip":
            clipped_j = float(np.clip(query_j, table_j[0], table_j[-1]))
            notes.append(f"Advance ratio {query_j:.6g} clipped to table endpoint {clipped_j:.6g}.")
            return (
                float(np.interp(clipped_j, table_j, table_ct)),
                float(np.interp(clipped_j, table_j, table_cp)),
                tuple(notes),
            )

        if query_j < table_j[0]:
            x0, x1 = table_j[0], table_j[1]
            ct0, ct1 = table_ct[0], table_ct[1]
            cp0, cp1 = table_cp[0], table_cp[1]
        else:
            x0, x1 = table_j[-2], table_j[-1]
            ct0, ct1 = table_ct[-2], table_ct[-1]
            cp0, cp1 = table_cp[-2], table_cp[-1]

        fraction = (query_j - x0) / (x1 - x0)
        notes.append(f"Advance ratio {query_j:.6g} linearly extrapolated outside the table range.")
        return (
            float(ct0 + fraction * (ct1 - ct0)),
            float(cp0 + fraction * (cp1 - cp0)),
            tuple(notes),
        )

    def evaluate(
        self,
        *,
        airspeed: QuantityInput,
        rotational_speed: QuantityInput,
        density: QuantityInput = 1.225,
    ) -> PropellerOperatingPoint:
        """Evaluate propeller loads from interpolated CT and CP values."""
        airspeed_m_s, rotational_speed_rpm, angular_speed, density_kg_m3, diameter_m, advance_ratio = (
            _coerce_prop_inputs(
                airspeed=airspeed,
                rotational_speed=rotational_speed,
                density=density,
                diameter=self.diameter,
            )
        )
        ct, cp, notes = self.coefficients_at(advance_ratio)
        return _result_from_coefficients(
            airspeed=airspeed_m_s,
            rotational_speed=rotational_speed_rpm,
            angular_speed=angular_speed,
            density=density_kg_m3,
            diameter=diameter_m,
            advance_ratio=advance_ratio,
            ct=ct,
            cp=cp,
            notes=notes,
        )


__all__ = [
    "CoefficientPropeller",
    "PropellerModel",
    "PropellerOperatingPoint",
    "TabulatedPropeller",
]
