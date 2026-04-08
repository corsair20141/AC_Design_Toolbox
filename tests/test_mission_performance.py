"""Focused tests for the mission-performance API."""

from __future__ import annotations

import math
import unittest
from pathlib import Path
from unittest.mock import patch

from ac_design_toolbox import (
    AnalyticMissionPerformanceModel,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
)
from ac_design_toolbox.atmosphere import standard_atmosphere
from ac_design_toolbox.mission import MissionPerformanceModel

try:
    from ac_design_toolbox.mission import AVLMissionPerformanceModel
except ImportError:
    AVLMissionPerformanceModel = None


class MissionPerformanceTests(unittest.TestCase):
    """Check the thin mission-performance API and its first-pass behavior."""

    def setUp(self) -> None:
        """Build a reusable aircraft-performance configuration for the tests."""
        self.config = MissionAircraftPerformanceConfig(
            mass_kg=12.0,
            wing_area_m2=2.4,
            aspect_ratio=14.0,
            oswald_efficiency=0.85,
            zero_lift_drag_coefficient=0.03,
            propulsive_efficiency=0.75,
            max_lift_coefficient=1.5,
            max_bank_deg=60.0,
            max_load_factor=3.0,
        )
        self.model = AnalyticMissionPerformanceModel(self.config)

    def test_operating_point_defaults_are_immutable(self) -> None:
        """Ensure defaults and validation behave predictably for operating points."""
        op = MissionOperatingPoint(
            phase_name="cruise",
            altitude_m=0.0,
            true_airspeed_m_s=20.0,
            climb_rate_m_s=0.0,
        )

        self.assertEqual(op.temp_shift_F, 0.0)
        self.assertEqual(dict(op.metadata), {})

        with self.assertRaises(TypeError):
            op.metadata["tag"] = "mutable"

        with self.assertRaises(ValueError):
            MissionOperatingPoint(
                phase_name="bad",
                altitude_m=0.0,
                true_airspeed_m_s=0.0,
                climb_rate_m_s=0.0,
            )

    def test_from_airplane_infers_reference_geometry(self) -> None:
        """Check the optional helper that builds a config from an airplane object."""
        try:
            from ac_design_toolbox.geometry.aircraft import simple_aircraft
        except ModuleNotFoundError:
            self.skipTest("AeroSandbox geometry helpers are unavailable in this environment.")

        airplane = simple_aircraft(name="Mission Test", S_w=10.0, AR_w=12.0, lambda_w=0.7)
        config = MissionAircraftPerformanceConfig.from_airplane(
            airplane,
            mass_kg=5.0,
            oswald_efficiency=0.82,
            zero_lift_drag_coefficient=0.028,
            propulsive_efficiency=0.72,
        )

        self.assertAlmostEqual(config.wing_area_m2, 10.0)
        self.assertAlmostEqual(config.aspect_ratio, 12.0)

    def test_straight_and_level_case_matches_closed_form_estimate(self) -> None:
        """Compare the straight-flight result against the expected analytic formulas."""
        op = MissionOperatingPoint(
            phase_name="cruise",
            altitude_m=500.0,
            true_airspeed_m_s=22.0,
            climb_rate_m_s=0.0,
        )
        result = self.model.evaluate(op)

        rho = float(standard_atmosphere(500.0)["rho"])
        q = 0.5 * rho * op.true_airspeed_m_s**2
        weight_newtons = self.config.mass_kg * 9.80665
        expected_cl = weight_newtons / (q * self.config.wing_area_m2)
        expected_cd = self.config.zero_lift_drag_coefficient + expected_cl**2 / (
            math.pi * self.config.aspect_ratio * self.config.oswald_efficiency
        )
        expected_drag = q * self.config.wing_area_m2 * expected_cd
        expected_power = expected_drag * op.true_airspeed_m_s / self.config.propulsive_efficiency

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.bank_deg, 0.0, places=7)
        self.assertAlmostEqual(result.pitch_deg, 0.0, places=7)
        self.assertAlmostEqual(result.load_factor, 1.0, places=7)
        self.assertAlmostEqual(result.dynamic_pressure_pa, q, places=7)
        self.assertAlmostEqual(result.lift_coefficient, expected_cl, places=7)
        self.assertAlmostEqual(result.drag_coefficient, expected_cd, places=7)
        self.assertAlmostEqual(result.drag_force_n, expected_drag, places=7)
        self.assertAlmostEqual(result.propulsion_power_w, expected_power, places=7)
        self.assertEqual(result.notes, "")

    def test_turning_and_climbing_case_infers_bank_and_load_factor(self) -> None:
        """Check the coupled climb-turn estimate for a feasible operating point."""
        op = MissionOperatingPoint(
            phase_name="climb_turn",
            altitude_m=1200.0,
            true_airspeed_m_s=28.0,
            climb_rate_m_s=3.5,
            turn_radius_m=90.0,
        )
        result = self.model.evaluate(op)

        gamma_rad = math.asin(op.climb_rate_m_s / op.true_airspeed_m_s)
        horizontal_speed_sq = op.true_airspeed_m_s**2 - op.climb_rate_m_s**2
        expected_bank_deg = math.degrees(
            math.atan(horizontal_speed_sq / (9.80665 * op.turn_radius_m * math.cos(gamma_rad)))
        )
        expected_load_factor = math.cos(gamma_rad) / math.cos(math.radians(expected_bank_deg))

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.pitch_deg, math.degrees(gamma_rad), places=7)
        self.assertAlmostEqual(result.bank_deg, expected_bank_deg, places=7)
        self.assertAlmostEqual(result.load_factor, expected_load_factor, places=7)
        self.assertGreater(result.drag_force_n, 0.0)
        self.assertGreater(result.propulsion_power_w, 0.0)

    def test_feasibility_failures_report_limit_violations(self) -> None:
        """Verify that simple CL, bank, and load-factor limits mark the point infeasible."""
        limited_model = AnalyticMissionPerformanceModel(
            MissionAircraftPerformanceConfig(
                mass_kg=12.0,
                wing_area_m2=2.4,
                aspect_ratio=14.0,
                oswald_efficiency=0.85,
                zero_lift_drag_coefficient=0.03,
                propulsive_efficiency=0.75,
                max_lift_coefficient=0.60,
                max_bank_deg=40.0,
                max_load_factor=1.40,
            )
        )
        op = MissionOperatingPoint(
            phase_name="tight_turn",
            altitude_m=0.0,
            true_airspeed_m_s=14.0,
            climb_rate_m_s=0.0,
            turn_radius_m=15.0,
        )
        result = limited_model.evaluate(op)

        self.assertFalse(result.feasible)
        self.assertIn("Lift coefficient", result.notes)
        self.assertIn("Load factor", result.notes)
        self.assertIn("Bank angle", result.notes)

    def test_model_matches_protocol(self) -> None:
        """Confirm the analytic evaluator satisfies the mission protocol."""
        self.assertIsInstance(self.model, MissionPerformanceModel)

    @unittest.skipUnless(AVLMissionPerformanceModel is not None, "AVL mission adapter dependencies are unavailable.")
    @patch("ac_design_toolbox.mission.avl.avl_trim_longitudinal")
    @patch("ac_design_toolbox.mission.avl.prepare_avl_airplane")
    def test_avl_model_wraps_trim_results(self, mock_prepare, mock_trim) -> None:
        """Check that the AVL-backed adapter preserves the mission API contract."""
        mock_prepare.return_value = {"control_index_map": {"aileron": 1, "elevator": 2, "rudder": 3, "flap": 4}}
        mock_trim.return_value = {
            "alpha_trim_deg": 4.0,
            "elevator_trim_deg": -1.5,
            "CL": 0.15,
            "Cm": 0.0,
            "CD": 0.041,
            "rho": 1.10,
            "newton2d_failure_reason": "",
        }

        model = AVLMissionPerformanceModel(
            airplane=object(),
            aircraft=self.config,
            avl_exe=Path("avl.exe"),
            working_directory=Path.cwd() / "test_runs" / "mission_avl",
        )
        op = MissionOperatingPoint(
            phase_name="climb_turn",
            altitude_m=1200.0,
            true_airspeed_m_s=28.0,
            climb_rate_m_s=3.5,
            turn_radius_m=90.0,
        )
        result = model.evaluate(op)

        gamma_rad = math.asin(op.climb_rate_m_s / op.true_airspeed_m_s)
        expected_pitch_deg = math.degrees(gamma_rad) + 4.0
        expected_q = 0.5 * 1.10 * op.true_airspeed_m_s**2
        expected_drag = expected_q * self.config.wing_area_m2 * 0.041

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.pitch_deg, expected_pitch_deg, places=7)
        self.assertAlmostEqual(result.drag_force_n, expected_drag, places=7)
        self.assertIn("AVL longitudinal trim solved alpha=4.000 deg and elevator=-1.500 deg.", result.notes)
        self.assertIn("Banked-turn effects enter through the target load factor only", result.notes)
        self.assertEqual(mock_prepare.call_count, 1)

        trim_kwargs = mock_trim.call_args.kwargs
        self.assertEqual(trim_kwargs["case_name"], "mission_avl_climb_turn")
        self.assertFalse(trim_kwargs["write_geom"])
        self.assertEqual(trim_kwargs["control_index_map"]["elevator"], 2)


if __name__ == "__main__":
    unittest.main()
