"""Low-level AVL file, case-directory, and process I/O helpers."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aerosandbox as asb


_AVL_HEADER_REFS = re.compile(
    r"^\s*(?P<Sref>[-+.\deE]+)\s+(?P<Cref>[-+.\deE]+)\s+(?P<Bref>[-+.\deE]+)\s*$"
)


def write_avl_files_asb(
    airplane,
    work_root: Path,
    op_point: Optional[asb.OperatingPoint] = None,
) -> Dict[str, Path]:
    """Write AVL geometry using AeroSandbox and return the generated file path."""
    work_root.mkdir(parents=True, exist_ok=True)
    geom_path = work_root / "Airplane.avl"

    if isinstance(airplane, asb.AVL):
        avl = airplane
    else:
        if op_point is None:
            op_point = asb.OperatingPoint()
        avl = asb.AVL(airplane=airplane, op_point=op_point, working_directory=work_root)

    avl.write_avl(geom_path)

    if not geom_path.exists():
        raise FileNotFoundError(f"ASB did not produce {geom_path}.")
    return {"geom": geom_path}


def ensure_case_dir(working_directory: Path, case_name: str) -> Path:
    """Create and return the per-case working directory."""
    case_dir = (working_directory / case_name).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def parse_refs_from_avl(avl_path: Path) -> Tuple[float, float, float]:
    """Parse ``Sref``, ``Cref``, and ``Bref`` from an AVL geometry header."""
    with avl_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = handle.readlines()

    for index in range(min(80, len(lines))):
        match = _AVL_HEADER_REFS.match(lines[index].strip())
        if match:
            Sref = float(match.group("Sref"))
            Cref = float(match.group("Cref"))
            Bref = float(match.group("Bref"))
            if Sref > 0 and Cref > 0 and Bref > 0:
                return Sref, Cref, Bref
    raise ValueError(f"Could not parse Sref/Cref/Bref from {avl_path}")


def isa_density(altitude_m: float, temp_shift_F: float = 0.0) -> float:
    """Return ISA density with an optional temperature offset in degrees Fahrenheit."""
    T0 = 288.15
    p0 = 101325.0
    lapse = -0.0065
    gas_constant = 287.058
    g0 = 9.80665
    altitude = max(0.0, float(altitude_m))

    temperature = T0 + lapse * altitude
    temperature += temp_shift_F * (5.0 / 9.0)
    pressure = p0 * (temperature / T0) ** (-g0 / (lapse * gas_constant))
    return pressure / (gas_constant * temperature)


def write_min_mass_file(case_dir: Path, rho: float) -> Path:
    """Write the minimal AVL ``.mass`` file needed to set density and gravity."""
    mass_path = case_dir / "case.mass"
    mass_path.write_text(
        "Lunit = 1.0 m\n"
        "Munit = 1.0 kg\n"
        "Tunit = 1.0 s\n"
        "g = 9.81\n"
        f"rho = {rho:.6f}\n",
        encoding="utf-8",
    )
    return mass_path


def build_keystrokes(
    *,
    case_dir: Path,
    case_name: str,
    alpha: float,
    beta: float,
    mach: float = 0.0,
    velocity: float = 0.0,
    density: float = 1.225,
    mass: float = 0.0,
    pb2V: float,
    qc2V: float,
    rb2V: float,
    control_index_map: Dict[str, int],
    control_deflections_deg: Dict[str, float],
    use_mass_file: bool,
) -> Path:
    """Create the AVL keystroke file for one operating point."""
    lines: List[str] = ["LOAD Airplane.avl"]
    if use_mass_file:
        lines.append("MASS case.mass")
    lines.append("OPER")

    lines.extend(["A", f"A {alpha:.6g}", "B", f"B {beta:.6g}"])

    if abs(mach) > 0 or abs(velocity) > 0 or density > 0 or mass > 0:
        lines.append("M")
        if abs(mach) > 0:
            if abs(mach) >= 1.0:
                raise ValueError("Mach >= 1.0 not supported in AVL.")
            lines.append(f"MN {mach:.6g}")
        if abs(velocity) > 0:
            lines.append(f"V {velocity:.6g}")
        if density > 0:
            lines.append(f"D {density:.6g}")
        if mass > 0:
            lines.append(f"M {mass:.6g}")
        lines.append("")

    lines.extend(
        [
            f"R R {pb2V:.9g}",
            f"P P {qc2V:.9g}",
            f"Y Y {rb2V:.9g}",
        ]
    )

    for name, deg in control_deflections_deg.items():
        if name not in control_index_map:
            raise KeyError(f"Control '{name}' not found in control_index_map.")
        index = control_index_map[name]
        lines.append(f"D{index} D{index} {deg:.6g}")

    lines.extend(
        [
            "X",
            "FT",
            f"{case_name}.forces",
            "ST",
            f"{case_name}.stability",
            "FS",
            f"{case_name}.strip",
            "HM",
            f"{case_name}.hinge",
            "",
            "QUIT",
        ]
    )

    runfile = case_dir / f"{case_name}.keystrokes"
    runfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runfile


def run_avl(
    avl_exe: Path,
    case_dir: Path,
    keystrokes: Path,
    case_name: str,
    timeout_s: int = 300,
) -> Tuple[Path, Path]:
    """Run AVL with a prepared keystroke file and capture stdout and stderr."""
    out_path = case_dir / f"{case_name}_out.txt"
    err_path = case_dir / f"{case_name}_err.txt"
    with open(keystrokes, "rb") as stdin_handle, open(out_path, "wb") as stdout_handle, open(
        err_path, "wb"
    ) as stderr_handle:
        subprocess.run(
            [str(avl_exe)],
            stdin=stdin_handle,
            stdout=stdout_handle,
            stderr=stderr_handle,
            cwd=case_dir,
            timeout=timeout_s,
            check=False,
        )
    return out_path, err_path


__all__ = [
    "build_keystrokes",
    "ensure_case_dir",
    "isa_density",
    "parse_refs_from_avl",
    "run_avl",
    "write_avl_files_asb",
    "write_min_mass_file",
]
