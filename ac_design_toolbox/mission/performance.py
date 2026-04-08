"""Mission-performance interfaces and a first-pass analytic evaluator.

This module intentionally operates on air-relative operating points only. It
does not perform mission propagation, path geometry integration, or wind
modeling. Those responsibilities remain external so projects such as
``Solar_UAS`` can provide their own mission simulator while reusing the
toolbox's aircraft-performance logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import acos, asin, atan, copysign, cos, degrees, isfinite, radians, sin
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Mapping, Protocol, runtime_checkable

from ac_design_toolbox.atmosphere import standard_atmosphere
from ac_design_toolbox.conceptual.performance import CD_i_oswald

if TYPE_CHECKING:
    import aerosandbox as asb


STANDARD_GRAVITY_M_S2 = 9.80665
COSINE_FLOOR = 1e-6


def _require_finite_scalar(name: str, value: float) -> float:
    """Return a scalar float after checking that it is finite."""
    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")
    return scalar_value


def _clip_unit_interval(value: float) -> float:
    """Clamp a scalar to the interval used by inverse trigonometric helpers."""
    return max(-1.0, min(1.0, float(value)))


@dataclass(frozen=True)
class _ResolvedMissionState:
    """Internal resolved kinematics and notes for one operating point."""

    bank_deg: float
    bank_rad: float
    pitch_deg: float
    flight_path_angle_rad: float
    load_factor: float
    feasible: bool
    notes: tuple[str, ...]


@dataclass(frozen=True)
class MissionOperatingPoint:
    """Air-relative operating conditions for one mission-performance query.

    The operating point is intentionally minimal. It carries only the
    air-relative state needed to estimate first-pass aerodynamic and power
    quantities for a single instant. Mission path propagation, ENU kinematics,
    and wind injection remain external responsibilities.
    """

    phase_name: str
    altitude_m: float
    true_airspeed_m_s: float
    climb_rate_m_s: float
    turn_radius_m: float | None = None
    bank_deg_hint: float | None = None
    pitch_deg_hint: float | None = None
    load_factor_hint: float | None = None
    temp_shift_F: float = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate scalar inputs and freeze metadata into an immutable mapping."""
        phase_name = str(self.phase_name).strip()
        if not phase_name:
            raise ValueError("phase_name must be a non-empty string.")
        object.__setattr__(self, "phase_name", phase_name)

        airspeed = _require_finite_scalar("true_airspeed_m_s", self.true_airspeed_m_s)
        if airspeed <= 0.0:
            raise ValueError("true_airspeed_m_s must be positive.")
        object.__setattr__(self, "true_airspeed_m_s", airspeed)

        object.__setattr__(self, "altitude_m", _require_finite_scalar("altitude_m", self.altitude_m))
        object.__setattr__(self, "climb_rate_m_s", _require_finite_scalar("climb_rate_m_s", self.climb_rate_m_s))
        object.__setattr__(self, "temp_shift_F", _require_finite_scalar("temp_shift_F", self.temp_shift_F))

        if self.turn_radius_m is not None:
            turn_radius_m = _require_finite_scalar("turn_radius_m", self.turn_radius_m)
            if turn_radius_m <= 0.0:
                raise ValueError("turn_radius_m must be positive when provided.")
            object.__setattr__(self, "turn_radius_m", turn_radius_m)

        if self.bank_deg_hint is not None:
            object.__setattr__(self, "bank_deg_hint", _require_finite_scalar("bank_deg_hint", self.bank_deg_hint))

        if self.pitch_deg_hint is not None:
            object.__setattr__(self, "pitch_deg_hint", _require_finite_scalar("pitch_deg_hint", self.pitch_deg_hint))

        if self.load_factor_hint is not None:
            object.__setattr__(
                self,
                "load_factor_hint",
                _require_finite_scalar("load_factor_hint", self.load_factor_hint),
            )

        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class MissionPerformancePoint:
    """Resolved first-pass aircraft-performance state for one operating point."""

    feasible: bool
    bank_deg: float
    pitch_deg: float
    load_factor: float
    propulsion_power_w: float
    drag_force_n: float | None = None
    lift_coefficient: float | None = None
    drag_coefficient: float | None = None
    dynamic_pressure_pa: float | None = None
    air_density_kg_m3: float | None = None
    notes: str = ""


@dataclass(frozen=True)
class MissionAircraftPerformanceConfig:
    """Scalar aircraft-performance inputs for the mission analytic model.

    The container is intentionally thin so external projects can depend on a
    stable interface without importing geometry-heavy workflows. It is meant for
    first-pass performance estimation from a prescribed air-relative operating
    point rather than for full trim or high-fidelity aerodynamic prediction.
    """

    mass_kg: float
    wing_area_m2: float
    aspect_ratio: float
    oswald_efficiency: float
    zero_lift_drag_coefficient: float
    propulsive_efficiency: float
    max_lift_coefficient: float | None = None
    max_bank_deg: float | None = None
    max_load_factor: float | None = None

    def __post_init__(self) -> None:
        """Validate the scalar aircraft parameters used by the analytic model."""
        mass_kg = _require_finite_scalar("mass_kg", self.mass_kg)
        wing_area_m2 = _require_finite_scalar("wing_area_m2", self.wing_area_m2)
        aspect_ratio = _require_finite_scalar("aspect_ratio", self.aspect_ratio)
        oswald_efficiency = _require_finite_scalar("oswald_efficiency", self.oswald_efficiency)
        zero_lift_drag_coefficient = _require_finite_scalar(
            "zero_lift_drag_coefficient",
            self.zero_lift_drag_coefficient,
        )
        propulsive_efficiency = _require_finite_scalar("propulsive_efficiency", self.propulsive_efficiency)

        if mass_kg <= 0.0:
            raise ValueError("mass_kg must be positive.")
        if wing_area_m2 <= 0.0:
            raise ValueError("wing_area_m2 must be positive.")
        if aspect_ratio <= 0.0:
            raise ValueError("aspect_ratio must be positive.")
        if oswald_efficiency <= 0.0:
            raise ValueError("oswald_efficiency must be positive.")
        if zero_lift_drag_coefficient < 0.0:
            raise ValueError("zero_lift_drag_coefficient must be non-negative.")
        if propulsive_efficiency <= 0.0 or propulsive_efficiency > 1.0:
            raise ValueError("propulsive_efficiency must lie in the interval (0, 1].")

        object.__setattr__(self, "mass_kg", mass_kg)
        object.__setattr__(self, "wing_area_m2", wing_area_m2)
        object.__setattr__(self, "aspect_ratio", aspect_ratio)
        object.__setattr__(self, "oswald_efficiency", oswald_efficiency)
        object.__setattr__(self, "zero_lift_drag_coefficient", zero_lift_drag_coefficient)
        object.__setattr__(self, "propulsive_efficiency", propulsive_efficiency)

        if self.max_lift_coefficient is not None:
            max_lift_coefficient = _require_finite_scalar("max_lift_coefficient", self.max_lift_coefficient)
            if max_lift_coefficient <= 0.0:
                raise ValueError("max_lift_coefficient must be positive when provided.")
            object.__setattr__(self, "max_lift_coefficient", max_lift_coefficient)

        if self.max_bank_deg is not None:
            max_bank_deg = _require_finite_scalar("max_bank_deg", self.max_bank_deg)
            if max_bank_deg <= 0.0 or max_bank_deg >= 90.0:
                raise ValueError("max_bank_deg must lie in the interval (0, 90).")
            object.__setattr__(self, "max_bank_deg", max_bank_deg)

        if self.max_load_factor is not None:
            max_load_factor = _require_finite_scalar("max_load_factor", self.max_load_factor)
            if max_load_factor <= 0.0:
                raise ValueError("max_load_factor must be positive when provided.")
            object.__setattr__(self, "max_load_factor", max_load_factor)

    @classmethod
    def from_airplane(
        cls,
        airplane: "asb.Airplane | Any",
        *,
        mass_kg: float,
        oswald_efficiency: float,
        zero_lift_drag_coefficient: float,
        propulsive_efficiency: float,
        max_lift_coefficient: float | None = None,
        max_bank_deg: float | None = None,
        max_load_factor: float | None = None,
    ) -> "MissionAircraftPerformanceConfig":
        """Build a mission config from an AeroSandbox-style airplane object.

        The helper extracts only the reference wing area and span needed for the
        analytic model. It does not attempt to derive a higher-fidelity drag
        polar or trim model from geometry alone.
        """
        try:
            wing_area_m2 = float(getattr(airplane, "s_ref"))
            span_m = float(getattr(airplane, "b_ref"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("airplane must expose numeric s_ref and b_ref attributes.") from exc

        if wing_area_m2 <= 0.0 or span_m <= 0.0:
            raise ValueError("airplane reference area and span must be positive.")

        return cls(
            mass_kg=mass_kg,
            wing_area_m2=wing_area_m2,
            aspect_ratio=span_m**2 / wing_area_m2,
            oswald_efficiency=oswald_efficiency,
            zero_lift_drag_coefficient=zero_lift_drag_coefficient,
            propulsive_efficiency=propulsive_efficiency,
            max_lift_coefficient=max_lift_coefficient,
            max_bank_deg=max_bank_deg,
            max_load_factor=max_load_factor,
        )


def _resolve_bank_angle_rad(
    op: MissionOperatingPoint,
    *,
    flight_path_angle_rad: float,
    gravity_m_s2: float,
) -> tuple[float, list[str]]:
    """Infer the bank angle from hints, turn radius, or coordinated straight flight."""
    notes: list[str] = []

    if op.bank_deg_hint is not None:
        return radians(op.bank_deg_hint), notes

    if op.turn_radius_m is not None:
        horizontal_speed_sq = max(op.true_airspeed_m_s**2 - op.climb_rate_m_s**2, 0.0)
        gamma_cosine = max(cos(flight_path_angle_rad), COSINE_FLOOR)
        return atan(horizontal_speed_sq / (gravity_m_s2 * op.turn_radius_m * gamma_cosine)), notes

    if op.load_factor_hint is not None:
        if op.load_factor_hint <= 0.0:
            notes.append("load_factor_hint could not define a coordinated bank angle, so bank defaults to 0 deg.")
            return 0.0, notes

        cosine_argument = cos(flight_path_angle_rad) / op.load_factor_hint
        clipped_argument = _clip_unit_interval(cosine_argument)
        if abs(cosine_argument) > 1.0:
            notes.append("load_factor_hint is inconsistent with coordinated flight at the requested climb rate.")
        return copysign(acos(clipped_argument), 1.0), notes

    return 0.0, notes


def _coordinated_load_factor(
    *,
    bank_rad: float,
    flight_path_angle_rad: float,
) -> tuple[float, bool]:
    """Return the coordinated load factor and whether the bank cosine was clipped."""
    bank_cosine = cos(bank_rad)
    clipped_bank_cosine = abs(bank_cosine) < COSINE_FLOOR
    if clipped_bank_cosine:
        bank_cosine = copysign(COSINE_FLOOR, bank_cosine if bank_cosine != 0.0 else 1.0)

    return cos(flight_path_angle_rad) / bank_cosine, clipped_bank_cosine


def _resolve_operating_point_state(
    op: MissionOperatingPoint,
    *,
    gravity_m_s2: float,
) -> _ResolvedMissionState:
    """Resolve bank, pitch, load factor, and first-pass feasibility notes."""
    feasible = True
    notes: list[str] = []

    climb_ratio = op.climb_rate_m_s / op.true_airspeed_m_s
    clipped_climb_ratio = _clip_unit_interval(climb_ratio)
    if abs(climb_ratio) > 1.0:
        feasible = False
        notes.append("Requested climb rate magnitude exceeds true airspeed, so the flight-path angle was clipped.")

    # The model uses climb rate to determine the flight-path angle because
    # pitch hints describe attitude reporting, not the energy rate.
    flight_path_angle_rad = asin(clipped_climb_ratio)
    pitch_deg = float(op.pitch_deg_hint) if op.pitch_deg_hint is not None else degrees(flight_path_angle_rad)
    if op.pitch_deg_hint is not None:
        notes.append("Reported pitch uses pitch_deg_hint; force balance still follows climb_rate_m_s.")

    bank_rad, bank_notes = _resolve_bank_angle_rad(
        op,
        flight_path_angle_rad=flight_path_angle_rad,
        gravity_m_s2=gravity_m_s2,
    )
    notes.extend(bank_notes)
    bank_deg = degrees(bank_rad)

    coordinated_load_factor, clipped_bank_cosine = _coordinated_load_factor(
        bank_rad=bank_rad,
        flight_path_angle_rad=flight_path_angle_rad,
    )
    if clipped_bank_cosine:
        feasible = False
        notes.append("Bank angle is too close to 90 deg for the coordinated-flight approximation.")

    if op.load_factor_hint is not None:
        load_factor = float(op.load_factor_hint)
        if load_factor <= 0.0:
            feasible = False
            notes.append("load_factor_hint must be positive for this lifting-flight approximation.")
        elif abs(load_factor - coordinated_load_factor) > max(0.05, 0.05 * abs(coordinated_load_factor)):
            notes.append("load_factor_hint overrides the coordinated-flight load-factor estimate.")
    else:
        load_factor = coordinated_load_factor

    return _ResolvedMissionState(
        bank_deg=bank_deg,
        bank_rad=bank_rad,
        pitch_deg=pitch_deg,
        flight_path_angle_rad=flight_path_angle_rad,
        load_factor=load_factor,
        feasible=feasible,
        notes=tuple(notes),
    )


def _apply_feasibility_limits(
    aircraft: MissionAircraftPerformanceConfig,
    *,
    lift_coefficient: float,
    load_factor: float,
    bank_deg: float,
    feasible: bool,
    notes: list[str],
) -> bool:
    """Append simple aerodynamic limit checks and return the updated feasibility flag."""
    if aircraft.max_lift_coefficient is not None and lift_coefficient > aircraft.max_lift_coefficient:
        feasible = False
        notes.append(f"Lift coefficient {lift_coefficient:.3f} exceeds CL_max {aircraft.max_lift_coefficient:.3f}.")

    if aircraft.max_load_factor is not None and load_factor > aircraft.max_load_factor:
        feasible = False
        notes.append(f"Load factor {load_factor:.3f} exceeds n_max {aircraft.max_load_factor:.3f}.")

    if aircraft.max_bank_deg is not None and abs(bank_deg) > aircraft.max_bank_deg:
        feasible = False
        notes.append(f"Bank angle {bank_deg:.3f} deg exceeds phi_max {aircraft.max_bank_deg:.3f} deg.")

    return feasible


@runtime_checkable
class MissionPerformanceModel(Protocol):
    """Protocol for evaluators that solve one air-relative operating point at a time."""

    def evaluate(self, op: MissionOperatingPoint) -> MissionPerformancePoint:
        """Return the resolved aircraft-performance state for one operating point."""
        ...


@dataclass(frozen=True)
class AnalyticMissionPerformanceModel:
    """Transparent first-pass mission evaluator based on a parabolic drag polar.

    The model uses:

    - atmospheric density from :func:`ac_design_toolbox.atmosphere.standard_atmosphere`
    - coordinated-turn relations for inferred bank and load factor
    - a parabolic drag polar with Oswald-efficiency induced drag
    - a propulsive-efficiency correction to convert useful power to propulsion
      system power

    It is designed to be stable and easy to inspect rather than to replace AVL
    trim or higher-fidelity aerodynamic analysis.
    """

    aircraft: MissionAircraftPerformanceConfig
    gravity_m_s2: float = STANDARD_GRAVITY_M_S2

    def evaluate(self, op: MissionOperatingPoint) -> MissionPerformancePoint:
        """Evaluate one air-relative operating point with transparent approximations."""
        atmosphere = standard_atmosphere(op.altitude_m, units="si", temp_shift_F=op.temp_shift_F)
        if isinstance(atmosphere, list):
            raise TypeError("Mission operating-point evaluation expects a scalar altitude.")

        air_density_kg_m3 = float(atmosphere["rho"])
        dynamic_pressure_pa = 0.5 * air_density_kg_m3 * op.true_airspeed_m_s**2

        resolved_state = _resolve_operating_point_state(op, gravity_m_s2=self.gravity_m_s2)
        feasible = resolved_state.feasible
        notes = list(resolved_state.notes)

        weight_newtons = self.aircraft.mass_kg * self.gravity_m_s2
        lift_force_n = weight_newtons * resolved_state.load_factor
        lift_coefficient = lift_force_n / (dynamic_pressure_pa * self.aircraft.wing_area_m2)
        drag_coefficient = self.aircraft.zero_lift_drag_coefficient + CD_i_oswald(
            CL=lift_coefficient,
            AR=self.aircraft.aspect_ratio,
            e=self.aircraft.oswald_efficiency,
        )
        drag_force_n = dynamic_pressure_pa * self.aircraft.wing_area_m2 * drag_coefficient

        useful_propulsive_force_n = drag_force_n + weight_newtons * sin(resolved_state.flight_path_angle_rad)
        propulsion_power_w = useful_propulsive_force_n * op.true_airspeed_m_s / self.aircraft.propulsive_efficiency
        if propulsion_power_w < 0.0:
            notes.append(
                "Negative propulsion_power_w means this first-pass model predicts no net propulsive input is required."
            )

        feasible = _apply_feasibility_limits(
            self.aircraft,
            lift_coefficient=lift_coefficient,
            load_factor=resolved_state.load_factor,
            bank_deg=resolved_state.bank_deg,
            feasible=feasible,
            notes=notes,
        )

        return MissionPerformancePoint(
            feasible=feasible,
            bank_deg=resolved_state.bank_deg,
            pitch_deg=resolved_state.pitch_deg,
            load_factor=resolved_state.load_factor,
            propulsion_power_w=propulsion_power_w,
            drag_force_n=drag_force_n,
            lift_coefficient=lift_coefficient,
            drag_coefficient=drag_coefficient,
            dynamic_pressure_pa=dynamic_pressure_pa,
            air_density_kg_m3=air_density_kg_m3,
            notes=" ".join(notes).strip(),
        )


__all__ = [
    "AnalyticMissionPerformanceModel",
    "MissionAircraftPerformanceConfig",
    "MissionOperatingPoint",
    "MissionPerformanceModel",
    "MissionPerformancePoint",
]
