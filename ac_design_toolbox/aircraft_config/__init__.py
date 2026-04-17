"""Public aircraft-configuration interfaces for AC_Design_Toolbox."""

from ac_design_toolbox.aircraft_config.models import (
    AircraftDefinition,
    DesignVariableSpec,
    FuselageConfig,
    MainWingConfig,
    ReferenceGeometryConfig,
    SCHEMA_VERSION,
    TAIL_TYPES,
    TailAssemblyConfig,
    TailSurfaceConfig,
)
from ac_design_toolbox.aircraft_config.variables import (
    collect_component_ids,
    design_variable_records,
    resolve_path_value,
)

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
    "collect_component_ids",
    "design_variable_records",
    "resolve_path_value",
]

try:
    from ac_design_toolbox.aircraft_config.builder import build_aircraft
    from ac_design_toolbox.aircraft_config.rendering import (
        render_aircraft_plotly,
        render_aircraft_three_view_image,
    )

    __all__ += [
        "build_aircraft",
        "render_aircraft_plotly",
        "render_aircraft_three_view_image",
    ]
except ModuleNotFoundError:
    # Geometry-backed aircraft building and rendering require AeroSandbox and
    # related visualization dependencies.
    pass
