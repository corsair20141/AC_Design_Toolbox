"""High-level convenience API for common geometry and AVL workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import aerosandbox as asb


@dataclass
class AVLCaseConfig:
    """Configuration for a single AVL operating-point analysis."""

    case_name: str = "avl_case"
    alpha: float = 0.0
    beta: float = 0.0
    mach: float = 0.0
    velocity: float = 0.0
    density: float = 1.225
    aircraft_mass: float = 0.0
    roll_rate: float = 0.0
    pitch_rate: float = 0.0
    yaw_rate: float = 0.0
    control_deflections: dict[str, float] = field(default_factory=dict)
    altitude: float | None = None
    temp_shift_F: float = 0.0
    timeout_s: int = 300


@dataclass
class AVLTrimConfig:
    """Configuration for longitudinal trim about a target lift coefficient."""

    case_name: str = "trim_case"
    CL_target: float = 0.0
    velocity: float = 0.0
    altitude: float | None = None
    temp_shift_F: float = 0.0
    mach: float = 0.0
    baseline_controls: dict[str, float] = field(default_factory=dict)
    elevator_bounds: tuple[float, float] = (-20.0, 20.0)
    alpha_seed_deg: float = 4.0
    elevator_seed_deg: float = 0.0
    tol_CL: float = 1e-2
    tol_Cm: float = 1e-3
    max_iter: int = 12
    timeout_s: float | None = None


def build_simple_aircraft(*args, **kwargs):
    """Preferred package-level alias for :func:`geometry.simple_aircraft`."""
    from ac_design_toolbox.geometry.aircraft import simple_aircraft

    return simple_aircraft(*args, **kwargs)


def prepare_avl_airplane(
    airplane: "asb.Airplane",
    working_directory: str | Path,
    op_point: "asb.OperatingPoint | None" = None,
    file_name: str = "Airplane.avl",
) -> dict[str, Any]:
    """Write AVL geometry and return the control-index map discovered by the patched writer."""
    import aerosandbox as asb

    from ac_design_toolbox.geometry.avl_patch import patched_AVL

    working_directory = Path(working_directory)
    working_directory.mkdir(parents=True, exist_ok=True)

    if op_point is None:
        op_point = asb.OperatingPoint()

    avl = patched_AVL(airplane=airplane, op_point=op_point, working_directory=working_directory)
    avl.write_avl(file_name)

    return {
        "geom": working_directory / file_name,
        "control_index_map": dict(getattr(avl, "_control_index_map", {})),
    }


def run_case(
    airplane: "asb.Airplane",
    avl_exe: str | Path,
    working_directory: str | Path,
    config: AVLCaseConfig,
    *,
    control_index_map: dict[str, int] | None = None,
    op_point: "asb.OperatingPoint | None" = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True,
    geom_writer=None,
):
    """Run a single AVL case using a structured configuration object."""
    from ac_design_toolbox.avl.analysis import run_avl_case

    working_directory = Path(working_directory)
    effective_write_geom = write_geom

    if control_index_map is None:
        case_dir = working_directory / config.case_name
        prepared = prepare_avl_airplane(airplane=airplane, working_directory=case_dir, op_point=op_point)
        control_index_map = prepared["control_index_map"]
        effective_write_geom = False

    return run_avl_case(
        airplane=airplane,
        avl_exe=avl_exe,
        working_directory=working_directory,
        case_name=config.case_name,
        alpha=config.alpha,
        beta=config.beta,
        mach=config.mach,
        velocity=config.velocity,
        density=config.density,
        aircraft_mass=config.aircraft_mass,
        roll_rate=config.roll_rate,
        pitch_rate=config.pitch_rate,
        yaw_rate=config.yaw_rate,
        control_deflections=config.control_deflections,
        control_index_map=control_index_map,
        altitude=config.altitude,
        temp_shift_F=config.temp_shift_F,
        timeout_s=config.timeout_s,
        op_point=op_point,
        write_geom=effective_write_geom,
        force_rewrite_geom=force_rewrite_geom,
        geom_writer=geom_writer,
    )


def trim_longitudinal_case(
    airplane: "asb.Airplane",
    avl_exe: str | Path,
    working_directory: str | Path,
    config: AVLTrimConfig,
    *,
    control_index_map: dict[str, int] | None = None,
    op_point: "asb.OperatingPoint | None" = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True,
    geom_writer=None,
):
    """Run the preferred longitudinal-trim workflow with structured inputs."""
    from ac_design_toolbox.avl.trim import avl_trim_longitudinal

    working_directory = Path(working_directory)
    effective_write_geom = write_geom

    if control_index_map is None:
        case_dir = working_directory / config.case_name
        prepared = prepare_avl_airplane(airplane=airplane, working_directory=case_dir, op_point=op_point)
        control_index_map = prepared["control_index_map"]
        effective_write_geom = False

    return avl_trim_longitudinal(
        airplane=airplane,
        avl_exe=avl_exe,
        working_directory=working_directory,
        case_name=config.case_name,
        CL_target=config.CL_target,
        velocity=config.velocity,
        altitude=config.altitude,
        temp_shift_F=config.temp_shift_F,
        mach=config.mach,
        control_index_map=control_index_map,
        baseline_controls=config.baseline_controls,
        elevator_bounds=config.elevator_bounds,
        alpha_seed_deg=config.alpha_seed_deg,
        elevator_seed_deg=config.elevator_seed_deg,
        tol_CL=config.tol_CL,
        tol_Cm=config.tol_Cm,
        max_iter=config.max_iter,
        timeout_s=config.timeout_s,
        write_geom=effective_write_geom,
        force_rewrite_geom=force_rewrite_geom,
        geom_writer=geom_writer,
    )


__all__ = [
    "AVLCaseConfig",
    "AVLTrimConfig",
    "build_simple_aircraft",
    "prepare_avl_airplane",
    "run_case",
    "trim_longitudinal_case",
]
