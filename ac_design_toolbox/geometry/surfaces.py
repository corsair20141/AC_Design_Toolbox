"""Surface-construction helpers for wings and tail surfaces."""

import aerosandbox as asb
import aerosandbox.numpy as np

from ac_design_toolbox.geometry._common import (
    _airfoil_blend_array,
    _as_array,
    _augmented_eta,
    _chords_from_area_or_taper,
    _place,
    _rotate_wing_about_x,
)


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
    area: float = None,
    AR: float = None,
    c_root: float = None,
    c_tip: float = None,
    taper: float = None,
    sweep_le=0.0,
    dihedral=0.0,
    x_le_root=0.0,
    y_le_root=0.0,
    z_le_root=0.0,
    twist=0.0,
    chord_override=None,
    airfoil_root: asb.Airfoil = None,
    airfoil_tip: asb.Airfoil = None,
    airfoils=None,
    control_surface_name: str | None = None,
    control_surface_is_symmetric: bool | None = None,
    control_surface_deflection: float | None = None,
    control_surface_span_fraction: tuple[float, float] = (0.0, 0.0),
    control_hinge_point: float | None = 0.75,
    control_surface_specs: list[dict] | None = None,
    span_frac_flap: tuple[float, float] | None = None,
    delta_flap: float | None = 0.0,
    hinge_point_flap: float | None = 0.75,
    flap_is_symmetric: bool = True,
):
    """Build a generic wing component with robust control-surface placement."""
    if n_sections_w < 2:
        raise ValueError("n_sections must be >= 2 (root + at least one more station).")

    if chord_override is not None:
        chords = np.asarray(chord_override, dtype=float)
        if len(chords) != n_sections_w:
            raise ValueError("chord_override must have length n_sections_w.")
    else:
        res = _chords_from_area_or_taper(
            span=span, n_sections=n_sections_w, area=area, AR=AR, c_root=c_root, c_tip=c_tip, taper=taper
        )
        chords = res[0]

    twist_arr = _as_array(twist, n_sections_w)
    airfoil_arr = _airfoil_blend_array(airfoil_root, airfoil_tip, n_sections_w, airfoils)

    def _valid_window(window):
        return (
            window is not None
            and len(window) == 2
            and (window[0] is not None)
            and (window[1] is not None)
            and (window[1] > window[0])
        )

    controls_to_place: list[dict] = []
    if control_surface_specs:
        controls_to_place.extend([dict(spec) for spec in control_surface_specs])
    elif control_surface_name is not None:
        controls_to_place.append(
            {
                "name": str(control_surface_name),
                "symmetric": bool(control_surface_is_symmetric),
                "deflection": 0.0 if control_surface_deflection is None else float(control_surface_deflection),
                "hinge_point": 0.75 if control_hinge_point is None else float(control_hinge_point),
                "span_fraction": control_surface_span_fraction,
            }
        )

    if span_frac_flap is not None:
        controls_to_place.append(
            {
                "name": "flap",
                "symmetric": bool(flap_is_symmetric),
                "deflection": 0.0 if delta_flap is None else float(delta_flap),
                "hinge_point": 0.75 if hinge_point_flap is None else float(hinge_point_flap),
                "span_fraction": span_frac_flap,
            }
        )

    valid_controls: list[dict] = []
    eta = _augmented_eta(n_sections_w, None)
    for control in controls_to_place:
        window = control.get("span_fraction")
        if not _valid_window(window):
            continue
        valid_controls.append(control)
        for edge in (window[0], window[1]):
            if 0.0 < float(edge) < 1.0 and all(abs(float(edge) - e) > 1e-12 for e in eta):
                eta = np.sort(np.append(eta, float(edge)))

    eta = np.unique(np.round(eta.astype(float), 12))
    n_sections = len(eta)

    if chord_override is not None:
        chords = np.asarray(chord_override, dtype=float)
        if len(chords) != n_sections_w:
            raise ValueError("chord_override must have length n_sections_w.")
        chords = np.interp(eta, np.linspace(0, 1, len(chords)), chords)
    else:
        res = _chords_from_area_or_taper(
            span=span, n_sections=n_sections, area=area, AR=AR, c_root=c_root, c_tip=c_tip, taper=taper
        )
        chords = res[0]

    twist_arr = _as_array(twist, n_sections)
    airfoil_arr = _airfoil_blend_array(airfoil_root, airfoil_tip, n_sections)

    y_local = (span / 2) * eta
    sweep_rad = np.deg2rad(sweep_le)
    dihedral_rad = np.deg2rad(dihedral)
    x_local = y_local * np.tan(sweep_rad)
    z_local = y_local * np.tan(dihedral_rad)

    def _boundary_flags(window):
        flags = [False] * n_sections
        if not _valid_window(window):
            return flags
        seg_mid_eta = (eta[:-1] + eta[1:]) / 2.0
        seg_active = (seg_mid_eta >= window[0]) & (seg_mid_eta < window[1])
        for i in range(n_sections - 1):
            enter_run = seg_active[i] and (i == 0 or not seg_active[i - 1])
            leave_run = seg_active[i] and (i == len(seg_active) - 1 or not seg_active[i + 1])
            if enter_run:
                flags[i] = True
            if leave_run:
                flags[i + 1] = True
        return flags

    control_boundary_flags = [
        _boundary_flags(control["span_fraction"])
        for control in valid_controls
    ]

    EPS = 1e-12
    xsecs = []
    for i in range(n_sections):
        controls = []

        for control, boundary_flags in zip(valid_controls, control_boundary_flags):
            window = control["span_fraction"]
            in_window = float(window[0]) - EPS <= eta[i] <= float(window[1]) + EPS
            control_name = str(control["name"])
            if in_window or boundary_flags[i]:
                if not any(getattr(c, "name", "") == control_name for c in controls):
                    controls.append(
                        asb.ControlSurface(
                            name=control_name,
                            symmetric=bool(control.get("symmetric", False)),
                            deflection=float(control.get("deflection", 0.0) or 0.0),
                            hinge_point=float(control.get("hinge_point", 0.75) or 0.75),
                        )
                    )

        xsecs.append(
            asb.WingXSec(
                xyz_le=[x_local[i], y_local[i], z_local[i]],
                chord=float(chords[i]),
                twist=float(twist_arr[i]),
                airfoil=airfoil_arr[i],
                control_surfaces=controls,
            )
        )

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
    return _place(wing, [x_le_root, y_le_root, z_le_root])


def make_ht(
    name: str,
    span: float | None,
    n_sections_ht: int,
    n_chordwise_ht=8,
    chordwise_spacing_ht="cosine",
    n_spanwise_ht=21,
    spanwise_spacing_ht="cosine",
    *,
    x_le: float,
    y_le: float,
    z_le: float,
    area: float | None = None,
    AR: float | None = None,
    c_root: float | None = None,
    c_tip: float | None = None,
    taper: float | None = 0.8,
    sweep_le: float = 0.0,
    dihedral: float = 0.0,
    twist=0.0,
    airfoil_root: asb.Airfoil | None = None,
    airfoil_tip: asb.Airfoil | None = None,
    span_frac_elevator: tuple[float, float] | None = (0.20, 0.95),
    delta_elevator: float | None = 0.0,
    hinge_point_elevator: float | None = 0.75,
    control_surface_specs: list[dict] | None = None,
    return_metrics: bool = False,
):
    """Build a horizontal tail surface with an optional elevator control."""
    solve = _chords_from_area_or_taper(
        span=span, n_sections=n_sections_ht, area=area, AR=AR, c_root=c_root, c_tip=c_tip, taper=taper
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
        chord_override=solve.chords,
        sweep_le=sweep_le,
        dihedral=dihedral,
        x_le_root=x_le,
        y_le_root=y_le,
        z_le_root=z_le,
        twist=twist,
        airfoil_root=airfoil_root,
        airfoil_tip=airfoil_tip,
        control_surface_name=("elevator" if span_frac_elevator is not None and control_surface_specs is None else None),
        control_surface_is_symmetric=True,
        control_surface_deflection=(0.0 if delta_elevator is None else float(delta_elevator)),
        control_surface_span_fraction=(span_frac_elevator or (0.0, 0.0)),
        control_hinge_point=hinge_point_elevator,
        control_surface_specs=control_surface_specs,
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


def make_vt(
    name: str,
    span: float | None,
    n_sections_vt: int,
    n_chordwise_vt=8,
    chordwise_spacing_vt="cosine",
    n_spanwise_vt=15,
    spanwise_spacing_vt="cosine",
    *,
    x_le: float,
    y_le: float,
    z_le: float,
    area: float | None = None,
    AR: float | None = None,
    c_root: float | None = None,
    c_tip: float | None = None,
    taper: float | None = 0.9,
    sweep_le: float = 25.0,
    cant: float = 0.0,
    twist=0.0,
    airfoil_root: asb.Airfoil | None = None,
    airfoil_tip: asb.Airfoil | None = None,
    span_frac_rudder: tuple[float, float] | None = (0.20, 0.95),
    delta_rudder: float | None = 0.0,
    hinge_point_rudder: float | None = 0.75,
    control_surface_specs: list[dict] | None = None,
    return_metrics: bool = False,
):
    """Build a vertical tail by constructing a wing and rotating it into place."""
    if n_sections_vt < 2:
        raise ValueError("n_sections_vt must be >= 2.")

    solve = _chords_from_area_or_taper(
        span=span, n_sections=n_sections_vt, area=area, AR=AR, c_root=c_root, c_tip=c_tip, taper=taper
    )

    w_y = make_wing(
        name=name,
        span=float(solve.b * 2),
        n_sections_w=n_sections_vt,
        n_chordwise_w=n_chordwise_vt,
        chordwise_spacing_w=chordwise_spacing_vt,
        n_spanwise_w=n_spanwise_vt,
        spanwise_spacing_w=spanwise_spacing_vt,
        symmetric=False,
        chord_override=solve.chords,
        sweep_le=sweep_le,
        dihedral=0.0,
        x_le_root=0.0,
        y_le_root=0.0,
        z_le_root=0.0,
        twist=twist,
        airfoil_root=airfoil_root,
        airfoil_tip=airfoil_tip,
        control_surface_name=("rudder" if span_frac_rudder is not None and control_surface_specs is None else None),
        control_surface_is_symmetric=True,
        control_surface_deflection=(0.0 if delta_rudder is None else float(delta_rudder)),
        control_surface_span_fraction=(span_frac_rudder or (0.0, 0.0)),
        control_hinge_point=hinge_point_rudder,
        control_surface_specs=control_surface_specs,
    )

    w_z = _rotate_wing_about_x(w_y, +90.0)
    if abs(cant) > 1e-12:
        w_z = _rotate_wing_about_x(w_z, float(cant))

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

__all__ = ["make_ht", "make_vt", "make_wing"]
