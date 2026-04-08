"""Private shared helpers for geometry construction."""

from __future__ import annotations

import aerosandbox as asb
import aerosandbox.numpy as np

from ac_design_toolbox.geometry.types import PlanformSolve


def _as_array(value, n, default=None):
    """Normalize a parameter into an array of length ``n``."""
    if value is None:
        value = 0.0 if default is None else default

    if np.isscalar(value):
        return np.full(n, float(value))

    value = np.asarray(value, dtype=float)
    if value.ndim == 1 and value.size == 2:
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
    """Accept an AeroSandbox airfoil object, a NACA string, or ``None``."""
    if isinstance(a, asb.Airfoil):
        return a
    if isinstance(a, str):
        return asb.Airfoil(a)
    return a


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
    """Solve trapezoidal planform geometry and return chord distribution data."""
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
        "cr_ct_span": {"cr", "ct", "span"},
        "cr_lam_span": {"cr", "lam", "span"},
        "ct_lam_span": {"ct", "lam", "span"},
        "area_span_lam": {"area", "span", "lam"},
        "AR_span_lam": {"AR", "span", "lam"},
        "area_AR_lam": {"area", "AR", "lam"},
        "area_span_cr": {"area", "span", "cr"},
        "area_span_ct": {"area", "span", "ct"},
    }

    patterns = {name: (provided_keys == req) for name, req in spec_sets.items()}
    n_true = sum(patterns.values())

    if n_true > 1:
        active = [k for k, v in patterns.items() if v]
        raise ValueError(f"Overspecified planform: matches multiple spec sets {active}. Provide exactly one valid set.")

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

        provided = {
            k: v
            for k, v in dict(span=span, area=area, AR=AR, c_root=c_root, c_tip=c_tip, taper=taper).items()
            if v is not None
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

    if patterns["cr_ct_span"]:
        cr, ct = float(c_root), float(c_tip)
        b = float(span)
    elif patterns["cr_lam_span"]:
        cr = float(c_root)
        lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (lambda) must be > 0.")
        ct = lam * cr
        b = float(span)
    elif patterns["ct_lam_span"]:
        ct = float(c_tip)
        lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (lambda) must be > 0.")
        cr = ct / lam
        b = float(span)
    elif patterns["area_span_lam"]:
        S = float(area)
        b = float(span)
        lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (lambda) must be > 0.")
        cr = 2 * S / (b * (1 + lam))
        ct = lam * cr
    elif patterns["AR_span_lam"]:
        ARv = float(AR)
        b = float(span)
        S = b**2 / ARv
        lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (lambda) must be > 0.")
        cr = 2 * S / (b * (1 + lam))
        ct = lam * cr
    elif patterns["area_AR_lam"]:
        S = float(area)
        ARv = float(AR)
        b = (ARv * S) ** 0.5
        lam = float(taper)
        if lam <= 0:
            raise ValueError("taper (lambda) must be > 0.")
        cr = 2 * S / (b * (1 + lam))
        ct = lam * cr
    elif patterns["area_span_cr"]:
        S = float(area)
        b = float(span)
        cr = float(c_root)
        ct = 2 * S / b - cr
        if ct <= 0:
            raise ValueError("In (area, span, c_root), the implied c_tip <= 0. Check inputs.")
    elif patterns["area_span_ct"]:
        S = float(area)
        b = float(span)
        ct = float(c_tip)
        cr = 2 * S / b - ct
        if cr <= 0:
            raise ValueError("In (area, span, c_tip), the implied c_root <= 0. Check inputs.")
    else:
        raise RuntimeError("Internal pattern selection error.")

    if cr <= 0 or ct <= 0 or b <= 0:
        raise ValueError("All solved quantities must be positive (c_root, c_tip, span).")

    lam = ct / cr
    S = 0.5 * b * (cr + ct)
    ARv = b**2 / S
    MAC = (2 / 3) * cr * (1 + lam + lam**2) / (1 + lam)
    eta = np.linspace(0, 1, n_sections)
    chords = cr + (ct - cr) * eta

    return PlanformSolve(chords=chords, c_root=cr, c_tip=ct, b=b, S=S, AR=ARv, lam=lam, MAC=MAC)


def _airfoil_blend_array(airfoil_root, airfoil_tip=None, n_sections=2, airfoils=None):
    """Create an airfoil array along the span."""
    if airfoils is not None:
        if len(airfoils) != n_sections:
            raise ValueError("Length of 'airfoils' must equal n_sections.")
        return airfoils

    if (airfoil_tip is None) or (airfoil_tip == airfoil_root):
        return [airfoil_root for _ in range(n_sections)]

    arr = [airfoil_root for _ in range(n_sections)]
    arr[-1] = airfoil_tip
    return arr


def _place(surface: asb.Wing, xyz_le):
    """Translate a surface built at the origin to a target leading-edge location."""
    return surface.translate([float(xyz_le[0]), float(xyz_le[1]), float(xyz_le[2])])


def _augmented_eta(n_base: int, breaks: tuple[float, float] | None):
    """Return section stations that include exact control-edge breakpoints."""
    base = list(np.linspace(0.0, 1.0, n_base))
    if breaks is None:
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
    return np.unique(np.round(eta, 12))


def _rotate_wing_about_x(wing: asb.Wing, angle_deg: float) -> asb.Wing:
    """Rigid-rotate a wing about the body X axis by ``angle_deg`` degrees."""
    ang = np.deg2rad(angle_deg)
    c = float(np.cos(ang))
    s = float(np.sin(ang))
    rotated = wing.copy()
    for xs in rotated.xsecs:
        x, y, z = xs.xyz_le
        y2 = y * c - z * s
        z2 = y * s + z * c
        xs.xyz_le = [float(x), float(y2), float(z2)]
    return rotated


def _resolve_wing_planform(b, S=None, AR=None, taper=1.0):
    """Resolve trapezoidal wing planform metrics from span plus area or AR."""
    if S is None and AR is None:
        raise ValueError("Provide either wing area S or aspect ratio AR.")
    if S is None:
        S = b**2 / AR
    else:
        AR = b**2 / S

    c_root = 2 * S / (b * (1 + taper))
    c_tip = taper * c_root
    MAC = (2 / 3) * c_root * (1 + taper + taper**2) / (1 + taper)
    return dict(S=S, AR=AR, c_root=c_root, c_tip=c_tip, MAC=MAC)
