# ASB_Wrappers.py
import aerosandbox.numpy as np
import aerosandbox as asb
from pathlib import Path
from collections import namedtuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import os
import types
import re


# ---------- helpers ----------
def _as_array(value, n, default=None):
    """
    Normalize a parameter into an array of length n.
    \nAccepted forms:
      - scalar -> constant array
      - (root, tip) tuple/list -> linear interpolation
      - list/array of length n (used as-is)
      - None -> use "default" (scalar or pair) or zeros
    """
    if value is None:
        value = 0.0 if default is None else default

    if np.isscalar(value):
        return np.full(n, float(value))

    value = np.asarray(value, dtype=float)
    if value.ndim == 1 and value.size == 2:  # (root, tip)
        root, tip = value
        eta = np.linspace(0, 1, n)
        return root + (tip - root) * eta

    if value.ndim == 1 and value.size == n:
        return value

    raise ValueError(
        f"Could not broadcast parameter to length {n}. "
        f"Provide a scalar, a (root, tip) pair, or an array of length {n}."
    )


def _coerce_airfoil(a):
    """Accept asb.Airfoil, string (e.g. 'naca2412'), or None."""
    if isinstance(a, asb.Airfoil):
        return a
    if isinstance(a, str):
        return asb.Airfoil(a)
    return a  # None or already-OK types



def _planform_metrics_from_cr_ct_b(cr: float, ct: float, b: float):
    """
    Given root chord, tip chord, and full span, return (S, AR, lambda, MAC).
    """
    lam = ct / cr
    S = 0.5 * b * (cr + ct)
    AR = b ** 2 / S
    MAC = (2/3) * cr * (1 + lam + lam**2) / (1 + lam)
    return S, AR, lam, MAC


PlanformSolve = namedtuple("PlanformSolve", "chords c_root c_tip b S AR lam MAC")
def _chords_from_area_or_taper(
    span: float | None,
    n_sections: int,
    *,
    area: float | None = None,
    AR: float | None = None,
    c_root: float | None = None,
    c_tip: float | None = None,
    taper: float | None = None,
):
    """
    Compute linear chord distribution for a trapezoidal planform given exactly 
    ONE of the following spec sets:

      1) c_root, c_tip, span
      2) c_root, taper, span
      3) c_tip,  taper, span
      4) area,  span,  taper
      5) AR, span, taper
      6) area,  AR, taper   # span is inferred; do NOT pass span
      7) area, span, root chord
      8) area, span, tip chord

    Any overspecification (e.g., area & AR & span) or underspecification raises ValueError.

    **Note 1: there are other ways to fully specify a trapezoidal planform, but this function is
    currently limited to these for simplicity.**

    **Note 2: For cranked wings, or other non-trapezoidal planforms, needs updates.**
    """

    if n_sections < 2:
        raise ValueError("n_sections must be >= 2.")

    has = dict(
        span=span is not None,
        area=area is not None,
        AR=AR is not None,
        cr=c_root is not None,
        ct=c_tip is not None,
        lam=taper is not None,
    )

    provided_keys = {k for k, v in has.items() if v}
    spec_sets = {
        "cr_ct_span":    {"cr", "ct", "span"},
        "cr_lam_span":   {"cr", "lam", "span"},
        "ct_lam_span":   {"ct", "lam", "span"},
        "area_span_lam": {"area", "span", "lam"},
        "AR_span_lam":   {"AR", "span", "lam"},
        "area_AR_lam":   {"area", "AR", "lam"},  # span inferred; must NOT include span
        "area_span_cr":  {"area", "span", "cr"},
        "area_span_ct":  {"area", "span", "ct"},
    }

    patterns = {name: (provided_keys == req) for name, req in spec_sets.items()}
    n_true = sum(patterns.values())

    if n_true > 1:
        active = [k for k, v in patterns.items() if v]
        raise ValueError(f"Overspecified planform: matches multiple spec sets {active}. Provide exactly one valid set.")

    # Helpful diagnostics for supersets / underspecification
    superset_matches = [
        (name, sorted(list(provided_keys - req)))
        for name, req in spec_sets.items()
        if req.issubset(provided_keys) and provided_keys != req
    ]
    if n_true == 0:
        if len(superset_matches) >= 1:
            details = "; ".join([f"{name} + extra {extras}" for name, extras in superset_matches])
            raise ValueError(
                "Overspecified planform: you provided a valid specification plus extra parameter(s). "
                f"Detected: {sorted(list(provided_keys))}. Supersets: {details}.\n"
                "Provide exactly one of:\n"
                "  1) c_root, c_tip, span\n"
                "  2) c_root, taper, span\n"
                "  3) c_tip,  taper, span\n"
                "  4) area,  span,  taper\n"
                "  5) AR, span, taper\n"
                "  6) area,  AR, taper   (span inferred; do NOT pass span)\n"
                "  7) area, span, root chord\n"
                "  8) area, span, tip chord"
            )
        else:
            provided = {
                k: v for k, v in dict(
                    span=span, area=area, AR=AR, c_root=c_root, c_tip=c_tip, taper=taper
                ).items() if v is not None
            }
            raise ValueError(
                "Underspecified or invalid planform specification. "
                f"You provided: {provided}\n"
                "Provide exactly one of:\n"
                "  1) c_root, c_tip, span\n"
                "  2) c_root, taper, span\n"
                "  3) c_tip,  taper, span\n"
                "  4) area,  span,  taper\n"
                "  5) AR, span, taper\n"
                "  6) area,  AR, taper   (span inferred; do NOT pass span)\n"
                "  7) area, span, root chord\n"
                "  8) area, span, tip chord\n"
            )

    # ---- Solve base (cr, ct, b)
    if patterns["cr_ct_span"]:
        cr, ct = float(c_root), float(c_tip)
        b = float(span)

    elif patterns["cr_lam_span"]:
        cr = float(c_root)
        lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (λ) must be > 0.")
        ct = lam * cr
        b = float(span)

    elif patterns["ct_lam_span"]:
        ct = float(c_tip)
        lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (λ) must be > 0.")
        cr = ct / lam
        b = float(span)

    elif patterns["area_span_lam"]:
        S = float(area); b = float(span); lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (λ) must be > 0.")
        cr = 2 * S / (b * (1 + lam)); ct = lam * cr

    elif patterns["AR_span_lam"]:
        ARv = float(AR); b = float(span); S = b**2 / ARv; lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (λ) must be > 0.")
        cr = 2 * S / (b * (1 + lam)); ct = lam * cr

    elif patterns["area_AR_lam"]:
        S = float(area); ARv = float(AR); b = (ARv * S) ** 0.5; lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (λ) must be > 0.")
        cr = 2 * S / (b * (1 + lam)); ct = lam * cr

    elif patterns["area_span_cr"]:
        S = float(area); b = float(span); cr = float(c_root)
        ct = 2 * S / b - cr
        if ct <= 0:
            raise ValueError("In (area, span, c_root), the implied c_tip <= 0. Check inputs.")

    elif patterns["area_span_ct"]:
        S = float(area); b = float(span); ct = float(c_tip)
        cr = 2 * S / b - ct
        if cr <= 0:
            raise ValueError("In (area, span, c_tip), the implied c_root <= 0. Check inputs.")

    else:
        raise RuntimeError("Internal pattern selection error.")

    if cr <= 0 or ct <= 0 or b <= 0:
        raise ValueError("All solved quantities must be positive (c_root, c_tip, span).")

    # ---- Secondary metrics
    lam = ct / cr
    S = 0.5 * b * (cr + ct)
    ARv = b**2 / S
    MAC = (2/3) * cr * (1 + lam + lam**2) / (1 + lam)

    # ---- Linear chord distribution
    eta = np.linspace(0, 1, n_sections)
    chords = cr + (ct - cr) * eta

    return PlanformSolve(chords=chords, c_root=cr, c_tip=ct, b=b, S=S, AR=ARv, lam=lam, MAC=MAC)




def _airfoil_blend_array(airfoil_root, airfoil_tip=None, n_sections=2, airfoils=None):
    """
    Make an array of airfoils per section.
    - If 'airfoils' provided as list of len n_sections, return as-is.
    - Else blend root->tip if airfoil_tip provided, else constant root.
    """
    if airfoils is not None:
        if len(airfoils) != n_sections:
            raise ValueError("Length of 'airfoils' must equal n_sections.")
        return airfoils

    if (airfoil_tip is None) or (airfoil_tip == airfoil_root):
        return [airfoil_root for _ in range(n_sections)]

    # Linear blend by index (AeroSandbox will blend between neighboring XSecs anyway)
    # Here we just assign root to all stations except the last, which we set to tip.
    # (This is typical; ASB blends between neighboring sections.)
    arr = [airfoil_root for _ in range(n_sections)]
    arr[-1] = airfoil_tip
    return arr


def _place(surface: asb.Wing, xyz_le):
    """
    Place a surface whose constructor built it at the origin.
    Do NOT read surface.xyz_le; just translate by the target.
    """
    return surface.translate([float(xyz_le[0]), float(xyz_le[1]), float(xyz_le[2])])


def _augmented_eta(n_base: int, breaks: tuple[float, float] | None):
    """
    Return a sorted, unique eta array (surface xsecs) in [0,1] that includes the two
    breakpoints if provided. Ensures exact xsec stations at control edges.
    """
    base = list(np.linspace(0.0, 1.0, n_base))
    if breaks is None:
        # Dedup anyway to guard against n_base==2 + numeric weirdness
        return np.unique(np.round(np.asarray(base, dtype=float), 12))

    e0, e1 = breaks
    add = []
    for e in (e0, e1):
        if e is None:
            continue
        e = float(e)
        if 0.0 < e < 1.0 and all(abs(e - b) > 1e-12 for b in base):
            add.append(e)

    eta = np.array(sorted(base + add), dtype=float)
    # Final robust dedup to avoid coincident stations (important for drawing/hinge math)
    eta = np.unique(np.round(eta, 12))
    return eta


def _iter_controls_from_geometry(airplane):
    """
    Read per-section ControlSurface.deflection values (deg) and coalesce by name.
    (You already verified with dump that these are set by with_control_deflections().)
    """
    name_to_defl = {}
    for w in getattr(airplane, "wings", []):
        for xs in getattr(w, "xsecs", []):
            for cs in getattr(xs, "control_surfaces", []):
                nm = str(getattr(cs, "name", "")).strip()
                if not nm:
                    continue
                dv = float(getattr(cs, "deflection", 0.0) or 0.0)
                # If multiple sections share the same control name, prefer nonzero; otherwise last seen
                if abs(dv) > 0 or nm not in name_to_defl:
                    name_to_defl[nm] = dv
    return name_to_defl

def _custom_keystrokes(self):
    run = []

    # Enter OPER menu
    run += ["oper"]

    # Mach (handle method vs property)
    m_attr = getattr(self.op_point, "mach", None)
    if callable(m_attr):
        mval = float(m_attr())
    elif m_attr is not None:
        mval = float(m_attr)
    else:
        a = float(self.op_point.atmosphere.speed_of_sound())
        mval = float(self.op_point.velocity) / a

    # State
    run += [
        "m",
        f"mn {mval}",
        f"v {float(self.op_point.velocity)}",
        f"d {float(self.op_point.atmosphere.density())}",
        "g 9.81",
        "",
    ]

    # Analysis state (non-dim rates)
    p_bar = self.op_point.p * self.airplane.b_ref / (2 * self.op_point.velocity)
    q_bar = self.op_point.q * self.airplane.c_ref / (2 * self.op_point.velocity)
    r_bar = self.op_point.r * self.airplane.b_ref / (2 * self.op_point.velocity)
    run += [
        f"a a {float(self.op_point.alpha)}",
        f"b b {float(self.op_point.beta)}",
        f"r r {float(p_bar)}",
        f"p p {float(q_bar)}",
        f"y y {float(r_bar)}",
    ]

    # Controls by name (degrees)
    for nm, dv in _iter_controls_from_geometry(self.airplane).items():
        if nm:
            run += [f"d {nm} {float(dv)}"]

    # Optional: print control table for one run to verify names/values
    # run += ["dc"]

    # Execute
    run += ["x"]
    return run


def apply_avl_keystroke_patch():
    """
    Force AVL to use our keystrokes everywhere, even if something else imported ASB after us.
    """
    import aerosandbox as asb
    # Patch the public alias
    asb.AVL._default_keystroke_file_contents = _custom_keystrokes
    # Patch the defining class too (some versions import through this path)
    try:
        from aerosandbox.aerodynamics.aero_3D import avl as asb_avl_mod
        asb_avl_mod.AVL._default_keystroke_file_contents = _custom_keystrokes
    except Exception:
        pass


class patched_AVL(asb.AVL):
    """
    Local AVL subclass:
      A) write_avl(): fixes CONTROL hinge vectors and builds a name->index map
      B) _default_keystroke_file_contents(): sets controls by *index* and executes with 'x'
    """
    def write_avl(self, file_name="airplane.avl"):
        # call original writer
        directory = Path(self.working_directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (file_name if isinstance(file_name, str) else str(file_name))
        super().write_avl(path)

        # Build hinge-axis lookup from geometry
        axis_idx = {}
        for wing in getattr(self.airplane, "wings", []):
            surf = str(getattr(wing, "name", "")).strip().lower()
            for xs in getattr(wing, "xsecs", []):
                for cs in getattr(xs, "control_surfaces", []):
                    cname = str(getattr(cs, "name", "")).strip().lower()
                    axis = getattr(cs, "_avl_hinge_axis", None)
                    if axis is None:
                        axis = (0.0, 0.0, 1.0) if ("rudder" in cname or "vertical" in surf) else (0.0, 1.0, 0.0)
                    axis_idx[(surf, cname)] = tuple(float(x) for x in axis)

        # Read, patch CONTROL lines, and simultaneously collect control order
        lines = path.read_text().splitlines()
        current_surface = None

        def _first_data_line(j):
            while j < len(lines):
                s = lines[j].strip()
                if s and not s.startswith("#"):
                    return j
                j += 1
            return None

        control_order = []  # list of control names in the order AVL will see them
        i = 0
        while i < len(lines):
            line = lines[i]

            # Capture current SURFACE name
            if re.match(r"^\s*SURFACE\s*$", line, re.IGNORECASE):
                j = _first_data_line(i + 1)
                if j is not None:
                    current_surface = lines[j].strip().lower()
                    i = j

            # Patch CONTROL data line and record order
            elif re.match(r"^\s*CONTROL\s*$", line, re.IGNORECASE):
                j = _first_data_line(i + 1)
                if j is not None:
                    toks = lines[j].split()
                    if len(toks) >= 7:
                        cname = toks[0].strip()
                        cname_l = cname.lower()
                        # record order (unique names only)
                        if cname not in control_order:
                            control_order.append(cname)

                        # hinge vector patch
                        key = ((current_surface or ""), cname_l)
                        axis = axis_idx.get(key)
                        if axis is None:
                            axis = (0.0, 0.0, 1.0) if ("rudder" in cname_l or "vertical" in (current_surface or "")) else (0.0, 1.0, 0.0)
                        toks[3] = f"{axis[0]:g}"
                        toks[4] = f"{axis[1]:g}"
                        toks[5] = f"{axis[2]:g}"
                        lines[j] = " ".join(toks)

            i += 1

        # Persist patched file
        path.write_text("\n".join(lines))

        # Save name->index map on *this* instance (1-based, like AVL)
        self._control_index_map = {name: idx + 1 for idx, name in enumerate(control_order)}

    def _default_keystroke_file_contents(self):
        run = []

        # OPER
        run += ["oper"]

        # Mach (method vs property safe)
        m_attr = getattr(self.op_point, "mach", None)
        if callable(m_attr):
            mval = float(m_attr())
        elif m_attr is not None:
            mval = float(m_attr)
        else:
            a = float(self.op_point.atmosphere.speed_of_sound())
            mval = float(self.op_point.velocity) / a

        # State
        run += [
            "m",
            f"mn {mval}",
            f"v {float(self.op_point.velocity)}",
            f"d {float(self.op_point.atmosphere.density())}",
            "g 9.81",
            "",
        ]

        # Non-dimensional rates
        p_bar = self.op_point.p * self.airplane.b_ref / (2 * self.op_point.velocity)
        q_bar = self.op_point.q * self.airplane.c_ref / (2 * self.op_point.velocity)
        r_bar = self.op_point.r * self.airplane.b_ref / (2 * self.op_point.velocity)
        run += [
            f"a a {float(self.op_point.alpha)}",
            f"b b {float(self.op_point.beta)}",
            f"r r {float(p_bar)}",
            f"p p {float(q_bar)}",
            f"y y {float(r_bar)}",
        ]

        # Controls: set by *index* using the map we built in write_avl()
        # Build desired deflections from geometry
        name_to_defl = {}
        for w in getattr(self.airplane, "wings", []):
            for xs in getattr(w, "xsecs", []):
                for cs in getattr(xs, "control_surfaces", []):
                    nm = str(getattr(cs, "name", "")).strip()
                    if not nm:
                        continue
                    dv = float(getattr(cs, "deflection", 0.0) or 0.0)
                    if abs(dv) > 0 or nm not in name_to_defl:
                        name_to_defl[nm] = dv

        # Ensure map exists (write_avl() is called by run() internally, but be safe)
        control_map = getattr(self, "_control_index_map", {})
        # If missing (e.g., user called run() without write_avl()), regenerate by writing once:
        if not control_map:
            # cause the writer to populate the map
            self.write_avl("airplane.avl")
            control_map = getattr(self, "_control_index_map", {})

        # drive by index: d{idx} <val>
        for nm, dv in name_to_defl.items():
            idx = control_map.get(nm)
            if idx is not None:
                run += [f"d{idx} {float(dv)}"]

        # Optional: show control table
        # run += ["dc"]

        # Execute
        run += ["x"]
        return run


# ---------- main builders ----------

def make_wing(
    name: str,
    span: float,
    n_sections_w: int,
    n_chordwise_w=12,
    chordwise_spacing_w="cosine",
    n_spanwise_w=36,
    spanwise_spacing_w="cosine",
    *,
    symmetric: bool = True,
    # planform sizing
    area: float = None,
    AR: float = None,
    c_root: float = None,
    c_tip: float = None,
    taper: float = None,
    # geometry
    sweep_le=0.0,
    dihedral=0.0,
    x_le_root=0.0, y_le_root=0.0, z_le_root=0.0,
    # distributions
    twist=0.0,
    chord_override=None,
    # airfoils
    airfoil_root: asb.Airfoil = None,
    airfoil_tip: asb.Airfoil = None,
    airfoils=None,
    control_surface_name: str | None = None,     # e.g. "aileron", "elevator", "rudder"
    control_surface_is_symmetric: bool | None = None,
    control_surface_deflection: float | None = None,
    control_surface_span_fraction: tuple[float, float] = (0.0, 0.0),  # (eta_start, eta_end)
    control_hinge_point: float | None = 0.75,     # x/c of control surface hinge
    # --- flaps (inboard TE control) ---
    span_frac_flap: tuple[float, float] | None = None,  # e.g. (0.15, 0.60)
    delta_flap: float | None = 0.0,
    hinge_point_flap: float | None = 0.75,
    flap_is_symmetric: bool = True,
):
    """
    Builds a generic wing component with robust control surface placement.
    """
    if n_sections_w < 2:
        raise ValueError("n_sections must be >= 2 (root + at least one more station).")

    # ---- chords
    if chord_override is not None:
        chords = np.asarray(chord_override, dtype=float)
        if len(chords) != n_sections_w:
            raise ValueError("chord_override must have length n_sections_w.")
    else:
        res = _chords_from_area_or_taper(
            span=span, n_sections=n_sections_w, area=area, AR=AR,
            c_root=c_root, c_tip=c_tip, taper=taper,
        )
        chords = res[0]

    # ---- distributions and station axes
    twist_arr = _as_array(twist, n_sections_w)
    airfoil_arr = _airfoil_blend_array(airfoil_root, airfoil_tip, n_sections_w, airfoils)

    # ---- control-surface windows (support both aileron *and* flap)
    def _valid_window(w):
        return (
            w is not None and
            len(w) == 2 and
            (w[0] is not None) and (w[1] is not None) and
            (w[1] > w[0])
        )

    e_ail = control_surface_span_fraction if control_surface_name is not None else None
    has_ail = _valid_window(e_ail)

    e_flp = span_frac_flap
    has_flp = _valid_window(e_flp)

    # Base eta with guaranteed inclusion of aileron edges (if any)
    eta = _augmented_eta(n_sections_w, e_ail if has_ail else None)

    # Ensure flap edges are also present exactly (union of breakpoints)
    if has_flp:
        for edge in (e_flp[0], e_flp[1]):
            if edge is None:
                continue
            if 0.0 < edge < 1.0 and all(abs(edge - e) > 1e-12 for e in eta):
                eta = np.sort(np.append(eta, float(edge)))

    # Final safety de-dup/round (covers union of windows and floating noise)
    eta = np.unique(np.round(eta.astype(float), 12))
    n_sections = len(eta)

    # Recompute distributions to length n_sections
    if chord_override is not None:
        chords = np.asarray(chord_override, dtype=float)
        if len(chords) != n_sections_w:
            raise ValueError("chord_override must have length n_sections_w.")
        chords = np.interp(eta, np.linspace(0, 1, len(chords)), chords)
    else:
        res = _chords_from_area_or_taper(
            span=span, n_sections=n_sections, area=area, AR=AR,
            c_root=c_root, c_tip=c_tip, taper=taper,
        )
        chords = res[0]

    twist_arr   = _as_array(twist, n_sections)
    airfoil_arr = _airfoil_blend_array(airfoil_root, airfoil_tip, n_sections)

    # station axes (recomputed with new eta)
    y_local = (span / 2) * eta
    sweep_rad = np.deg2rad(sweep_le)
    dihedral_rad = np.deg2rad(dihedral)
    x_local = y_local * np.tan(sweep_rad)
    z_local = y_local * np.tan(dihedral_rad)

    def _boundary_flags(win):
        flags = [False] * n_sections
        if not _valid_window(win):
            return flags
        seg_mid_eta = (eta[:-1] + eta[1:]) / 2.0
        seg_active  = (seg_mid_eta >= win[0]) & (seg_mid_eta < win[1])
        for i in range(n_sections - 1):
            enter_run = seg_active[i] and (i == 0 or not seg_active[i - 1])
            leave_run = seg_active[i] and (i == len(seg_active) - 1 or not seg_active[i + 1])
            if enter_run:
                flags[i] = True
            if leave_run:
                flags[i + 1] = True
        return flags

    boundary_ail = _boundary_flags(e_ail)
    boundary_flp = _boundary_flags(e_flp)

    # ---- build x-sections (single append per station)
    EPS = 1e-12
    xsecs = []
    for i in range(n_sections):
        controls = []

        # Aileron
        if has_ail:
            in_window_ail = (e_ail[0] - EPS <= eta[i] <= e_ail[1] + EPS)
            if in_window_ail or boundary_ail[i]:
                if not any(getattr(c, "name", "") == str(control_surface_name) for c in controls):
                    controls.append(asb.ControlSurface(
                        name=str(control_surface_name),
                        symmetric=bool(control_surface_is_symmetric),
                        deflection=0.0,  # geometry deflection stays 0; set at run-time
                        hinge_point=(0.75 if control_hinge_point is None else float(control_hinge_point)),
                    ))

        # Flap
        if has_flp:
            in_window_flp = (e_flp[0] - EPS <= eta[i] <= e_flp[1] + EPS)
            if in_window_flp or boundary_flp[i]:
                if not any(getattr(c, "name", "") == "flap" for c in controls):
                    controls.append(asb.ControlSurface(
                        name="flap",
                        symmetric=bool(flap_is_symmetric),
                        deflection=0.0,  # geometry deflection stays 0; set at run-time
                        hinge_point=(0.75 if hinge_point_flap is None else float(hinge_point_flap)),
                    ))

        xsecs.append(asb.WingXSec(
            xyz_le=[x_local[i], y_local[i], z_local[i]],
            chord=float(chords[i]),
            twist=float(twist_arr[i]),
            airfoil=airfoil_arr[i],
            control_surfaces=controls,
        ))

    wing = asb.Wing(
        name=name,
        xyz_le=[0.0, 0.0, 0.0],
        symmetric=bool(symmetric),
        xsecs=xsecs,
        n_chordwise=n_chordwise_w,
        chordwise_spacing=chordwise_spacing_w,
        n_spanwise=n_spanwise_w,
        spanwise_spacing=spanwise_spacing_w,
    )
    wing = _place(wing, [x_le_root, y_le_root, z_le_root])
    return wing



def make_ht(
    name: str,
    span: float | None,                 # allow None if (area, AR, taper) infers span
    n_sections_ht: int,
    n_chordwise_ht=8,
    chordwise_spacing_ht="cosine",
    n_spanwise_ht=21,
    spanwise_spacing_ht="cosine",
    *,
    x_le: float, y_le: float, z_le: float,
    area: float | None = None,
    AR: float | None = None,
    c_root: float | None = None,
    c_tip: float | None = None,
    taper: float | None = 0.8,
    sweep_le: float = 0.0,
    dihedral: float = 0.0,
    twist = 0.0,
    airfoil_root: asb.Airfoil | None = None,
    airfoil_tip:  asb.Airfoil | None = None,
    span_frac_elevator: tuple[float, float] | None = (0.20, 0.95),
    delta_elevator: float | None = 0.0,
    hinge_point_elevator: float | None = 0.75,  
    return_metrics: bool = False # return fully-specified planform metrics
):
    """
    Horizontal tail with a named 'elevator' control (symmetric on both halves).
    Wrapper around `make_wing` that accepts any uniquely-determining planform combo.
    When return_metrics=True, returns (wing, metrics_dict).
    """
    # Solve planform from any valid combo:
    solve = _chords_from_area_or_taper(
        span=span,
        n_sections=n_sections_ht,
        area=area,
        AR=AR,
        c_root=c_root,
        c_tip=c_tip,
        taper=taper,
    )

    wing = make_wing(
        name=name,
        span=float(solve.b),
        n_sections_w=n_sections_ht,
        n_chordwise_w=n_chordwise_ht,
        chordwise_spacing_w=chordwise_spacing_ht,
        n_spanwise_w=n_spanwise_ht,
        spanwise_spacing_w=spanwise_spacing_ht,
        symmetric=True,
        chord_override=solve.chords,    # <— use solved chords
        sweep_le=sweep_le,
        dihedral=dihedral,
        x_le_root=x_le, y_le_root=y_le, z_le_root=z_le,
        twist=twist,
        airfoil_root=airfoil_root, airfoil_tip=airfoil_tip,
        control_surface_name=("elevator" if span_frac_elevator is not None else None),
        control_surface_is_symmetric=True,
        control_surface_deflection=(0.0 if delta_elevator is None else float(delta_elevator)),
        control_surface_span_fraction=(span_frac_elevator or (0.0, 0.0)),
        control_hinge_point=hinge_point_elevator,
    )

    if return_metrics:
        metrics = dict(
            b=float(solve.b),
            S=float(solve.S),
            AR=float(solve.AR),
            lam=float(solve.lam),
            c_root=float(solve.c_root),
            c_tip=float(solve.c_tip),
            MAC=float(solve.MAC),
        )
        return wing, metrics

    return wing



def _rotate_wing_about_x(wing: asb.Wing, angle_deg: float) -> asb.Wing:
    """Rigid-rotate a Wing about the body X axis by angle_deg (degrees)."""
    ang = np.deg2rad(angle_deg)
    c = float(np.cos(ang)); s = float(np.sin(ang))
    w = wing.copy()
    # rotate each section LE; twist is about local x and remains valid
    for xs in w.xsecs:
        x, y, z = xs.xyz_le
        y2 =  y * c - z * s
        z2 =  y * s + z * c
        xs.xyz_le = [float(x), float(y2), float(z2)]
    return w

def make_vt(
    name: str,
    span: float | None,
    n_sections_vt: int,
    n_chordwise_vt=8,
    chordwise_spacing_vt="cosine",
    n_spanwise_vt=15,
    spanwise_spacing_vt="cosine",
    *,
    x_le: float, y_le: float, z_le: float,
    area: float | None = None,
    AR: float | None = None,
    c_root: float | None = None,
    c_tip: float | None = None,
    taper: float | None = 0.9,
    sweep_le: float = 25.0,     # desired sweep in x–z after rotation
    cant: float = 0.0,          # optional extra cant after rotation
    twist = 0.0,
    airfoil_root: asb.Airfoil | None = None,
    airfoil_tip:  asb.Airfoil | None = None,
    span_frac_rudder: tuple[float, float] | None = (0.20, 0.95),
    delta_rudder: float | None = 0.0,
    hinge_point_rudder: float | None = 0.75,
    return_metrics: bool = False,
):
    """
    Build the vertical tail by:
      1) Building a *wing* in the Y-span frame (re-using make_wing, which already handles
         control-edge section insertion perfectly).
      2) Rotating the finished wing +90° about X so span points along +Z.
      3) Optionally applying an extra 'cant' about X.
      4) Translating once to (x_le, y_le, z_le).
    """
    if n_sections_vt < 2:
        raise ValueError("n_sections_vt must be >= 2.")

    # Solve a baseline planform (root/tip chords, MAC, etc.) for the *wing* frame
    solve = _chords_from_area_or_taper(
        span=span, n_sections=n_sections_vt, area=area, AR=AR,
        c_root=c_root, c_tip=c_tip, taper=taper,
    )

    # 1) Build as a standard wing (span in Y), re-using the working wing path
    w_y = make_wing(
        name=name,
        span=float(solve.b *2),                 
        n_sections_w=n_sections_vt,
        n_chordwise_w=n_chordwise_vt,
        chordwise_spacing_w=chordwise_spacing_vt,
        n_spanwise_w=n_spanwise_vt,
        spanwise_spacing_w=spanwise_spacing_vt,
        symmetric=False,                     # single fin
        chord_override=solve.chords,         # keep chords consistent
        sweep_le=sweep_le,                   # sweep in x–y (becomes x–z after rotation)
        dihedral=0.0,                        # keep flat in x–y; we’ll rotate to vertical
        x_le_root=0.0, y_le_root=0.0, z_le_root=0.0,  # build at origin first
        twist=twist,
        airfoil_root=airfoil_root, airfoil_tip=airfoil_tip,
        control_surface_name=("rudder" if span_frac_rudder is not None else None),
        control_surface_is_symmetric=True,   # deflection same sign on that single surface
        control_surface_deflection=(0.0 if delta_rudder is None else float(delta_rudder)),
        control_surface_span_fraction=(span_frac_rudder or (0.0, 0.0)),
        control_hinge_point=hinge_point_rudder,
    )

    # 2) Rotate +90° about X: Y->Z (vertical fin). This preserves the straight LE.
    w_z = _rotate_wing_about_x(w_y, +90.0)

    # 3) Optional extra cant about X (e.g., tip leaning left/right)
    if abs(cant) > 1e-12:
        w_z = _rotate_wing_about_x(w_z, float(cant))

    # 4) Translate once to the requested root LE position
    vt = _place(w_z, [x_le, y_le, z_le])

    if return_metrics:
        metrics = dict(
            b=float(solve.b),
            S=float(solve.S),
            AR=float(solve.AR),
            lam=float(solve.lam),
            c_root=float(solve.c_root),
            c_tip=float(solve.c_tip),
            MAC=float(solve.MAC),
        )
        return vt, metrics

    return vt



def _resolve_wing_planform(b, S=None, AR=None, taper=1.0):
    """
    Resolve (S, AR, c_root, c_tip, MAC) from span b and either S or AR plus taper.
    """
    if S is None and AR is None:
        raise ValueError("Provide either wing area S or aspect ratio AR.")
    if S is None:
        S = b ** 2 / AR
    else:
        AR = b ** 2 / S

    # c_root from S = b (c_root + c_tip)/2, with c_tip = λ c_root
    c_root = 2 * S / (b * (1 + taper))
    c_tip = taper * c_root
    # Mean aerodynamic chord for a linear-taper wing
    MAC = (2 / 3) * c_root * (1 + taper + taper ** 2) / (1 + taper)
    return dict(S=S, AR=AR, c_root=c_root, c_tip=c_tip, MAC=MAC)


def simple_aircraft(
    # ---- global / layout ----
    name: str = "Simple Aircraft",
    xyz_ref = (0.0, 0.0, 0.0),      # CG location (x,y,z) [m]

    # ---- main wing: any valid combo of these is OK ----
    b_w: float = None,                # total wingspan [m]
    S_w: float | None = None,        # wing area [m^2] (optional if AR_w is given)
    AR_w: float | None = None,        # aspect ratio (optional if S_w is given)
    lambda_w: float = None,
    c_root_w: float | None = None,
    c_tip_w: float | None = None,
    gamma_LE_w: float = 0.0,
    dihedral_w: float = 0.0,
    nsec_w: int = 2,
    n_chordwise_w=12,
    chordwise_spacing_w="cosine",
    n_spanwise_w=36,
    spanwise_spacing_w="cosine",
    twist_w = 0.0,               # scalar, (root,tip), or array(nsec_w)
    x_LE_w: float = 0.0, y_LE_w: float = 0.0, z_LE_w: float = 0.0,
    airfoil_root_w: asb.Airfoil | None = None,
    airfoil_tip_w:  asb.Airfoil | None = None,
    # ---------- Ailerons ---
    span_frac_aileron = None,
    delta_aileron: float | None = 0.0,
    hinge_point_aileron: float | None = 0.75,
    hinge_axis_aileron = (0.0, 1.0, 0.0),
    # ---------- Flaps ---
    span_frac_flap = None,        # e.g. (0.15, 0.60)
    delta_flap: float | None = 0.0,
    hinge_point_flap: float | None = 0.75,
    flap_is_symmetric: bool = True,

    # ---- horizontal tail ----
    L_ht: float = None,               # OPTIONAL: tail moment arm from wing LE at root to HT LE [m] (can also define via x_LE_ht)
    S_ht: float | None = None,       # optional direct override [m^2]
    AR_ht: float = None,
    lambda_ht: float = None,
    c_root_ht: float | None = None,   
    c_tip_ht:  float | None = None,   
    b_ht: float | None = None,        
    gamma_LE_ht: float = 0.0,
    dihedral_ht: float = 0.0,
    nsec_ht: int = 2,
    n_chordwise_ht=12,
    chordwise_spacing_ht="cosine",
    n_spanwise_ht=36,
    spanwise_spacing_ht="cosine",
    twist_ht = None,
    x_LE_ht: float = None,          # forward/aft placement of HT LE
    y_LE_ht: float = None,            # left/right placement of HT LE
    z_LE_ht: float = None,            # vertical placement of HT LE
    airfoil_root_ht: asb.Airfoil | None = None,
    airfoil_tip_ht:  asb.Airfoil | None = None,
    # ---------- Elevator ---
    span_frac_elevator = (0.2, 0.95),
    delta_elevator: float | None = 0.0,
    hinge_point_elevator: float | None = 0.75,
    hinge_axis_elevator = (0.0, 1.0, 0.0),

    # ---- vertical tail ----
    L_vt: float | None = None,       # if None, uses L_ht, or x_LE_vt if given
    S_vt: float | None = None,       # optional direct override [m^2]
    AR_vt: float = None,
    lambda_vt: float = None,
    c_root_vt: float | None = None,   
    c_tip_vt:  float | None = None,   
    b_vt: float | None = None,        
    gamma_LE_vt: float = 0.0,
    nsec_vt: int = 2,
    n_chordwise_vt=12,
    chordwise_spacing_vt="cosine",
    n_spanwise_vt=36,
    spanwise_spacing_vt="cosine",
    twist_vt = 0.0,
    x_LE_vt: float = None,          # forward/aft placement of VT LE
    y_LE_vt: float = None,            # left/right placement of VT LE
    z_LE_vt: float = None,            # vertical placement of VT LE
    airfoil_root_vt: asb.Airfoil | None = None,
    airfoil_tip_vt:  asb.Airfoil | None = None,
    # ---------- Rudder ---
    span_frac_rudder = (0.2, 0.95),
    delta_rudder: float | None = 0.0,
    hinge_point_rudder: float | None = 0.75,
    hinge_axis_rudder   = (0.0, 0.0, 1.0),

    # ---- fuselage (very simple parametric body; optional) ----
    make_simple_fuselage: bool = False,
    L_fuse: float = 0.9 * 0 + 3.0,     # avoid “unused var” lint: expression keeps number visible
    rad_fuse_max: float = 0.12,
    fuse_camper = (0.0, 0.0),               # (x,z) linear camber of fuselage centerline from nose->tail
    nsec_fuse: int = 21,
    x_fuse_nose: float = 0.0,
    y_fuse_nose: float = 0.0,
    z_fuse_nose: float = 0.0,

    # ---- returns ----
    return_parts: bool = False,
):
    """
    Build an AeroSandbox Airplane from conceptual-design parameters.

    - Main wing, HT, and VT planforms can each be defined by ANY uniquely-determining
    combo among {S, AR, lambda, c_root, c_tip, b}. (gamma_LE/dihedral/cant control placement only.)
    - HT/VT placement can be given either as absolute x_LE_* (and/or y,z) or via
    a moment arm L_ht / L_vt relative to the wing root LE (x_LE_w).
    """


    # ---- Helpers
    def _coalesce(*vals):
        """Return the first value that is not None."""
        for v in vals:
            if v is not None:
                return v
        return None
     

    def _has_unique_planform_spec(*, span, area, AR, c_root, c_tip, taper) -> bool:
        """
        Return True iff exactly one valid trapezoid planform spec is provided.
        Mirrors the accepted patterns in _chords_from_area_or_taper().
        """
        has = dict(
            span = span is not None,
            area = area is not None,
            AR   = AR   is not None,
            cr   = c_root is not None,
            ct   = c_tip  is not None,
            lam  = taper  is not None,
        )
        provided = {k for k, v in has.items() if v}

        spec_sets = [
            {"cr", "ct", "span"},
            {"cr", "lam", "span"},
            {"ct", "lam", "span"},
            {"area", "span", "lam"},
            {"AR", "span", "lam"},
            {"area", "AR", "lam"},   # span is inferred
            {"area", "span", "cr"},
            {"area", "span", "ct"},
        ]
        matches = sum(provided == s for s in spec_sets)
        return matches == 1
    

    def _tag_hinge_axes(wing):
        for xs in getattr(wing, "xsecs", []):
            for cs in getattr(xs, "control_surfaces", []):
                n = str(getattr(cs, "name", "")).lower()
                if "aileron" in n:
                    cs._avl_hinge_axis = hinge_axis_aileron
                elif "flap" in n:
                    cs._avl_hinge_axis = (0.0, 1.0, 0.0)  # TE flap: hinge about +y
                elif "elevator" in n:
                    cs._avl_hinge_axis = hinge_axis_elevator
                elif "rudder" in n:
                    cs._avl_hinge_axis = hinge_axis_rudder
                else:
                    # Safe default for trailing-edge flaps on wings/tails
                    cs._avl_hinge_axis = (0.0, 1.0, 0.0)


    # ------------------------
    # Decide which components are enabled from specs
    # ------------------------
    wing_enabled = _has_unique_planform_spec(
        span=b_w, area=S_w, AR=AR_w, c_root=c_root_w, c_tip=c_tip_w, taper=lambda_w
    )
    ht_enabled = _has_unique_planform_spec(
        span=b_ht, area=S_ht, AR=AR_ht, c_root=c_root_ht, c_tip=c_tip_ht, taper=lambda_ht
    )
    vt_enabled = _has_unique_planform_spec(
        span=b_vt, area=S_vt, AR=AR_vt, c_root=c_root_vt, c_tip=c_tip_vt, taper=lambda_vt
    )

    # ------------------------
    # Default airfoils only if component will be built
    # ------------------------
    if wing_enabled:
        airfoil_root_w = _coerce_airfoil(airfoil_root_w) or asb.Airfoil("naca2412")
        airfoil_tip_w  = _coerce_airfoil(airfoil_tip_w)  or airfoil_root_w

    if ht_enabled:
        airfoil_root_ht = _coerce_airfoil(airfoil_root_ht) or asb.Airfoil("naca0010")
        airfoil_tip_ht  = _coerce_airfoil(airfoil_tip_ht)  or airfoil_root_ht

    if vt_enabled:
        # if HT not present, fall back to 0010 root
        fallback_ht_root = airfoil_root_ht if ht_enabled else asb.Airfoil("naca0010")
        airfoil_root_vt = _coerce_airfoil(airfoil_root_vt) or fallback_ht_root
        airfoil_tip_vt  = _coerce_airfoil(airfoil_tip_vt)  or airfoil_root_vt

    # ------------------------
    # Build components conditionally
    # ------------------------
    wings = []
    parts = {}
    wing_planform = ht_planform = vt_planform = None

    # ---------- Main Wing ----------
    if wing_enabled:
        solve_w = _chords_from_area_or_taper(
            span=b_w, n_sections=nsec_w, area=S_w, AR=AR_w,
            c_root=c_root_w, c_tip=c_tip_w, taper=lambda_w,
        )
        chords_w  = solve_w.chords
        b_w       = float(solve_w.b)
        S_w       = float(solve_w.S)
        AR_w      = float(solve_w.AR)
        lambda_w  = float(solve_w.lam)
        c_root_w  = float(solve_w.c_root)
        c_tip_w   = float(solve_w.c_tip)
        MAC_w     = float(solve_w.MAC)

        main_wing = make_wing(
            name="Main Wing",
            span=b_w,
            n_sections_w=nsec_w,
            n_chordwise_w=n_chordwise_w,
            chordwise_spacing_w=chordwise_spacing_w,
            n_spanwise_w=n_spanwise_w,
            spanwise_spacing_w=spanwise_spacing_w,
            symmetric=True,
            chord_override=chords_w,
            sweep_le=gamma_LE_w,
            dihedral=dihedral_w,
            x_le_root=x_LE_w, y_le_root=y_LE_w, z_le_root=z_LE_w,
            twist=twist_w,
            airfoil_root=airfoil_root_w,
            airfoil_tip=airfoil_tip_w,
            control_surface_name=("aileron" if span_frac_aileron is not None else None),
            control_surface_is_symmetric=False,
            control_surface_deflection=(0.0 if delta_aileron is None else float(delta_aileron)),
            control_surface_span_fraction=(span_frac_aileron or (0.0, 0.0)),
            control_hinge_point=hinge_point_aileron,
            span_frac_flap=span_frac_flap,
            delta_flap=(0.0 if delta_flap is None else float(delta_flap)),
            hinge_point_flap=hinge_point_flap,
            flap_is_symmetric=flap_is_symmetric,
        )
        wings.append(main_wing)

        wing_planform = dict(
            b=b_w, S=S_w, AR=AR_w, lam=lambda_w,
            c_root=c_root_w, c_tip=c_tip_w, MAC=MAC_w,
            sweep_le_deg=gamma_LE_w, dihedral_deg=dihedral_w,
            xyz_le_root=(x_LE_w, y_LE_w, z_LE_w),
            n_sections=nsec_w,
        )
        parts["main_wing"] = main_wing
        parts.update(dict(S_w=S_w, AR_w=AR_w, c_root_w=c_root_w, c_tip_w=c_tip_w, MAC_w=MAC_w))

        _tag_hinge_axes(main_wing) # add control surface hinge rotation vector defaults


    # ---------- Horizontal Tail ----------
    if ht_enabled:
        x_ht = _coalesce(x_LE_ht, (x_LE_w + (L_ht or 0.0)))
        y_ht = _coalesce(y_LE_ht, y_LE_w)
        z_ht = _coalesce(z_LE_ht, z_LE_w)

        ht, ht_metrics = make_ht(
            name="Horizontal Stabilizer",
            span=b_ht,
            n_sections_ht=nsec_ht,
            n_chordwise_ht=n_chordwise_ht,
            chordwise_spacing_ht=chordwise_spacing_ht,
            n_spanwise_ht=n_spanwise_ht,
            spanwise_spacing_ht=spanwise_spacing_ht,
            x_le=float(x_ht), y_le=float(y_ht), z_le=float(z_ht),
            area=S_ht, AR=AR_ht, c_root=c_root_ht, c_tip=c_tip_ht, taper=lambda_ht,
            sweep_le=gamma_LE_ht,
            dihedral=dihedral_ht,
            twist=twist_ht,
            airfoil_root=airfoil_root_ht,
            airfoil_tip=airfoil_tip_ht,
            span_frac_elevator=span_frac_elevator,
            delta_elevator=(0.0 if delta_elevator is None else float(delta_elevator)),
            hinge_point_elevator=hinge_point_elevator,
            return_metrics=True,
        )
        wings.append(ht)
        parts["horizontal_tail"] = ht
        ht_planform = dict(
            **ht_metrics,
            sweep_le_deg=gamma_LE_ht, dihedral_deg=dihedral_ht,
            xyz_le_root=(float(x_ht), float(y_ht), float(z_ht)),
            n_sections=nsec_ht,
        )
        parts.update(dict(b_ht=ht_metrics["b"], S_ht=ht_metrics["S"]))

        _tag_hinge_axes(ht) # add control surface hinge rotation vector defaults


    # ---------- Vertical Tail ----------
    if vt_enabled:
        L_vt_eff = _coalesce(L_vt, L_ht, 0.0)
        x_vt = _coalesce(x_LE_vt, (x_LE_w + L_vt_eff))
        y_vt = _coalesce(y_LE_vt, y_LE_w)
        z_vt = _coalesce(z_LE_vt, z_LE_w)

        vt, vt_metrics = make_vt(
            name="Vertical Stabilizer",
            span=b_vt,
            n_sections_vt=nsec_vt,
            n_chordwise_vt=n_chordwise_vt,
            chordwise_spacing_vt=chordwise_spacing_vt,
            n_spanwise_vt=n_spanwise_vt,
            spanwise_spacing_vt=spanwise_spacing_vt,
            x_le=float(x_vt), y_le=float(y_vt), z_le=float(z_vt),
            area=S_vt, AR=AR_vt, c_root=c_root_vt, c_tip=c_tip_vt, taper=lambda_vt,
            sweep_le=gamma_LE_vt,
            cant=0.0,
            twist=twist_vt,
            airfoil_root=airfoil_root_vt,
            airfoil_tip=airfoil_tip_vt,
            span_frac_rudder=span_frac_rudder,
            delta_rudder=(0.0 if delta_rudder is None else float(delta_rudder)),
            hinge_point_rudder=hinge_point_rudder,
            return_metrics=True,
        )
        wings.append(vt)
        parts["vertical_tail"] = vt
        vt_planform = dict(
            **vt_metrics,
            sweep_le_deg=gamma_LE_vt, cant_deg=0.0,
            xyz_le_root=(float(x_vt), float(y_vt), float(z_vt)),
            n_sections=nsec_vt,
        )
        parts.update(dict(b_vt=vt_metrics["b"], S_vt=vt_metrics["S"]))

        _tag_hinge_axes(vt) # add control surface hinge rotation vector defaults


    # ---------- Optional fuselage ----------
    fuselages = []
    if make_simple_fuselage:
        xi = np.linspace(0, 1, nsec_fuse)
        cam_x = np.linspace(0.0, L_fuse, nsec_fuse)
        cam_z = np.linspace(fuse_camper[0], fuse_camper[1], nsec_fuse)
        radius = rad_fuse_max * (1 - (2 * (xi - 0.5))**2) ** 0.6
        fus = asb.Fuselage(
            name="Fuselage",
            xsecs=[
                asb.FuselageXSec(
                    xyz_c=[cam_x[i], 0.0, cam_z[i]],
                    radius=float(max(radius[i], 1e-4)),
                )
                for i in range(nsec_fuse)
            ],
        ).translate([x_fuse_nose, y_fuse_nose, z_fuse_nose])
        fuselages = [fus]

    airplane = asb.Airplane(
        name=name,
        xyz_ref=list(xyz_ref),
        wings=wings,               # <-- only what we actually built
        fuselages=fuselages,
    )

    if return_parts:
        ret = dict()
        if "main_wing" in parts:            ret["main_wing"] = parts["main_wing"]
        if "horizontal_tail" in parts:      ret["horizontal_tail"] = parts["horizontal_tail"]
        if "vertical_tail" in parts:        ret["vertical_tail"] = parts["vertical_tail"]
        if wing_planform is not None:       ret["wing_planform"] = wing_planform
        if ht_planform is not None:         ret["ht_planform"] = ht_planform
        if vt_planform is not None:         ret["vt_planform"] = vt_planform
        # legacy convenience keys if wing/HT/VT exist:
        if "S_w" in parts:                  ret.update(dict(S_w=parts["S_w"], AR_w=parts["AR_w"],
                                                           c_root_w=parts["c_root_w"], c_tip_w=parts["c_tip_w"],
                                                           MAC_w=parts["MAC_w"]))
        if "b_ht" in parts:                 ret["b_ht"] = parts["b_ht"]
        if "S_ht" in parts:                 ret["S_ht"] = parts["S_ht"]
        if "b_vt" in parts:                 ret["b_vt"] = parts["b_vt"]
        if "S_vt" in parts:                 ret["S_vt"] = parts["S_vt"]
        return airplane, ret

    return airplane

