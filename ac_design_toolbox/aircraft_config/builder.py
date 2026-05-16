"""Geometry builders for the canonical aircraft-definition schema."""

from __future__ import annotations

from copy import deepcopy
from math import radians, tan

import aerosandbox as asb
import aerosandbox.numpy as np

from ac_design_toolbox.geometry._common import _airfoil_blend_array, _chords_from_area_or_taper
from ac_design_toolbox.geometry.surfaces import make_vt, make_wing

from .models import AircraftDefinition, LiftingSurfaceConfig, SurfaceAnchorConfig


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


def _control_surfaces_at_eta(control_specs: list[dict], eta: float) -> list[asb.ControlSurface]:
    """Return controls active at one normalized span station."""
    controls = []
    eps = 1e-12
    for control in control_specs:
        span_fraction = control.get("span_fraction")
        if span_fraction is None or len(span_fraction) != 2:
            continue
        start, end = float(span_fraction[0]), float(span_fraction[1])
        if start - eps <= eta <= end + eps:
            controls.append(
                asb.ControlSurface(
                    name=str(control["name"]),
                    symmetric=bool(control.get("symmetric", False)),
                    deflection=float(control.get("deflection", 0.0) or 0.0),
                    hinge_point=float(control.get("hinge_point", 0.75) or 0.75),
                )
            )
    return controls


def _anchored_eta(surface: LiftingSurfaceConfig) -> np.ndarray:
    """Return section stations with control edges included exactly."""
    eta = np.linspace(0.0, 1.0, int(surface.n_sections))
    for control in _control_surface_specs(surface):
        span_fraction = control.get("span_fraction")
        if span_fraction is None or len(span_fraction) != 2:
            continue
        start, end = float(span_fraction[0]), float(span_fraction[1])
        if 0.0 < start < 1.0:
            eta = np.append(eta, start)
        if 0.0 < end < 1.0:
            eta = np.append(eta, end)
    return np.unique(np.round(eta.astype(float), 12))


def _interpolate_wing_xsec_values(wing: asb.Wing, span_fraction: float) -> tuple[np.ndarray, float]:
    """Return leading-edge point and chord at one root-to-tip station."""
    xsecs = list(getattr(wing, "xsecs", []))
    if len(xsecs) < 2:
        raise ValueError(f"Target surface {wing.name!r} must contain at least two xsecs.")

    stations = np.linspace(0.0, 1.0, len(xsecs))
    points = np.asarray([xsec.xyz_le for xsec in xsecs], dtype=float)
    chords = np.asarray([float(xsec.chord) for xsec in xsecs], dtype=float)
    span_fraction = float(span_fraction)
    point = np.asarray(
        [
            np.interp(span_fraction, stations, points[:, axis])
            for axis in range(3)
        ],
        dtype=float,
    )
    chord = float(np.interp(span_fraction, stations, chords))
    return point, chord


def _resolve_anchor_point(anchor: SurfaceAnchorConfig, built_wings: dict[str, asb.Wing]) -> np.ndarray:
    """Resolve one anchored-surface endpoint into a body-frame point."""
    wing = built_wings.get(anchor.surface_id)
    if wing is None:
        raise ValueError(
            f"Anchored surface references {anchor.surface_id!r}, but that surface has not been built yet. "
            "Place anchor targets earlier in lifting_surfaces and avoid cyclic connector references."
        )

    leading_edge, chord = _interpolate_wing_xsec_values(wing, anchor.span_fraction)
    if bool(getattr(wing, "symmetric", False)) and anchor.side == "left":
        leading_edge = np.asarray([leading_edge[0], -leading_edge[1], leading_edge[2]], dtype=float)
    point = leading_edge + np.asarray([float(chord) * anchor.chord_fraction, 0.0, 0.0], dtype=float)
    point += np.asarray([float(anchor.dx), float(anchor.dy), float(anchor.dz)], dtype=float)
    return point


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


def _station_root_chord(surface: LiftingSurfaceConfig) -> float:
    """Return the root chord used by a station-mode surface."""
    if surface.root_chord is not None:
        return float(surface.root_chord)
    return float(2.0 * surface.area / (surface.span * (1.0 + surface.taper)))


def _station_eta_values(surface: LiftingSurfaceConfig) -> list[float]:
    """Return station fractions augmented with exact control-surface edges."""
    spans = [float(station.span) for station in surface.stations]
    total_span = float(sum(spans))
    if total_span <= 0.0:
        raise ValueError(f"Stationed surface {surface.component_id!r} has no positive span.")
    cumulative = 0.0
    eta = [0.0]
    for span in spans:
        cumulative += span
        eta.append(float(cumulative / total_span))

    for control in _control_surface_specs(surface):
        span_fraction = control.get("span_fraction")
        if span_fraction is None or len(span_fraction) != 2:
            continue
        start, end = float(span_fraction[0]), float(span_fraction[1])
        if 0.0 < start < 1.0:
            eta.append(start)
        if 0.0 < end < 1.0:
            eta.append(end)
    return [float(value) for value in np.unique(np.round(np.asarray(eta, dtype=float), 12))]


def _station_profile_values(
    surface: LiftingSurfaceConfig,
    *,
    y_le: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[asb.Airfoil]]:
    """Return station-mode section values at the user-defined station breaks."""
    root_y = float(surface.y_le if y_le is None else y_le)
    current_xyz = np.asarray([float(surface.x_le), root_y, float(surface.z_le)], dtype=float)
    current_chord = _station_root_chord(surface)
    current_span = 0.0

    spans = [float(station.span) for station in surface.stations]
    total_span = float(sum(spans))
    eta_values = [0.0]
    points = [current_xyz.copy()]
    chords = [float(current_chord)]
    twists = [float(surface.twist_root_deg)]
    airfoils = [_as_airfoil(surface.root_airfoil)]

    for station, segment_span in zip(surface.stations, spans):
        sweep_dx = segment_span * tan(radians(float(station.sweep_le_deg)))
        secondary = segment_span * tan(radians(float(station.dihedral_deg)))
        if surface.orientation == "vertical":
            delta = np.asarray([sweep_dx, secondary, segment_span], dtype=float)
        else:
            delta = np.asarray([sweep_dx, segment_span, secondary], dtype=float)
        current_xyz = current_xyz + delta
        current_chord = station.end_chord(current_chord)
        current_span += segment_span

        eta_values.append(float(current_span / total_span))
        points.append(current_xyz.copy())
        chords.append(float(current_chord))
        twists.append(float(station.twist_deg))
        airfoils.append(_as_airfoil(station.airfoil))

    return (
        np.asarray(eta_values, dtype=float),
        np.asarray(points, dtype=float),
        np.asarray(chords, dtype=float),
        np.asarray(twists, dtype=float),
        airfoils,
    )


def _station_airfoil_at_eta(base_eta: np.ndarray, airfoils: list[asb.Airfoil], eta: float) -> asb.Airfoil:
    """Return the station airfoil assigned to one possibly augmented station."""
    eta = float(eta)
    for index, base_value in enumerate(base_eta):
        if abs(float(base_value) - eta) <= 1e-12:
            return airfoils[index]
    outboard_index = int(np.searchsorted(base_eta, eta, side="right"))
    inboard_index = max(min(outboard_index - 1, len(airfoils) - 1), 0)
    return airfoils[inboard_index]


def _build_stationed_surface(
    surface: LiftingSurfaceConfig,
    *,
    name: str,
    y_le: float | None = None,
) -> asb.Wing:
    """Build one direct surface from explicit station segments."""
    if not surface.stations:
        raise ValueError(f"Stationed surface {surface.component_id!r} requires station segments.")

    base_eta, base_points, base_chords, base_twists, base_airfoils = _station_profile_values(surface, y_le=y_le)
    eta_values = _station_eta_values(surface)
    control_specs = _control_surface_specs(surface)

    xsecs = []
    for eta in eta_values:
        xyz_le = np.asarray(
            [
                np.interp(float(eta), base_eta, base_points[:, axis])
                for axis in range(3)
            ],
            dtype=float,
        )
        xsecs.append(
            asb.WingXSec(
                xyz_le=xyz_le,
                chord=float(np.interp(float(eta), base_eta, base_chords)),
                twist=float(np.interp(float(eta), base_eta, base_twists)),
                airfoil=_station_airfoil_at_eta(base_eta, base_airfoils, float(eta)),
                control_surfaces=_control_surfaces_at_eta(control_specs, float(eta)),
            )
        )

    return asb.Wing(
        name=name,
        xyz_le=[0.0, 0.0, 0.0],
        symmetric=bool(surface.symmetric and surface.orientation == "horizontal"),
        xsecs=xsecs,
        n_chordwise=surface.n_chordwise,
        chordwise_spacing=surface.chordwise_spacing,
        n_spanwise=surface.n_spanwise,
        spanwise_spacing=surface.spanwise_spacing,
    )


def _build_anchored_surface(surface: LiftingSurfaceConfig, built_wings: dict[str, asb.Wing]) -> asb.Wing:
    """Build one literal surface whose root and tip leading edges are anchored."""
    if surface.root_anchor is None or surface.tip_anchor is None:
        raise ValueError(f"Anchored surface {surface.component_id!r} is missing root or tip anchor.")

    root_point = _resolve_anchor_point(surface.root_anchor, built_wings)
    tip_point = _resolve_anchor_point(surface.tip_anchor, built_wings)
    span_vector = tip_point - root_point
    span = float(np.linalg.norm(span_vector))
    if span <= 1e-9:
        raise ValueError(f"Anchored surface {surface.component_id!r} has coincident root and tip anchors.")

    solve = _chords_from_area_or_taper(
        span=span,
        n_sections=int(surface.n_sections),
        area=float(surface.area),
        taper=float(surface.taper),
    )
    eta = _anchored_eta(surface)
    chord_base_eta = np.linspace(0.0, 1.0, int(surface.n_sections))
    chords = np.interp(eta, chord_base_eta, np.asarray(solve.chords, dtype=float))
    twist = np.interp(
        eta,
        np.asarray([0.0, 1.0], dtype=float),
        np.asarray([float(surface.twist_root_deg), float(surface.twist_tip_deg)], dtype=float),
    )
    airfoils = _airfoil_blend_array(
        _as_airfoil(surface.root_airfoil),
        _as_airfoil(surface.tip_airfoil),
        len(eta),
    )
    control_specs = _control_surface_specs(surface)

    xsecs = []
    for index, eta_value in enumerate(eta):
        xyz_le = root_point + float(eta_value) * span_vector
        xsecs.append(
            asb.WingXSec(
                xyz_le=xyz_le,
                chord=float(chords[index]),
                twist=float(twist[index]),
                airfoil=airfoils[index],
                control_surfaces=_control_surfaces_at_eta(control_specs, float(eta_value)),
            )
        )

    return asb.Wing(
        name=surface.component_id,
        xyz_le=[0.0, 0.0, 0.0],
        symmetric=False,
        xsecs=xsecs,
        n_chordwise=surface.n_chordwise,
        chordwise_spacing=surface.chordwise_spacing,
        n_spanwise=surface.n_spanwise,
        spanwise_spacing=surface.spanwise_spacing,
    )


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
        if surface.geometry_mode == "stationed":
            return [
                _build_stationed_surface(
                    surface,
                    name=surface.component_id,
                    y_le=float(surface.y_le),
                )
            ]
        return [
            _build_single_vertical_surface(
                surface,
                name=surface.component_id,
                y_le=float(surface.y_le),
            )
        ]

    if surface.geometry_mode == "stationed":
        right_surface = _build_stationed_surface(
            surface,
            name=f"{surface.component_id}_right",
            y_le=abs(float(surface.y_le)),
        )
        left_surface = _mirror_wing_about_xz(right_surface, name=f"{surface.component_id}_left")
        return [right_surface, left_surface]

    right_surface = _build_single_vertical_surface(
        surface,
        name=f"{surface.component_id}_right",
        y_le=abs(float(surface.y_le)),
    )
    left_surface = _mirror_wing_about_xz(right_surface, name=f"{surface.component_id}_left")
    return [right_surface, left_surface]


def _build_surface_group(surface: LiftingSurfaceConfig, built_wings: dict[str, asb.Wing]) -> list[asb.Wing]:
    """Return the built wing components emitted by one lifting-surface config."""
    if surface.geometry_mode == "anchored_le":
        return [_build_anchored_surface(surface, built_wings)]
    if surface.geometry_mode == "stationed" and surface.orientation == "horizontal":
        return [_build_stationed_surface(surface, name=surface.component_id)]
    if surface.orientation == "horizontal":
        return [_build_horizontal_surface(surface)]
    return _build_vertical_surface_group(surface)


def build_aircraft(definition: AircraftDefinition) -> asb.Airplane:
    """Build an AeroSandbox airplane from the canonical aircraft definition.

    The returned airplane uses stable component IDs as surface names so
    downstream tools can target surfaces deterministically.
    """
    wings: list[asb.Wing] = []
    built_wings: dict[str, asb.Wing] = {}
    for surface in definition.lifting_surfaces:
        surface_wings = _build_surface_group(surface, built_wings)
        for wing in surface_wings:
            if wing.name in built_wings:
                raise ValueError(f"Built surface IDs must be unique; duplicate {wing.name!r}.")
            built_wings[str(wing.name)] = wing
        wings.extend(surface_wings)

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
