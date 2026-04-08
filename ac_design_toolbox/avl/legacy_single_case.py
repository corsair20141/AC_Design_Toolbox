"""Preserved legacy AVL single-case workflow.

This module keeps the older single-run AVL path available without making it part
of the primary package surface. New integrations should prefer
``ac_design_toolbox.api`` or the grouped modules under ``ac_design_toolbox.avl``.
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any
import aerosandbox as asb

from ac_design_toolbox.atmosphere import SAC




# ----------------------------
# Small utilities
# ----------------------------
def _ensure_dir(p: Path):
    p.mkdir(parents=True, exist_ok=True)

def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def _write(p: Path, s: str):
    p.write_text(s, encoding="utf-8")

# -------------------------------------------
# 1) Write AVL geometry using ASB only
# -------------------------------------------
def write_avl_files_asb(airplane, workdir: Path, op_point: Optional[asb.OperatingPoint] = None) -> Dict[str, Path]:
    """
    Use ASB's AVL helper to emit geometry only.
    ASB's AVL ctor requires op_point; we provide a default empty one if none is given.
    """
    workdir.mkdir(parents=True, exist_ok=True)
    geom_path = workdir / "Airplane.avl"

    # If the caller passed an AVL instance, accept it; else build one with an OP.
    if isinstance(airplane, asb.AVL):
        avl = airplane
    else:
        if op_point is None:
            # Minimal OP; just to satisfy ASB's constructor
            op_point = asb.OperatingPoint()  # alpha=0, beta=0, V=0, ISA by default
        avl = asb.AVL(airplane=airplane, op_point=op_point, working_directory=workdir)

    avl.write_avl(geom_path)

    if not geom_path.exists():
        raise FileNotFoundError(f"ASB did not produce {geom_path}.")
    return {"geom": geom_path}



# ----------------------------------------------------------
# 2) Map control names -> d1,d2,... by parsing .avl CONTROL
# ----------------------------------------------------------
CONTROL_LINE_RE = re.compile(
    r"^\s*CONTROL\s+(\S+)\s+[+\-0-9.eE]+\s+[+\-0-9.eE]+\s+[+\-0-9.eE]+\s+[+\-0-9.eE]+\s+[+\-0-9.eE]+",
    re.IGNORECASE
)

def map_controls_d_indices(avl_geom_file: Path) -> Dict[str, str]:
    """
    Reads CONTROL lines in order of appearance; returns e.g. {"aileron": "d1", "elevator": "d2", ...}.
    """
    names: List[str] = []
    for line in _read(avl_geom_file).splitlines():
        m = CONTROL_LINE_RE.match(line)
        if m:
            names.append(m.group(1))
    # preserve first occurrence ordering, unique
    seen, ordered = set(), []
    for n in names:
        if n not in seen:
            seen.add(n)
            ordered.append(n)
    return {n: f"d{i+1}" for i, n in enumerate(ordered)}

# -------------------------------------------------
# 3) Build a minimal .run for ONE operating point
# -------------------------------------------------
from typing import Dict, Optional
from pathlib import Path

def build_single_runfile(
    *,
    geom_file: Path,            # unused in keystrokes; the file is passed on the CLI
    outdir: Path,
    case_name: str,
    alpha: float = 0.0,
    beta: float = 0.0,
    mach: float = 0.0,
    velocity: Optional[float] = None,   # if provided, we set V and density
    p: float = 0.0,
    q: float = 0.0,
    r: float = 0.0,
    control_deflections: Optional[Dict[str, float]] = None,  # {"aileron": +5.0, ...} [deg]
    control_index_map: Dict[str, str] = None,                # optional mapping, not strictly needed
    density_kg_m3: Optional[float] = None,                   # if provided, we set d
) -> str:
    """
    Construct the exact keystroke sequence ASB uses, with optional control deflections.
    Returns a single string ending in '\n'.
    """
    outdir = Path(outdir)
    fs_file = f"{case_name}.fs"      # strip forces output
    stab_file = f"{case_name}.stb"   # stability (ST) output

    # Convert rates to nondimensional bars
    # You must pass b_ref and c_ref in your run_single_case() and compute these bars there,
    # or fetch them from your airplane object before calling this builder.
    # To keep this builder independent, assume caller already converted to nondimensional:
    # p, q, r here are *dimensional* (rad/s). We need pb/2V etc., so we require callers to pass V, b_ref, c_ref.
    # Simpler: do the nondimensionalization in the caller, then pass pb2V, qc2V, rb2V here.
    # But to match your current API, we’ll assume the caller computed:
    #   _pb2V, _qc2V, _rb2V = <caller precompute>
    # and put them into the dict below by monkey-patching via kwargs or closure.
    # To avoid overreach, we’ll compute them here *only if* velocity, b_ref, c_ref are attached to a closure.
    # For now we leave placeholders and expect the caller to replace them when building the final string.
    # >>> Replace these three with real values in your run_single_case before calling this function:
    pb2V = getattr(build_single_runfile, "_pb2V", 0.0)
    qc2V = getattr(build_single_runfile, "_qc2V", 0.0)
    rb2V = getattr(build_single_runfile, "_rb2V", 0.0)

    ks = []

    # 1) Disable graphics (exactly ASB)
    ks += ["plop", "g", ""]

    # 2) ENTER OPER
    ks += ["oper"]

    # 3) p,q,r in body axes (exactly ASB: 'o', 'r', '')
    ks += ["o", "r", ""]

    # 4) Modify parameters (m ... blank to exit)
    ks += ["m", f"mn {float(mach)}"]
    if velocity is not None:
        ks += [f"v {float(velocity)}"]
    if density_kg_m3 is not None:
        ks += [f"d {float(density_kg_m3)}"]
    ks += ["g 9.81", ""]  # blank line to exit Modify

    # 5) State (double-letter form prevents falling into the constraint editor)
    ks += [
        f"a a {float(alpha)}",
        f"b b {float(beta)}",
        f"r r {float(pb2V)}",
        f"p p {float(qc2V)}",
        f"y y {float(rb2V)}",
    ]

    # 6) Controls (optional). Syntax: enter D1 first to enable control variables.
    # ASB sends "d1 d1 1" to ensure the control variable system is active.
    ks += ["d1 d1 1"]
    if control_deflections:
        # AVL accepts: "<control_name> <value>" once in control prompt.
        # Safe pattern that works across versions: go through the "D1" prompt each time:
        # 'd1 <name> <value>' (same as typing D1 key then filling name & deflection).
        for name, val_deg in control_deflections.items():
            ks += [f"d1 {name} {float(val_deg)}"]

    # 7) Execute & write stability text like ASB
    ks += [
        "x",          # execute
        "st",         # stability derivatives (unformatted text)
        f"{stab_file}",
        "o",          # overwrite if exists
        "",           # default surface
        "",           # return from prompt
        "ft",         # total forces (terse)
        f"{fs_file}",
        "o",
        "",
        "",
        "quit",
    ]

    # Join + ensure trailing newline
    return "\n".join(ks) + "\n"


# -------------------------------------------------
# 4) Run AVL (stdin <- .run contents)
# -------------------------------------------------
def run_avl(*, avl_exe: str, workdir: Path, runfile_text: str, timeout: Optional[float] = 10.0) -> None:
    """
    Launch AVL with stdin keystrokes. Expects that the geometry file 'Airplane.avl'
    and any .afN airfoil files are already in workdir. runfile_text should end with '\n'.
    """
    workdir = Path(workdir)
    command = [avl_exe, "Airplane.avl"]

    # IMPORTANT: exactly the ASB approach: communicate() with text input; no shell, no extra pipes
    proc = subprocess.Popen(
        command,
        cwd=workdir,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,   # capture for debugging; flip to DEVNULL if desired
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = proc.communicate(input=runfile_text, timeout=timeout)
    rc = proc.poll()

    if rc not in (0, None):
        # Enrich the error with helpful hints
        msg = f"AVL exited with code {rc}\n--- STDOUT ---\n{out}\n--- STDERR ---\n{err}"
        if "CDCL" in out or "CDCL" in err:
            msg += ("\nHint: CL–CD polar block issue. Ensure each section has exactly one CDCL "
                    "and that your sections run root→tip in order; controls must attach to valid segments.")
        raise RuntimeError(msg)

# -------------------------------------------------
# 5) Parse .fs and .st (compact but robust)
# -------------------------------------------------
FS_MAIN_RE = re.compile(r"CLtot\s*=\s*([\-0-9.+Ee]+)\s*CDtot\s*=\s*([\-0-9.+Ee]+)\s*CYtot\s*=\s*([\-0-9.+Ee]+)")
FS_MOM_RE  = re.compile(r"Cltot\s*=\s*([\-0-9.+Ee]+)\s*Cmtot\s*=\s*([\-0-9.+Ee]+)\s*Cntot\s*=\s*([\-0-9.+Ee]+)")

def parse_fs(fs_path: Path) -> Dict[str, float]:
    s = _read(fs_path)
    m1, m2 = FS_MAIN_RE.search(s), FS_MOM_RE.search(s)
    if not (m1 and m2):
        raise ValueError(f"Could not parse {fs_path.name}; capture patterns may need adjustment.")
    return {
        "CL": float(m1.group(1)),
        "CD": float(m1.group(2)),
        "CY": float(m1.group(3)),
        "Cl": float(m2.group(1)),
        "Cm": float(m2.group(2)),
        "Cn": float(m2.group(3)),
    }

ST_BLOCK_RE = re.compile(r"STABILITY DERIVATIVES(.*?)(?:\n\s*\n|\Z)", re.DOTALL | re.IGNORECASE)
DERIV_LINE_RE = re.compile(r"^\s*(C[LYmnl][a-zA-Z]?)\s*=\s*([\-0-9.+Ee]+)\s*$", re.MULTILINE)
CTRL_LINE_RE  = re.compile(r"^\s*(C[LYmnl])\s*\(d/d\(delta\-([^)]+)\)\)\s*=\s*([\-0-9.+Ee]+)\s*$",
                           re.MULTILINE | re.IGNORECASE)

def parse_st(st_path: Path) -> Dict[str, Any]:
    s = _read(st_path)
    blk = ST_BLOCK_RE.search(s)
    if not blk:
        raise ValueError(f"'STABILITY DERIVATIVES' section not found in {st_path.name}.")
    text = blk.group(1)
    out: Dict[str, Any] = {"derivatives": {}, "control_derivatives": {}}
    for m in DERIV_LINE_RE.finditer(text):
        out["derivatives"][m.group(1)] = float(m.group(2))
    for m in CTRL_LINE_RE.finditer(text):
        coeff, ctrl, val = m.group(1), m.group(2).strip().lower(), float(m.group(3))
        out["control_derivatives"].setdefault(ctrl, {})[coeff] = val
    return out

# -------------------------------------------------
# 6) Public “single run” entrypoint (SI-first)
# -------------------------------------------------

def run_single_case(
    *,
    airplane,
    avl_exe: str,
    working_directory: Path,
    case_name: str,
    alpha: float = 0.0,
    beta: float = 0.0,
    mach: float = 0.0,
    velocity: float = 0.0,             # m/s
    p: float = 0.0, q: float = 0.0, r: float = 0.0,   # rad/s (body rates)
    control_deflections: Optional[Dict[str, float]] = None,  # {"aileron": +5.0, ...} [deg]
    altitude: Optional[float] = None,  # m
    temp_shift_F: float = 0.0,
):
    working_directory = Path(working_directory)
    working_directory.mkdir(parents=True, exist_ok=True)

    # 1) ASB emits geometry via your helper
    files = write_avl_files_asb(airplane, working_directory)
    geom = Path(files["geom"])

    # Ensure the filename is exactly "Airplane.avl" because run_avl calls:
    #   [avl_exe, "Airplane.avl"]
    target_geom = working_directory / "Airplane.avl"
    if geom.resolve() != target_geom.resolve():
        # If your writer produced a different name (e.g. "airplane.avl"), normalize it:
        target_geom.write_text(geom.read_text(encoding="utf-8"), encoding="utf-8")
        geom = target_geom

    # 2) Density from SAC if altitude provided (kg/m^3)
    density = None
    if altitude is not None:
        sac = SAC(altitude=altitude, temp_shift_F=temp_shift_F, SI_Imp="SI")  # your helper’s API
        density = float(sac["rho"])

    # 3) Reference lengths and nondimensional rates
    try:
        b_ref = float(airplane.b_ref)
        c_ref = float(airplane.c_ref)
    except Exception as e:
        raise ValueError("Airplane must expose b_ref and c_ref (ASB Airplane has these).") from e

    if velocity <= 0:
        raise ValueError("velocity must be > 0 to compute pb/2V, qc/2V, rb/2V.")

    pb2V = (p * b_ref) / (2.0 * velocity)
    qc2V = (q * c_ref) / (2.0 * velocity)
    rb2V = (r * b_ref) / (2.0 * velocity)

    # 4) Inject nondimensional rates into the keystroke builder (as previously agreed)
    build_single_runfile._pb2V = pb2V
    build_single_runfile._qc2V = qc2V
    build_single_runfile._rb2V = rb2V

    # 5) Build ASB-style keystrokes (the builder you now have)
    runfile_text = build_single_runfile(
        geom_file=geom,
        outdir=working_directory,
        case_name=case_name,
        alpha=alpha,
        beta=beta,
        mach=mach,
        velocity=velocity,
        p=p, q=q, r=r,
        control_deflections=control_deflections,
        control_index_map=None,
        density_kg_m3=density,
    )

    # 6) Run AVL
    run_avl(avl_exe=avl_exe, workdir=working_directory, runfile_text=runfile_text, timeout=20.0)

    # 7) Parse outputs with your existing readers
    fs = parse_fs(working_directory / f"{case_name}.fs")
    st = parse_st(working_directory / f"{case_name}.stb")
    return {**fs, **st}


__all__ = [
    "build_single_runfile",
    "map_controls_d_indices",
    "parse_fs",
    "parse_st",
    "run_avl",
    "run_single_case",
    "write_avl_files_asb",
]

