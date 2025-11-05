# tools/avl_pipeline.py
from __future__ import annotations
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import math

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

    results = {
        "paths": {
            "case_dir": str(case_dir),
            "stdout": str(out_txt),
            "stderr": str(err_txt),
            "keystrokes": str(ks),
            "airplane_avl": str(geom),
            "mass_file": str(case_dir / "case.mass") if use_mass else None,
        },
        "scalars": parsed,             # unified dict of everything we parsed/derived
        "strip_forces": parse_strip_forces(text),   # keep your existing FS-table extractor
        "raw": text,
    }
    return results