"""Canonical aircraft-definition models for installable cross-project use.

This module defines a typed, JSON-round-trippable aircraft configuration
schema. The schema is intentionally explicit and first-pass: it focuses on
geometry, stable component identifiers, and optimizer-facing metadata rather
than trying to represent every possible aircraft design feature up front.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from math import isfinite
from typing import Any

from ac_design_toolbox.mission.units import QuantityInput, coerce_quantity


SCHEMA_VERSION = "acdt_aircraft_definition_v1"
TAIL_TYPES = ("conventional", "t_tail", "v_tail", "h_tail", "y_tail")


def _coerce_required_string(name: str, value: Any) -> str:
    """Return a stripped required string value."""
    text = "" if value is None else str(value).strip()
    if not text:
        raise ValueError(f"{name} must be a non-empty string.")
    return text


def _coerce_optional_string(value: Any) -> str:
    """Return a plain string for optional descriptive fields."""
    return "" if value is None else str(value)


def _coerce_fraction(name: str, value: Any) -> float:
    """Return a finite scalar fraction in the closed interval [0, 1]."""
    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")
    if scalar_value < 0.0 or scalar_value > 1.0:
        raise ValueError(f"{name} must lie in [0, 1].")
    return scalar_value


def _coerce_positive_float(name: str, value: Any) -> float:
    """Return a positive finite scalar float."""
    scalar_value = float(value)
    if not isfinite(scalar_value):
        raise ValueError(f"{name} must be finite.")
    if scalar_value <= 0.0:
        raise ValueError(f"{name} must be positive.")
    return scalar_value


def _json_safe_copy(name: str, value: Any) -> Any:
    """Return a JSON-safe deep copy of extension-like payloads."""
    try:
        return json.loads(json.dumps(value))
    except TypeError as exc:
        raise TypeError(f"{name} must be JSON-serializable.") from exc


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
class MainWingConfig:
    """Main-wing geometry definition used by the canonical aircraft schema.

    Bare scalar dimensional inputs are stored as meters, square meters, and
    degrees after normalization.
    """

    component_id: str = "main_wing"
    span: QuantityInput = 1.8288
    area: QuantityInput = 0.41806368
    taper: float = 0.65
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

    def __post_init__(self) -> None:
        """Normalize the wing geometry into canonical computational units."""
        self.component_id = _coerce_required_string("component_id", self.component_id)
        self.span = coerce_quantity("span", self.span, "m", "length")
        self.area = coerce_quantity("area", self.area, "m2", "area")
        self.taper = _coerce_positive_float("taper", self.taper)
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return {
            "component_id": self.component_id,
            "span": self.span,
            "area": self.area,
            "taper": self.taper,
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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MainWingConfig":
        """Build the configuration from a plain dictionary."""
        return cls(
            component_id=data.get("component_id", "main_wing"),
            span=data.get("span", 1.8288),
            area=data.get("area", 0.41806368),
            taper=data.get("taper", 0.65),
            sweep_le_deg=data.get("sweep_le_deg", 0.0),
            dihedral_deg=data.get("dihedral_deg", 7.0),
            x_le=data.get("x_le", 0.2286),
            y_le=data.get("y_le", 0.0),
            z_le=data.get("z_le", 0.03048),
            twist_root_deg=data.get("twist_root_deg", 0.0),
            twist_tip_deg=data.get("twist_tip_deg", 0.0),
            root_airfoil=data.get("root_airfoil", "naca4412"),
            tip_airfoil=data.get("tip_airfoil", "naca4412"),
            n_sections=data.get("n_sections", 3),
            n_chordwise=data.get("n_chordwise", 12),
            n_spanwise=data.get("n_spanwise", 36),
            chordwise_spacing=data.get("chordwise_spacing", "cosine"),
            spanwise_spacing=data.get("spanwise_spacing", "cosine"),
        )


@dataclass
class TailSurfaceConfig:
    """Tail-surface geometry definition for horizontal, vertical, or V-tail use.

    Bare scalar dimensional inputs are stored as meters, square meters, and
    degrees after normalization.
    """

    component_id: str
    span: QuantityInput
    area: QuantityInput
    taper: float = 0.8
    sweep_le_deg: QuantityInput = 20.0
    dihedral_deg: QuantityInput = 0.0
    x_le: QuantityInput = 0.0
    y_le: QuantityInput = 0.0
    z_le: QuantityInput = 0.0
    twist_root_deg: QuantityInput = 0.0
    twist_tip_deg: QuantityInput = 0.0
    root_airfoil: str = "naca0010"
    tip_airfoil: str = "naca0010"
    n_sections: int = 3
    n_chordwise: int = 8
    n_spanwise: int = 21
    chordwise_spacing: str = "cosine"
    spanwise_spacing: str = "cosine"

    def __post_init__(self) -> None:
        """Normalize the tail-surface definition into canonical units."""
        self.component_id = _coerce_required_string("component_id", self.component_id)
        self.span = coerce_quantity("span", self.span, "m", "length")
        self.area = coerce_quantity("area", self.area, "m2", "area")
        self.taper = _coerce_positive_float("taper", self.taper)
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

    def to_dict(self) -> dict[str, Any]:
        """Serialize the configuration to a plain dictionary."""
        return {
            "component_id": self.component_id,
            "span": self.span,
            "area": self.area,
            "taper": self.taper,
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
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TailSurfaceConfig":
        """Build the configuration from a plain dictionary."""
        return cls(
            component_id=data["component_id"],
            span=data["span"],
            area=data["area"],
            taper=data.get("taper", 0.8),
            sweep_le_deg=data.get("sweep_le_deg", 20.0),
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
        )


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
    """Optimizer-facing metadata for a scalar design variable path."""

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
class TailAssemblyConfig:
    """Tail-family selection and associated tail-geometry definitions."""

    tail_type: str = "conventional"
    horizontal_tail: TailSurfaceConfig = field(
        default_factory=lambda: TailSurfaceConfig(
            component_id="horizontal_tail",
            span=0.6858,
            area=0.123950337843,
            taper=0.8,
            sweep_le_deg=10.0,
            dihedral_deg=0.0,
            x_le=0.8382,
            y_le=0.0,
            z_le=0.0,
        )
    )
    vertical_tail: TailSurfaceConfig = field(
        default_factory=lambda: TailSurfaceConfig(
            component_id="vertical_tail",
            span=0.3048,
            area=0.06020771943,
            taper=0.7,
            sweep_le_deg=25.0,
            dihedral_deg=0.0,
            x_le=0.8382,
            y_le=0.0,
            z_le=0.0,
        )
    )
    v_tail_surface: TailSurfaceConfig = field(
        default_factory=lambda: TailSurfaceConfig(
            component_id="v_tail_surface",
            span=2.1,
            area=0.28,
            taper=0.8,
            sweep_le_deg=18.0,
            dihedral_deg=45.0,
            x_le=2.5,
            y_le=0.0,
            z_le=0.0,
        )
    )
    t_tail_mount_fraction: float = 1.0

    def __post_init__(self) -> None:
        """Validate the selected tail family and nested geometry."""
        self.tail_type = _coerce_required_string("tail_type", self.tail_type)
        if self.tail_type not in TAIL_TYPES:
            raise ValueError(f"tail_type must be one of {TAIL_TYPES}, got {self.tail_type!r}.")
        if isinstance(self.horizontal_tail, dict):
            self.horizontal_tail = TailSurfaceConfig.from_dict(self.horizontal_tail)
        if isinstance(self.vertical_tail, dict):
            self.vertical_tail = TailSurfaceConfig.from_dict(self.vertical_tail)
        if isinstance(self.v_tail_surface, dict):
            self.v_tail_surface = TailSurfaceConfig.from_dict(self.v_tail_surface)
        self.t_tail_mount_fraction = _coerce_fraction("t_tail_mount_fraction", self.t_tail_mount_fraction)

    def active_component_ids(self) -> list[str]:
        """Return the stable component identifiers implied by the tail family."""
        if self.tail_type in {"conventional", "t_tail"}:
            return [
                self.horizontal_tail.component_id,
                self.vertical_tail.component_id,
            ]
        if self.tail_type == "h_tail":
            return [
                self.horizontal_tail.component_id,
                f"{self.vertical_tail.component_id}_right",
                f"{self.vertical_tail.component_id}_left",
            ]
        if self.tail_type == "y_tail":
            return [
                self.vertical_tail.component_id,
                f"{self.v_tail_surface.component_id}_right",
                f"{self.v_tail_surface.component_id}_left",
            ]
        base_id = self.v_tail_surface.component_id
        return [f"{base_id}_right", f"{base_id}_left"]

    def to_dict(self) -> dict[str, Any]:
        """Serialize the tail assembly to a plain dictionary."""
        return {
            "tail_type": self.tail_type,
            "horizontal_tail": self.horizontal_tail.to_dict(),
            "vertical_tail": self.vertical_tail.to_dict(),
            "v_tail_surface": self.v_tail_surface.to_dict(),
            "t_tail_mount_fraction": self.t_tail_mount_fraction,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TailAssemblyConfig":
        """Build the tail assembly from a plain dictionary."""
        default_tail = cls()
        return cls(
            tail_type=data.get("tail_type", "conventional"),
            horizontal_tail=TailSurfaceConfig.from_dict(
                data.get("horizontal_tail", default_tail.horizontal_tail.to_dict())
            ),
            vertical_tail=TailSurfaceConfig.from_dict(
                data.get("vertical_tail", default_tail.vertical_tail.to_dict())
            ),
            v_tail_surface=TailSurfaceConfig.from_dict(
                data.get("v_tail_surface", default_tail.v_tail_surface.to_dict())
            ),
            t_tail_mount_fraction=data.get("t_tail_mount_fraction", 1.0),
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
    main_wing: MainWingConfig = field(default_factory=MainWingConfig)
    tail_assembly: TailAssemblyConfig = field(default_factory=TailAssemblyConfig)
    fuselage: FuselageConfig = field(default_factory=FuselageConfig)
    design_variables: list[DesignVariableSpec] = field(
        default_factory=lambda: [
            DesignVariableSpec(
                path="main_wing.span",
                label="Wing Span",
                lower=14.0,
                upper=24.0,
                step=0.1,
                unit="m",
            ),
            DesignVariableSpec(
                path="main_wing.area",
                label="Wing Area",
                lower=1.8,
                upper=4.5,
                step=0.05,
                unit="m2",
            ),
            DesignVariableSpec(
                path="tail_assembly.horizontal_tail.area",
                label="Horizontal Tail Area",
                lower=0.4,
                upper=1.2,
                step=0.02,
                unit="m2",
            ),
        ]
    )
    extensions: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Coerce nested dictionaries into typed dataclasses and validate JSON state."""
        self.schema_version = _coerce_required_string("schema_version", self.schema_version)
        self.name = _coerce_required_string("name", self.name)
        self.description = _coerce_optional_string(self.description)
        if isinstance(self.reference_geometry, dict):
            self.reference_geometry = ReferenceGeometryConfig.from_dict(self.reference_geometry)
        if isinstance(self.main_wing, dict):
            self.main_wing = MainWingConfig.from_dict(self.main_wing)
        if isinstance(self.tail_assembly, dict):
            self.tail_assembly = TailAssemblyConfig.from_dict(self.tail_assembly)
        if isinstance(self.fuselage, dict):
            self.fuselage = FuselageConfig.from_dict(self.fuselage)
        self.design_variables = [
            variable if isinstance(variable, DesignVariableSpec) else DesignVariableSpec.from_dict(variable)
            for variable in self.design_variables
        ]
        self.extensions = _json_safe_copy("extensions", self.extensions)

    def active_component_ids(self) -> list[str]:
        """Return stable component identifiers for the currently active surfaces."""
        component_ids = [self.main_wing.component_id]
        component_ids.extend(self.tail_assembly.active_component_ids())
        return component_ids

    def to_dict(self) -> dict[str, Any]:
        """Serialize the full aircraft definition to a plain dictionary."""
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "reference_geometry": self.reference_geometry.to_dict(),
            "main_wing": self.main_wing.to_dict(),
            "tail_assembly": self.tail_assembly.to_dict(),
            "fuselage": self.fuselage.to_dict(),
            "design_variables": [variable.to_dict() for variable in self.design_variables],
            "extensions": _json_safe_copy("extensions", self.extensions),
        }

    def to_json(self, *, indent: int = 2) -> str:
        """Serialize the aircraft definition to formatted JSON."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AircraftDefinition":
        """Build an aircraft definition from a plain dictionary."""
        defaults = cls()
        return cls(
            schema_version=data.get("schema_version", SCHEMA_VERSION),
            name=data.get("name", defaults.name),
            description=data.get("description", defaults.description),
            reference_geometry=ReferenceGeometryConfig.from_dict(data.get("reference_geometry", {})),
            main_wing=MainWingConfig.from_dict(data.get("main_wing", {})),
            tail_assembly=TailAssemblyConfig.from_dict(data.get("tail_assembly", {})),
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
    "DesignVariableSpec",
    "FuselageConfig",
    "MainWingConfig",
    "ReferenceGeometryConfig",
    "SCHEMA_VERSION",
    "TAIL_TYPES",
    "TailAssemblyConfig",
    "TailSurfaceConfig",
]
