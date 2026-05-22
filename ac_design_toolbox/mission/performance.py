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
from ac_design_toolbox.mission.units import QuantityInput, coerce_optional_quantity, coerce_quantity

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


def _require_optional_finite_scalar(name: str, value: float | None) -> float | None:
    """Return an optional scalar float after checking that it is finite."""
    if value is None:
        return None

    return _require_finite_scalar(name, value)


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

    Dimensional public inputs accept either bare scalars in the stored
    computational unit, ``(value, "unit")`` tuples, or ``[value, "unit"]``
    lists. After normalization this dataclass stores:

    - ``altitude`` in ``m``
    - ``airspeed`` and ``climb_rate`` in ``m_s``
    - ``turn_radius`` in ``m``
    - ``bank_hint`` and ``pitch_hint`` in ``deg``
    - ``temp_shift`` in ``degF``

    The operating point is intentionally minimal. It carries only the
    air-relative state needed to estimate first-pass aerodynamic and power
    quantities for a single instant. Mission path propagation, ENU kinematics,
    and wind injection remain external responsibilities.
    """

    phase_name: str
    altitude: QuantityInput
    airspeed: QuantityInput
    climb_rate: QuantityInput
    turn_radius: QuantityInput | None = None
    bank_hint: QuantityInput | None = None
    pitch_hint: QuantityInput | None = None
    load_factor_hint: float | None = None
    temp_shift: QuantityInput = 0.0
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Normalize public inputs into the mission solver's computational units."""
        phase_name = str(self.phase_name).strip()
        if not phase_name:
            raise ValueError("phase_name must be a non-empty string.")
        object.__setattr__(self, "phase_name", phase_name)

        altitude = coerce_quantity("altitude", self.altitude, "m", "length")
        airspeed = coerce_quantity("airspeed", self.airspeed, "m_s", "speed")
        climb_rate = coerce_quantity("climb_rate", self.climb_rate, "m_s", "rate")
        temp_shift = coerce_quantity("temp_shift", self.temp_shift, "degF", "temperature_delta")

        if airspeed <= 0.0:
            raise ValueError("airspeed must be positive.")

        object.__setattr__(self, "altitude", altitude)
        object.__setattr__(self, "airspeed", airspeed)
        object.__setattr__(self, "climb_rate", climb_rate)
        object.__setattr__(self, "temp_shift", temp_shift)

        turn_radius = coerce_optional_quantity("turn_radius", self.turn_radius, "m", "length")
        if turn_radius is not None and turn_radius <= 0.0:
            raise ValueError("turn_radius must be positive when provided.")
        object.__setattr__(self, "turn_radius", turn_radius)

        object.__setattr__(self, "bank_hint", coerce_optional_quantity("bank_hint", self.bank_hint, "deg", "angle"))
        object.__setattr__(self, "pitch_hint", coerce_optional_quantity("pitch_hint", self.pitch_hint, "deg", "angle"))

        if self.load_factor_hint is not None:
            object.__setattr__(
                self,
                "load_factor_hint",
                _require_finite_scalar("load_factor_hint", self.load_factor_hint),
            )

        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class MissionPerformancePoint:
    """Resolved first-pass aircraft-performance state for one operating point.

    Dimensional constructor inputs accept either bare scalars in the stored
    computational unit, ``(value, "unit")`` tuples, or ``[value, "unit"]``
    lists. After normalization this dataclass stores:

    - ``bank`` and ``pitch`` in ``deg``
    - ``propulsion_power`` in ``w``
    - ``drag_force`` in ``n``
    - ``dynamic_pressure`` in ``pa``
    - ``air_density`` in ``kg_m3``
    - optional aerodynamic/control angles in ``deg``
    """

    feasible: bool
    bank: QuantityInput
    pitch: QuantityInput
    load_factor: float
    propulsion_power: QuantityInput
    drag_force: QuantityInput | None = None
    lift_coefficient: float | None = None
    drag_coefficient: float | None = None
    dynamic_pressure: QuantityInput | None = None
    air_density: QuantityInput | None = None
    angle_of_attack: QuantityInput | None = None
    sideslip_angle: QuantityInput | None = None
    elevator_deflection: QuantityInput | None = None
    aileron_deflection: QuantityInput | None = None
    rudder_deflection: QuantityInput | None = None
    flap_deflection: QuantityInput | None = None
    control_surface_deflections: Mapping[str, QuantityInput] = field(default_factory=dict)
    notes: str = ""

    def __post_init__(self) -> None:
        """Normalize public result fields into the documented computational units."""
        object.__setattr__(self, "feasible", bool(self.feasible))
        object.__setattr__(self, "bank", coerce_quantity("bank", self.bank, "deg", "angle"))
        object.__setattr__(self, "pitch", coerce_quantity("pitch", self.pitch, "deg", "angle"))
        object.__setattr__(self, "load_factor", _require_finite_scalar("load_factor", self.load_factor))
        object.__setattr__(
            self,
            "propulsion_power",
            coerce_quantity("propulsion_power", self.propulsion_power, "w", "power"),
        )
        object.__setattr__(
            self,
            "drag_force",
            coerce_optional_quantity("drag_force", self.drag_force, "n", "force"),
        )
        object.__setattr__(
            self,
            "dynamic_pressure",
            coerce_optional_quantity("dynamic_pressure", self.dynamic_pressure, "pa", "pressure"),
        )
        object.__setattr__(
            self,
            "air_density",
            coerce_optional_quantity("air_density", self.air_density, "kg_m3", "density"),
        )
        object.__setattr__(
            self,
            "lift_coefficient",
            _require_optional_finite_scalar("lift_coefficient", self.lift_coefficient),
        )
        object.__setattr__(
            self,
            "drag_coefficient",
            _require_optional_finite_scalar("drag_coefficient", self.drag_coefficient),
        )
        for field_name in (
            "angle_of_attack",
            "sideslip_angle",
            "elevator_deflection",
            "aileron_deflection",
            "rudder_deflection",
            "flap_deflection",
        ):
            object.__setattr__(
                self,
                field_name,
                coerce_optional_quantity(field_name, getattr(self, field_name), "deg", "angle"),
            )
        object.__setattr__(
            self,
            "control_surface_deflections",
            MappingProxyType(
                {
                    str(control_name): coerce_quantity(
                        f"control_surface_deflections[{control_name}]",
                        deflection,
                        "deg",
                        "angle",
                    )
                    for control_name, deflection in dict(self.control_surface_deflections).items()
                }
            ),
        )
        object.__setattr__(self, "notes", str(self.notes))


@dataclass(frozen=True)
class MissionAircraftPerformanceConfig:
    """Scalar aircraft-performance inputs for the mission analytic model.

    Dimensional public inputs accept either bare scalars in the stored
    computational unit, ``(value, "unit")`` tuples, or ``[value, "unit"]``
    lists. After normalization this dataclass stores:

    - ``mass`` in ``kg``
    - ``wing_area`` in ``m2``
    - ``max_bank`` in ``deg``

    The container is intentionally thin so external projects can depend on a
    stable interface without importing geometry-heavy workflows. It is meant for
    first-pass performance estimation from a prescribed air-relative operating
    point rather than for full trim or high-fidelity aerodynamic prediction.
    """

    mass: QuantityInput
    wing_area: QuantityInput
    aspect_ratio: float
    oswald_efficiency: float
    zero_lift_drag_coefficient: float
    propulsive_efficiency: float
    max_lift_coefficient: float | None = None
    max_bank: QuantityInput | None = None
    max_load_factor: float | None = None

    def __post_init__(self) -> None:
        """Normalize public inputs into the analytic model's computational units."""
        mass = coerce_quantity("mass", self.mass, "kg", "mass")
        wing_area = coerce_quantity("wing_area", self.wing_area, "m2", "area")
        aspect_ratio = _require_finite_scalar("aspect_ratio", self.aspect_ratio)
        oswald_efficiency = _require_finite_scalar("oswald_efficiency", self.oswald_efficiency)
        zero_lift_drag_coefficient = _require_finite_scalar(
            "zero_lift_drag_coefficient",
            self.zero_lift_drag_coefficient,
        )
        propulsive_efficiency = _require_finite_scalar("propulsive_efficiency", self.propulsive_efficiency)

        if mass <= 0.0:
            raise ValueError("mass must be positive.")
        if wing_area <= 0.0:
            raise ValueError("wing_area must be positive.")
        if aspect_ratio <= 0.0:
            raise ValueError("aspect_ratio must be positive.")
        if oswald_efficiency <= 0.0:
            raise ValueError("oswald_efficiency must be positive.")
        if zero_lift_drag_coefficient < 0.0:
            raise ValueError("zero_lift_drag_coefficient must be non-negative.")
        if propulsive_efficiency <= 0.0 or propulsive_efficiency > 1.0:
            raise ValueError("propulsive_efficiency must lie in the interval (0, 1].")

        object.__setattr__(self, "mass", mass)
        object.__setattr__(self, "wing_area", wing_area)
        object.__setattr__(self, "aspect_ratio", aspect_ratio)
        object.__setattr__(self, "oswald_efficiency", oswald_efficiency)
        object.__setattr__(self, "zero_lift_drag_coefficient", zero_lift_drag_coefficient)
        object.__setattr__(self, "propulsive_efficiency", propulsive_efficiency)

        if self.max_lift_coefficient is not None:
            max_lift_coefficient = _require_finite_scalar("max_lift_coefficient", self.max_lift_coefficient)
            if max_lift_coefficient <= 0.0:
                raise ValueError("max_lift_coefficient must be positive when provided.")
            object.__setattr__(self, "max_lift_coefficient", max_lift_coefficient)

        max_bank = coerce_optional_quantity("max_bank", self.max_bank, "deg", "angle")
        if max_bank is not None:
            if max_bank <= 0.0 or max_bank >= 90.0:
                raise ValueError("max_bank must lie in the interval (0, 90).")
            object.__setattr__(self, "max_bank", max_bank)

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
        mass: QuantityInput,
        oswald_efficiency: float,
        zero_lift_drag_coefficient: float,
        propulsive_efficiency: float,
        max_lift_coefficient: float | None = None,
        max_bank: QuantityInput | None = None,
        max_load_factor: float | None = None,
    ) -> "MissionAircraftPerformanceConfig":
        """Build a mission config from an AeroSandbox-style airplane object.

        The public ``mass`` and ``max_bank`` inputs accept bare scalars in
        canonical units, ``(value, "unit")`` tuples, and ``[value, "unit"]``
        lists. The extracted reference wing area and span from the airplane
        object are assumed to already be in SI units from AeroSandbox.
        """
        try:
            wing_area_m2 = float(getattr(airplane, "s_ref"))
            span_m = float(getattr(airplane, "b_ref"))
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError("airplane must expose numeric s_ref and b_ref attributes.") from exc

        if wing_area_m2 <= 0.0 or span_m <= 0.0:
            raise ValueError("airplane reference area and span must be positive.")

        return cls(
            mass=mass,
            wing_area=wing_area_m2,
            aspect_ratio=span_m**2 / wing_area_m2,
            oswald_efficiency=oswald_efficiency,
            zero_lift_drag_coefficient=zero_lift_drag_coefficient,
            propulsive_efficiency=propulsive_efficiency,
            max_lift_coefficient=max_lift_coefficient,
            max_bank=max_bank,
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

    if op.bank_hint is not None:
        return radians(op.bank_hint), notes

    if op.turn_radius is not None:
        horizontal_speed_sq = max(op.airspeed**2 - op.climb_rate**2, 0.0)
        gamma_cosine = max(cos(flight_path_angle_rad), COSINE_FLOOR)
        return atan(horizontal_speed_sq / (gravity_m_s2 * op.turn_radius * gamma_cosine)), notes

    if op.load_factor_hint is not None:
        if op.load_factor_hint <= 0.0:
            notes.append("load_factor_hint could not define a coordinated bank angle, so bank defaults to 0 deg.")
            return 0.0, notes

        cosine_argument = cos(flight_path_angle_rad) / op.load_factor_hint
        clipped_argument = _clip_unit_interval(cosine_argument)
        if abs(cosine_argument) > 1.0:
            notes.append("load_factor_hint is inconsistent with coordinated flight at the requested climb_rate.")
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

    climb_ratio = op.climb_rate / op.airspeed
    clipped_climb_ratio = _clip_unit_interval(climb_ratio)
    if abs(climb_ratio) > 1.0:
        feasible = False
        notes.append("Requested climb_rate magnitude exceeds airspeed, so the flight-path angle was clipped.")

    # The model uses climb rate to determine the flight-path angle because
    # pitch hints describe attitude reporting, not the energy rate.
    flight_path_angle_rad = asin(clipped_climb_ratio)
    pitch_deg = float(op.pitch_hint) if op.pitch_hint is not None else degrees(flight_path_angle_rad)
    if op.pitch_hint is not None:
        notes.append("Reported pitch uses pitch_hint; force balance still follows climb_rate.")

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

    if aircraft.max_bank is not None and abs(bank_deg) > aircraft.max_bank:
        feasible = False
        notes.append(f"Bank angle {bank_deg:.3f} deg exceeds phi_max {aircraft.max_bank:.3f} deg.")

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

    Public mission inputs are expected to arrive through the unit-aware mission
    dataclasses and are already normalized to plain floats before the math here
    runs.
    """

    aircraft: MissionAircraftPerformanceConfig
    gravity_m_s2: float = STANDARD_GRAVITY_M_S2

    def evaluate(self, op: MissionOperatingPoint) -> MissionPerformancePoint:
        """Evaluate one air-relative operating point with transparent approximations."""
        atmosphere = standard_atmosphere(op.altitude, units="si", temp_shift_F=op.temp_shift)
        if isinstance(atmosphere, list):
            raise TypeError("Mission operating-point evaluation expects a scalar altitude.")

        air_density_kg_m3 = float(atmosphere["rho"])
        dynamic_pressure_pa = 0.5 * air_density_kg_m3 * op.airspeed**2

        resolved_state = _resolve_operating_point_state(op, gravity_m_s2=self.gravity_m_s2)
        feasible = resolved_state.feasible
        notes = list(resolved_state.notes)

        weight_newtons = self.aircraft.mass * self.gravity_m_s2
        lift_force_n = weight_newtons * resolved_state.load_factor
        lift_coefficient = lift_force_n / (dynamic_pressure_pa * self.aircraft.wing_area)
        drag_coefficient = self.aircraft.zero_lift_drag_coefficient + CD_i_oswald(
            CL=lift_coefficient,
            AR=self.aircraft.aspect_ratio,
            e=self.aircraft.oswald_efficiency,
        )
        drag_force_n = dynamic_pressure_pa * self.aircraft.wing_area * drag_coefficient

        useful_propulsive_force_n = drag_force_n + weight_newtons * sin(resolved_state.flight_path_angle_rad)
        propulsion_power_w = useful_propulsive_force_n * op.airspeed / self.aircraft.propulsive_efficiency
        if propulsion_power_w < 0.0:
            notes.append("Negative propulsion_power means this first-pass model predicts no net propulsive input.")

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
            bank=resolved_state.bank_deg,
            pitch=resolved_state.pitch_deg,
            load_factor=resolved_state.load_factor,
            propulsion_power=propulsion_power_w,
            drag_force=drag_force_n,
            lift_coefficient=lift_coefficient,
            drag_coefficient=drag_coefficient,
            dynamic_pressure=dynamic_pressure_pa,
            air_density=air_density_kg_m3,
            notes=" ".join(notes).strip(),
        )


__all__ = [
    "AnalyticMissionPerformanceModel",
    "MissionAircraftPerformanceConfig",
    "MissionOperatingPoint",
    "MissionPerformanceModel",
    "MissionPerformancePoint",
]
