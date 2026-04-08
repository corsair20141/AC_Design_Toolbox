"""Tests for the high-level package API surface."""

import unittest

from ac_design_toolbox import AVLCaseConfig, AVLTrimConfig
from ac_design_toolbox.api import build_simple_aircraft, prepare_avl_airplane, run_case, trim_longitudinal_case


class PackageApiTests(unittest.TestCase):
    """Check the high-level API objects that should be importable without AeroSandbox."""

    def test_top_level_exports_include_high_level_configs(self) -> None:
        case = AVLCaseConfig()
        trim = AVLTrimConfig()

        self.assertEqual(case.case_name, "avl_case")
        self.assertEqual(trim.case_name, "trim_case")

    def test_high_level_callables_are_importable(self) -> None:
        self.assertTrue(callable(build_simple_aircraft))
        self.assertTrue(callable(prepare_avl_airplane))
        self.assertTrue(callable(run_case))
        self.assertTrue(callable(trim_longitudinal_case))


if __name__ == "__main__":
    unittest.main()
