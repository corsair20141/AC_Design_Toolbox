"""Optional AVL-backed mission-performance adapter."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from math import degrees, sin
import math
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

from ac_design_toolbox.api import prepare_avl_airplane
from ac_design_toolbox.avl.io import isa_density
from ac_design_toolbox.avl.trim import avl_trim_longitudinal
from ac_design_toolbox.mission.performance import (
    STANDARD_GRAVITY_M_S2,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
    MissionPerformancePoint,
    _apply_feasibility_limits,
    _resolve_operating_point_state,
)

if TYPE_CHECKING:
    import aerosandbox as asb


def _sanitize_case_name(text: str) -> str:
    """Return a filesystem-friendly AVL case name."""
    sanitized = re.sub(r"[^0-9A-Za-z_]+", "_", text.strip())
    sanitized = sanitized.strip("_")
    return sanitized or "mission"


def _first_float(mapping: Mapping[str, Any], *keys: str) -> float | None:
    """Return the first finite scalar value from a result mapping."""
    for key in keys:
        if key not in mapping or mapping[key] is None:
            continue
        return float(mapping[key])
    return None


def _avl_control_deflections(
    result: Mapping[str, Any],
    baseline_controls: Mapping[str, float],
) -> dict[str, float]:
    """Return named control deflections from AVL result data plus baselines."""
    controls = {str(name): float(value) for name, value in baseline_controls.items()}
    result_controls = result.get("control_surface_deflections") or result.get("control_deflections")
    if isinstance(result_controls, Mapping):
        controls.update({str(name): float(value) for name, value in result_controls.items()})

    for control_name in ("elevator", "aileron", "rudder", "flap"):
        value = _first_float(
            result,
            f"{control_name}_trim_deg",
            f"{control_name}_deflection_deg",
            f"{control_name}_deflection",
            control_name,
        )
        if value is not None:
            controls[control_name] = value
    return controls


def _avl_angle_of_attack(result: Mapping[str, Any]) -> float | None:
    """Return angle of attack from common AVL result field names."""
    return _first_float(result, "alpha_trim_deg", "alpha_deg", "Alpha", "alpha")


def _avl_sideslip_angle(result: Mapping[str, Any]) -> float | None:
    """Return sideslip angle from common AVL result field names."""
    return _first_float(result, "beta_trim_deg", "beta_deg", "Beta", "beta")


def _avl_oswald_efficiency(result: Mapping[str, Any], aspect_ratio: float) -> float | None:
    """Estimate AVL span efficiency from reported induced-drag data."""
    for key in ("oswald_efficiency", "span_efficiency", "e"):
        try:
            value = float(result[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value) and value > 0.0:
            return value

    try:
        k_value = float(result.get("K"))
    except (TypeError, ValueError):
        k_value = float("nan")
    if math.isfinite(k_value) and k_value > 0.0 and aspect_ratio > 0.0:
        return 1.0 / (math.pi * float(aspect_ratio) * k_value)

    try:
        cl_value = float(result.get("CL"))
        cdi_value = float(result.get("CDi", result.get("CDind")))
    except (TypeError, ValueError):
        return None
    if math.isfinite(cl_value) and math.isfinite(cdi_value) and cdi_value > 0.0 and aspect_ratio > 0.0:
        return cl_value * cl_value / (math.pi * float(aspect_ratio) * cdi_value)
    return None


@dataclass
class AVLMissionPerformanceModel:
    """Mission-performance adapter that gets aerodynamic coefficients from AVL.

    The adapter preserves the same unit-aware operating-point contract as the
    analytic model. Public mission dataclasses normalize quantity inputs before
    this adapter runs, so the AVL path still works on plain floats in the same
    computational units used by the analytic solver.

    Bank angle, flight-path angle, and load factor are still inferred from the
    prescribed air-relative operating point. AVL is then used only for
    quasi-steady longitudinal trim at the resulting target lift coefficient.

    This keeps the interface thin and stable, but it also means the current
    AVL-backed path does not solve full turning or lateral-directional trim.
    Banked-turn effects enter through the required load factor rather than
    through a separate rudder/aileron/sideslip solution.
    """

    airplane: "asb.Airplane | Any"
    aircraft: MissionAircraftPerformanceConfig
    avl_exe: str | Path
    working_directory: str | Path
    control_index_map: Mapping[str, int] | None = None
    baseline_controls: Mapping[str, float] = field(default_factory=dict)
    mach: float = 0.0
    elevator_bounds: tuple[float, float] = (-20.0, 20.0)
    alpha_seed_deg: float = 4.0
    elevator_seed_deg: float = 0.0
    tol_CL: float = 1e-2
    tol_Cm: float = 1e-3
    max_iter: int = 12
    timeout_s: float | None = None
    case_name_prefix: str = "mission_avl"
    gravity_m_s2: float = STANDARD_GRAVITY_M_S2
    _cached_control_index_map: dict[str, int] | None = field(init=False, default=None, repr=False)

    def __post_init__(self) -> None:
        """Normalize path-like and mapping inputs for repeat mission queries."""
        self.avl_exe = Path(self.avl_exe)
        self.working_directory = Path(self.working_directory)
        self.working_directory.mkdir(parents=True, exist_ok=True)
        self.baseline_controls = dict(self.baseline_controls)
        if self.control_index_map is not None:
            self.control_index_map = {str(key): int(value) for key, value in self.control_index_map.items()}
            self._cached_control_index_map = dict(self.control_index_map)

    def evaluate(self, op: MissionOperatingPoint) -> MissionPerformancePoint:
        """Evaluate one air-relative operating point with AVL-based trim coefficients."""
        resolved_state = _resolve_operating_point_state(op, gravity_m_s2=self.gravity_m_s2)
        air_density_kg_m3 = isa_density(op.altitude, temp_shift_F=op.temp_shift)
        dynamic_pressure_pa = 0.5 * air_density_kg_m3 * op.airspeed**2
        weight_newtons = self.aircraft.mass * self.gravity_m_s2
        lift_target_newtons = weight_newtons * resolved_state.load_factor
        lift_coefficient_target = lift_target_newtons / (dynamic_pressure_pa * self.aircraft.wing_area)

        case_name = self._build_case_name(op)
        control_index_map = self._ensure_case_setup(case_name)

        try:
            trim_result = avl_trim_longitudinal(
                airplane=self.airplane,
                avl_exe=self.avl_exe,
                working_directory=self.working_directory,
                case_name=case_name,
                CL_target=lift_coefficient_target,
                velocity=op.airspeed,
                altitude=op.altitude,
                temp_shift_F=op.temp_shift,
                mach=self.mach,
                control_index_map=control_index_map,
                baseline_controls=self.baseline_controls,
                elevator_bounds=self.elevator_bounds,
                alpha_seed_deg=self.alpha_seed_deg,
                elevator_seed_deg=self.elevator_seed_deg,
                tol_CL=self.tol_CL,
                tol_Cm=self.tol_Cm,
                max_iter=self.max_iter,
                timeout_s=self.timeout_s,
                write_geom=False,
                force_rewrite_geom=False,
            )
        except Exception as exc:
            raise RuntimeError(f"AVL mission-performance evaluation failed for phase '{op.phase_name}'.") from exc

        air_density_kg_m3 = float(trim_result.get("rho", air_density_kg_m3))
        dynamic_pressure_pa = 0.5 * air_density_kg_m3 * op.airspeed**2
        lift_coefficient = float(trim_result["CL"])
        raw_avl_drag_coefficient = float(trim_result["CD"])
        drag_coefficient = raw_avl_drag_coefficient + self.aircraft.zero_lift_drag_coefficient
        drag_force_n = dynamic_pressure_pa * self.aircraft.wing_area * drag_coefficient
        useful_propulsive_force_n = drag_force_n + weight_newtons * sin(resolved_state.flight_path_angle_rad)
        propulsion_power_w = useful_propulsive_force_n * op.airspeed / self.aircraft.propulsive_efficiency

        pitch_deg = resolved_state.pitch_deg
        notes = list(resolved_state.notes)
        if op.pitch_hint is None:
            pitch_deg = degrees(resolved_state.flight_path_angle_rad) + float(trim_result["alpha_trim_deg"])
            notes.append("Returned pitch adds AVL trim alpha to the prescribed flight-path angle.")

        reported_alpha_deg = _avl_angle_of_attack(trim_result)
        reported_controls = _avl_control_deflections(trim_result, self.baseline_controls)
        reported_elevator_deg = reported_controls.get("elevator")
        if reported_alpha_deg is not None and reported_elevator_deg is not None:
            self.alpha_seed_deg = float(reported_alpha_deg)
            self.elevator_seed_deg = float(reported_elevator_deg)
            notes.append(
                f"AVL solved alpha={reported_alpha_deg:.3f} deg and "
                f"elevator={reported_elevator_deg:.3f} deg."
            )
        if trim_result.get("newton2d_failure_reason"):
            notes.append(f"AVL trim fell back to the 1D solver ({trim_result['newton2d_failure_reason']}).")
        if abs(resolved_state.bank_deg) > 1e-9:
            notes.append(
                "Banked-turn effects enter through the target load factor only; lateral-directional trim is not solved."
            )
        if abs(lift_coefficient - lift_coefficient_target) > self.tol_CL:
            notes.append(
                f"AVL trim missed the CL target by {lift_coefficient - lift_coefficient_target:+.4f}."
            )
        if abs(float(trim_result["Cm"])) > self.tol_Cm:
            notes.append(f"AVL trim residual Cm is {float(trim_result['Cm']):+.4f}.")
        if propulsion_power_w < 0.0:
            notes.append("Negative propulsion_power means the climb-energy balance predicts no net propulsive input.")

        control_surface_deflections = reported_controls
        alpha_deg = reported_alpha_deg
        beta_deg = _avl_sideslip_angle(trim_result)
        avl_oswald_efficiency = _avl_oswald_efficiency(trim_result, self.aircraft.aspect_ratio)

        feasible = resolved_state.feasible
        if abs(lift_coefficient - lift_coefficient_target) > self.tol_CL or abs(float(trim_result["Cm"])) > self.tol_Cm:
            feasible = False

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
            pitch=pitch_deg,
            load_factor=resolved_state.load_factor,
            propulsion_power=propulsion_power_w,
            drag_force=drag_force_n,
            lift_coefficient=lift_coefficient,
            drag_coefficient=drag_coefficient,
            dynamic_pressure=dynamic_pressure_pa,
            air_density=air_density_kg_m3,
            angle_of_attack=alpha_deg,
            sideslip_angle=beta_deg,
            elevator_deflection=control_surface_deflections.get("elevator"),
            aileron_deflection=control_surface_deflections.get("aileron"),
            rudder_deflection=control_surface_deflections.get("rudder"),
            flap_deflection=control_surface_deflections.get("flap"),
            control_surface_deflections=control_surface_deflections,
            notes=" ".join(notes).strip(),
            diagnostics={
                "avl_call_count": trim_result.get("avl_calls"),
                "raw_avl_drag_coefficient": raw_avl_drag_coefficient,
                "zero_lift_drag_coefficient": self.aircraft.zero_lift_drag_coefficient,
                **(
                    {"avl_oswald_efficiency": avl_oswald_efficiency}
                    if avl_oswald_efficiency is not None
                    else {}
                ),
            },
        )

    def _build_case_name(self, op: MissionOperatingPoint) -> str:
        """Build a stable case name from the configured prefix and mission phase."""
        return f"{_sanitize_case_name(self.case_name_prefix)}_{_sanitize_case_name(op.phase_name)}"

    def _ensure_case_setup(self, case_name: str) -> dict[str, int]:
        """Ensure patched AVL geometry exists and return a matching control map."""
        case_dir = self.working_directory / case_name
        geom_path = case_dir / "Airplane.avl"

        control_index_map = (
            dict(self.control_index_map) if self.control_index_map is not None else self._cached_control_index_map
        )

        if not geom_path.exists() or control_index_map is None:
            prepared = prepare_avl_airplane(self.airplane, working_directory=case_dir)
            prepared_map = {str(key): int(value) for key, value in prepared["control_index_map"].items()}

            if self.control_index_map is not None:
                if prepared_map != dict(self.control_index_map):
                    raise ValueError("Provided control_index_map does not match the patched AVL geometry control order.")
                control_index_map = dict(self.control_index_map)
            else:
                control_index_map = prepared_map
                self._cached_control_index_map = dict(prepared_map)

        if control_index_map is None:
            raise RuntimeError("Unable to determine a control_index_map for AVL mission evaluation.")

        return dict(control_index_map)


__all__ = ["AVLMissionPerformanceModel"]
