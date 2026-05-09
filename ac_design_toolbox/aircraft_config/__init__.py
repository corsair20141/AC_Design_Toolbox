"""Public aircraft-configuration interfaces for AC_Design_Toolbox."""

from ac_design_toolbox.aircraft_config.models import (
    AircraftDefinition,
    ControlSurfaceConfig,
    DesignVariableSpec,
    FuselageConfig,
    LiftingSurfaceConfig,
    ReferenceGeometryConfig,
    SCHEMA_VERSION,
    SURFACE_GEOMETRY_MODES,
    SURFACE_ORIENTATIONS,
    SURFACE_ROLES,
    SurfaceAnchorConfig,
    default_horizontal_tail_surface,
    default_lifting_surfaces,
    default_main_wing_surface,
    default_vertical_tail_surface,
)
from ac_design_toolbox.aircraft_config.sizing import (
    PlanformSizingResult,
    canted_pair_projected_area_factor,
    mean_aerodynamic_chord_spanwise_station,
    planform_quarter_chord_x,
    solve_canted_pair_surface_area_from_horizontal_volume_coefficient,
    solve_canted_pair_surface_area_from_vertical_volume_coefficient,
    solve_horizontal_tail_area_from_volume_coefficient,
    solve_planform,
    solve_twin_vertical_tail_surface_area_from_volume_coefficient,
    solve_vertical_tail_area_from_volume_coefficient,
)
from ac_design_toolbox.aircraft_config.variables import (
    collect_component_ids,
    design_variable_records,
    resolve_path_value,
)

__all__ = [
    "AircraftDefinition",
    "ControlSurfaceConfig",
    "DesignVariableSpec",
    "FuselageConfig",
    "LiftingSurfaceConfig",
    "PlanformSizingResult",
    "ReferenceGeometryConfig",
    "SCHEMA_VERSION",
    "SURFACE_GEOMETRY_MODES",
    "SURFACE_ORIENTATIONS",
    "SURFACE_ROLES",
    "SurfaceAnchorConfig",
    "canted_pair_projected_area_factor",
    "collect_component_ids",
    "default_horizontal_tail_surface",
    "default_lifting_surfaces",
    "default_main_wing_surface",
    "default_vertical_tail_surface",
    "design_variable_records",
    "mean_aerodynamic_chord_spanwise_station",
    "planform_quarter_chord_x",
    "resolve_path_value",
    "solve_canted_pair_surface_area_from_horizontal_volume_coefficient",
    "solve_canted_pair_surface_area_from_vertical_volume_coefficient",
    "solve_horizontal_tail_area_from_volume_coefficient",
    "solve_planform",
    "solve_twin_vertical_tail_surface_area_from_volume_coefficient",
    "solve_vertical_tail_area_from_volume_coefficient",
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
except (ImportError, ModuleNotFoundError):
    # Geometry-backed aircraft building and rendering require AeroSandbox and
    # related visualization dependencies.
    pass
