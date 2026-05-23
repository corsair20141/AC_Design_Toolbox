"""AVL-generated polar lookup backend for mission performance."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import degrees, pi, sin
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping

import numpy as np
import pandas as pd
import joblib

from ac_design_toolbox.api import prepare_avl_airplane
from ac_design_toolbox.avl.io import isa_density
from ac_design_toolbox.avl.analysis import run_avl_case
from ac_design_toolbox.mission.avl import (
    _sanitize_case_name,
    _avl_control_deflections,
    _avl_angle_of_attack,
    _avl_sideslip_angle,
)
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


@dataclass
class AVLAeroPolarConfig:
    alpha_min_deg: float = -5.0
    alpha_max_deg: float = 15.0
    alpha_step_deg: float = 1.0
    beta_deg: float = 0.0
    elevator_bounds: tuple[float, float] = (-20.0, 20.0)
    baseline_controls: Mapping[str, float] = field(default_factory=dict)
    avl_exe_path: str | Path = "avl.exe"
    avl_working_directory: str | Path = "simulation_avl"
    tol_Cm: float = 1e-3
    max_elev_iter: int = 15
    timeout_s: float | None = None
    n_jobs: int = -1


@dataclass
class AVLAeroPolarTable:
    config: AVLAeroPolarConfig
    data: pd.DataFrame

    @classmethod
    def from_dataframe(cls, config: AVLAeroPolarConfig, dataframe: pd.DataFrame) -> "AVLAeroPolarTable":
        """Build a polar table from an existing DataFrame."""
        return cls(config=config, data=dataframe.copy())

    @classmethod
    def from_records(cls, config: AVLAeroPolarConfig, records: list[dict[str, Any]]) -> "AVLAeroPolarTable":
        """Build a polar table from JSON-style row records."""
        return cls(config=config, data=pd.DataFrame(list(records)))

    def to_dataframe(self, flatten: bool = True) -> pd.DataFrame:
        """Return the polar table as a DataFrame."""
        return self.data.copy()


def _trim_elevator_for_cm(
    airplane: "asb.Airplane",
    avl_exe: Path,
    working_directory: Path,
    case_name: str,
    alpha_deg: float,
    config: AVLAeroPolarConfig,
    control_index_map: dict[str, int],
    velocity: float = 15.0,
) -> dict[str, Any]:
    """1D root find for elevator to hit Cm=0 at a given alpha."""

    def eval_at(elev_deg: float) -> tuple[float, dict]:
        ctrl = dict(config.baseline_controls)
        ctrl["elevator"] = elev_deg
        res = run_avl_case(
            airplane=airplane,
            avl_exe=avl_exe,
            working_directory=working_directory,
            case_name=case_name,
            alpha=alpha_deg,
            beta=config.beta_deg,
            mach=0.0,
            velocity=velocity,
            density=1.225,
            control_deflections=ctrl,
            control_index_map=control_index_map,
            timeout_s=config.timeout_s,
            write_geom=True,
            force_rewrite_geom=False,
        )
        cm = float(res["scalars"].get("Cm", float("nan")))
        return cm, res

    if "elevator" not in control_index_map:
        cm, res = eval_at(0.0)
        return {"trimmed": False, "elevator_deg": 0.0, "res": res, "Cm": cm}

    de_low, de_high = float(config.elevator_bounds[0]), float(config.elevator_bounds[1])
    cm_low, res_low = eval_at(de_low)
    cm_high, res_high = eval_at(de_high)

    if cm_low * cm_high > 0:
        # Bracket failed, just return elevator=0
        cm, res = eval_at(0.0)
        return {"trimmed": False, "elevator_deg": 0.0, "res": res, "Cm": cm}

    a, fa = de_low, cm_low
    b, fb = de_high, cm_high
    de_hit, res_hit = b, res_high

    for _ in range(config.max_elev_iter):
        if abs(b - a) < 1e-9 or abs(fb - fa) < 1e-9:
            de_new = 0.5 * (a + b)
        else:
            slope = (fb - fa) / (b - a)
            de_new = b - fb / slope
        de_new = 0.7 * de_new + 0.3 * b

        cm_new, res_new = eval_at(de_new)
        de_hit, res_hit = de_new, res_new

        if abs(cm_new) < config.tol_Cm:
            return {"trimmed": True, "elevator_deg": de_new, "res": res_new, "Cm": cm_new}

        if fa * cm_new <= 0.0:
            b, fb = de_new, cm_new
        else:
            a, fa = de_new, cm_new

    return {"trimmed": False, "elevator_deg": de_hit, "res": res_hit, "Cm": fb}


def _polar_oswald_efficiency(row: dict[str, float], aspect_ratio: float) -> float | None:
    """Estimate AVL span efficiency from one interpolated polar row."""
    for key in ("avl_e", "avl_oswald_efficiency", "avl_span_efficiency", "e", "span_efficiency"):
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
        if np.isfinite(value) and value > 0.0:
            return value

    try:
        cl_value = float(row.get("CL"))
        cdi_value = float(row.get("avl_CDind", row.get("CDi", row.get("CDind"))))
    except (TypeError, ValueError):
        return None
    if np.isfinite(cl_value) and np.isfinite(cdi_value) and cdi_value > 0.0 and aspect_ratio > 0.0:
        return cl_value * cl_value / (pi * float(aspect_ratio) * cdi_value)
    return None


def _evaluate_single_alpha(
    alpha: float,
    airplane: "asb.Airplane",
    config: AVLAeroPolarConfig,
    control_index_map: dict[str, int],
    case_name_prefix: str,
) -> dict[str, Any]:
    case_name = f"{case_name_prefix}_a{alpha:.1f}".replace(".", "p").replace("-", "m")
    
    print(f"[{case_name}] Generating polar: solving alpha = {alpha:.1f} deg...")
    
    avl_exe = Path(config.avl_exe_path)
    working_directory = Path(config.avl_working_directory) / case_name
    working_directory.mkdir(parents=True, exist_ok=True)

    trim_res = _trim_elevator_for_cm(
        airplane=airplane,
        avl_exe=avl_exe,
        working_directory=working_directory,
        case_name=case_name,
        alpha_deg=alpha,
        config=config,
        control_index_map=control_index_map,
    )

    res = trim_res["res"]
    row = {
        "CL": float(res["scalars"].get("CL", float("nan"))),
        "CD": float(res["scalars"].get("CD", float("nan"))),
        "alpha_deg": float(alpha),
        "beta_deg": float(config.beta_deg),
        "elevator_deg": float(trim_res["elevator_deg"]),
        "feasible": float(1.0 if trim_res["trimmed"] else 0.0),
        "Cm_residual": float(trim_res["Cm"]),
    }

    # Flattened scalars
    for k, v in res.get("scalars", {}).items():
        if k not in ("CL", "CD", "alpha_deg", "beta_deg", "elevator_deg", "Cm"):
            row[f"avl_{k}"] = float(v) if isinstance(v, (int, float)) else v

    # Stability derivatives
    stab = res.get("stability") or {}
    for k, v in stab.items():
        row[f"stab_{k}"] = float(v) if isinstance(v, (int, float)) else v

    # Add generic controls
    for k, v in _avl_control_deflections(res["scalars"], config.baseline_controls).items():
        row[f"control_{k}_deg"] = float(v)

    return row


def generate_avl_polar(
    airplane: "asb.Airplane",
    config: AVLAeroPolarConfig,
    control_index_map: dict[str, int],
    case_name_prefix: str = "polar",
) -> AVLAeroPolarTable:
    """Generate an AVL polar by sweeping alpha and trimming elevator."""
    alphas = np.arange(config.alpha_min_deg, config.alpha_max_deg + 1e-9, config.alpha_step_deg)

    rows = joblib.Parallel(n_jobs=config.n_jobs, prefer="threads")(
        joblib.delayed(_evaluate_single_alpha)(
            float(alpha),
            airplane,
            config,
            control_index_map,
            case_name_prefix,
        )
        for alpha in alphas
    )

    df = pd.DataFrame(rows)
    df = df.sort_values(by="CL").reset_index(drop=True)
    return AVLAeroPolarTable(config=config, data=df)


@dataclass
class AVLPolarMissionPerformanceModel:
    """Mission-performance adapter that uses an upfront AVL polar lookup table."""

    airplane: "asb.Airplane | Any"
    aircraft: MissionAircraftPerformanceConfig
    config: AVLAeroPolarConfig
    polar_table: AVLAeroPolarTable | None = None
    control_index_map: Mapping[str, int] | None = None
    case_name_prefix: str = "mission_polar"
    gravity_m_s2: float = STANDARD_GRAVITY_M_S2

    _table: AVLAeroPolarTable | None = field(init=False, default=None, repr=False)
    _cached_control_index_map: dict[str, int] | None = field(init=False, default=None, repr=False)

    def __post_init__(self):
        if self.control_index_map is not None:
            self._cached_control_index_map = dict(self.control_index_map)
        if self.polar_table is not None:
            self._table = self.polar_table

    def get_polar_table(self) -> AVLAeroPolarTable:
        """Return the underlying polar table, generating it if necessary."""
        if self._table is not None:
            return self._table

        case_dir = Path(self.config.avl_working_directory) / self.case_name_prefix
        case_dir.mkdir(parents=True, exist_ok=True)

        control_index_map = self._cached_control_index_map
        if control_index_map is None:
            prepared = prepare_avl_airplane(self.airplane, working_directory=case_dir)
            control_index_map = {str(key): int(value) for key, value in prepared["control_index_map"].items()}
            self._cached_control_index_map = control_index_map

        self._table = generate_avl_polar(
            airplane=self.airplane,
            config=self.config,
            control_index_map=control_index_map,
            case_name_prefix=self.case_name_prefix,
        )
        return self._table

    def evaluate(self, op: MissionOperatingPoint) -> MissionPerformancePoint:
        """Evaluate one air-relative operating point using the polar lookup table."""
        table = self.get_polar_table()
        df = table.data

        resolved_state = _resolve_operating_point_state(op, gravity_m_s2=self.gravity_m_s2)
        air_density_kg_m3 = isa_density(op.altitude, temp_shift_F=op.temp_shift)
        dynamic_pressure_pa = 0.5 * air_density_kg_m3 * op.airspeed**2
        weight_newtons = self.aircraft.mass * self.gravity_m_s2
        lift_target_newtons = weight_newtons * resolved_state.load_factor
        lift_coefficient_target = lift_target_newtons / (dynamic_pressure_pa * self.aircraft.wing_area)

        notes = list(resolved_state.notes)
        feasible = resolved_state.feasible

        min_CL = df["CL"].min()
        max_CL = df["CL"].max()
        if lift_coefficient_target < min_CL or lift_coefficient_target > max_CL:
            feasible = False
            notes.append(
                f"Required CL {lift_coefficient_target:.4f} is outside polar range "
                f"[{min_CL:.4f}, {max_CL:.4f}]. Clamping."
            )

        clamped_CL = float(np.clip(lift_coefficient_target, min_CL, max_CL))

        interp_row = {}
        for col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                interp_row[col] = float(np.interp(clamped_CL, df["CL"], df[col]))

        raw_avl_drag_coefficient = interp_row.get("CD", float("nan"))
        drag_coefficient = raw_avl_drag_coefficient + self.aircraft.zero_lift_drag_coefficient
        avl_oswald_efficiency = _polar_oswald_efficiency(interp_row, self.aircraft.aspect_ratio)
        alpha_deg = interp_row.get("alpha_deg", float("nan"))
        beta_deg = interp_row.get("beta_deg", float("nan"))

        if interp_row.get("feasible", 1.0) < 0.5:
            feasible = False
            notes.append(f"Polar row at CL {clamped_CL:.4f} is marked infeasible (likely untrimmed).")

        drag_force_n = dynamic_pressure_pa * self.aircraft.wing_area * drag_coefficient
        useful_propulsive_force_n = drag_force_n + weight_newtons * sin(resolved_state.flight_path_angle_rad)
        propulsion_power_w = useful_propulsive_force_n * op.airspeed / self.aircraft.propulsive_efficiency

        pitch_deg = resolved_state.pitch_deg
        if op.pitch_hint is None:
            pitch_deg = degrees(resolved_state.flight_path_angle_rad) + alpha_deg
            notes.append("Returned pitch adds AVL polar alpha to the prescribed flight-path angle.")

        if abs(resolved_state.bank_deg) > 1e-9:
            notes.append(
                "Banked-turn effects enter through the target load factor only; lateral-directional trim is not solved."
            )
        if propulsion_power_w < 0.0:
            notes.append("Negative propulsion_power means the climb-energy balance predicts no net propulsive input.")

        feasible = _apply_feasibility_limits(
            self.aircraft,
            lift_coefficient=clamped_CL,
            load_factor=resolved_state.load_factor,
            bank_deg=resolved_state.bank_deg,
            feasible=feasible,
            notes=notes,
        )

        controls = {}
        for col in df.columns:
            if col.startswith("control_") and col.endswith("_deg"):
                name = col[len("control_") : -len("_deg")]
                controls[name] = interp_row[col]

        diagnostics = {
            "avl_call_count": 0,
            "raw_avl_drag_coefficient": raw_avl_drag_coefficient,
            "zero_lift_drag_coefficient": self.aircraft.zero_lift_drag_coefficient,
            **(
                {"avl_oswald_efficiency": avl_oswald_efficiency}
                if avl_oswald_efficiency is not None
                else {}
            ),
        }
        for col in df.columns:
            if col not in ("CL", "CD", "alpha_deg", "beta_deg", "feasible", "elevator_deg") and not col.startswith(
                "control_"
            ):
                if col in interp_row:
                    diagnostics[f"performance_polar_{col}"] = interp_row[col]

        return MissionPerformancePoint(
            feasible=feasible,
            bank=resolved_state.bank_deg,
            pitch=pitch_deg,
            load_factor=resolved_state.load_factor,
            propulsion_power=propulsion_power_w,
            drag_force=drag_force_n,
            lift_coefficient=clamped_CL,
            drag_coefficient=drag_coefficient,
            dynamic_pressure=dynamic_pressure_pa,
            air_density=air_density_kg_m3,
            angle_of_attack=alpha_deg,
            sideslip_angle=beta_deg,
            elevator_deflection=controls.get("elevator"),
            aileron_deflection=controls.get("aileron"),
            rudder_deflection=controls.get("rudder"),
            flap_deflection=controls.get("flap"),
            control_surface_deflections=controls,
            notes=" ".join(notes).strip(),
            diagnostics=diagnostics,
        )


__all__ = [
    "AVLAeroPolarConfig",
    "AVLAeroPolarTable",
    "AVLPolarMissionPerformanceModel",
]
