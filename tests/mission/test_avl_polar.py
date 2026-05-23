"""Tests for the AVL polar-generated mission performance backend."""

from __future__ import annotations

import math
import unittest
from typing import Any

import pandas as pd

from ac_design_toolbox.mission import (
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
)
from ac_design_toolbox.mission.avl_polar import (
    AVLAeroPolarConfig,
    AVLAeroPolarTable,
    AVLPolarMissionPerformanceModel,
)


class TestAVLPolarMissionPerformanceModel(unittest.TestCase):
    def test_polar_interpolation(self):
        config = AVLAeroPolarConfig(alpha_min_deg=0.0, alpha_max_deg=10.0, alpha_step_deg=5.0)
        df = pd.DataFrame({
            "CL": [0.1, 0.5, 0.9],
            "CD": [0.02, 0.03, 0.05],
            "alpha_deg": [0.0, 5.0, 10.0],
            "beta_deg": [0.0, 0.0, 0.0],
            "elevator_deg": [2.0, 0.0, -2.0],
            "feasible": [1.0, 1.0, 1.0],
            "avl_Cma": [-1.0, -1.0, -1.0],
            "control_elevator_deg": [2.0, 0.0, -2.0],
        })
        table = AVLAeroPolarTable(config=config, data=df)
        
        aircraft = MissionAircraftPerformanceConfig(
            mass=10.0,
            wing_area=1.0,
            aspect_ratio=10.0,
            oswald_efficiency=0.8,
            zero_lift_drag_coefficient=0.02,
            propulsive_efficiency=1.0,
            max_lift_coefficient=1.5,
            max_bank=30.0,
            max_load_factor=2.0,
        )
        
        # We need a dummy airplane just to initialize
        class DummyAirplane:
            pass
        
        model = AVLPolarMissionPerformanceModel(
            airplane=DummyAirplane(),
            aircraft=aircraft,
            config=config,
            control_index_map={"elevator": 1},
        )
        # Inject our mock table so it doesn't call AVL
        model._table = table
        
        # dynamic_pressure = 0.5 * rho * v^2
        # mass = 10, gravity ~ 9.80665 -> weight ~ 98.0665
        # We want CL = 0.5 exactly. target_dynamic_pressure = weight / (wing_area * CL) = 98.0665 / (1.0 * 0.5) = 196.133
        # rho at altitude=0 is 1.225
        # v = sqrt(2 * q / rho) = sqrt(2 * 196.133 / 1.225) = 17.893
        v = math.sqrt(2 * 196.133 / 1.225)
        
        op = MissionOperatingPoint(
            phase_name="test_phase",
            altitude=0.0,
            airspeed=v,
            turn_radius=None,
            climb_rate=0.0,
        )
        
        pt = model.evaluate(op)
        
        self.assertTrue(pt.feasible)
        self.assertAlmostEqual(pt.lift_coefficient, 0.5, places=2)
        self.assertAlmostEqual(pt.drag_coefficient, 0.03, places=3)
        self.assertAlmostEqual(pt.angle_of_attack, 5.0, places=2)
        self.assertAlmostEqual(pt.elevator_deflection, 0.0, places=3)
        self.assertEqual(pt.diagnostics["avl_call_count"], 0)
        self.assertEqual(pt.diagnostics["performance_polar_avl_Cma"], -1.0)
        
    def test_out_of_range_clamping(self):
        config = AVLAeroPolarConfig()
        df = pd.DataFrame({
            "CL": [0.1, 0.5],
            "CD": [0.02, 0.03],
            "alpha_deg": [0.0, 5.0],
            "beta_deg": [0.0, 0.0],
            "feasible": [1.0, 1.0],
        })
        table = AVLAeroPolarTable(config=config, data=df)
        
        aircraft = MissionAircraftPerformanceConfig(
            mass=10.0, wing_area=1.0, aspect_ratio=10.0, oswald_efficiency=0.8,
            zero_lift_drag_coefficient=0.02, propulsive_efficiency=1.0,
            max_lift_coefficient=1.5, max_bank=30.0, max_load_factor=2.0,
        )
        
        model = AVLPolarMissionPerformanceModel(
            airplane=None, aircraft=aircraft, config=config, control_index_map={}
        )
        model._table = table
        
        # velocity low -> requires high CL (e.g. CL=1.0)
        op = MissionOperatingPoint(phase_name="test", altitude=0, airspeed=5.0, climb_rate=0)
        pt = model.evaluate(op)
        
        self.assertFalse(pt.feasible)
        self.assertAlmostEqual(pt.lift_coefficient, 0.5) # clamped to max
        self.assertAlmostEqual(pt.drag_coefficient, 0.03)
        self.assertIn("clamping", pt.notes.lower())

if __name__ == "__main__":
    unittest.main()
