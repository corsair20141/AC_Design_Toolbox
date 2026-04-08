"""Programmatic AVL operating-point and stability-analysis workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

import aerosandbox as asb

from ac_design_toolbox.avl.io import (
    build_keystrokes,
    ensure_case_dir,
    isa_density,
    parse_refs_from_avl,
    run_avl,
    write_avl_files_asb,
    write_min_mass_file,
)
from ac_design_toolbox.avl.parsing import parse_avl_stdout_like_asb, parse_stability_file, parse_strip_forces


def run_avl_case(
    *,
    airplane,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str,
    alpha: float = 0.0,
    beta: float = 0.0,
    mach: float = 0.0,
    velocity: float = 0.0,
    density: float = 1.225,
    aircraft_mass: float = 0.0,
    roll_rate: float = 0.0,
    pitch_rate: float = 0.0,
    yaw_rate: float = 0.0,
    control_deflections: Optional[Dict[str, float]] = None,
    control_index_map: Optional[Dict[str, int]] = None,
    altitude: Optional[float] = None,
    temp_shift_F: float = 0.0,
    timeout_s: int = 300,
    op_point: Optional[asb.OperatingPoint] = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True,
    geom_writer=None,
) -> Dict:
    """Run one AVL case and return parsed scalar, stability, and file outputs."""
    case_dir = ensure_case_dir(working_directory, case_name)
    avl_exe = Path(avl_exe)

    if geom_writer is None:
        geom_writer = write_avl_files_asb

    geom = case_dir / "Airplane.avl"
    if write_geom and (force_rewrite_geom or not geom.exists()):
        geom_writer(airplane, case_dir, op_point=op_point)

    if not geom.exists():
        raise FileNotFoundError(f"{geom} not found after geometry write. Did geom_writer run?")

    use_mass = altitude is not None
    if use_mass:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
        write_min_mass_file(case_dir, rho)

    Sref, Cref, Bref = parse_refs_from_avl(geom)

    if any(abs(value) > 0 for value in (roll_rate, pitch_rate, yaw_rate)) and velocity <= 0:
        raise ValueError("Nonzero p/q/r require a positive 'velocity' to form pb/2V, qc/2V, rb/2V.")

    velocity = float(velocity)
    pb2V = (roll_rate * Bref) / (2.0 * velocity) if velocity > 0 else 0.0
    qc2V = (pitch_rate * Cref) / (2.0 * velocity) if velocity > 0 else 0.0
    rb2V = (yaw_rate * Bref) / (2.0 * velocity) if velocity > 0 else 0.0

    ctrl_defs = {"aileron": 0.0, "elevator": 0.0, "rudder": 0.0, "flap": 0.0}
    if control_deflections:
        ctrl_defs.update({key: float(value) for key, value in control_deflections.items()})
    if control_index_map is None:
        raise ValueError("control_index_map is required (e.g., {'aileron':1,'elevator':2,'rudder':3}).")
    ctrl_apply = {key: ctrl_defs[key] for key in ctrl_defs.keys() if key in control_index_map}

    keystrokes = build_keystrokes(
        case_dir=case_dir,
        case_name=case_name,
        alpha=float(alpha),
        beta=float(beta),
        mach=float(mach),
        velocity=velocity,
        density=density,
        mass=aircraft_mass,
        pb2V=pb2V,
        qc2V=qc2V,
        rb2V=rb2V,
        control_index_map=control_index_map,
        control_deflections_deg=ctrl_apply,
        use_mass_file=use_mass,
    )

    out_txt, err_txt = run_avl(avl_exe, case_dir, keystrokes, case_name, timeout_s=timeout_s)
    text = out_txt.read_text(encoding="utf-8", errors="replace")

    parsed = parse_avl_stdout_like_asb(
        text,
        velocity=velocity,
        rho=density,
        Sref=Sref,
        Cref=Cref,
        Bref=Bref,
        alpha_deg=alpha,
        beta_deg=beta,
    )

    stab_path = case_dir / f"{case_name}.stability"
    stability_derivs = None
    if stab_path.exists():
        stability_derivs = parse_stability_file(stab_path)
        for key, value in stability_derivs.items():
            if key not in parsed:
                parsed[key] = value

    return {
        "paths": {
            "case_dir": str(case_dir),
            "stdout": str(out_txt),
            "stderr": str(err_txt),
            "keystrokes": str(keystrokes),
            "airplane_avl": str(geom),
            "mass_file": str(case_dir / "case.mass") if use_mass else None,
        },
        "scalars": parsed,
        "stability": stability_derivs,
        "strip_forces": parse_strip_forces(text),
        "raw": text,
    }


def avl_neutral_point_and_SM(
    airplane: asb.Airplane,
    *,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str = "np_case",
    alpha_deg: float = 0.0,
    beta_deg: float = 0.0,
    mach: float = 0.0,
    velocity: float = 50.0,
    altitude: float | None = None,
    temp_shift_F: float = 0.0,
    control_deflections: Optional[Dict[str, float]] = None,
    control_index_map: Optional[Dict[str, int]] = None,
    timeout_s: float | None = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = False,
    geom_writer=None,
) -> Dict[str, float]:
    """Compute the neutral point and static margin about the current CG."""
    result = run_avl_case(
        airplane=airplane,
        avl_exe=avl_exe,
        working_directory=working_directory,
        case_name=case_name,
        alpha=float(alpha_deg),
        beta=float(beta_deg),
        mach=float(mach),
        velocity=float(velocity),
        altitude=float(altitude) if altitude is not None else None,
        temp_shift_F=float(temp_shift_F),
        control_deflections=control_deflections,
        control_index_map=control_index_map,
        timeout_s=timeout_s,
        write_geom=write_geom,
        force_rewrite_geom=force_rewrite_geom,
        geom_writer=geom_writer,
    )

    scalars = result["scalars"]
    CLa = scalars.get("CLa")
    Cma = scalars.get("Cma")
    if CLa is None or Cma is None:
        raise RuntimeError(
            "CLa or Cma not found in AVL output. Check that 'ST' is being executed in the keystrokes."
        )

    avl_path = Path(result["paths"]["airplane_avl"])
    _, Cref, _ = parse_refs_from_avl(avl_path)
    x_ref = float(airplane.xyz_ref[0])
    SM = -float(Cma) / float(CLa)
    x_np = x_ref + SM * Cref

    return {
        "CLa": float(CLa),
        "Cma": float(Cma),
        "SM": float(SM),
        "x_np": float(x_np),
        "x_ref": float(x_ref),
        "Cref": float(Cref),
    }


def set_cg_for_static_margin(
    airplane: asb.Airplane,
    *,
    x_np: float,
    Cref: float,
    SM_target: float,
    y_cg: float | None = None,
    z_cg: float | None = None,
) -> asb.Airplane:
    """Update ``airplane.xyz_ref`` to the CG required for a target static margin."""
    _, y_old, z_old = [float(value) for value in airplane.xyz_ref]
    if y_cg is None:
        y_cg = y_old
    if z_cg is None:
        z_cg = z_old

    x_cg = float(x_np) - float(SM_target) * float(Cref)
    airplane.xyz_ref = [x_cg, float(y_cg), float(z_cg)]
    return airplane


__all__ = [
    "avl_neutral_point_and_SM",
    "run_avl_case",
    "set_cg_for_static_margin",
]
