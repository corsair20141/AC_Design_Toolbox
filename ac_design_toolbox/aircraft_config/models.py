"""Canonical aircraft-definition models for installable cross-project use.

This module defines the canonical JSON-round-trippable aircraft configuration
schema used by both AC_Design_Toolbox and Solar_UAS. The current schema is a
hard-break surface-list model: all wing-like geometry lives in
``AircraftDefinition.lifting_surfaces`` and family-specific tail wrappers are
intentionally out of scope.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from math import atan, degrees, isfinite, radians, tan
from typing import Any

from ac_design_toolbox.mission.units import QuantityInput, coerce_quantity


SCHEMA_VERSION = "acdt_aircraft_definition_v2"
SURFACE_ROLES = (
    "main_wing",
    "wing",
    "horizontal_tail",
    "vertical_tail",
    "canted_tail",
    "canard",
    "other",
)
SURFACE_ORIENTATIONS = ("horizontal", "vertical")
SURFACE_GEOMETRY_MODES = ("direct", "stationed", "anchored_le")
_LEGACY_SCHEMA_KEYS = ("main_wing", "tail_assembly")


def _coerce_required_string(name: str, value: Any) -> str:
    """Return a stripped required string value."""
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty string.")
    return text


def _coerce_optional_string(value: Any) -> str:
    """Return a plain string for optional descriptive fields."""
    return "" if value is None else str(value)


def _coerce_positive_float(name: str, value: Any) -> float:
    """Return a positive finite scalar float."""
    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")
    if scalar_value <= 0.0:
        raise ValueError(f"{name} must be positive.")
    return scalar_value


def _coerce_fraction(name: str, value: Any) -> float:
    """Return a finite scalar fraction in the inclusive range ``[0, 1]``."""
    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")
    if scalar_value < 0.0 or scalar_value > 1.0:
        raise ValueError(f"{name} must be between 0 and 1.")
    return scalar_value


def _coerce_finite_float(name: str, value: Any) -> float:
    """Return a finite scalar float."""
    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")
    return scalar_value


def _json_safe_copy(name: str, value: Any) -> Any:
    """Return a JSON-safe deep copy of extension-like payloads."""
    try:
        return json.loads(json.dumps(value))
    except TypeError as exc:
        raise TypeError(f"{name} must be JSON-serializable.") from exc


def _center_of_gravity_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return native or legacy CG payload from an aircraft-definition mapping."""

    if "center_of_gravity" in data:
        return data.get("center_of_gravity", {})
    extensions = data.get("extensions", {})
    if isinstance(extensions, dict):
        solar_uas_extension = extensions.get("solar_uas", {})
        if isinstance(solar_uas_extension, dict):
            legacy_cg = solar_uas_extension.get("center_of_gravity")
            if isinstance(legacy_cg, dict):
                return legacy_cg
    return {}


@dataclass
class ControlSurfaceConfig:
    """Canonical control-surface definition for one lifting surface.

    Span fractions are measured from the lifting-surface root toward the tip in
    the same normalized convention used by the geometry builders. Deflection is
    stored in degrees for analysis workflows; geometry previews draw the
    undeflected panel footprint.
    """

    name: str = "aileron"
    span_start_fraction: float = 0.65
    span_end_fraction: float = 0.95
    hinge_point: float = 0.75
    symmetric: bool = False
    deflection_deg: float = 0.0

    def __post_init__(self) -> None:
        """Normalize and validate the control-surface definition."""
        self.name = _coerce_required_string("name", self.name)
        self.span_start_fraction = _coerce_fraction(
            "span_start_fraction",
            self.span_start_fraction,
        )
        self.span_end_fraction = _coerce_fraction(
            "span_end_fraction",
            self.span_end_fraction,
        )
        if self.span_end_fraction <= self.span_start_fraction:
            raise ValueError("span_end_fraction must be greater than span_start_fraction.")

        self.hinge_point = _coerce_fraction("hinge_point", self.hinge_point)
        if self.hinge_point <= 0.0 or self.hinge_point >= 1.0:
            raise ValueError("hinge_point must be greater than 0 and less than 1.")

        self.symmetric = bool(self.symmetric)
        self.deflection_deg = _coerce_finite_float("deflection_deg", self.deflection_deg)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the control-surface configuration to a plain dictionary."""
        return {
            "name": self.name,
            "span_start_fraction": self.span_start_fraction,
            "span_end_fraction": self.span_end_fraction,
            "hinge_point": self.hinge_point,
            "symmetric": self.symmetric,
            "deflection_deg": self.deflection_deg,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ControlSurfaceConfig":
        """Build the control-surface configuration from a plain dictionary."""
        return cls(
            name=data.get("name", "control_surface"),
            span_start_fraction=data.get("span_start_fraction", 0.65),
            span_end_fraction=data.get("span_end_fraction", 0.95),
            hinge_point=data.get("hinge_point", 0.75),
            symmetric=data.get("symmetric", False),
            deflection_deg=data.get("deflection_deg", 0.0),
        )


@dataclass
class ReferenceGeometryConfig:
    """Aerodynamic reference-point placement for the aircraft definition.

    Bare scalar dimensional inputs are stored in meters after normalization.
    """

    x_ref: QuantityInput = 0.0
    y_ref: QuantityInput = 0.0
    z_ref: QuantityInput = 0.0

    def __post_init__(self) -> None:
        """Normalize the reference coordinates into meters."""
        self.x_ref = coerce_quantity("x_ref", self.x_ref, "m", "length")
        self.y_ref = coerce_quantity("y_ref", self.y_ref, "m", "length")
        self.z_ref = coerce_quantity("z_ref", self.z_ref, "m", "length")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return {
            "x_ref": self.x_ref,
            "y_ref": self.y_ref,
            "z_ref": self.z_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReferenceGeometryConfig":
        """Build the configuration from a plain dictionary."""
        return cls(
            x_ref=data.get("x_ref", 0.0),
            y_ref=data.get("y_ref", 0.0),
            z_ref=data.get("z_ref", 0.0),
        )


@dataclass
class CenterOfGravityConfig:
    """Aircraft center-of-gravity location in body-frame coordinates.

    Bare scalar dimensional inputs are stored in meters after normalization.
    This is separate from ``ReferenceGeometryConfig`` because the aerodynamic
    moment-reference point and the physical CG are not necessarily identical.
    """

    x_cg: QuantityInput = 0.0
    y_cg: QuantityInput = 0.0
    z_cg: QuantityInput = 0.0

    def __post_init__(self) -> None:
        """Normalize the CG coordinates into meters."""
        self.x_cg = coerce_quantity("x_cg", self.x_cg, "m", "length")
        self.y_cg = coerce_quantity("y_cg", self.y_cg, "m", "length")
        self.z_cg = coerce_quantity("z_cg", self.z_cg, "m", "length")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return {
            "x_cg": self.x_cg,
            "y_cg": self.y_cg,
            "z_cg": self.z_cg,
        }

    def as_tuple(self) -> tuple[float, float, float]:
        """Return the CG as a numeric body-frame tuple in meters."""
        return (float(self.x_cg), float(self.y_cg), float(self.z_cg))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CenterOfGravityConfig":
        """Build the configuration from a plain dictionary."""
        return cls(
            x_cg=data.get("x_cg", data.get("x", 0.0)),
            y_cg=data.get("y_cg", data.get("y", 0.0)),
            z_cg=data.get("z_cg", data.get("z", 0.0)),
        )


@dataclass
class SurfaceAnchorConfig:
    """Attachment point for an anchored lifting surface.

    The anchor is resolved on an already built wing-like component. Fractions
    use the same root-to-tip span convention and leading-to-trailing chord
    convention as the AeroSandbox wing sections. Offsets are body-frame meters.
    """

    surface_id: str = "main_wing"
    side: str = "right"
    span_fraction: float = 1.0
    chord_fraction: float = 0.0
    dx: QuantityInput = 0.0
    dy: QuantityInput = 0.0
    dz: QuantityInput = 0.0

    def __post_init__(self) -> None:
        """Normalize anchor values into canonical computational units."""
        self.surface_id = _coerce_required_string("surface_id", self.surface_id)
        self.side = _coerce_required_string("side", self.side).lower()
        if self.side not in {"right", "left"}:
            raise ValueError("SurfaceAnchorConfig.side must be 'right' or 'left'.")
        self.span_fraction = _coerce_fraction("span_fraction", self.span_fraction)
        self.chord_fraction = _coerce_fraction("chord_fraction", self.chord_fraction)
        self.dx = coerce_quantity("dx", self.dx, "m", "length")
        self.dy = coerce_quantity("dy", self.dy, "m", "length")
        self.dz = coerce_quantity("dz", self.dz, "m", "length")

    def mirrored(self) -> "SurfaceAnchorConfig":
        """Return this anchor mirrored across the aircraft centerline."""
        return SurfaceAnchorConfig(
            surface_id=self.surface_id,
            side="left" if self.side == "right" else "right",
            span_fraction=self.span_fraction,
            chord_fraction=self.chord_fraction,
            dx=self.dx,
            dy=-self.dy,
            dz=self.dz,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the anchor to a plain dictionary."""
        return {
            "surface_id": self.surface_id,
            "side": self.side,
            "span_fraction": self.span_fraction,
            "chord_fraction": self.chord_fraction,
            "dx": self.dx,
            "dy": self.dy,
            "dz": self.dz,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "SurfaceAnchorConfig":
        """Build an anchor from a plain dictionary."""
        if isinstance(data, SurfaceAnchorConfig):
            return data
        data = dict(data or {})
        return cls(
            surface_id=data.get("surface_id", "main_wing"),
            side=data.get("side", "right"),
            span_fraction=data.get("span_fraction", 1.0),
            chord_fraction=data.get("chord_fraction", 0.0),
            dx=data.get("dx", data.get("dx_m", 0.0)),
            dy=data.get("dy", data.get("dy_m", 0.0)),
            dz=data.get("dz", data.get("dz_m", 0.0)),
        )


@dataclass
class LiftingSurfaceStationConfig:
    """One segment end station for a multi-station direct lifting surface.

    The root station is stored on ``LiftingSurfaceConfig`` through ``x_le``,
    ``y_le``, ``z_le``, ``root_chord``, ``twist_root_deg``, and
    ``root_airfoil``. Each station record advances from the previous station
    by a positive projected span. Sweep drives the X advance, dihedral or cant
    drives the secondary vertical/lateral advance, and either ``chord`` or
    ``taper`` sets the end-station chord.
    """

    span: QuantityInput = 0.5
    sweep_le_deg: QuantityInput = 0.0
    dihedral_deg: QuantityInput = 0.0
    taper: float | None = 1.0
    chord: QuantityInput | None = None
    twist_deg: QuantityInput = 0.0
    airfoil: str = "naca0010"

    def __post_init__(self) -> None:
        """Normalize the station segment into canonical computational units."""
        self.span = coerce_quantity("station span", self.span, "m", "length")
        if self.span <= 0.0:
            raise ValueError("station span must be positive.")
        self.sweep_le_deg = coerce_quantity(
            "station sweep_le_deg",
            self.sweep_le_deg,
            "deg",
            "angle",
        )
        self.dihedral_deg = coerce_quantity(
            "station dihedral_deg",
            self.dihedral_deg,
            "deg",
            "angle",
        )
        self.twist_deg = coerce_quantity("station twist_deg", self.twist_deg, "deg", "angle")
        self.airfoil = _coerce_required_string("station airfoil", self.airfoil)

        if self.chord in (None, ""):
            self.chord = None
        else:
            self.chord = coerce_quantity("station chord", self.chord, "m", "length")
            if self.chord <= 0.0:
                raise ValueError("station chord must be positive when provided.")

        if self.taper in (None, ""):
            self.taper = None
        else:
            self.taper = _coerce_positive_float("station taper", self.taper)

        if self.chord is None and self.taper is None:
            raise ValueError("station segments require either chord or taper.")

    def end_chord(self, previous_chord: float) -> float:
        """Return this station's end chord from the previous station chord."""
        if self.chord is not None:
            return float(self.chord)
        return float(previous_chord) * float(self.taper)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the station segment to a plain dictionary."""
        return {
            "span": self.span,
            "sweep_le_deg": self.sweep_le_deg,
            "dihedral_deg": self.dihedral_deg,
            "taper": self.taper,
            "chord": self.chord,
            "twist_deg": self.twist_deg,
            "airfoil": self.airfoil,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LiftingSurfaceStationConfig":
        """Build a station segment from a plain dictionary."""
        if isinstance(data, LiftingSurfaceStationConfig):
            return data
        return cls(
            span=data.get("span", data.get("span_m", 0.5)),
            sweep_le_deg=data.get("sweep_le_deg", 0.0),
            dihedral_deg=data.get("dihedral_deg", 0.0),
            taper=data.get("taper", 1.0),
            chord=data.get("chord", data.get("chord_m")),
            twist_deg=data.get("twist_deg", 0.0),
            airfoil=data.get("airfoil", "naca0010"),
        )


@dataclass
class LiftingSurfaceConfig:
    """Canonical lifting-surface geometry definition.

    The schema intentionally uses one shared surface model for main wings, extra
    wings, canards, and tail-like surfaces. A few conventions matter:

    - Horizontal symmetric surfaces use the traditional wing convention where
      ``span`` and ``area`` describe the full mirrored surface.
    - Vertical symmetric surfaces represent one literal surface definition that
      will be mirrored into right/left built components.
    - Non-symmetric surfaces always represent one literal, unmirrored surface.

    Bare scalar dimensional inputs are stored as meters, square meters, and
    degrees after normalization.
    """

    component_id: str = "main_wing"
    role: str = "main_wing"
    orientation: str = "horizontal"
    geometry_mode: str = "direct"
    symmetric: bool = True
    span: QuantityInput = 1.8288
    area: QuantityInput = 0.41806368
    taper: float = 0.65
    root_chord: QuantityInput | None = None
    sweep_le_deg: QuantityInput = 0.0
    dihedral_deg: QuantityInput = 7.0
    x_le: QuantityInput = 0.2286
    y_le: QuantityInput = 0.0
    z_le: QuantityInput = 0.03048
    twist_root_deg: QuantityInput = 0.0
    twist_tip_deg: QuantityInput = 0.0
    root_airfoil: str = "naca4412"
    tip_airfoil: str = "naca4412"
    n_sections: int = 3
    n_chordwise: int = 12
    n_spanwise: int = 36
    chordwise_spacing: str = "cosine"
    spanwise_spacing: str = "cosine"
    control_surfaces: list[ControlSurfaceConfig] = field(default_factory=list)
    stations: list[LiftingSurfaceStationConfig] = field(default_factory=list)
    root_anchor: SurfaceAnchorConfig | None = None
    tip_anchor: SurfaceAnchorConfig | None = None

    def __post_init__(self) -> None:
        """Normalize the surface geometry into canonical computational units."""
        self.component_id = _coerce_required_string("component_id", self.component_id)
        self.role = _coerce_required_string("role", self.role)
        if self.role not in SURFACE_ROLES:
            raise ValueError(f"role must be one of {SURFACE_ROLES}, got {self.role!r}.")

        self.orientation = _coerce_required_string("orientation", self.orientation)
        if self.orientation not in SURFACE_ORIENTATIONS:
            raise ValueError(
                f"orientation must be one of {SURFACE_ORIENTATIONS}, got {self.orientation!r}."
            )

        self.geometry_mode = _coerce_required_string("geometry_mode", self.geometry_mode)
        if self.geometry_mode not in SURFACE_GEOMETRY_MODES:
            raise ValueError(
                f"geometry_mode must be one of {SURFACE_GEOMETRY_MODES}, got {self.geometry_mode!r}."
            )

        self.symmetric = bool(self.symmetric)
        self.span = coerce_quantity("span", self.span, "m", "length")
        self.area = coerce_quantity("area", self.area, "m2", "area")
        self.taper = _coerce_positive_float("taper", self.taper)
        if self.root_chord in (None, ""):
            self.root_chord = None
        else:
            self.root_chord = coerce_quantity("root_chord", self.root_chord, "m", "length")
            if self.root_chord <= 0.0:
                raise ValueError("root_chord must be positive when provided.")
        self.sweep_le_deg = coerce_quantity("sweep_le_deg", self.sweep_le_deg, "deg", "angle")
        self.dihedral_deg = coerce_quantity("dihedral_deg", self.dihedral_deg, "deg", "angle")
        self.x_le = coerce_quantity("x_le", self.x_le, "m", "length")
        self.y_le = coerce_quantity("y_le", self.y_le, "m", "length")
        self.z_le = coerce_quantity("z_le", self.z_le, "m", "length")
        self.twist_root_deg = coerce_quantity("twist_root_deg", self.twist_root_deg, "deg", "angle")
        self.twist_tip_deg = coerce_quantity("twist_tip_deg", self.twist_tip_deg, "deg", "angle")
        self.root_airfoil = _coerce_required_string("root_airfoil", self.root_airfoil)
        self.tip_airfoil = _coerce_required_string("tip_airfoil", self.tip_airfoil)
        self.n_sections = int(self.n_sections)
        self.n_chordwise = int(self.n_chordwise)
        self.n_spanwise = int(self.n_spanwise)
        self.control_surfaces = [
            control if isinstance(control, ControlSurfaceConfig) else ControlSurfaceConfig.from_dict(control)
            for control in self.control_surfaces
        ]
        self.stations = [
            station if isinstance(station, LiftingSurfaceStationConfig) else LiftingSurfaceStationConfig.from_dict(station)
            for station in self.stations
        ]
        self.root_anchor = (
            None
            if self.root_anchor is None
            else self.root_anchor
            if isinstance(self.root_anchor, SurfaceAnchorConfig)
            else SurfaceAnchorConfig.from_dict(self.root_anchor)
        )
        self.tip_anchor = (
            None
            if self.tip_anchor is None
            else self.tip_anchor
            if isinstance(self.tip_anchor, SurfaceAnchorConfig)
            else SurfaceAnchorConfig.from_dict(self.tip_anchor)
        )

        if self.span <= 0.0:
            raise ValueError("span must be positive.")
        if self.area <= 0.0:
            raise ValueError("area must be positive.")
        if self.n_sections < 2:
            raise ValueError("n_sections must be >= 2.")
        if self.n_chordwise < 1:
            raise ValueError("n_chordwise must be >= 1.")
        if self.n_spanwise < 1:
            raise ValueError("n_spanwise must be >= 1.")

        if self.role in {"main_wing", "horizontal_tail", "canard"} and self.orientation != "horizontal":
            raise ValueError(f"{self.role} surfaces must use horizontal orientation.")
        if self.role in {"vertical_tail", "canted_tail"} and self.orientation != "vertical":
            raise ValueError(f"{self.role} surfaces must use vertical orientation.")
        if self.geometry_mode == "anchored_le":
            if self.symmetric:
                raise ValueError("anchored_le surfaces must be literal, non-symmetric surfaces.")
            if self.root_anchor is None or self.tip_anchor is None:
                raise ValueError("anchored_le surfaces require both root_anchor and tip_anchor.")
            if self.stations:
                raise ValueError("anchored_le surfaces do not support station segments.")
        if self.geometry_mode == "stationed":
            if self.root_anchor is not None or self.tip_anchor is not None:
                raise ValueError("stationed surfaces cannot use root_anchor or tip_anchor.")
            if not self.stations:
                raise ValueError("stationed surfaces require at least one station segment.")
            self._apply_station_summary()

    def _root_chord_value(self) -> float:
        """Return the root chord used for station-mode geometry."""
        if self.root_chord is not None:
            return float(self.root_chord)
        return float(2.0 * self.area / (self.span * (1.0 + self.taper)))

    def _apply_station_summary(self) -> None:
        """Derive whole-surface planform summaries from station segments."""
        root_chord = self._root_chord_value()
        projected_span = 0.0
        literal_area = 0.0
        total_x = 0.0
        total_secondary = 0.0
        previous_chord = root_chord
        for station in self.stations:
            segment_span = float(station.span)
            next_chord = station.end_chord(previous_chord)
            projected_span += segment_span
            literal_area += 0.5 * segment_span * (previous_chord + next_chord)
            total_x += segment_span * tan(radians(float(station.sweep_le_deg)))
            total_secondary += segment_span * tan(radians(float(station.dihedral_deg)))
            previous_chord = next_chord

        if projected_span <= 0.0:
            raise ValueError("stationed surfaces require positive total station span.")
        if literal_area <= 0.0:
            raise ValueError("stationed surfaces require positive derived area.")

        mirrored_horizontal = self.orientation == "horizontal" and self.symmetric
        area_factor = 2.0 if mirrored_horizontal else 1.0
        span_factor = 2.0 if mirrored_horizontal else 1.0
        self.span = float(span_factor * projected_span)
        self.area = float(area_factor * literal_area)
        self.taper = float(previous_chord / root_chord)
        self.sweep_le_deg = float(degrees(atan(total_x / projected_span)))
        self.dihedral_deg = float(degrees(atan(total_secondary / projected_span)))
        self.twist_tip_deg = float(self.stations[-1].twist_deg)
        self.tip_airfoil = str(self.stations[-1].airfoil)
        self.n_sections = max(int(self.n_sections), len(self.stations) + 1)

    def built_component_ids(self) -> list[str]:
        """Return the stable component IDs emitted by the geometry builder."""
        if self.orientation == "vertical" and self.symmetric:
            return [f"{self.component_id}_right", f"{self.component_id}_left"]
        return [self.component_id]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return {
            "component_id": self.component_id,
            "role": self.role,
            "orientation": self.orientation,
            "geometry_mode": self.geometry_mode,
            "symmetric": self.symmetric,
            "span": self.span,
            "area": self.area,
            "taper": self.taper,
            "root_chord": self.root_chord,
            "sweep_le_deg": self.sweep_le_deg,
            "dihedral_deg": self.dihedral_deg,
            "x_le": self.x_le,
            "y_le": self.y_le,
            "z_le": self.z_le,
            "twist_root_deg": self.twist_root_deg,
            "twist_tip_deg": self.twist_tip_deg,
            "root_airfoil": self.root_airfoil,
            "tip_airfoil": self.tip_airfoil,
            "n_sections": self.n_sections,
            "n_chordwise": self.n_chordwise,
            "n_spanwise": self.n_spanwise,
            "chordwise_spacing": self.chordwise_spacing,
            "spanwise_spacing": self.spanwise_spacing,
            "control_surfaces": [control.to_dict() for control in self.control_surfaces],
            "stations": [station.to_dict() for station in self.stations],
            "root_anchor": None if self.root_anchor is None else self.root_anchor.to_dict(),
            "tip_anchor": None if self.tip_anchor is None else self.tip_anchor.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LiftingSurfaceConfig":
        """Build the configuration from a plain dictionary."""
        return cls(
            component_id=data.get("component_id", "lifting_surface"),
            role=data.get("role", "other"),
            orientation=data.get("orientation", "horizontal"),
            geometry_mode=data.get("geometry_mode", "direct"),
            symmetric=data.get("symmetric", True),
            span=data.get("span", 1.0),
            area=data.get("area", 0.1),
            taper=data.get("taper", 0.8),
            root_chord=data.get("root_chord"),
            sweep_le_deg=data.get("sweep_le_deg", 0.0),
            dihedral_deg=data.get("dihedral_deg", 0.0),
            x_le=data.get("x_le", 0.0),
            y_le=data.get("y_le", 0.0),
            z_le=data.get("z_le", 0.0),
            twist_root_deg=data.get("twist_root_deg", 0.0),
            twist_tip_deg=data.get("twist_tip_deg", 0.0),
            root_airfoil=data.get("root_airfoil", "naca0010"),
            tip_airfoil=data.get("tip_airfoil", "naca0010"),
            n_sections=data.get("n_sections", 3),
            n_chordwise=data.get("n_chordwise", 8),
            n_spanwise=data.get("n_spanwise", 21),
            chordwise_spacing=data.get("chordwise_spacing", "cosine"),
            spanwise_spacing=data.get("spanwise_spacing", "cosine"),
            control_surfaces=[
                control if isinstance(control, ControlSurfaceConfig) else ControlSurfaceConfig.from_dict(control)
                for control in data.get("control_surfaces", [])
            ],
            stations=[
                station if isinstance(station, LiftingSurfaceStationConfig) else LiftingSurfaceStationConfig.from_dict(station)
                for station in data.get("stations", [])
            ],
            root_anchor=(
                None
                if data.get("root_anchor") is None
                else SurfaceAnchorConfig.from_dict(data.get("root_anchor"))
            ),
            tip_anchor=(
                None
                if data.get("tip_anchor") is None
                else SurfaceAnchorConfig.from_dict(data.get("tip_anchor"))
            ),
        )


def default_main_wing_surface() -> LiftingSurfaceConfig:
    """Return the default main-wing surface used by the reference definition."""
    return LiftingSurfaceConfig(
        component_id="main_wing",
        role="main_wing",
        orientation="horizontal",
        symmetric=True,
        span=1.8288,
        area=0.41806368,
        taper=0.65,
        sweep_le_deg=0.0,
        dihedral_deg=7.0,
        x_le=0.2286,
        y_le=0.0,
        z_le=0.03048,
        twist_root_deg=0.0,
        twist_tip_deg=0.0,
        root_airfoil="naca4412",
        tip_airfoil="naca4412",
        n_sections=3,
        n_chordwise=12,
        n_spanwise=36,
    )


def default_horizontal_tail_surface() -> LiftingSurfaceConfig:
    """Return the default horizontal-tail surface used by the reference definition."""
    return LiftingSurfaceConfig(
        component_id="horizontal_tail",
        role="horizontal_tail",
        orientation="horizontal",
        symmetric=True,
        span=0.6858,
        area=0.123950337843,
        taper=0.8,
        sweep_le_deg=10.0,
        dihedral_deg=0.0,
        x_le=0.8382,
        y_le=0.0,
        z_le=0.0,
        root_airfoil="naca0010",
        tip_airfoil="naca0010",
        n_sections=3,
        n_chordwise=8,
        n_spanwise=21,
    )


def default_vertical_tail_surface() -> LiftingSurfaceConfig:
    """Return the default centerline vertical-tail surface used by the reference definition."""
    return LiftingSurfaceConfig(
        component_id="vertical_tail",
        role="vertical_tail",
        orientation="vertical",
        symmetric=False,
        span=0.3048,
        area=0.06020771943,
        taper=0.7,
        sweep_le_deg=25.0,
        dihedral_deg=0.0,
        x_le=0.8382,
        y_le=0.0,
        z_le=0.0,
        root_airfoil="naca0010",
        tip_airfoil="naca0010",
        n_sections=3,
        n_chordwise=8,
        n_spanwise=21,
    )


def default_lifting_surfaces() -> list[LiftingSurfaceConfig]:
    """Return the default conventional lifting-surface set for a reference aircraft."""
    return [
        default_main_wing_surface(),
        default_horizontal_tail_surface(),
        default_vertical_tail_surface(),
    ]


@dataclass
class FuselageConfig:
    """Simple fuselage inputs for the canonical aircraft definition.

    Bare scalar dimensional inputs are stored in meters after normalization.
    """

    enabled: bool = True
    length: QuantityInput = 1.0668
    max_radius: QuantityInput = 0.05334
    n_sections: int = 21
    x_nose: QuantityInput = 0.0
    y_nose: QuantityInput = 0.0
    z_nose: QuantityInput = 0.0
    camber_start_z: QuantityInput = 0.0
    camber_end_z: QuantityInput = 0.0

    def __post_init__(self) -> None:
        """Normalize simple fuselage fields into canonical units."""
        self.enabled = bool(self.enabled)
        self.length = coerce_quantity("length", self.length, "m", "length")
        self.max_radius = coerce_quantity("max_radius", self.max_radius, "m", "length")
        self.n_sections = int(self.n_sections)
        self.x_nose = coerce_quantity("x_nose", self.x_nose, "m", "length")
        self.y_nose = coerce_quantity("y_nose", self.y_nose, "m", "length")
        self.z_nose = coerce_quantity("z_nose", self.z_nose, "m", "length")
        self.camber_start_z = coerce_quantity("camber_start_z", self.camber_start_z, "m", "length")
        self.camber_end_z = coerce_quantity("camber_end_z", self.camber_end_z, "m", "length")
        if self.length <= 0.0:
            raise ValueError("length must be positive.")
        if self.max_radius <= 0.0:
            raise ValueError("max_radius must be positive.")
        if self.n_sections < 3:
            raise ValueError("n_sections must be >= 3.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return {
            "enabled": self.enabled,
            "length": self.length,
            "max_radius": self.max_radius,
            "n_sections": self.n_sections,
            "x_nose": self.x_nose,
            "y_nose": self.y_nose,
            "z_nose": self.z_nose,
            "camber_start_z": self.camber_start_z,
            "camber_end_z": self.camber_end_z,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FuselageConfig":
        """Build the configuration from a plain dictionary."""
        return cls(
            enabled=data.get("enabled", True),
            length=data.get("length", 1.0668),
            max_radius=data.get("max_radius", 0.05334),
            n_sections=data.get("n_sections", 21),
            x_nose=data.get("x_nose", 0.0),
            y_nose=data.get("y_nose", 0.0),
            z_nose=data.get("z_nose", 0.0),
            camber_start_z=data.get("camber_start_z", 0.0),
            camber_end_z=data.get("camber_end_z", 0.0),
        )


@dataclass
class DesignVariableSpec:
    """Optimizer-facing metadata for a scalar design-variable path."""

    path: str
    label: str
    lower: float | None = None
    upper: float | None = None
    step: float | None = None
    unit: str = ""
    enabled: bool = True
    group: str = "geometry"

    def __post_init__(self) -> None:
        """Validate scalar optimizer metadata."""
        self.path = _coerce_required_string("path", self.path)
        self.label = _coerce_required_string("label", self.label)
        self.unit = "" if self.unit is None else str(self.unit)
        self.enabled = bool(self.enabled)
        self.group = _coerce_required_string("group", self.group)
        if self.lower is not None:
            self.lower = float(self.lower)
        if self.upper is not None:
            self.upper = float(self.upper)
        if self.step is not None:
            self.step = _coerce_positive_float("step", self.step)
        if self.lower is not None and not isfinite(self.lower):
            raise ValueError("lower must be finite when provided.")
        if self.upper is not None and not isfinite(self.upper):
            raise ValueError("upper must be finite when provided.")
        if self.lower is not None and self.upper is not None and self.lower > self.upper:
            raise ValueError("lower must be <= upper.")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the variable spec to a plain dictionary."""
        return {
            "path": self.path,
            "label": self.label,
            "lower": self.lower,
            "upper": self.upper,
            "step": self.step,
            "unit": self.unit,
            "enabled": self.enabled,
            "group": self.group,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DesignVariableSpec":
        """Build the variable spec from a plain dictionary."""
        return cls(
            path=data["path"],
            label=data.get("label", data["path"]),
            lower=data.get("lower"),
            upper=data.get("upper"),
            step=data.get("step"),
            unit=data.get("unit", ""),
            enabled=data.get("enabled", True),
            group=data.get("group", "geometry"),
        )


@dataclass
class AircraftDefinition:
    """Canonical aircraft definition shared across ACDT and Solar_UAS."""

    schema_version: str = SCHEMA_VERSION
    name: str = "Reference Solar UAV"
    description: str = (
        "Baseline aircraft definition for configuration, comparison, and "
        "downstream solar-layout work."
    )
    reference_geometry: ReferenceGeometryConfig = field(default_factory=ReferenceGeometryConfig)
    center_of_gravity: CenterOfGravityConfig = field(default_factory=CenterOfGravityConfig)
    lifting_surfaces: list[LiftingSurfaceConfig] = field(default_factory=default_lifting_surfaces)
    fuselage: FuselageConfig = field(default_factory=FuselageConfig)
    design_variables: list[DesignVariableSpec] = field(
        default_factory=lambda: [
            DesignVariableSpec(
                path="lifting_surfaces[main_wing].span",
                label="Main Wing Span",
                lower=14.0,
                upper=24.0,
                step=0.1,
                unit="m",
            ),
            DesignVariableSpec(
                path="lifting_surfaces[main_wing].area",
                label="Main Wing Area",
                lower=1.8,
                upper=4.5,
                step=0.05,
                unit="m2",
            ),
        ]
    )
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Coerce nested dictionaries into typed dataclasses and validate state."""
        self.schema_version = _coerce_required_string("schema_version", self.schema_version)
        self.name = _coerce_required_string("name", self.name)
        self.description = _coerce_optional_string(self.description)

        if isinstance(self.reference_geometry, dict):
            self.reference_geometry = ReferenceGeometryConfig.from_dict(self.reference_geometry)
        if isinstance(self.center_of_gravity, dict):
            self.center_of_gravity = CenterOfGravityConfig.from_dict(self.center_of_gravity)
        self.lifting_surfaces = [
            surface if isinstance(surface, LiftingSurfaceConfig) else LiftingSurfaceConfig.from_dict(surface)
            for surface in self.lifting_surfaces
        ]
        if not self.lifting_surfaces:
            raise ValueError("lifting_surfaces must contain at least one surface.")

        component_ids = [surface.component_id for surface in self.lifting_surfaces]
        duplicate_component_ids = sorted({surface_id for surface_id in component_ids if component_ids.count(surface_id) > 1})
        if duplicate_component_ids:
            raise ValueError(f"lifting_surfaces component_id values must be unique. Duplicates: {duplicate_component_ids}")

        main_wings = [surface for surface in self.lifting_surfaces if surface.role == "main_wing"]
        if len(main_wings) != 1:
            raise ValueError(
                "lifting_surfaces must contain exactly one role='main_wing' surface."
            )

        if isinstance(self.fuselage, dict):
            self.fuselage = FuselageConfig.from_dict(self.fuselage)
        self.design_variables = [
            variable if isinstance(variable, DesignVariableSpec) else DesignVariableSpec.from_dict(variable)
            for variable in self.design_variables
        ]
        self.extensions = _json_safe_copy("extensions", self.extensions)

    def surface_by_component_id(self, component_id: str) -> LiftingSurfaceConfig:
        """Return the canonical surface with the requested component ID."""
        normalized_component_id = _coerce_required_string("component_id", component_id)
        for surface in self.lifting_surfaces:
            if surface.component_id == normalized_component_id:
                return surface
        raise KeyError(f"No lifting surface exists with component_id {normalized_component_id!r}.")

    def main_wing_surface(self) -> LiftingSurfaceConfig:
        """Return the single canonical main-wing surface."""
        for surface in self.lifting_surfaces:
            if surface.role == "main_wing":
                return surface
        raise RuntimeError("AircraftDefinition is missing its required main wing.")

    def active_component_ids(self) -> list[str]:
        """Return stable buildable component identifiers for all active surfaces."""
        component_ids: list[str] = []
        for surface in self.lifting_surfaces:
            component_ids.extend(surface.built_component_ids())
        return component_ids

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full aircraft definition to a plain dictionary."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "reference_geometry": self.reference_geometry.to_dict(),
            "center_of_gravity": self.center_of_gravity.to_dict(),
            "lifting_surfaces": [surface.to_dict() for surface in self.lifting_surfaces],
            "fuselage": self.fuselage.to_dict(),
            "design_variables": [variable.to_dict() for variable in self.design_variables],
            "extensions": _json_safe_copy("extensions", self.extensions),
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the aircraft definition to formatted JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AircraftDefinition":
        """Build an aircraft definition from a plain dictionary.

        The v1 fixed-field schema is intentionally unsupported in this builder.
        """
        legacy_keys = [key for key in _LEGACY_SCHEMA_KEYS if key in data]
        if legacy_keys:
            legacy_list = ", ".join(legacy_keys)
            raise ValueError(
                "Legacy aircraft-definition schema fields are no longer supported: "
                f"{legacy_list}. Use lifting_surfaces instead."
            )

        defaults = cls()
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            name=data.get("name", defaults.name),
            description=data.get("description", defaults.description),
            reference_geometry=ReferenceGeometryConfig.from_dict(data.get("reference_geometry", {})),
            center_of_gravity=CenterOfGravityConfig.from_dict(_center_of_gravity_payload(data)),
            lifting_surfaces=[
                LiftingSurfaceConfig.from_dict(surface)
                for surface in data.get(
                    "lifting_surfaces",
                    [surface.to_dict() for surface in defaults.lifting_surfaces],
                )
            ],
            fuselage=FuselageConfig.from_dict(data.get("fuselage", {})),
            design_variables=[
                DesignVariableSpec.from_dict(variable)
                for variable in data.get("design_variables", [])
            ]
            or defaults.design_variables,
            extensions=data.get("extensions", {}),
        )

    @classmethod
    def from_json(cls, payload: str) -> "AircraftDefinition":
        """Build an aircraft definition from a JSON payload."""
        return cls.from_dict(json.loads(payload))


__all__ = [
    "AircraftDefinition",
    "CenterOfGravityConfig",
    "ControlSurfaceConfig",
    "DesignVariableSpec",
    "FuselageConfig",
    "LiftingSurfaceConfig",
    "LiftingSurfaceStationConfig",
    "ReferenceGeometryConfig",
    "SCHEMA_VERSION",
    "SURFACE_GEOMETRY_MODES",
    "SURFACE_ORIENTATIONS",
    "SURFACE_ROLES",
    "SurfaceAnchorConfig",
    "default_horizontal_tail_surface",
    "default_lifting_surfaces",
    "default_main_wing_surface",
    "default_vertical_tail_surface",
]
