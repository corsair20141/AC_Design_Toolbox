"""Geometry builders for the canonical aircraft-definition schema."""

from __future__ import annotations

from copy import deepcopy

import aerosandbox as asb
import aerosandbox.numpy as np

from ac_design_toolbox.geometry.surfaces import make_vt, make_wing

from .models import AircraftDefinition, LiftingSurfaceConfig


def _as_airfoil(value: str | asb.Airfoil) -> asb.Airfoil:
    """Return an AeroSandbox airfoil object from a supported input value."""
    if isinstance(value, asb.Airfoil):
        return value
    return asb.Airfoil(str(value))


def _mirror_wing_about_xz(wing: asb.Wing, *, name: str) -> asb.Wing:
    """Return a deep-copied wing mirrored across the body XZ plane."""
    mirrored = deepcopy(wing)
    mirrored.name = name
    for xsec in mirrored.xsecs:
        xsec.xyz_le = np.array(
            [
                float(xsec.xyz_le[0]),
                -float(xsec.xyz_le[1]),
                float(xsec.xyz_le[2]),
            ]
        )
    return mirrored


def _horizontal_build_inputs(surface: LiftingSurfaceConfig) -> tuple[float, float, bool]:
    """Return make_wing-compatible span, area, and symmetry values.

    ``make_wing()`` uses a full-span convention in both symmetric and
    asymmetric modes. For a literal one-side surface we therefore double the
    stored span and area before building an asymmetric component.
    """
    if surface.symmetric:
        return float(surface.span), float(surface.area), True
    return 2.0 * float(surface.span), 2.0 * float(surface.area), False


def _control_surface_specs(surface: LiftingSurfaceConfig) -> list[dict]:
    """Return make_wing-compatible control-surface dictionaries."""
    return [
        {
            "name": control.name,
            "symmetric": control.symmetric,
            "deflection": control.deflection_deg,
            "hinge_point": control.hinge_point,
            "span_fraction": (
                control.span_start_fraction,
                control.span_end_fraction,
            ),
        }
        for control in surface.control_surfaces
    ]


def _build_horizontal_surface(surface: LiftingSurfaceConfig) -> asb.Wing:
    """Build one horizontal lifting surface from the canonical config."""
    span, area, symmetric = _horizontal_build_inputs(surface)
    wing = make_wing(
        name=surface.component_id,
        span=span,
        n_sections_w=surface.n_sections,
        n_chordwise_w=surface.n_chordwise,
        chordwise_spacing_w=surface.chordwise_spacing,
        n_spanwise_w=surface.n_spanwise,
        spanwise_spacing_w=surface.spanwise_spacing,
        symmetric=symmetric,
        area=area,
        taper=surface.taper,
        sweep_le=surface.sweep_le_deg,
        dihedral=surface.dihedral_deg,
        x_le_root=surface.x_le,
        y_le_root=surface.y_le,
        z_le_root=surface.z_le,
        twist=(surface.twist_root_deg, surface.twist_tip_deg),
        airfoil_root=_as_airfoil(surface.root_airfoil),
        airfoil_tip=_as_airfoil(surface.tip_airfoil),
        control_surface_specs=_control_surface_specs(surface),
    )
    wing.name = surface.component_id
    return wing


def _build_single_vertical_surface(
    surface: LiftingSurfaceConfig,
    *,
    name: str,
    y_le: float,
) -> asb.Wing:
    """Build one literal vertical or canted surface from canonical inputs."""
    tail = make_vt(
        name=name,
        span=surface.span,
        n_sections_vt=surface.n_sections,
        n_chordwise_vt=surface.n_chordwise,
        chordwise_spacing_vt=surface.chordwise_spacing,
        n_spanwise_vt=surface.n_spanwise,
        spanwise_spacing_vt=surface.spanwise_spacing,
        x_le=surface.x_le,
        y_le=y_le,
        z_le=surface.z_le,
        area=surface.area,
        taper=surface.taper,
        sweep_le=surface.sweep_le_deg,
        cant=surface.dihedral_deg,
        twist=(surface.twist_root_deg, surface.twist_tip_deg),
        airfoil_root=_as_airfoil(surface.root_airfoil),
        airfoil_tip=_as_airfoil(surface.tip_airfoil),
        span_frac_rudder=None,
        delta_rudder=0.0,
        control_surface_specs=_control_surface_specs(surface),
    )
    tail.name = name
    return tail


def _build_vertical_surface_group(surface: LiftingSurfaceConfig) -> list[asb.Wing]:
    """Build one or two vertical-orientation components from one surface config."""
    if not surface.symmetric:
        return [
            _build_single_vertical_surface(
                surface,
                name=surface.component_id,
                y_le=float(surface.y_le),
            )
        ]

    right_surface = _build_single_vertical_surface(
        surface,
        name=f"{surface.component_id}_right",
        y_le=abs(float(surface.y_le)),
    )
    left_surface = _mirror_wing_about_xz(right_surface, name=f"{surface.component_id}_left")
    return [right_surface, left_surface]


def _build_surface_group(surface: LiftingSurfaceConfig) -> list[asb.Wing]:
    """Return the built wing components emitted by one lifting-surface config."""
    if surface.orientation == "horizontal":
        return [_build_horizontal_surface(surface)]
    return _build_vertical_surface_group(surface)


def build_aircraft(definition: AircraftDefinition) -> asb.Airplane:
    """Build an AeroSandbox airplane from the canonical aircraft definition.

    The returned airplane uses stable component IDs as surface names so
    downstream tools can target surfaces deterministically.
    """
    wings: list[asb.Wing] = []
    for surface in definition.lifting_surfaces:
        wings.extend(_build_surface_group(surface))

    fuselages: list[asb.Fuselage] = []
    if definition.fuselage.enabled:
        fuselage = definition.fuselage
        xi = np.linspace(0, 1, fuselage.n_sections)
        cam_x = np.linspace(0.0, fuselage.length, fuselage.n_sections)
        cam_z = np.linspace(
            fuselage.camber_start_z,
            fuselage.camber_end_z,
            fuselage.n_sections,
        )
        radius = fuselage.max_radius * (1 - (2 * (xi - 0.5)) ** 2) ** 0.6
        fuselages = [
            asb.Fuselage(
                name="fuselage",
                xsecs=[
                    asb.FuselageXSec(
                        xyz_c=[cam_x[index], 0.0, cam_z[index]],
                        radius=float(max(radius[index], 1e-4)),
                    )
                    for index in range(fuselage.n_sections)
                ],
            ).translate([fuselage.x_nose, fuselage.y_nose, fuselage.z_nose])
        ]

    return asb.Airplane(
        name=definition.name,
        xyz_ref=[
            definition.reference_geometry.x_ref,
            definition.reference_geometry.y_ref,
            definition.reference_geometry.z_ref,
        ],
        wings=wings,
        fuselages=fuselages,
    )


__all__ = ["build_aircraft"]
