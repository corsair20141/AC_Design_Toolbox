"""Tests for the high-level package API surface."""

import unittest

from ac_design_toolbox import (
    AVLCaseConfig,
    AVLTrimConfig,
    AnalyticMissionPerformanceModel,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
)
from ac_design_toolbox.api import build_simple_aircraft, prepare_avl_airplane, run_case, trim_longitudinal_case
from ac_design_toolbox.mission import MissionPerformancePoint

try:
    from ac_design_toolbox import AVLMissionPerformanceModel
except ImportError:
    AVLMissionPerformanceModel = None


class PackageApiTests(unittest.TestCase):
    """Check the high-level API objects that should be importable without AeroSandbox."""

    def test_top_level_exports_include_high_level_configs(self) -> None:
        case = AVLCaseConfig()
        trim = AVLTrimConfig()

        self.assertEqual(case.case_name, "avl_case")
        self.assertEqual(trim.case_name, "trim_case")

    def test_top_level_exports_include_mission_performance_objects(self) -> None:
        """Check the mission-performance objects exposed at the package root."""
        config = MissionAircraftPerformanceConfig(
            mass_kg=5.0,
            wing_area_m2=1.2,
            aspect_ratio=12.0,
            oswald_efficiency=0.82,
            zero_lift_drag_coefficient=0.03,
            propulsive_efficiency=0.75,
        )
        model = AnalyticMissionPerformanceModel(config)
        op = MissionOperatingPoint(
            phase_name="cruise",
            altitude_m=0.0,
            true_airspeed_m_s=20.0,
            climb_rate_m_s=0.0,
        )
        result = model.evaluate(op)

        self.assertTrue(result.feasible)
        self.assertIsInstance(result, MissionPerformancePoint)

    def test_high_level_callables_are_importable(self) -> None:
        self.assertTrue(callable(build_simple_aircraft))
        self.assertTrue(callable(prepare_avl_airplane))
        self.assertTrue(callable(run_case))
        self.assertTrue(callable(trim_longitudinal_case))

    def test_optional_avl_mission_model_imports_when_dependencies_exist(self) -> None:
        """Check the optional AVL-backed mission model import surface."""
        if AVLMissionPerformanceModel is None:
            self.skipTest("AVL mission adapter dependencies are unavailable.")

        self.assertTrue(callable(AVLMissionPerformanceModel))


if __name__ == "__main__":
    unittest.main()
