"""Mission-performance interfaces for unit-aware air-relative operating points."""

from ac_design_toolbox.mission.performance import (
    AnalyticMissionPerformanceModel,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
    MissionPerformanceModel,
    MissionPerformancePoint,
)

__all__ = [
    "AnalyticMissionPerformanceModel",
    "MissionAircraftPerformanceConfig",
    "MissionOperatingPoint",
    "MissionPerformanceModel",
    "MissionPerformancePoint",
]

try:
    from ac_design_toolbox.mission.avl import AVLMissionPerformanceModel
    from ac_design_toolbox.mission.avl_polar import (
        AVLAeroPolarConfig,
        AVLAeroPolarTable,
        AVLPolarMissionPerformanceModel,
    )

    __all__.extend([
        "AVLMissionPerformanceModel",
        "AVLAeroPolarConfig",
        "AVLAeroPolarTable",
        "AVLPolarMissionPerformanceModel",
    ])
except ModuleNotFoundError:
    # The AVL-backed mission path depends on AeroSandbox and the AVL stack.
    pass
