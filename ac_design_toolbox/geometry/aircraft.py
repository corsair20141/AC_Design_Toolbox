"""Aircraft assembly helpers built from the package surface constructors."""

from __future__ import annotations

import aerosandbox as asb
import aerosandbox.numpy as np

from ac_design_toolbox.geometry._common import _chords_from_area_or_taper, _coerce_airfoil
from ac_design_toolbox.geometry.surfaces import make_ht, make_vt, make_wing


def _coalesce(*values):
    """Return the first value that is not ``None``."""
    for value in values:
        if value is not None:
            return value
    return None


def _has_unique_planform_spec(*, span, area, AR, c_root, c_tip, taper) -> bool:
    """Return ``True`` when inputs match exactly one supported trapezoid spec."""
    has = dict(
        span=span is not None,
        area=area is not None,
        AR=AR is not None,
        cr=c_root is not None,
        ct=c_tip is not None,
        lam=taper is not None,
    )
    provided = {key for key, present in has.items() if present}

    spec_sets = [
        {"cr", "ct", "span"},
        {"cr", "lam", "span"},
        {"ct", "lam", "span"},
        {"area", "span", "lam"},
        {"AR", "span", "lam"},
        {"area", "AR", "lam"},
        {"area", "span", "cr"},
        {"area", "span", "ct"},
    ]
    return sum(provided == spec for spec in spec_sets) == 1


def _tag_hinge_axes(
    wing: asb.Wing,
    *,
    hinge_axis_aileron,
    hinge_axis_elevator,
    hinge_axis_rudder,
) -> None:
    """Attach AVL hinge-axis metadata to control surfaces on a wing."""
    for xsec in getattr(wing, "xsecs", []):
        for control in getattr(xsec, "control_surfaces", []):
            name = str(getattr(control, "name", "")).lower()
            if "aileron" in name:
                control._avl_hinge_axis = hinge_axis_aileron
            elif "flap" in name:
                control._avl_hinge_axis = (0.0, 1.0, 0.0)
            elif "elevator" in name:
                control._avl_hinge_axis = hinge_axis_elevator
            elif "rudder" in name:
                control._avl_hinge_axis = hinge_axis_rudder
            else:
                control._avl_hinge_axis = (0.0, 1.0, 0.0)


def simple_aircraft(
    name: str = "Simple Aircraft",
    xyz_ref=(0.0, 0.0, 0.0),
    b_w: float = None,
    S_w: float | None = None,
    AR_w: float | None = None,
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
    twist_w=0.0,
    x_LE_w: float = 0.0,
    y_LE_w: float = 0.0,
    z_LE_w: float = 0.0,
    airfoil_root_w: asb.Airfoil | None = None,
    airfoil_tip_w: asb.Airfoil | None = None,
    span_frac_aileron=None,
    delta_aileron: float | None = 0.0,
    hinge_point_aileron: float | None = 0.75,
    hinge_axis_aileron=(0.0, 1.0, 0.0),
    span_frac_flap=None,
    delta_flap: float | None = 0.0,
    hinge_point_flap: float | None = 0.75,
    flap_is_symmetric: bool = True,
    L_ht: float = None,
    S_ht: float | None = None,
    AR_ht: float = None,
    lambda_ht: float = None,
    c_root_ht: float | None = None,
    c_tip_ht: float | None = None,
    b_ht: float | None = None,
    gamma_LE_ht: float = 0.0,
    dihedral_ht: float = 0.0,
    nsec_ht: int = 2,
    n_chordwise_ht=12,
    chordwise_spacing_ht="cosine",
    n_spanwise_ht=36,
    spanwise_spacing_ht="cosine",
    twist_ht=None,
    x_LE_ht: float = None,
    y_LE_ht: float = None,
    z_LE_ht: float = None,
    airfoil_root_ht: asb.Airfoil | None = None,
    airfoil_tip_ht: asb.Airfoil | None = None,
    span_frac_elevator=(0.2, 0.95),
    delta_elevator: float | None = 0.0,
    hinge_point_elevator: float | None = 0.75,
    hinge_axis_elevator=(0.0, 1.0, 0.0),
    L_vt: float | None = None,
    S_vt: float | None = None,
    AR_vt: float = None,
    lambda_vt: float = None,
    c_root_vt: float | None = None,
    c_tip_vt: float | None = None,
    b_vt: float | None = None,
    gamma_LE_vt: float = 0.0,
    nsec_vt: int = 2,
    n_chordwise_vt=12,
    chordwise_spacing_vt="cosine",
    n_spanwise_vt=36,
    spanwise_spacing_vt="cosine",
    twist_vt=0.0,
    x_LE_vt: float = None,
    y_LE_vt: float = None,
    z_LE_vt: float = None,
    airfoil_root_vt: asb.Airfoil | None = None,
    airfoil_tip_vt: asb.Airfoil | None = None,
    span_frac_rudder=(0.2, 0.95),
    delta_rudder: float | None = 0.0,
    hinge_point_rudder: float | None = 0.75,
    hinge_axis_rudder=(0.0, 0.0, 1.0),
    make_simple_fuselage: bool = False,
    L_fuse: float = 3.0,
    rad_fuse_max: float = 0.12,
    fuse_camper=(0.0, 0.0),
    nsec_fuse: int = 21,
    x_fuse_nose: float = 0.0,
    y_fuse_nose: float = 0.0,
    z_fuse_nose: float = 0.0,
    return_parts: bool = False,
):
    """Build a simple aircraft from wing and tail planform definitions.

    Each lifting surface may be enabled by passing exactly one supported
    trapezoidal planform specification. The resulting ``Airplane`` uses
    ``xyz_ref`` as the aerodynamic reference point, typically the CG.
    """
    wing_enabled = _has_unique_planform_spec(
        span=b_w, area=S_w, AR=AR_w, c_root=c_root_w, c_tip=c_tip_w, taper=lambda_w
    )
    ht_enabled = _has_unique_planform_spec(
        span=b_ht, area=S_ht, AR=AR_ht, c_root=c_root_ht, c_tip=c_tip_ht, taper=lambda_ht
    )
    vt_enabled = _has_unique_planform_spec(
        span=b_vt, area=S_vt, AR=AR_vt, c_root=c_root_vt, c_tip=c_tip_vt, taper=lambda_vt
    )

    if wing_enabled:
        airfoil_root_w = _coerce_airfoil(airfoil_root_w) or asb.Airfoil("naca2412")
        airfoil_tip_w = _coerce_airfoil(airfoil_tip_w) or airfoil_root_w

    if ht_enabled:
        airfoil_root_ht = _coerce_airfoil(airfoil_root_ht) or asb.Airfoil("naca0010")
        airfoil_tip_ht = _coerce_airfoil(airfoil_tip_ht) or airfoil_root_ht

    if vt_enabled:
        fallback_ht_root = airfoil_root_ht if ht_enabled else asb.Airfoil("naca0010")
        airfoil_root_vt = _coerce_airfoil(airfoil_root_vt) or fallback_ht_root
        airfoil_tip_vt = _coerce_airfoil(airfoil_tip_vt) or airfoil_root_vt

    wings = []
    parts = {}
    wing_planform = ht_planform = vt_planform = None

    if wing_enabled:
        solve_w = _chords_from_area_or_taper(
            span=b_w,
            n_sections=nsec_w,
            area=S_w,
            AR=AR_w,
            c_root=c_root_w,
            c_tip=c_tip_w,
            taper=lambda_w,
        )
        chords_w = solve_w.chords
        b_w = float(solve_w.b)
        S_w = float(solve_w.S)
        AR_w = float(solve_w.AR)
        lambda_w = float(solve_w.lam)
        c_root_w = float(solve_w.c_root)
        c_tip_w = float(solve_w.c_tip)
        MAC_w = float(solve_w.MAC)

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
            x_le_root=x_LE_w,
            y_le_root=y_LE_w,
            z_le_root=z_LE_w,
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
        _tag_hinge_axes(
            main_wing,
            hinge_axis_aileron=hinge_axis_aileron,
            hinge_axis_elevator=hinge_axis_elevator,
            hinge_axis_rudder=hinge_axis_rudder,
        )
        wings.append(main_wing)

        wing_planform = dict(
            b=b_w,
            S=S_w,
            AR=AR_w,
            lam=lambda_w,
            c_root=c_root_w,
            c_tip=c_tip_w,
            MAC=MAC_w,
            sweep_le_deg=gamma_LE_w,
            dihedral_deg=dihedral_w,
            xyz_le_root=(x_LE_w, y_LE_w, z_LE_w),
            n_sections=nsec_w,
        )
        parts["main_wing"] = main_wing
        parts.update(dict(S_w=S_w, AR_w=AR_w, c_root_w=c_root_w, c_tip_w=c_tip_w, MAC_w=MAC_w))

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
            x_le=float(x_ht),
            y_le=float(y_ht),
            z_le=float(z_ht),
            area=S_ht,
            AR=AR_ht,
            c_root=c_root_ht,
            c_tip=c_tip_ht,
            taper=lambda_ht,
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
        _tag_hinge_axes(
            ht,
            hinge_axis_aileron=hinge_axis_aileron,
            hinge_axis_elevator=hinge_axis_elevator,
            hinge_axis_rudder=hinge_axis_rudder,
        )
        wings.append(ht)
        parts["horizontal_tail"] = ht
        ht_planform = dict(
            **ht_metrics,
            sweep_le_deg=gamma_LE_ht,
            dihedral_deg=dihedral_ht,
            xyz_le_root=(float(x_ht), float(y_ht), float(z_ht)),
            n_sections=nsec_ht,
        )
        parts.update(dict(b_ht=ht_metrics["b"], S_ht=ht_metrics["S"]))

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
            x_le=float(x_vt),
            y_le=float(y_vt),
            z_le=float(z_vt),
            area=S_vt,
            AR=AR_vt,
            c_root=c_root_vt,
            c_tip=c_tip_vt,
            taper=lambda_vt,
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
        _tag_hinge_axes(
            vt,
            hinge_axis_aileron=hinge_axis_aileron,
            hinge_axis_elevator=hinge_axis_elevator,
            hinge_axis_rudder=hinge_axis_rudder,
        )
        wings.append(vt)
        parts["vertical_tail"] = vt
        vt_planform = dict(
            **vt_metrics,
            sweep_le_deg=gamma_LE_vt,
            cant_deg=0.0,
            xyz_le_root=(float(x_vt), float(y_vt), float(z_vt)),
            n_sections=nsec_vt,
        )
        parts.update(dict(b_vt=vt_metrics["b"], S_vt=vt_metrics["S"]))

    fuselages = []
    if make_simple_fuselage:
        xi = np.linspace(0, 1, nsec_fuse)
        cam_x = np.linspace(0.0, L_fuse, nsec_fuse)
        cam_z = np.linspace(fuse_camper[0], fuse_camper[1], nsec_fuse)
        radius = rad_fuse_max * (1 - (2 * (xi - 0.5)) ** 2) ** 0.6
        fuselage = asb.Fuselage(
            name="Fuselage",
            xsecs=[
                asb.FuselageXSec(
                    xyz_c=[cam_x[i], 0.0, cam_z[i]],
                    radius=float(max(radius[i], 1e-4)),
                )
                for i in range(nsec_fuse)
            ],
        ).translate([x_fuse_nose, y_fuse_nose, z_fuse_nose])
        fuselages = [fuselage]

    airplane = asb.Airplane(
        name=name,
        xyz_ref=list(xyz_ref),
        wings=wings,
        fuselages=fuselages,
    )

    if return_parts:
        returned = {}
        if "main_wing" in parts:
            returned["main_wing"] = parts["main_wing"]
        if "horizontal_tail" in parts:
            returned["horizontal_tail"] = parts["horizontal_tail"]
        if "vertical_tail" in parts:
            returned["vertical_tail"] = parts["vertical_tail"]
        if wing_planform is not None:
            returned["wing_planform"] = wing_planform
        if ht_planform is not None:
            returned["ht_planform"] = ht_planform
        if vt_planform is not None:
            returned["vt_planform"] = vt_planform
        if "S_w" in parts:
            returned.update(
                dict(
                    S_w=parts["S_w"],
                    AR_w=parts["AR_w"],
                    c_root_w=parts["c_root_w"],
                    c_tip_w=parts["c_tip_w"],
                    MAC_w=parts["MAC_w"],
                )
            )
        if "b_ht" in parts:
            returned["b_ht"] = parts["b_ht"]
        if "S_ht" in parts:
            returned["S_ht"] = parts["S_ht"]
        if "b_vt" in parts:
            returned["b_vt"] = parts["b_vt"]
        if "S_vt" in parts:
            returned["S_vt"] = parts["S_vt"]
        return airplane, returned

    return airplane


__all__ = ["simple_aircraft"]
