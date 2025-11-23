# tools/avl_pipeline.py
from __future__ import annotations
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import math
import numpy as np

import matplotlib.pyplot as plt

import aerosandbox as asb

from ADC_SAC_v4 import SAC  # provides density via SAC(alt, "si", temp_shift_F=...)["rho"]




# -------------------------------------------
# Write AVL geometry using ASB only
# -------------------------------------------
def write_avl_files_asb(airplane, work_root: Path, op_point: Optional[asb.OperatingPoint] = None) -> Dict[str, Path]:
    """
    Use ASB's AVL helper to emit geometry only.
    ASB's AVL ctor requires op_point; we provide a default empty one if none is given.
    """
    work_root.mkdir(parents=True, exist_ok=True)
    geom_path = work_root / "Airplane.avl"

    # If the caller passed an AVL instance, accept it; else build one with an OP.
    if isinstance(airplane, asb.AVL):
        avl = airplane
    else:
        if op_point is None:
            # Minimal OP; just to satisfy ASB's constructor
            op_point = asb.OperatingPoint()  # alpha=0, beta=0, V=0, ISA by default
        avl = asb.AVL(airplane=airplane, op_point=op_point, working_directory=work_root)

    avl.write_avl(geom_path)

    if not geom_path.exists():
        raise FileNotFoundError(f"ASB did not produce {geom_path}.")
    return {"geom": geom_path}



# ---------------------------
# Utilities
# ---------------------------
def ensure_case_dir(working_directory: Path, case_name: str) -> Path:
    case_dir = (working_directory / case_name).resolve()
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir

_AVL_HEADER_REFS = re.compile(
    r"^\s*(?P<Sref>[-+.\deE]+)\s+(?P<Cref>[-+.\deE]+)\s+(?P<Bref>[-+.\deE]+)\s*$"
)

def parse_refs_from_avl(avl_path: Path) -> Tuple[float, float, float]:
    """
    Parse Sref, Cref, Bref from 'Airplane.avl' header (line with 3 numbers after iYsym/iZsym/Zsym).
    """
    with avl_path.open("r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    # Heuristic: find the first line with three floats that plausibly matches Sref Cref Bref.
    for i in range(min(80, len(lines))):
        m = _AVL_HEADER_REFS.match(lines[i].strip())
        if m:
            Sref = float(m.group("Sref"))
            Cref = float(m.group("Cref"))
            Bref = float(m.group("Bref"))
            # sanity: Sref>0, Cref>0, Bref>0
            if Sref > 0 and Cref > 0 and Bref > 0:
                return Sref, Cref, Bref
    raise ValueError(f"Could not parse Sref/Cref/Bref from {avl_path}")

def isa_density(altitude_m: float, temp_shift_F: float = 0.0) -> float:
    """
    ISA density with an optional temperature shift (°F) applied at altitude.
    Valid to ~11 km (troposphere). Units: kg/m^3.
    """
    # ISA base
    T0 = 288.15      # K
    p0 = 101325.0    # Pa
    L  = -0.0065     # K/m (lapse)
    R  = 287.058     # J/(kg K)
    g0 = 9.80665     # m/s^2
    h  = max(0.0, float(altitude_m))
    T = T0 + L * h
    # apply temp shift at altitude (°F -> K)
    T += (temp_shift_F) * (5.0/9.0)
    p = p0 * (T / T0) ** (-g0 / (L * R))
    rho = p / (R * T)
    return rho

def write_min_mass_file(case_dir: Path, rho: float) -> Path:
    """
    Minimal .mass file to set units and density (no mass breakdown needed).
    """
    mpath = case_dir / "case.mass"
    mpath.write_text(
        "Lunit = 1.0 m\n"
        "Munit = 1.0 kg\n"
        "Tunit = 1.0 s\n"
        f"g = 9.81\n"
        f"rho = {rho:.6f}\n",
        encoding="utf-8"
    )
    return mpath

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
    """
    Compose the stdin script. Assumes Airplane.avl (and case.mass if used) already in case_dir.
    """
    lines: List[str] = []
    lines.append("LOAD Airplane.avl")
    if use_mass_file:
        lines.append("MASS case.mass")     # use our density (affects Q)
    lines.append("OPER")

    # Set direct constraints/values
    # Alpha/Beta direct set:
    lines.append("A")
    lines.append(f"A {alpha:.6g}")
    lines.append("B")
    lines.append(f"B {beta:.6g}")

    # Modify Parameters submenu
    if abs(mach) > 0 or abs(velocity) > 0 or density > 0 or mass > 0:
        lines.append("M") # enter Modify Parameters submenu
        if abs(mach) > 0:
            if abs(mach) >= 1.0:
                raise ValueError("Mach >= 1.0 not supported in AVL.")
            lines.append(f"MN {mach:.6g}") # set mach number
        if abs(velocity) > 0:
            lines.append(f"V {velocity:.6g}") # set velocity
        if density > 0:
            lines.append(f"D {density:.6g}")  # set density
        if mass > 0:
            lines.append(f"M {mass:.6g}")      # set mass
        lines.append("") # exist Modify Parameters submenu

    # Set rates as nondimensional (pb/2V, qc/2V, rb/2V)
    lines.append(f"R R {pb2V:.9g}")         # roll rate, non-dimensionalized (pb/2V)
    lines.append(f"P P {qc2V:.9g}")         # pitch rate, non-dimensionalized (qc/2V)
    lines.append(f"Y Y {rb2V:.9g}")         # yaw rate, non-dimensionalized (rb/2V)

    # Controls via D# indices
    for name, deg in control_deflections_deg.items():
        if name not in control_index_map:
            raise KeyError(f"Control '{name}' not found in control_index_map.")
        d_idx = control_index_map[name]
        lines.append(f"D{d_idx} D{d_idx} {deg:.6g}")

    # Execute + outputs
    lines += [
        "X",   # execute
        # "RE",  # Reference quantities [THIS IS IF YOU WANT TO CHANGE THE REF QTYs like S_Ref etc.]
        "FT",  # Total forces
        f"{case_name}"+".forces", # write Total Forces file
        "ST",  # Stability derivatives
        f"{case_name}"+".stability", # write Stability Derivatives file
        "FS",  # Strip forces
        f"{case_name}"+".strip", # write Strip Forces file
        "HM",  # hinge moments
        f"{case_name}"+".hinge", # write Hinge Moments file
        "", # return to exit OPER
        "QUIT",
    ]

    runfile = case_dir / f"{case_name}.keystrokes"
    runfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return runfile

def run_avl(avl_exe: Path, case_dir: Path, keystrokes: Path, case_name: str, timeout_s: int = 300) -> Tuple[Path, Path]:
    out_path = case_dir / f"{case_name}_out.txt"
    err_path = case_dir / f"{case_name}_err.txt"
    with open(keystrokes, "rb") as fin, open(out_path, "wb") as fout, open(err_path, "wb") as ferr:
        subprocess.run([str(avl_exe)], stdin=fin, stdout=fout, stderr=ferr, cwd=case_dir, timeout=timeout_s, check=False)
    return out_path, err_path


# ---- Parse Outputs (helpers) ----
def _parse_kv_blocks(s: str, data_identifier: str = " = ",
                     cast_to_float: bool = True,
                     overwrite: bool = True) -> Dict[str, float]:
    """
    ASB-like unformatted data parser: extracts every '<key> = <value>' pair across the text.
    See AeroSandbox avl.py: parse_unformatted_data_output for the same idea.  :contentReference[oaicite:1]{index=1}
    """
    out: Dict[str, float] = {}
    idx = s.find(data_identifier)
    while idx != -1:
        # read key to the left
        i = idx - 1
        while i >= 0 and s[i] == " ":
            i -= 1
        key = ""
        while i >= 0 and s[i] not in (" ", "\n"):
            key = s[i] + key
            i -= 1

        # read value to the right
        j = idx + len(data_identifier)
        while j < len(s) and s[j] == " ":
            j += 1
        val = ""
        while j < len(s) and s[j] not in (" ", "\n"):
            val += s[j]
            j += 1

        if cast_to_float:
            try:
                val = float(val)
            except Exception:
                val = float("nan")

        if key in out and not overwrite:
            pass
        else:
            out[key] = val

        s = s[idx + len(data_identifier):]
        idx = s.find(data_identifier)

    return out

def _rot_wind_to_body(alpha_deg: float, beta_deg: float) -> List[List[float]]:
    """
    Direction cosine matrix R = R_y(alpha) @ R_z(beta) mapping wind->body.
    Body axes: X fwd, Y right, Z down. Alpha, beta in degrees.
    """
    a = math.radians(alpha_deg)
    b = math.radians(beta_deg)
    ca, sa = math.cos(a), math.sin(a)
    cb, sb = math.cos(b), math.sin(b)

    # R_z(beta)
    Rz = [
        [cb, -sb, 0.0],
        [sb,  cb, 0.0],
        [0.0, 0.0, 1.0],
    ]
    # R_y(alpha)
    Ry = [
        [ ca, 0.0,  sa],
        [0.0, 1.0, 0.0],
        [-sa, 0.0,  ca],
    ]
    # R = Ry * Rz
    R = [
        [
            Ry[0][0]*Rz[0][0] + Ry[0][1]*Rz[1][0] + Ry[0][2]*Rz[2][0],
            Ry[0][0]*Rz[0][1] + Ry[0][1]*Rz[1][1] + Ry[0][2]*Rz[2][1],
            Ry[0][0]*Rz[0][2] + Ry[0][1]*Rz[1][2] + Ry[0][2]*Rz[2][2],
        ],
        [
            Ry[1][0]*Rz[0][0] + Ry[1][1]*Rz[1][0] + Ry[1][2]*Rz[2][0],
            Ry[1][0]*Rz[0][1] + Ry[1][1]*Rz[1][1] + Ry[1][2]*Rz[2][1],
            Ry[1][0]*Rz[0][2] + Ry[1][1]*Rz[1][2] + Ry[1][2]*Rz[2][2],
        ],
        [
            Ry[2][0]*Rz[0][0] + Ry[2][1]*Rz[1][0] + Ry[2][2]*Rz[2][0],
            Ry[2][0]*Rz[0][1] + Ry[2][1]*Rz[1][1] + Ry[2][2]*Rz[2][1],
            Ry[2][0]*Rz[0][2] + Ry[2][1]*Rz[1][2] + Ry[2][2]*Rz[2][2],
        ],
    ]
    return R

def _matvec(R: List[List[float]], v: List[float]) -> List[float]:
    return [
        R[0][0]*v[0] + R[0][1]*v[1] + R[0][2]*v[2],
        R[1][0]*v[0] + R[1][1]*v[1] + R[1][2]*v[2],
        R[2][0]*v[0] + R[2][1]*v[1] + R[2][2]*v[2],
    ]

def parse_avl_stdout_like_asb(
    text: str,
    *,
    velocity: float,
    rho: float,
    Sref: float,
    Cref: float,
    Bref: float,
    alpha_deg: float,
    beta_deg: float,
) -> Dict:
    """Parse stdout for AVL outputs, in the same spirit as AeroSandbox’s avl.py."""
    # 1) pull all key-value pairs
    kv = _parse_kv_blocks(text, data_identifier=" = ", cast_to_float=True, overwrite=True)  # :contentReference[oaicite:2]{index=2}

    # 2) normalize certain keys
    for old in ["Alpha", "Beta", "Mach"]:
        if old in kv:
            kv[old.lower()] = kv.pop(old)

    # 3) strip *tot → match ASB behavior where they remove 'tot' for totals
    #    e.g., 'CLtot' -> 'CL', 'CDtot' -> 'CD'
    for k in list(kv.keys()):
        if "tot" in k:
            kv[k.replace("tot", "")] = kv.pop(k)

    # 4) compute useful derived quantities
    V = float(velocity)
    q_dyn = 0.5 * rho * V * V

    # dimensional angular rates from nondimensional pb/2V, qc/2V, rb/2V
    if "pb/2V" in kv:
        kv["p"] = kv["pb/2V"] * (2.0 * V / Bref)
    if "qc/2V" in kv:
        # call it 'q_rate' to avoid clobbering dynamic pressure 'q'
        kv["q_rate"] = kv["qc/2V"] * (2.0 * V / Cref)
    if "rb/2V" in kv:
        kv["r"] = kv["rb/2V"] * (2.0 * V / Bref)

    # forces & moments (wind-axis signs: +X downwind → drag positive, +Z down → lift negative)
    if "CL" in kv:
        kv["L"] = q_dyn * Sref * kv["CL"]
    if "CY" in kv:
        kv["Y"] = q_dyn * Sref * kv["CY"]
    if "CD" in kv:
        kv["D"] = q_dyn * Sref * kv["CD"]
    if "Cl" in kv:
        kv["l_b"] = q_dyn * Sref * Bref * kv["Cl"]
    if "Cm" in kv:
        kv["m_b"] = q_dyn * Sref * Cref * kv["Cm"]
    if "Cn" in kv:
        kv["n_b"] = q_dyn * Sref * Bref * kv["Cn"]

    # wind/body force vectors (like ASB F_w / F_b)
    if all(k in kv for k in ["L", "Y", "D"]):
        F_w = [-kv["D"], kv["Y"], -kv["L"]]  # wind axes
        R = _rot_wind_to_body(alpha_deg, beta_deg)
        Fx_b, Fy_b, Fz_b = _matvec(R, F_w)
        kv["F_w"] = F_w
        kv["F_b"] = [Fx_b, Fy_b, Fz_b]
        # geometry frame ~ body frame here; if you later add CG/axes offsets, transform similarly:
        kv["F_g"] = kv["F_b"]

    # handy ratio used in lateral-directional checks (guard zeros)
    try:
        kv["Clb Cnr / Clr Cnb"] = kv["Clb"] * kv["Cnr"] / (kv["Clr"] * kv["Cnb"])
    except Exception:
        pass

    return kv

def _find_section(text: str, heading_regex: str) -> Optional[Tuple[int, int]]:
    lines = text.splitlines()
    head_pat = re.compile(heading_regex, re.IGNORECASE)
    caps_heading = re.compile(r"^[A-Z][A-Z \t\.\(\)/-]{3,}$")
    start = None
    for i, line in enumerate(lines):
        if head_pat.search(line):
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        if caps_heading.match(lines[j]) and j > start + 1:
            end = j
            break
    return (start, end)

def parse_strip_forces(text: str) -> List[Dict[str, float]]:
    """
    Parse AVL 'FS' output (Strip Forces) into a list of dicts.
    Handles multiple surfaces by capturing the 'Surface #' and name lines.
    Returns [] if no FS section present.
    """
    sec = _find_section(text, r"^Strip Forces\b")
    if not sec:
        return []
    start, end = sec
    lines = text.splitlines()[start:end]

    rows: List[Dict[str, float]] = []
    current_surface_name: str = ""
    header_cols: List[str] = []
    header_idx: int = -1

    # Heuristics for identifying header and numeric rows
    def is_separator(line: str) -> bool:
        s = line.strip()
        return len(s) > 0 and all(ch in "-=_" for ch in s)

    float_token = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue

        # Detect "Surface #  i  name:  Main Wing" style line
        if s.lower().startswith("surface"):
            # Try to extract name after colon, fallback to the whole line
            m = re.search(r"Surface\s*#?\s*\d*\s*:\s*(.+)$", s, re.IGNORECASE)
            current_surface_name = (m.group(1).strip() if m else s)
            continue

        # Detect header (contains typical FS labels)
        if header_cols == [] and re.search(r'\b(i|Yle|Chord|Area|c_cl|cl|ai|cd|cm|Xle|Zle|C.P.)\b', s, re.IGNORECASE):
            header_cols = re.split(r"\s+", s)
            header_idx = i
            continue

        # Skip separators and obvious headings
        if is_separator(s):
            continue
        if re.match(r"^[A-Z][A-Z \t\.\(\)/-]{3,}$", s):
            # next major heading—FS block will end soon anyway
            continue

        # Data lines come after header; must be mostly numeric tokens
        if header_cols and i > header_idx:
            parts = re.split(r"\s+", s)
            # Require the first token to be an index integer (strip number)
            if not parts:
                continue
            # tolerate occasional non-numeric last column (e.g., CP marker)
            numeric_like = sum(1 for p in parts if float_token.match(p))
            if numeric_like < max(2, len(parts) - 1):
                # not a data row
                continue

            row: Dict[str, float] = {}
            for h, v in zip(header_cols, parts):
                try:
                    row[h] = float(v)
                except ValueError:
                    # keep only numeric columns; skip text tokens
                    pass

            if row:
                if current_surface_name:
                    row["Surface"] = current_surface_name
                rows.append(row)

    return rows


def parse_stability_file(stab_path: Path) -> Dict[str, float]:
    """
    Parse an AVL .stability file and return a flat dict of all
    'name = value' pairs we can find, plus some special extras.

    Examples of what this picks up:
        Sref, Cref, Bref, Xref, Yref, Zref
        CLa, CLb, Cma, Cmb
        CLp, CLq, CLr, CYp, CYq, CYr, ...
        CLd01, CDd01, Cmd03, ...
        Xnp (neutral point)
        ed01, ed02, ... (span efficiency sensitivities)
        etc.

    If the file isn't in the "standard" AVL format, this may need adjustment.
    """
    text = stab_path.read_text(encoding="utf-8", errors="replace")

    derivs: Dict[str, float] = {}

    # Generic: catch any "<Name> = <number>" pair.
    # This will capture things like:
    #   Sref = 16.166
    #   CLa = 5.290586
    #   CLq = 12.650696
    #   CLd01 = 0.041073
    #   Xnp = 0.632307
    #
    # We KEEP THE FIRST value we see for any key to avoid overwriting,
    # e.g. Cnb from the main table vs. the "Clb Cnr / Clr Cnb" summary line.
    for name, val in re.findall(r"([A-Za-z][A-Za-z0-9']*)\s*=\s*([-+0-9.eE]+)", text):
        if name not in derivs:
            try:
                derivs[name] = float(val)
            except ValueError:
                # If something weird slips through, just skip
                continue

    # Special: Spiral-stability ratio line:
    #   "Clb Cnr / Clr Cnb  =   0.467093    (  > 1 if spirally stable )"
    m = re.search(r"Clb Cnr / Clr Cnb\s*=\s*([-+0-9.eE]+)", text)
    if m:
        derivs["ClbCnr_over_ClrCnb"] = float(m.group(1))

    # You now have, for example:
    #   derivs["CLa"], derivs["Cma"], derivs["CLp"], derivs["CLq"], ...
    #   derivs["Xnp"], derivs["Sref"], derivs["Cref"], derivs["Bref"], ...
    return derivs


# **********************************************************************
# **********************************************************************
# **********************************************************************
# **********************************************************************
# **********************************************************************



# ---------------------------
# Public: write geometry and then run_case
# ---------------------------
def run_avl_case(
    *,
    airplane,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str,
    alpha: float = 0.0,
    beta: float = 0.0,
    mach: float = 0.0,
    velocity: float = 0.0,             # m/s
    density: float = 1.225,            # kg/m^3
    aircraft_mass: float = 0.0,        # kg
    roll_rate: float = 0.0, pitch_rate: float = 0.0, yaw_rate: float = 0.0,   # rad/s
    control_deflections: Optional[Dict[str, float]] = None,
    control_index_map: Optional[Dict[str, int]] = None,
    altitude: Optional[float] = None,
    temp_shift_F: float = 0.0,
    timeout_s: int = 300,
    op_point: Optional["asb.OperatingPoint"] = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True, # allow overwrite if already exists
    geom_writer = None,   # defaults to write_avl_files_asb if None
) -> Dict:

    """
    Orchestrate a case:
      - ensure per-case dir
      - ensure Airplane.avl exists (caller writes via ASB before calling)
      - write .mass if altitude provided; load it
      - convert p/q/r -> pb/2V, qc/2V, rb/2V using Cref/Bref from Airplane.avl
      - build keystrokes with alpha/beta/mach/rates/controls
      - run AVL and parse stdout
    Returns: {"paths": {...}, "scalars": {...}, "strip_forces": [...], "raw": "..."}
    """
    case_dir = ensure_case_dir(working_directory, case_name)
    avl_exe = Path(avl_exe)

    # 0) write geometry
    if geom_writer is None:
        geom_writer = write_avl_files_asb  # your function from below

    geom = case_dir / "Airplane.avl"
    if write_geom and (force_rewrite_geom or not geom.exists()):
        geom_writer(airplane, case_dir, op_point=op_point)

    # Safety: verify it exists
    if not geom.exists():
        raise FileNotFoundError(f"{geom} not found after geometry write. Did geom_writer run?")

    # 1) geometry must exist
    geom = case_dir / "Airplane.avl"
    if not geom.exists():
        raise FileNotFoundError(f"{geom} not found. Write it first (e.g., write_avl_files_asb(airplane, case_dir)).")

    # 2) prepare density via .mass if altitude provided
    use_mass = altitude is not None
    if use_mass:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
        write_min_mass_file(case_dir, rho)

    # 3) parse refs for rate conversion
    Sref, Cref, Bref = parse_refs_from_avl(geom)

    # 4) nondimensional rates
    if any(abs(x) > 0 for x in (roll_rate, pitch_rate, yaw_rate)):
        if velocity <= 0:
            raise ValueError("Nonzero p/q/r require a positive 'velocity' to form pb/2V, qc/2V, rb/2V.")
    V = float(velocity)
    pb2V = (roll_rate * Bref) / (2.0 * V) if V > 0 else 0.0
    qc2V = (pitch_rate * Cref) / (2.0 * V) if V > 0 else 0.0
    rb2V = (yaw_rate * Bref) / (2.0 * V) if V > 0 else 0.0

    # 5) controls (default 0s)
    ctrl_defs = {"aileron": 0.0, "elevator": 0.0, "rudder": 0.0, "flap": 0.0}
    if control_deflections:
        ctrl_defs.update({k: float(v) for k, v in control_deflections.items()})
    # Require explicit mapping; don't guess indices.
    if control_index_map is None:
        raise ValueError("control_index_map is required (e.g., {'aileron':1,'elevator':2,'rudder':3}).")
    # Only include present keys
    ctrl_apply = {k: ctrl_defs[k] for k in ctrl_defs.keys() if k in control_index_map}

    # 6) keystrokes
    ks = build_keystrokes(
        case_dir=case_dir,
        case_name=case_name,
        alpha=float(alpha),
        beta=float(beta),
        mach=float(mach),
        velocity=V,
        density=density,
        mass=aircraft_mass,
        pb2V=pb2V,
        qc2V=qc2V,
        rb2V=rb2V,
        control_index_map=control_index_map,
        control_deflections_deg=ctrl_apply,
        use_mass_file=use_mass,
    )

    # 7) run
    out_txt, err_txt = run_avl(avl_exe, case_dir, ks, case_name, timeout_s=timeout_s)

    # 8) parse results
    text = out_txt.read_text(encoding="utf-8", errors="replace")

    parsed = parse_avl_stdout_like_asb(
        text,
        velocity=velocity,
        rho=density,
        Sref=Sref, Cref=Cref, Bref=Bref,   # you already parsed these from Airplane.avl earlier
        alpha_deg=alpha,
        beta_deg=beta,
    )

    # 9) Parse stability-derivative file if available
    stab_path = case_dir / f"{case_name}.stability"
    stability_derivs = None
    if stab_path.exists():
        stability_derivs = parse_stability_file(stab_path)

        # Optionally: inject these into the "scalars" dict for convenience.
        # We only fill keys that aren't already there to avoid stomping anything
        # parse_avl_stdout_like_asb() might have set.
        for k, v in stability_derivs.items():
            if k not in parsed:
                parsed[k] = v

    results = {
        "paths": {
            "case_dir": str(case_dir),
            "stdout": str(out_txt),
            "stderr": str(err_txt),
            "keystrokes": str(ks),
            "airplane_avl": str(geom),
            "mass_file": str(case_dir / "case.mass") if use_mass else None,
        },
        "scalars": parsed,                    # FT + anything else + stability if available
        "stability": stability_derivs,        # full dict from .stability file (or None)
        "strip_forces": parse_strip_forces(text),
        "raw": text,
    }
    return results



# ======================================================================
# Longitudinal stability and trim utilities
# ======================================================================

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
    """
    Compute neutral point and static margin about the current CG (xyz_ref).

    This runs a single AVL case (including stability derivatives via ST)
    and extracts CLa, Cma, static margin SM = -Cma/CLa, and the
    corresponding neutral point x_np relative to the current reference
    point (assumed CG).

    Parameters
    ----------
    airplane : asb.Airplane
        Geometry with xyz_ref set to the current CG (in meters, body axes).
    avl_exe : str | Path
        Path to the AVL executable.
    working_directory : Path
        Root directory where per-case folders will be created.
    case_name : str, optional
        Name of the AVL case subdirectory.
    alpha_deg, beta_deg : float, optional
        Angle of attack and sideslip in degrees for the stability evaluation.
        Small angles around trim (e.g. 0 deg) are typical for NP estimation.
    mach : float, optional
        Mach number for the run (default 0).
    velocity : float, optional
        Freestream speed in m/s. Needed for some derived quantities, but
        CLa/Cma themselves are non-dimensional.
    altitude : float | None, optional
        Altitude in meters for ISA density. If provided, a minimal .mass
        file is written and AVL uses that density.
    temp_shift_F : float, optional
        Temperature deviation from ISA in °F at the given altitude.
    control_deflections : dict, optional
        Baseline control deflections in degrees (elevator, aileron, etc.).
    control_index_map : dict, optional
        Mapping from control names to AVL D# indices. Required if controls
        are specified.
    timeout_s : float | None, optional
        Timeout in seconds for the AVL subprocess.
    write_geom, force_rewrite_geom, geom_writer :
        Passed through to run_avl_case.

    Returns
    -------
    Dict[str, float]
        Dictionary with keys:
          - "CLa", "Cma"
          - "SM"   (static margin, dimensionless fraction of Cref)
          - "x_np" (neutral point x-location, same units as xyz_ref and Cref)
          - "x_ref" (current reference x-location)
          - "Cref" (reference chord from Airplane.avl)
    """
    # Run a single AVL case (this will also compute stability derivatives via ST)
    res = run_avl_case(
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

    scalars = res["scalars"]

    # Extract stability derivatives; AVL uses 'CLa' and 'Cma' in its ST output.
    CLa = scalars.get("CLa", None)
    Cma = scalars.get("Cma", None)
    if CLa is None or Cma is None:
        raise RuntimeError(
            "CLa or Cma not found in AVL output. Check that 'ST' is being executed "
            "in build_keystrokes and that this case ran successfully."
        )

    # Reference geometry from the same Airplane.avl file
    avl_path = Path(res["paths"]["airplane_avl"])
    Sref, Cref, Bref = parse_refs_from_avl(avl_path)

    # Current reference point (assumed CG)
    x_ref = float(airplane.xyz_ref[0])

    # Static margin and neutral point (x_np)
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
    """Set airplane.xyz_ref (CG) to achieve a target static margin.

    This is a purely geometric operation: given a neutral point location
    x_np and a reference chord Cref (typically from avl_neutral_point_and_SM),
    compute the CG location that yields the desired static margin and update
    airplane.xyz_ref in-place.

    Static margin is defined here as:

        SM = (x_np - x_cg) / Cref

    so the CG corresponding to a target SM is:

        x_cg = x_np - SM_target * Cref

    Parameters
    ----------
    airplane : asb.Airplane
        Airplane whose xyz_ref will be updated.
    x_np : float
        Neutral point x-location (same units as xyz_ref and Cref).
    Cref : float
        Reference chord length.
    SM_target : float
        Target static margin (dimensionless fraction of Cref, positive for
        stable configurations).
    y_cg, z_cg : float, optional
        Y and Z coordinates of CG. If None, the existing yz of xyz_ref
        are preserved.

    Returns
    -------
    asb.Airplane
        The same airplane object, with xyz_ref updated to the new CG.
    """
    # Preserve existing y/z if not provided explicitly
    x_old, y_old, z_old = [float(v) for v in airplane.xyz_ref]
    if y_cg is None:
        y_cg = y_old
    if z_cg is None:
        z_cg = z_old

    x_cg = float(x_np) - float(SM_target) * float(Cref)
    airplane.xyz_ref = [x_cg, float(y_cg), float(z_cg)]
    return airplane



def _avl_trim_longitudinal_1D( # Fallback 1d solver if 2d Newton solver doesn't converge (this is slower but maybe more robust)
    airplane: asb.Airplane,
    *,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str = "trim_case",
    CL_target: float,
    velocity: float,
    altitude: float | None = None,
    temp_shift_F: float = 0.0,
    mach: float = 0.0,
    control_index_map: Dict[str, int],
    baseline_controls: Optional[Dict[str, float]] = None,
    elevator_bounds: Tuple[float, float] = (-20.0, 20.0),
    alpha_seed_deg: float = 4.0,
    tol_CL: float = 1e-2,
    tol_Cm: float = 1e-3,
    max_alpha_iter: int = 20,
    max_elev_iter: int = 20,
    timeout_s: float | None = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True,
    geom_writer=None,
) -> Dict:
    """Trim the aircraft in pitch for a given CL_target by adjusting alpha and elevator.

    This function solves the coupled trim problem

        CL(alpha, delta_e) = CL_target
        Cm(alpha, delta_e) = 0

    by:
      - inner loop: root-finding in alpha for CL = CL_target with elevator fixed
      - outer loop: root-finding in elevator for Cm = 0, calling the inner loop

    All calls are made through `run_avl_case`, so the AVL usage is identical
    to the rest of this module. Moments are taken about airplane.xyz_ref,
    which should therefore be set to the CG prior to calling this function.

    Parameters
    ----------
    airplane : asb.Airplane
        Geometry (with xyz_ref at CG).
    avl_exe : str | Path
        Path to AVL executable.
    working_directory : Path
        Root directory for case subfolder.
    case_name : str, optional
        Base name for this trim case (subdirectory inside working_directory).
    CL_target : float
        Target lift coefficient for steady flight (e.g. W / (q S)).
    velocity : float
        Freestream speed in m/s.
    altitude : float | None, optional
        Altitude in meters for ISA density and .mass file. Optional; if None,
        you must ensure that the density passed to AVL elsewhere is consistent.
    temp_shift_F : float, optional
        Temperature deviation from ISA in °F.
    mach : float, optional
        Mach number (default 0).
    control_index_map : dict
        Mapping from control names to AVL D# indices (e.g. {'aileron':1,'elevator':2,...}).
    baseline_controls : dict, optional
        Baseline control deflections in degrees (e.g. {'flap': 20.0}). Elevator
        will be overridden by the trim solver.
    elevator_bounds : (float, float), optional
        Lower and upper bounds on elevator deflection [deg] used for bracketing.
    alpha_seed_deg : float, optional
        Initial guess for alpha [deg] used for inner CL root solve.
    tol_CL, tol_Cm : float, optional
        Tolerances for CL and Cm residuals.
    max_alpha_iter, max_elev_iter : int, optional
        Maximum iterations for inner (alpha) and outer (elevator) solves.
    timeout_s, write_geom, force_rewrite_geom, geom_writer :
        Passed through to run_avl_case.

    Returns
    -------
    Dict
        Dictionary containing (at minimum):
          - 'alpha_trim_deg'
          - 'elevator_trim_deg'
          - 'CL', 'Cm', 'CD', 'CDi'
          - 'K' (induced-drag factor CDi / CL^2)
          - 'history' (iteration history for debugging)
    """
    # ------------------------
    # Density for CL_target and AVL (if altitude provided)
    # ------------------------
    if altitude is not None:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
    else:
        rho = 1.225  # fallback, shouldn't matter if you don't care about CL/CD scaling

    # ------------------------
    # Control baseline / indices
    # ------------------------
    baseline_controls = dict(baseline_controls) if baseline_controls is not None else {}
    for k in ("aileron", "elevator", "rudder", "flap"):
        baseline_controls.setdefault(k, 0.0)

    history: Dict[str, list] = {
        "elevator_iter": [],
        "alpha_iter": [],
    }

    avl_calls = 0  # <-- instrumentation

    # ------------------------
    # Inner solve: alpha for CL_target at fixed elevator (with re-use of prev. alpha for efficiency gains)
    # ------------------------
    def solve_alpha_for_CL(elevator_deg: float, alpha_seed_prev: float | None = None) -> Dict[str, float]:
        """
        Solve for alpha such that CL = CL_target at fixed elevator.
        Reuses previous alpha solution to dramatically reduce AVL calls.
        Falls back to full bracketing only when needed.
        """

        nonlocal avl_calls

        ctrl = dict(baseline_controls)
        ctrl["elevator"] = float(elevator_deg)

        def eval_at(alpha_deg: float):
            nonlocal avl_calls
            res = run_avl_case(
                airplane=airplane,
                avl_exe=avl_exe,
                working_directory=working_directory,
                case_name=case_name,
                alpha=float(alpha_deg),
                beta=0.0,
                mach=float(mach),
                velocity=float(velocity),
                density=float(rho),
                altitude=float(altitude) if altitude is not None else None,
                temp_shift_F=float(temp_shift_F),
                control_deflections=ctrl,
                control_index_map=control_index_map,
                timeout_s=timeout_s,
                write_geom=write_geom,
                force_rewrite_geom=force_rewrite_geom,
                geom_writer=geom_writer,
            )
            avl_calls += 1
            CL = res["scalars"].get("CL", float("nan"))
            return CL, res

        # -----------------------------
        # 1) Fast path: seed from previous alpha
        # -----------------------------
        if alpha_seed_prev is not None:
            alpha_test = float(alpha_seed_prev)
            CL_test, res_test = eval_at(alpha_test)
            f_test = CL_test - CL_target

            if abs(f_test) < tol_CL:
                # Already converged in one call
                return {
                    "alpha_deg": float(alpha_test),
                    "CL": float(CL_test),
                    "Cm": float(res_test["scalars"].get("Cm", float("nan"))),
                    "CD": float(res_test["scalars"].get("CD", float("nan"))),
                    "CDi": float(res_test["scalars"].get("CDind", float("nan"))),
                    "res": res_test,
                }

            # Try a very small bracket around previous α
            a_low = alpha_test - 0.3
            a_high = alpha_test + 0.3
            CL_low, res_low = eval_at(a_low)
            CL_high, res_high = eval_at(a_high)
            f_low = CL_low - CL_target
            f_high = CL_high - CL_target

            # If small bracket straddles root -> solve with secant
            if f_low * f_high <= 0.0:
                a, fa, resa = a_low, f_low, res_low
                b, fb, resb = a_high, f_high, res_high
                alpha_hit, res_hit = b, resb

                for it in range(max_alpha_iter):
                    if abs(b - a) < 1e-9 or abs(fb - fa) < 1e-9:
                        alpha_new = 0.5 * (a + b)
                    else:
                        slope = (fb - fa) / (b - a)
                        alpha_new = b - fb / slope
                    alpha_new = 0.7 * alpha_new + 0.3 * b

                    CL_new, res_new = eval_at(alpha_new)
                    f_new = CL_new - CL_target

                    alpha_hit, res_hit = alpha_new, res_new
                    if abs(f_new) < tol_CL:
                        break

                    if fa * f_new <= 0.0:
                        b, fb, resb = alpha_new, f_new, res_new
                    else:
                        a, fa, resa = alpha_new, f_new, res_new

                kv = res_hit["scalars"]
                return {
                    "alpha_deg": float(alpha_hit),
                    "CL": float(kv.get("CL", float("nan"))),
                    "Cm": float(kv.get("Cm", float("nan"))),
                    "CD": float(kv.get("CD", float("nan"))),
                    "CDi": float(kv.get("CDind", float("nan"))),
                    "res": res_hit,
                }

            # If the tiny bracket failed, fall through to full bracket…

        # -----------------------------
        # 2) Full fallback bracket (rare)
        # -----------------------------
        a_low = float(alpha_seed_deg) - 2.0
        a_high = float(alpha_seed_deg) + 2.0
        CL_low, res_low = eval_at(a_low)
        CL_high, res_high = eval_at(a_high)
        f_low = CL_low - CL_target
        f_high = CL_high - CL_target

        tries = 0
        while f_low * f_high > 0.0 and tries < 5:
            a_low -= 2.0
            a_high += 2.0
            CL_low, res_low = eval_at(a_low)
            CL_high, res_high = eval_at(a_high)
            f_low = CL_low - CL_target
            f_high = CL_high - CL_target
            tries += 1

        if f_low * f_high > 0.0:
            raise RuntimeError("Full bracket failed in solve_alpha_for_CL.")

        a, fa, resa = a_low, f_low, res_low
        b, fb, resb = a_high, f_high, res_high
        alpha_hit, res_hit = b, resb

        for it in range(max_alpha_iter):
            if abs(b - a) < 1e-9 or abs(fb - fa) < 1e-9:
                alpha_new = 0.5 * (a + b)
            else:
                slope = (fb - fa) / (b - a)
                alpha_new = b - fb / slope
            alpha_new = 0.7 * alpha_new + 0.3 * b

            CL_new, res_new = eval_at(alpha_new)
            f_new = CL_new - CL_target

            alpha_hit, res_hit = alpha_new, res_new
            if abs(f_new) < tol_CL:
                break

            if fa * f_new <= 0.0:
                b, fb, resb = alpha_new, f_new, res_new
            else:
                a, fa, resa = alpha_new, f_new, res_new

        kv = res_hit["scalars"]
        return {
            "alpha_deg": float(alpha_hit),
            "CL": float(kv.get("CL", float("nan"))),
            "Cm": float(kv.get("Cm", float("nan"))),
            "CD": float(kv.get("CD", float("nan"))),
            "CDi": float(kv.get("CDind", float("nan"))),
            "res": res_hit,
        }


    # ------------------------
    # Outer solve: elevator such that Cm = 0
    # ------------------------
    de_low, de_high = float(elevator_bounds[0]), float(elevator_bounds[1])
    if de_low >= de_high:
        raise ValueError("elevator_bounds must satisfy lower < upper.")

    sol_low = solve_alpha_for_CL(de_low)
    Cm_low = sol_low["Cm"]
    sol_high = solve_alpha_for_CL(de_high)
    Cm_high = sol_high["Cm"]

    tries = 0
    while Cm_low * Cm_high > 0.0 and tries < 5:
        span = de_high - de_low
        de_low -= 0.5 * span
        de_high += 0.5 * span
        sol_low = solve_alpha_for_CL(de_low)
        Cm_low = sol_low["Cm"]
        sol_high = solve_alpha_for_CL(de_high)
        Cm_high = sol_high["Cm"]
        tries += 1

    if Cm_low * Cm_high > 0.0:
        raise RuntimeError("Failed to bracket elevator for Cm=0 in avl_trim_longitudinal.")

    a_e, fa_e, sol_a = de_low, Cm_low, sol_low
    b_e, fb_e, sol_b = de_high, Cm_high, sol_high
    de_hit, sol_hit = b_e, sol_b

    for it in range(max_elev_iter):
        if abs(b_e - a_e) < 1e-9 or abs(fb_e - fa_e) < 1e-9:
            de_new = 0.5 * (a_e + b_e)
        else:
            slope = (fb_e - fa_e) / (b_e - a_e)
            de_new = b_e - fb_e / slope
        de_new = 0.7 * de_new + 0.3 * b_e

        sol_new = solve_alpha_for_CL(de_new, alpha_seed_prev=sol_hit["alpha_deg"])
        Cm_new = sol_new["Cm"]

        history["elevator_iter"].append({
            "iter": int(it),
            "elevator_deg": float(de_new),
            "Cm": float(Cm_new),
        })

        de_hit, sol_hit = de_new, sol_new
        if abs(Cm_new) < tol_Cm:
            break

        if fa_e * Cm_new <= 0.0:
            b_e, fb_e, sol_b = de_new, Cm_new, sol_new
        else:
            a_e, fa_e, sol_a = de_new, Cm_new, sol_new

    # ------------------------
    # Final trimmed state
    # ------------------------
    alpha_trim = sol_hit["alpha_deg"]
    CL_trim = sol_hit["CL"]
    Cm_trim = sol_hit["Cm"]
    CD_trim = sol_hit["CD"]
    CDi_trim = sol_hit["CDi"]
    K_trim = CDi_trim / max(CL_trim**2, 1e-12)

    out = {
        "alpha_trim_deg": float(alpha_trim),
        "elevator_trim_deg": float(de_hit),
        "CL": float(CL_trim),
        "Cm": float(Cm_trim),
        "CD": float(CD_trim),
        "CDi": float(CDi_trim),
        "K": float(K_trim),
        "rho": float(rho),
        "V": float(velocity),
        "avl_calls": int(avl_calls),     # <-- key metric
        "history": history,
    }
    return out


# ------------- 2D Newton Step Method --------------------
def avl_trim_longitudinal(
    airplane: asb.Airplane,
    *,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str = "trim_case",
    CL_target: float,
    velocity: float,
    altitude: float | None = None,
    temp_shift_F: float = 0.0,
    mach: float = 0.0,
    control_index_map: Dict[str, int],
    baseline_controls: Optional[Dict[str, float]] = None,
    elevator_bounds: Tuple[float, float] = (-20.0, 20.0),
    alpha_seed_deg: float = 4.0,
    elevator_seed_deg: float = 0.0,
    tol_CL: float = 1e-2,
    tol_Cm: float = 1e-3,
    max_iter: int = 12,
    jac_step_alpha: float = 0.2,   # finite-diff step [deg]
    jac_step_elev: float = 0.5,    # finite-diff step [deg]
    max_step_alpha: float = 3.0,   # Newton step clamp [deg]
    max_step_elev: float = 5.0,    # Newton step clamp [deg]
    # New safety knobs for fallback to 1d solver:
    max_cond_J: float = 1e6,
    residual_growth_factor: float = 2.0,  # how much ||f|| can grow before we bail
    timeout_s: float | None = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True,
    geom_writer=None,
) -> Dict:
    """
    2D Newton trim in (alpha, elevator) for:
        CL(alpha, delta_e) = CL_target
        Cm(alpha, delta_e) = 0

    Falls back to the original _avl_trim_longitudinal_1D (nested 1D solver)
    if Newton fails or becomes ill-conditioned.

    Returns same keys as avl_trim_longitudinal, plus a detailed history.
    """

        # ------------------------
    # Density
    # ------------------------
    if altitude is not None:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
    else:
        rho = 1.225  # fallback

    # ------------------------
    # Controls
    # ------------------------
    baseline_controls = dict(baseline_controls) if baseline_controls is not None else {}
    for k in ("aileron", "elevator", "rudder", "flap"):
        baseline_controls.setdefault(k, 0.0)

    # ------------------------
    # AVL call wrapper
    # ------------------------
    avl_calls = 0

    def eval_state(alpha_deg: float, elevator_deg: float) -> Dict[str, float]:
        nonlocal avl_calls

        ctrl = dict(baseline_controls)
        ctrl["elevator"] = float(elevator_deg)

        res = run_avl_case(
            airplane=airplane,
            avl_exe=avl_exe,
            working_directory=working_directory,
            case_name=case_name,
            alpha=float(alpha_deg),
            beta=0.0,
            mach=float(mach),
            velocity=float(velocity),
            density=float(rho),
            altitude=float(altitude) if altitude is not None else None,
            temp_shift_F=float(temp_shift_F),
            control_deflections=ctrl,
            control_index_map=control_index_map,
            timeout_s=timeout_s,
            write_geom=write_geom,
            force_rewrite_geom=force_rewrite_geom,
            geom_writer=geom_writer,
        )
        avl_calls += 1

        kv = res["scalars"]
        CL  = float(kv.get("CL",    float("nan")))
        Cm  = float(kv.get("Cm",    float("nan")))
        CD  = float(kv.get("CD",    float("nan")))
        CDi = float(kv.get("CDind", float("nan")))

        return {
            "alpha_deg": float(alpha_deg),
            "elevator_deg": float(elevator_deg),
            "CL": CL,
            "Cm": Cm,
            "CD": CD,
            "CDi": CDi,
            "res": res,
        }

    # ------------------------
    # Newton iterations + bookkeeping for fallback
    # ------------------------
    alpha = float(alpha_seed_deg)
    de = float(np.clip(elevator_seed_deg, elevator_bounds[0], elevator_bounds[1]))

    history: Dict[str, list] = {
        "iter": [],
    }

    converged = False
    failure_reason = ""
    norm_f_prev = None

    for it in range(max_iter):
        # Base evaluation
        st = eval_state(alpha, de)
        f1 = st["CL"] - CL_target  # CL residual
        f2 = st["Cm"]              # Cm residual

        # Residual norm for monitoring behaviour
        norm_f = float(np.sqrt(f1**2 + f2**2))

        history["iter"].append({
            "iter": int(it),
            "alpha_deg": float(alpha),
            "elevator_deg": float(de),
            "CL": float(st["CL"]),
            "Cm": float(st["Cm"]),
            "CD": float(st["CD"]),
            "CDi": float(st["CDi"]),
            "f_CL": float(f1),
            "f_Cm": float(f2),
            "norm_f": norm_f,
            "avl_calls": int(avl_calls),
        })

        # Primary convergence check
        if abs(f1) < tol_CL and abs(f2) < tol_Cm:
            converged = True
            break

        # Check if residual is blowing up compared to previous iteration
        if norm_f_prev is not None and norm_f > residual_growth_factor * norm_f_prev:
            failure_reason = "residual_increasing"
            break
        norm_f_prev = norm_f

        # ------------------------
        # Finite-diff Jacobian
        # ------------------------
        st_da = eval_state(alpha + jac_step_alpha, de)
        st_de = eval_state(alpha, de + jac_step_elev)

        df1_dalpha = (st_da["CL"] - st["CL"]) / jac_step_alpha
        df2_dalpha = (st_da["Cm"] - st["Cm"]) / jac_step_alpha

        df1_delev = (st_de["CL"] - st["CL"]) / jac_step_elev
        df2_delev = (st_de["Cm"] - st["Cm"]) / jac_step_elev

        J = np.array([
            [df1_dalpha, df1_delev],
            [df2_dalpha, df2_delev],
        ], dtype=float)
        f_vec = np.array([f1, f2], dtype=float)

        # ---- NEW: Jacobian diagnostics ----
        try:
            condJ = float(np.linalg.cond(J))
        except np.linalg.LinAlgError:
            condJ = float("inf")

        try:
            detJ = float(np.linalg.det(J))
        except np.linalg.LinAlgError:
            detJ = float("nan")

        # Attach diagnostics to the *current* iteration history entry
        history["iter"][-1]["condJ"] = condJ
        history["iter"][-1]["detJ"] = detJ

        # Check Jacobian conditioning BEFORE solving
        try:
            condJ = float(np.linalg.cond(J))
        except np.linalg.LinAlgError:
            condJ = np.inf

        history["iter"][-1]["condJ"] = condJ

        if not np.isfinite(condJ) or condJ > max_cond_J:
            failure_reason = "ill_conditioned_J"
            break

        # Solve J * dx = -f
        try:
            dx = np.linalg.solve(J, -f_vec)
        except np.linalg.LinAlgError:
            # Near singular even if condJ didn't flag it
            failure_reason = "singular_J"
            break

        d_alpha_raw, d_de_raw = float(dx[0]), float(dx[1])

        # Clamp step sizes for robustness
        d_alpha = float(np.clip(d_alpha_raw, -max_step_alpha, max_step_alpha))
        d_de    = float(np.clip(d_de_raw,   -max_step_elev,  max_step_elev))

        # ---- NEW: log step sizes (raw and clamped) ----
        history["iter"][-1]["d_alpha_raw"] = d_alpha_raw
        history["iter"][-1]["d_elev_raw"]  = d_de_raw
        history["iter"][-1]["d_alpha"]     = d_alpha
        history["iter"][-1]["d_elev"]      = d_de       

        # Update iterate
        alpha = alpha + d_alpha
        de    = np.clip(de + d_de, elevator_bounds[0], elevator_bounds[1])

    # ------------------------
    # Decide: use Newton result, or fallback to old solver
    # ------------------------
    if not converged:
        # Optional: small print/log hook for debugging
        print(f"[WARN] avl_trim_longitudinal (newton2d) fallback to 1d solver: reason={failure_reason}, "
              f"alpha_seed={alpha_seed_deg}, elevator_seed={elevator_seed_deg}")

        # FALLBACK: call your robust 1D/nested solver.
        # Note: we add avl_calls from Newton into the fallback result so you still
        # see the total AVL usage in the returned dict.
        fallback = _avl_trim_longitudinal_1D(
            airplane=airplane,
            avl_exe=avl_exe,
            working_directory=working_directory,
            case_name=f"{case_name}_fallback",
            CL_target=CL_target,
            velocity=velocity,
            altitude=altitude,
            temp_shift_F=temp_shift_F,
            mach=mach,
            control_index_map=control_index_map,
            baseline_controls=baseline_controls,
            elevator_bounds=elevator_bounds,
            alpha_seed_deg=alpha_seed_deg,  # or alpha from last Newton iterate
            tol_CL=tol_CL,
            tol_Cm=tol_Cm,
            # pass through other args if your 1D version has them
        )

        # Add the AVL calls already spent in Newton to the fallback count
        if "avl_calls" in fallback:
            fallback["avl_calls"] = int(fallback["avl_calls"]) + int(avl_calls)

        # Optional: expose failure info
        fallback.setdefault("newton2d_failure_reason", failure_reason)
        fallback.setdefault("newton2d_history", history)

        return fallback

    # ------------------------
    # Final state from successful Newton
    # ------------------------
    st_final = eval_state(alpha, de)
    CL_trim  = st_final["CL"]
    Cm_trim  = st_final["Cm"]
    CD_trim  = st_final["CD"]
    CDi_trim = st_final["CDi"]
    K_trim   = CDi_trim / max(CL_trim**2, 1e-12)

    out = {
        "alpha_trim_deg": float(st_final["alpha_deg"]),
        "elevator_trim_deg": float(st_final["elevator_deg"]),
        "CL": float(CL_trim),
        "Cm": float(Cm_trim),
        "CD": float(CD_trim),
        "CDi": float(CDi_trim),
        "K": float(K_trim),
        "rho": float(rho),
        "V": float(velocity),
        "avl_calls": int(avl_calls),
        "history": history,
        "newton2d_failure_reason": "",
    }
    return out



def plot_trim_residual_surfaces(
    *,
    airplane: asb.Airplane,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str,
    CL_target: float,
    velocity: float,
    altitude: float | None,
    temp_shift_F: float,
    mach: float,
    control_index_map: Dict[str, int],
    baseline_controls: Dict[str, float],
    alpha_center_deg: float,
    elevator_center_deg: float,
    alpha_span_deg: float = 6.0,
    elev_span_deg: float = 10.0,
    n_alpha: int = 25,
    n_elev: int = 25,
    timeout_s: float | None = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = False,
    geom_writer=None,
):
    """
    Visualize f1 = CL - CL_target and f2 = Cm over (alpha, elevator) space
    around a given trim point.
    """

    # ---- Atmospheric / density (consistent with trim) ----
    if altitude is not None:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
    else:
        rho = 1.225

    # ---- Build ranges and mesh ----
    alpha_min = alpha_center_deg - 0.5 * alpha_span_deg
    alpha_max = alpha_center_deg + 0.5 * alpha_span_deg

    elev_min = elevator_center_deg - 0.5 * elev_span_deg
    elev_max = elevator_center_deg + 0.5 * elev_span_deg

    alpha_vec = np.linspace(alpha_min, alpha_max, n_alpha)
    elev_vec  = np.linspace(elev_min, elev_max, n_elev)

    A_grid, E_grid = np.meshgrid(alpha_vec, elev_vec, indexing="xy")

    f1_grid = np.zeros_like(A_grid, dtype=float)
    f2_grid = np.zeros_like(A_grid, dtype=float)
    normf_grid = np.zeros_like(A_grid, dtype=float)

    # ---- Evaluate on grid ----
    for i in range(n_elev):
        for j in range(n_alpha):
            alpha_ij = float(A_grid[i, j])
            elev_ij  = float(E_grid[i, j])

            ctrl = dict(baseline_controls)
            ctrl["elevator"] = elev_ij

            res = run_avl_case(
                airplane=airplane,
                avl_exe=avl_exe,
                working_directory=working_directory,
                case_name=f"{case_name}_surf",
                alpha=alpha_ij,
                beta=0.0,
                mach=float(mach),
                velocity=float(velocity),
                density=float(rho),
                altitude=float(altitude) if altitude is not None else None,
                temp_shift_F=float(temp_shift_F),
                control_deflections=ctrl,
                control_index_map=control_index_map,
                timeout_s=timeout_s,
                write_geom=write_geom,
                force_rewrite_geom=force_rewrite_geom,
                geom_writer=geom_writer,
            )

            kv = res["scalars"]
            CL = float(kv.get("CL", float("nan")))
            Cm = float(kv.get("Cm", float("nan")))

            f1 = CL - CL_target
            f2 = Cm
            normf = np.sqrt(f1**2 + f2**2)

            f1_grid[i, j] = f1
            f2_grid[i, j] = f2
            normf_grid[i, j] = normf

    # ---- Plotting ----
    fig, axs = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)

    # f1 = CL - CL_target
    cs1 = axs[0].contourf(A_grid, E_grid, f1_grid, levels=31)
    axs[0].contour(A_grid, E_grid, f1_grid, levels=[0.0], colors="k", linewidths=1.5)
    axs[0].scatter([alpha_center_deg], [elevator_center_deg], marker="x")
    axs[0].set_xlabel(r"$\alpha$ [deg]")
    axs[0].set_ylabel(r"$\delta_e$ [deg]")
    axs[0].set_title(r"$f_1 = CL - CL_{\rm target}$")
    fig.colorbar(cs1, ax=axs[0])

    # f2 = Cm
    cs2 = axs[1].contourf(A_grid, E_grid, f2_grid, levels=31)
    axs[1].contour(A_grid, E_grid, f2_grid, levels=[0.0], colors="k", linewidths=1.5)
    axs[1].scatter([alpha_center_deg], [elevator_center_deg], marker="x")
    axs[1].set_xlabel(r"$\alpha$ [deg]")
    axs[1].set_ylabel(r"$\delta_e$ [deg]")
    axs[1].set_title(r"$f_2 = Cm$")
    fig.colorbar(cs2, ax=axs[1])

    # ||f||
    cs3 = axs[2].contourf(A_grid, E_grid, normf_grid, levels=31)
    axs[2].scatter([alpha_center_deg], [elevator_center_deg], marker="x")
    axs[2].set_xlabel(r"$\alpha$ [deg]")
    axs[2].set_ylabel(r"$\delta_e$ [deg]")
    axs[2].set_title(r"$\|f\| = \sqrt{f_1^2 + f_2^2}$")
    fig.colorbar(cs3, ax=axs[2])

    fig.suptitle("Trim residual surfaces around Newton solution")
    plt.show()