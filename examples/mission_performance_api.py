"""Minimal example for the unit-aware mission-performance interface.

The default `main()` path stays analytic so the example runs without AVL.
An optional helper below shows how to construct the AVL-backed adapter when
the local environment includes AeroSandbox and an AVL executable.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Allow the example to run directly from the repository without installation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ac_design_toolbox.mission import (
    AnalyticMissionPerformanceModel,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
)


def main() -> None:
    """Evaluate a single air-relative operating point with the analytic model."""
    config = MissionAircraftPerformanceConfig(
        mass=(26.455, "lb"),
        wing_area=[25.8334, "sqft"],
        aspect_ratio=14.0,
        oswald_efficiency=0.85,
        zero_lift_drag_coefficient=0.03,
        propulsive_efficiency=0.75,
        max_lift_coefficient=1.30,
        max_bank=(55.0, "deg"),
        max_load_factor=2.5,
    )
    model = AnalyticMissionPerformanceModel(config)

    operating_point = MissionOperatingPoint(
        phase_name="climb_turn",
        altitude=[3937.01, "ft"],
        airspeed=(54.4276, "kts"),
        climb_rate=[700.0, "ft/min"],
        turn_radius=(295.276, "ft"),
        temp_shift=(2.0, "degC"),
        metadata={"source": "example"},
    )

    print(f"Normalized altitude: {operating_point.altitude:.3f} m")
    print(f"Normalized airspeed: {operating_point.airspeed:.3f} m/s")
    print(f"Normalized climb rate: {operating_point.climb_rate:.3f} m/s")
    result = model.evaluate(operating_point)
    print(result)


def build_optional_avl_model() -> Any | None:
    """Return an AVL-backed mission model when the local dependencies are available."""
    try:
        from ac_design_toolbox.geometry.aircraft import simple_aircraft
        from ac_design_toolbox.mission import AVLMissionPerformanceModel
    except ModuleNotFoundError:
        return None

    avl_exe = REPO_ROOT / "avl.exe"
    if not avl_exe.exists():
        return None

    airplane = simple_aircraft(
        name="Mission Example Aircraft",
        S_w=2.4,
        AR_w=14.0,
        lambda_w=0.7,
        span_frac_aileron=(0.65, 0.95),
        b_ht=0.9,
        S_ht=0.35,
        lambda_ht=0.8,
        L_ht=1.2,
        span_frac_elevator=(0.3, 0.95),
    )
    config = MissionAircraftPerformanceConfig.from_airplane(
        airplane,
        mass=(26.455, "lbm"),
        oswald_efficiency=0.85,
        zero_lift_drag_coefficient=0.03,
        propulsive_efficiency=0.75,
        max_lift_coefficient=1.30,
        max_bank=(55.0, "deg"),
        max_load_factor=2.5,
    )

    return AVLMissionPerformanceModel(
        airplane=airplane,
        aircraft=config,
        avl_exe=avl_exe,
        working_directory=REPO_ROOT / "example_runs" / "mission_avl",
    )


if __name__ == "__main__":
    main()
