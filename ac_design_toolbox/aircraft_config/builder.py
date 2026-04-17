"""Geometry builders for the canonical aircraft-definition schema."""

from __future__ import annotations

from copy import deepcopy
from math import radians, tan

import aerosandbox as asb
import aerosandbox.numpy as np

from ac_design_toolbox.geometry.surfaces import make_ht, make_vt, make_wing

from .models import AircraftDefinition, TailSurfaceConfig


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


def _wing_tip_leading_edge_xyz(wing: asb.Wing) -> tuple[float, float, float]:
    """Return the right-tip leading-edge coordinates for a built wing."""
    if not getattr(wing, "xsecs", None):
        raise ValueError("Wing must contain at least one cross section.")
    tip_xsec = wing.xsecs[-1]
    return (
        float(tip_xsec.xyz_le[0]),
        float(tip_xsec.xyz_le[1]),
        float(tip_xsec.xyz_le[2]),
    )


def _build_main_wing(definition: AircraftDefinition) -> asb.Wing:
    """Build the main wing using the canonical wing configuration."""
    wing = definition.main_wing
    return make_wing(
        name=wing.component_id,
        span=wing.span,
        n_sections_w=wing.n_sections,
        n_chordwise_w=wing.n_chordwise,
        chordwise_spacing_w=wing.chordwise_spacing,
        n_spanwise_w=wing.n_spanwise,
        spanwise_spacing_w=wing.spanwise_spacing,
        symmetric=True,
        area=wing.area,
        taper=wing.taper,
        sweep_le=wing.sweep_le_deg,
        dihedral=wing.dihedral_deg,
        x_le_root=wing.x_le,
        y_le_root=wing.y_le,
        z_le_root=wing.z_le,
        twist=(wing.twist_root_deg, wing.twist_tip_deg),
        airfoil_root=_as_airfoil(wing.root_airfoil),
        airfoil_tip=_as_airfoil(wing.tip_airfoil),
    )


def _build_horizontal_tail(surface: TailSurfaceConfig) -> asb.Wing:
    """Build a horizontal tail surface from canonical tail inputs."""
    tail = make_ht(
        name=surface.component_id,
        span=surface.span,
        n_sections_ht=surface.n_sections,
        n_chordwise_ht=surface.n_chordwise,
        chordwise_spacing_ht=surface.chordwise_spacing,
        n_spanwise_ht=surface.n_spanwise,
        spanwise_spacing_ht=surface.spanwise_spacing,
        x_le=surface.x_le,
        y_le=surface.y_le,
        z_le=surface.z_le,
        area=surface.area,
        taper=surface.taper,
        sweep_le=surface.sweep_le_deg,
        dihedral=surface.dihedral_deg,
        twist=(surface.twist_root_deg, surface.twist_tip_deg),
        airfoil_root=_as_airfoil(surface.root_airfoil),
        airfoil_tip=_as_airfoil(surface.tip_airfoil),
        span_frac_elevator=None,
        delta_elevator=0.0,
    )
    tail.name = surface.component_id
    return tail


def _build_vertical_tail(surface: TailSurfaceConfig) -> asb.Wing:
    """Build a vertical tail surface from canonical tail inputs."""
    tail = make_vt(
        name=surface.component_id,
        span=surface.span,
        n_sections_vt=surface.n_sections,
        n_chordwise_vt=surface.n_chordwise,
        chordwise_spacing_vt=surface.chordwise_spacing,
        n_spanwise_vt=surface.n_spanwise,
        spanwise_spacing_vt=surface.spanwise_spacing,
        x_le=surface.x_le,
        y_le=surface.y_le,
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
    )
    tail.name = surface.component_id
    return tail


def _t_tail_horizontal_surface(definition: AircraftDefinition) -> TailSurfaceConfig:
    """Return a horizontal-tail config remounted to the VT upper station."""
    horizontal_tail = definition.tail_assembly.horizontal_tail
    vertical_tail = definition.tail_assembly.vertical_tail
    tip_fraction = definition.tail_assembly.t_tail_mount_fraction
    z_offset = vertical_tail.span * tip_fraction
    x_offset = vertical_tail.span * tip_fraction * tan(radians(vertical_tail.sweep_le_deg))
    return TailSurfaceConfig(
        component_id=horizontal_tail.component_id,
        span=horizontal_tail.span,
        area=horizontal_tail.area,
        taper=horizontal_tail.taper,
        sweep_le_deg=horizontal_tail.sweep_le_deg,
        dihedral_deg=horizontal_tail.dihedral_deg,
        x_le=vertical_tail.x_le + x_offset,
        y_le=horizontal_tail.y_le,
        z_le=vertical_tail.z_le + z_offset,
        twist_root_deg=horizontal_tail.twist_root_deg,
        twist_tip_deg=horizontal_tail.twist_tip_deg,
        root_airfoil=horizontal_tail.root_airfoil,
        tip_airfoil=horizontal_tail.tip_airfoil,
        n_sections=horizontal_tail.n_sections,
        n_chordwise=horizontal_tail.n_chordwise,
        n_spanwise=horizontal_tail.n_spanwise,
        chordwise_spacing=horizontal_tail.chordwise_spacing,
        spanwise_spacing=horizontal_tail.spanwise_spacing,
    )


def _build_v_tail_surfaces(definition: AircraftDefinition) -> list[asb.Wing]:
    """Build mirrored V-tail surfaces with stable right/left component IDs."""
    surface = definition.tail_assembly.v_tail_surface
    return _build_canted_tail_pair(
        surface,
        right_id=f"{surface.component_id}_right",
        left_id=f"{surface.component_id}_left",
    )


def _build_canted_tail_pair(
    surface: TailSurfaceConfig,
    *,
    right_id: str,
    left_id: str,
) -> list[asb.Wing]:
    """Build a mirrored canted-tail pair from one canonical surface definition."""
    right_surface = make_wing(
        name=right_id,
        span=2.0 * surface.span,
        n_sections_w=surface.n_sections,
        n_chordwise_w=surface.n_chordwise,
        chordwise_spacing_w=surface.chordwise_spacing,
        n_spanwise_w=surface.n_spanwise,
        spanwise_spacing_w=surface.spanwise_spacing,
        symmetric=False,
        area=surface.area,
        taper=surface.taper,
        sweep_le=surface.sweep_le_deg,
        dihedral=surface.dihedral_deg,
        x_le_root=surface.x_le,
        y_le_root=surface.y_le,
        z_le_root=surface.z_le,
        twist=(surface.twist_root_deg, surface.twist_tip_deg),
        airfoil_root=_as_airfoil(surface.root_airfoil),
        airfoil_tip=_as_airfoil(surface.tip_airfoil),
    )
    right_surface.name = right_id
    left_surface = _mirror_wing_about_xz(right_surface, name=left_id)
    return [right_surface, left_surface]


def _build_h_tail_surfaces(definition: AircraftDefinition) -> list[asb.Wing]:
    """Build an H-tail using the HT plus twin vertical fins at the HT tips."""
    horizontal_tail = _build_horizontal_tail(definition.tail_assembly.horizontal_tail)
    tip_x, tip_y, tip_z = _wing_tip_leading_edge_xyz(horizontal_tail)
    vertical_tail = definition.tail_assembly.vertical_tail
    right_surface = make_vt(
        name=f"{vertical_tail.component_id}_right",
        span=vertical_tail.span,
        n_sections_vt=vertical_tail.n_sections,
        n_chordwise_vt=vertical_tail.n_chordwise,
        chordwise_spacing_vt=vertical_tail.chordwise_spacing,
        n_spanwise_vt=vertical_tail.n_spanwise,
        spanwise_spacing_vt=vertical_tail.spanwise_spacing,
        x_le=tip_x,
        y_le=tip_y,
        z_le=tip_z,
        area=vertical_tail.area,
        taper=vertical_tail.taper,
        sweep_le=vertical_tail.sweep_le_deg,
        cant=vertical_tail.dihedral_deg,
        twist=(vertical_tail.twist_root_deg, vertical_tail.twist_tip_deg),
        airfoil_root=_as_airfoil(vertical_tail.root_airfoil),
        airfoil_tip=_as_airfoil(vertical_tail.tip_airfoil),
        span_frac_rudder=None,
        delta_rudder=0.0,
    )
    right_surface.name = f"{vertical_tail.component_id}_right"
    left_surface = _mirror_wing_about_xz(right_surface, name=f"{vertical_tail.component_id}_left")
    return [horizontal_tail, right_surface, left_surface]


def _build_y_tail_surfaces(definition: AircraftDefinition) -> list[asb.Wing]:
    """Build a Y-tail using one center fin plus a mirrored canted pair."""
    tail_assembly = definition.tail_assembly
    wings: list[asb.Wing] = [_build_vertical_tail(tail_assembly.vertical_tail)]
    wings.extend(
        _build_canted_tail_pair(
            tail_assembly.v_tail_surface,
            right_id=f"{tail_assembly.v_tail_surface.component_id}_right",
            left_id=f"{tail_assembly.v_tail_surface.component_id}_left",
        )
    )
    return wings


def build_aircraft(definition: AircraftDefinition) -> asb.Airplane:
    """Build an AeroSandbox airplane from the canonical aircraft definition.

    The returned airplane uses stable component IDs as surface names so
    downstream tools can target surfaces deterministically.
    """
    wings: list[asb.Wing] = [_build_main_wing(definition)]
    tail_assembly = definition.tail_assembly

    if tail_assembly.tail_type == "conventional":
        wings.append(_build_horizontal_tail(tail_assembly.horizontal_tail))
        wings.append(_build_vertical_tail(tail_assembly.vertical_tail))
    elif tail_assembly.tail_type == "t_tail":
        wings.append(_build_vertical_tail(tail_assembly.vertical_tail))
        wings.append(_build_horizontal_tail(_t_tail_horizontal_surface(definition)))
    elif tail_assembly.tail_type == "v_tail":
        wings.extend(_build_v_tail_surfaces(definition))
    elif tail_assembly.tail_type == "h_tail":
        wings.extend(_build_h_tail_surfaces(definition))
    elif tail_assembly.tail_type == "y_tail":
        wings.extend(_build_y_tail_surfaces(definition))
    else:
        raise ValueError(f"Unsupported tail_type {tail_assembly.tail_type!r}.")

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
