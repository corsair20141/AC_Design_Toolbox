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
from ac_design_toolbox.mission import MissionPerformanceModel, MissionPerformancePoint
from ac_design_toolbox.mission.units import convert_value

try:
    from ac_design_toolbox.mission import AVLMissionPerformanceModel
except ImportError:
    AVLMissionPerformanceModel = None


FT_TO_M = 0.3048
KTS_TO_M_S = 0.5144444444444445
FT2_TO_M2 = 0.09290304
LBM_TO_KG = 0.45359237
LBF_TO_N = 4.4482216152605


class MissionPerformanceTests(unittest.TestCase):
    """Check the thin mission-performance API and its first-pass behavior."""

    def setUp(self) -> None:
        """Build a reusable aircraft-performance configuration for the tests."""
        self.config = MissionAircraftPerformanceConfig(
            mass=12.0,
            wing_area=2.4,
            aspect_ratio=14.0,
            oswald_efficiency=0.85,
            zero_lift_drag_coefficient=0.03,
            propulsive_efficiency=0.75,
            max_lift_coefficient=1.5,
            max_bank=60.0,
            max_load_factor=3.0,
        )
        self.model = AnalyticMissionPerformanceModel(self.config)

    def test_public_dataclasses_normalize_units_and_freeze_metadata(self) -> None:
        """Check the unit-aware mission dataclasses at the public API boundary."""
        op = MissionOperatingPoint(
            phase_name="cruise",
            altitude=[1000.0, "ft"],
            airspeed=(20.0, "m/s"),
            climb_rate=[300.0, "ft/min"],
            bank_hint=(15.0, "deg"),
            pitch_hint=[2.5, "deg"],
            temp_shift=(10.0, "degC"),
        )
        config = MissionAircraftPerformanceConfig(
            mass=(12.0 / LBM_TO_KG, "lb"),
            wing_area=[2.4 / FT2_TO_M2, "sqft"],
            aspect_ratio=14.0,
            oswald_efficiency=0.85,
            zero_lift_drag_coefficient=0.03,
            propulsive_efficiency=0.75,
            max_bank=(55.0, "deg"),
        )
        result = MissionPerformancePoint(
            feasible=1,
            bank=[30.0, "deg"],
            pitch=(5.0, "deg"),
            load_factor=1.2,
            propulsion_power=(1500.0, "w"),
            drag_force=(10.0, "lbf"),
            dynamic_pressure=(250.0, "pa"),
            air_density=(1.225, "kg/m3"),
            notes="normalized",
        )

        self.assertAlmostEqual(op.altitude, 1000.0 * FT_TO_M, places=7)
        self.assertAlmostEqual(op.airspeed, 20.0, places=7)
        self.assertAlmostEqual(op.climb_rate, 300.0 * FT_TO_M / 60.0, places=7)
        self.assertAlmostEqual(op.bank_hint, 15.0, places=7)
        self.assertAlmostEqual(op.pitch_hint, 2.5, places=7)
        self.assertAlmostEqual(op.temp_shift, 18.0, places=7)
        self.assertEqual(dict(op.metadata), {})

        with self.assertRaises(TypeError):
            op.metadata["tag"] = "mutable"

        self.assertAlmostEqual(config.mass, 12.0, places=7)
        self.assertAlmostEqual(config.wing_area, 2.4, places=7)
        self.assertAlmostEqual(config.max_bank, 55.0, places=7)

        self.assertIs(result.feasible, True)
        self.assertAlmostEqual(result.bank, 30.0, places=7)
        self.assertAlmostEqual(result.pitch, 5.0, places=7)
        self.assertAlmostEqual(result.propulsion_power, 1500.0, places=7)
        self.assertAlmostEqual(result.drag_force, 10.0 * LBF_TO_N, places=7)
        self.assertAlmostEqual(result.dynamic_pressure, 250.0, places=7)
        self.assertAlmostEqual(result.air_density, 1.225, places=7)

    def test_direct_unit_helper_handles_speed_and_rate_families(self) -> None:
        """Check direct helper conversions where units appear in more than one family."""
        self.assertAlmostEqual(convert_value(30.0, "m_s", "kts"), 30.0 / KTS_TO_M_S, places=7)
        self.assertAlmostEqual(convert_value(500.0, "ft/min", "m_s"), 500.0 * FT_TO_M / 60.0, places=7)

    def test_clean_break_and_invalid_units_fail(self) -> None:
        """Verify malformed quantities, unsupported units, and old kwargs fail clearly."""
        with self.assertRaises(ValueError):
            MissionOperatingPoint(
                phase_name="bad",
                altitude=0.0,
                airspeed=(20.0, "mph"),
                climb_rate=0.0,
            )

        with self.assertRaises(TypeError):
            MissionOperatingPoint(
                phase_name="bad",
                altitude=[0.0, "m", "extra"],
                airspeed=20.0,
                climb_rate=0.0,
            )

        with self.assertRaises(TypeError):
            MissionOperatingPoint(
                phase_name="legacy",
                altitude_m=0.0,
                true_airspeed_m_s=20.0,
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
            mass=(5.0 / LBM_TO_KG, "lbm"),
            oswald_efficiency=0.82,
            zero_lift_drag_coefficient=0.028,
            propulsive_efficiency=0.72,
        )

        self.assertAlmostEqual(config.mass, 5.0, places=7)
        self.assertAlmostEqual(config.wing_area, 10.0, places=7)
        self.assertAlmostEqual(config.aspect_ratio, 12.0, places=7)

    def test_equivalent_inputs_preserve_normalized_values_and_results(self) -> None:
        """Check tuple/list inputs normalize to the same state and model outputs."""
        canonical_config = MissionAircraftPerformanceConfig(
            mass=12.0,
            wing_area=2.4,
            aspect_ratio=14.0,
            oswald_efficiency=0.85,
            zero_lift_drag_coefficient=0.03,
            propulsive_efficiency=0.75,
            max_lift_coefficient=1.5,
            max_bank=60.0,
            max_load_factor=3.0,
        )
        quantity_config = MissionAircraftPerformanceConfig(
            mass=(12.0 / LBM_TO_KG, "lb"),
            wing_area=[2.4 / FT2_TO_M2, "sqft"],
            aspect_ratio=14.0,
            oswald_efficiency=0.85,
            zero_lift_drag_coefficient=0.03,
            propulsive_efficiency=0.75,
            max_lift_coefficient=1.5,
            max_bank=(60.0, "deg"),
            max_load_factor=3.0,
        )

        canonical_op = MissionOperatingPoint(
            phase_name="cruise",
            altitude=500.0,
            airspeed=22.0,
            climb_rate=0.0,
        )
        quantity_op = MissionOperatingPoint(
            phase_name="cruise",
            altitude=[500.0 / FT_TO_M, "ft"],
            airspeed=(22.0 / KTS_TO_M_S, "kts"),
            climb_rate=[0.0, "ft/min"],
        )

        self.assertAlmostEqual(quantity_config.mass, canonical_config.mass, places=7)
        self.assertAlmostEqual(quantity_config.wing_area, canonical_config.wing_area, places=7)
        self.assertAlmostEqual(quantity_op.altitude, canonical_op.altitude, places=7)
        self.assertAlmostEqual(quantity_op.airspeed, canonical_op.airspeed, places=7)
        self.assertAlmostEqual(quantity_op.climb_rate, canonical_op.climb_rate, places=7)

        canonical_result = AnalyticMissionPerformanceModel(canonical_config).evaluate(canonical_op)
        quantity_result = AnalyticMissionPerformanceModel(quantity_config).evaluate(quantity_op)

        self.assertEqual(quantity_result.feasible, canonical_result.feasible)
        self.assertAlmostEqual(quantity_result.bank, canonical_result.bank, places=7)
        self.assertAlmostEqual(quantity_result.pitch, canonical_result.pitch, places=7)
        self.assertAlmostEqual(quantity_result.load_factor, canonical_result.load_factor, places=7)
        self.assertAlmostEqual(quantity_result.propulsion_power, canonical_result.propulsion_power, places=7)
        self.assertAlmostEqual(quantity_result.drag_force, canonical_result.drag_force, places=7)
        self.assertAlmostEqual(quantity_result.dynamic_pressure, canonical_result.dynamic_pressure, places=7)
        self.assertAlmostEqual(quantity_result.air_density, canonical_result.air_density, places=7)
        self.assertAlmostEqual(quantity_result.lift_coefficient, canonical_result.lift_coefficient, places=7)
        self.assertAlmostEqual(quantity_result.drag_coefficient, canonical_result.drag_coefficient, places=7)

    def test_straight_and_level_case_matches_closed_form_estimate(self) -> None:
        """Compare the straight-flight result against the expected analytic formulas."""
        op = MissionOperatingPoint(
            phase_name="cruise",
            altitude=500.0,
            airspeed=22.0,
            climb_rate=0.0,
        )
        result = self.model.evaluate(op)

        rho = float(standard_atmosphere(500.0)["rho"])
        q = 0.5 * rho * op.airspeed**2
        weight_newtons = self.config.mass * 9.80665
        expected_cl = weight_newtons / (q * self.config.wing_area)
        expected_cd = self.config.zero_lift_drag_coefficient + expected_cl**2 / (
            math.pi * self.config.aspect_ratio * self.config.oswald_efficiency
        )
        expected_drag = q * self.config.wing_area * expected_cd
        expected_power = expected_drag * op.airspeed / self.config.propulsive_efficiency

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.bank, 0.0, places=7)
        self.assertAlmostEqual(result.pitch, 0.0, places=7)
        self.assertAlmostEqual(result.load_factor, 1.0, places=7)
        self.assertAlmostEqual(result.dynamic_pressure, q, places=7)
        self.assertAlmostEqual(result.lift_coefficient, expected_cl, places=7)
        self.assertAlmostEqual(result.drag_coefficient, expected_cd, places=7)
        self.assertAlmostEqual(result.drag_force, expected_drag, places=7)
        self.assertAlmostEqual(result.propulsion_power, expected_power, places=7)
        self.assertEqual(result.notes, "")

    def test_turning_and_climbing_case_infers_bank_and_load_factor(self) -> None:
        """Check the coupled climb-turn estimate for a feasible operating point."""
        op = MissionOperatingPoint(
            phase_name="climb_turn",
            altitude=1200.0,
            airspeed=28.0,
            climb_rate=3.5,
            turn_radius=90.0,
        )
        result = self.model.evaluate(op)

        gamma_rad = math.asin(op.climb_rate / op.airspeed)
        horizontal_speed_sq = op.airspeed**2 - op.climb_rate**2
        expected_bank_deg = math.degrees(
            math.atan(horizontal_speed_sq / (9.80665 * op.turn_radius * math.cos(gamma_rad)))
        )
        expected_load_factor = math.cos(gamma_rad) / math.cos(math.radians(expected_bank_deg))

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.pitch, math.degrees(gamma_rad), places=7)
        self.assertAlmostEqual(result.bank, expected_bank_deg, places=7)
        self.assertAlmostEqual(result.load_factor, expected_load_factor, places=7)
        self.assertGreater(result.drag_force, 0.0)
        self.assertGreater(result.propulsion_power, 0.0)

    def test_feasibility_failures_report_limit_violations(self) -> None:
        """Verify that simple CL, bank, and load-factor limits mark the point infeasible."""
        limited_model = AnalyticMissionPerformanceModel(
            MissionAircraftPerformanceConfig(
                mass=12.0,
                wing_area=2.4,
                aspect_ratio=14.0,
                oswald_efficiency=0.85,
                zero_lift_drag_coefficient=0.03,
                propulsive_efficiency=0.75,
                max_lift_coefficient=0.60,
                max_bank=40.0,
                max_load_factor=1.40,
            )
        )
        op = MissionOperatingPoint(
            phase_name="tight_turn",
            altitude=0.0,
            airspeed=14.0,
            climb_rate=0.0,
            turn_radius=15.0,
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
            altitude=[1200.0 / FT_TO_M, "ft"],
            airspeed=(28.0 / KTS_TO_M_S, "kts"),
            climb_rate=[3.5 / FT_TO_M * 60.0, "ft/min"],
            turn_radius=[90.0 / FT_TO_M, "ft"],
        )
        result = model.evaluate(op)

        gamma_rad = math.asin(op.climb_rate / op.airspeed)
        expected_pitch_deg = math.degrees(gamma_rad) + 4.0
        expected_q = 0.5 * 1.10 * op.airspeed**2
        expected_drag = expected_q * self.config.wing_area * 0.041

        self.assertTrue(result.feasible)
        self.assertAlmostEqual(result.pitch, expected_pitch_deg, places=7)
        self.assertAlmostEqual(result.drag_force, expected_drag, places=7)
        self.assertIn("AVL longitudinal trim solved alpha=4.000 deg and elevator=-1.500 deg.", result.notes)
        self.assertIn("Banked-turn effects enter through the target load factor only", result.notes)
        self.assertEqual(mock_prepare.call_count, 1)

        trim_kwargs = mock_trim.call_args.kwargs
        self.assertEqual(trim_kwargs["case_name"], "mission_avl_climb_turn")
        self.assertFalse(trim_kwargs["write_geom"])
        self.assertEqual(trim_kwargs["control_index_map"]["elevator"], 2)
        self.assertAlmostEqual(trim_kwargs["velocity"], 28.0, places=7)
        self.assertAlmostEqual(trim_kwargs["altitude"], 1200.0, places=7)


if __name__ == "__main__":
    unittest.main()
