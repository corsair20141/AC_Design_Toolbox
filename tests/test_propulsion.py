"""Focused tests for electric propulsion operating-point models."""

from __future__ import annotations

import importlib.util
import math
import unittest

from ac_design_toolbox import (
    BatteryPack,
    CoefficientPropeller,
    ElectricMotor,
    ElectronicSpeedController,
    PropulsionOperatingPoint,
    TabulatedPropeller,
    infer_diameter_from_name,
    infer_propeller_size_from_name,
    parse_apc_performance_text,
    parse_uiuc_performance_text,
    solve_motor_prop_operating_point,
    solve_throttle_for_required_thrust,
)
from ac_design_toolbox.propulsion.data import (
    load_apc_performance_file,
    load_apc_table_for_rpm,
    load_uiuc_performance_file,
    load_uiuc_table_set,
)
from ac_design_toolbox.propulsion.backends import pyprop_backend


class PropulsionModelTests(unittest.TestCase):
    """Check motor, propeller, and coupled solver behavior."""

    def test_motor_torque_current_consistency(self) -> None:
        """Current-to-torque and torque-to-current estimates should invert."""
        motor = ElectricMotor(
            kv=(1000.0, "rpm/V"),  # catalog speed constant
            resistance=(0.1, "ohm"),  # winding resistance
            no_load_current=(1.0, "A"),  # no-load current
        )
        torque = (0.2, "N*m")  # output shaft torque

        current = motor.estimate_current_for_torque(torque)
        recovered_torque = motor.estimate_torque_for_current(current)

        self.assertAlmostEqual(motor.speed_constant, 1000.0 * math.pi / 30.0)
        self.assertAlmostEqual(motor.torque_constant, 1.0 / motor.speed_constant)
        self.assertAlmostEqual(recovered_torque, 0.2, places=12)

    def test_motor_voltage_speed_relationship(self) -> None:
        """The first-order motor equations should match the closed form."""
        motor = ElectricMotor(
            kv=(1000.0, "rpm/V"),  # catalog speed constant
            resistance=0.1,  # ohm
            no_load_current=1.0,  # A
        )
        result = motor.evaluate_from_voltage_and_rotational_speed(
            voltage=12.0,  # V
            rotational_speed=6000.0,  # rpm
        )

        omega = 6000.0 * math.pi / 30.0
        expected_current = (12.0 - omega / motor.speed_constant) / motor.resistance
        expected_torque = (expected_current - motor.no_load_current) / motor.speed_constant

        self.assertAlmostEqual(result.current, expected_current, places=12)
        self.assertAlmostEqual(result.torque, expected_torque, places=12)
        self.assertAlmostEqual(result.shaft_power, result.torque * result.angular_speed, places=12)
        self.assertTrue(result.is_within_limits)

    def test_coefficient_propeller_equations(self) -> None:
        """Constant propeller coefficients should unnormalize to textbook equations."""
        propeller = CoefficientPropeller(
            diameter=0.5,  # m
            ct=0.1,
            cp=0.05,
        )
        result = propeller.evaluate(
            airspeed=10.0,  # m/s
            rotational_speed=6000.0,  # rpm
            density=1.225,  # kg/m^3
        )

        n = 6000.0 / 60.0
        expected_j = 10.0 / (n * 0.5)
        expected_thrust = 0.1 * 1.225 * n**2 * 0.5**4
        expected_power = 0.05 * 1.225 * n**3 * 0.5**5

        self.assertAlmostEqual(result.advance_ratio, expected_j, places=12)
        self.assertAlmostEqual(result.thrust, expected_thrust, places=12)
        self.assertAlmostEqual(result.shaft_power, expected_power, places=12)
        self.assertAlmostEqual(result.torque, expected_power / result.angular_speed, places=12)
        self.assertAlmostEqual(result.cq or 0.0, 0.05 / (2.0 * math.pi), places=12)

    def test_tabulated_propeller_interpolation_and_clip_notes(self) -> None:
        """Tabulated propellers should interpolate CT/CP and flag clipped extrapolation."""
        propeller = TabulatedPropeller.from_arrays(
            diameter=0.5,  # m
            advance_ratio=[0.0, 0.5, 1.0],
            ct=[0.10, 0.05, 0.0],
            cp=[0.04, 0.03, 0.02],
            extrapolation_mode="clip",
        )

        result = propeller.evaluate(
            airspeed=12.5,  # m/s gives J = 0.25 at 6000 rpm and D = 0.5 m
            rotational_speed=6000.0,  # rpm
            density=1.225,  # kg/m^3
        )
        clipped = propeller.evaluate(
            airspeed=80.0,  # m/s, outside table range
            rotational_speed=6000.0,  # rpm
            density=1.225,  # kg/m^3
        )

        self.assertAlmostEqual(result.advance_ratio, 0.25, places=12)
        self.assertAlmostEqual(result.ct or 0.0, 0.075, places=12)
        self.assertAlmostEqual(result.cp or 0.0, 0.035, places=12)
        self.assertTrue(clipped.notes)
        self.assertIn("clipped", clipped.notes[0])

    def test_uiuc_parser_loads_j_ct_cp_tables(self) -> None:
        """UIUC wind-tunnel files should parse into TabulatedPropeller objects."""
        text = """J CT CP eta
        0.100 0.0900 0.0400 0.225
        0.200 0.0800 0.0390 0.410
        0.300 0.0700 0.0370 0.568
        """

        propeller = parse_uiuc_performance_text(
            text,
            diameter=(10.0, "in"),  # propeller diameter
            name="uiuc sample",
            source="apcsf_10x4.7_4008.txt",
        )

        self.assertAlmostEqual(propeller.diameter, 10.0 * 0.0254)
        self.assertEqual(propeller.advance_ratio, (0.1, 0.2, 0.3))
        self.assertEqual(propeller.ct, (0.09, 0.08, 0.07))
        self.assertEqual(propeller.cp, (0.04, 0.039, 0.037))

    def test_uiuc_static_files_are_rejected(self) -> None:
        """UIUC static RPM tables do not define CT/CP versus advance ratio."""
        text = """RPM CT CP
        2377 0.1059 0.0431
        2676 0.1079 0.0437
        """

        with self.assertRaises(ValueError):
            parse_uiuc_performance_text(text, diameter=(10.0, "in"))

    def test_apc_parser_loads_rpm_blocks(self) -> None:
        """APC PER3 blocks should parse as one table per RPM."""
        text = """
        10x5E ====== PERFORMANCE DATA ======
        PROP RPM = 1000
        V J Pe Ct Cp PWR Torque Thrust PWR Torque Thrust THR/PWR Mach Reyn FOM
        (mph) (Adv_Ratio) - - - (Hp) (In-Lbf) (Lbf) (W) (N-m) (N) (g/W) - - -
        0.00 0.0000 0.0000 0.0996 0.0469 0.000 0.024 0.032 0.281 0.003 0.141 51.143 0.04 11591. 0.5345
        0.21 0.0225 0.0467 0.0977 0.0470 0.000 0.024 0.031 0.282 0.003 0.139 50.042 0.04 11599. 0.5182
        PROP RPM = 2000
        V J Pe Ct Cp PWR Torque Thrust PWR Torque Thrust THR/PWR Mach Reyn FOM
        0.00 0.0000 0.0000 0.0999 0.0419 0.003 0.085 0.127 2.012 0.010 0.567 28.722 0.08 23182. 0.6015
        0.41 0.0219 0.0510 0.0982 0.0421 0.003 0.085 0.125 2.022 0.010 0.557 28.076 0.08 23198. 0.5828
        """

        table_set = parse_apc_performance_text(
            text,
            diameter=(10.0, "in"),  # propeller diameter
            name="APC 10x5E sample",
            source="PER3_10x5E.dat",
        )

        self.assertEqual(sorted(table_set.tables_by_rpm), [1000.0, 2000.0])
        self.assertAlmostEqual(table_set.table_for_rpm(1000.0).ct[0], 0.0996)
        self.assertAlmostEqual(table_set.table_for_rpm(2000.0).cp[1], 0.0421)

    def test_propeller_filename_diameter_inference_and_file_loaders(self) -> None:
        """Common UIUC/APC filenames should infer diameter for parser helpers."""
        import tempfile
        from pathlib import Path

        self.assertAlmostEqual(infer_diameter_from_name("apcsf_9x4.7_kt1033_4008.txt") or 0.0, 9.0 * 0.0254)
        self.assertAlmostEqual(infer_diameter_from_name("PER3_105x45.dat") or 0.0, 10.5 * 0.0254)
        self.assertEqual(infer_propeller_size_from_name("PER3_105x45.dat"), (10.5, 4.5))
        self.assertEqual(infer_propeller_size_from_name("PER3_10x5E.dat"), (10.0, 5.0))
        self.assertEqual(infer_propeller_size_from_name("apce_11x7_4008.txt"), (11.0, 7.0))
        self.assertEqual(infer_propeller_size_from_name("apcsf_9x4.7_kt1033_4008.txt"), (9.0, 4.7))

        with tempfile.TemporaryDirectory() as tmpdir:
            uiuc_path = Path(tmpdir) / "apcsf_9x4.7_kt1033_4008.txt"
            uiuc_path.write_text("J CT CP eta\n0.1 0.09 0.04 0.22\n0.2 0.08 0.039 0.41\n", encoding="utf-8")
            uiuc_propeller = load_uiuc_performance_file(uiuc_path)
            self.assertAlmostEqual(uiuc_propeller.diameter, 9.0 * 0.0254)

            apc_path = Path(tmpdir) / "PER3_105x45.dat"
            apc_path.write_text(
                "PROP RPM = 1000\n"
                "V J Pe Ct Cp PWR Torque Thrust PWR Torque Thrust THR/PWR Mach Reyn FOM\n"
                "0.0 0.0 0.0 0.1 0.04 0 0 0 0 0 0 0 0 0 0\n"
                "1.0 0.1 0.2 0.09 0.039 0 0 0 0 0 0 0 0 0 0\n",
                encoding="utf-8",
            )
            apc_propeller = load_apc_table_for_rpm(apc_path, 1000.0)
            self.assertAlmostEqual(apc_propeller.diameter, 10.5 * 0.0254)

    def test_propeller_table_set_evaluates_nearest_rpm_table(self) -> None:
        """RPM-indexed table sets should satisfy the propeller model protocol."""
        table_set = parse_apc_performance_text(
            """
            PROP RPM = 1000
            V J Pe Ct Cp PWR Torque Thrust PWR Torque Thrust THR/PWR Mach Reyn FOM
            0.0 0.0 0.0 0.10 0.040 0 0 0 0 0 0 0 0 0 0
            1.0 0.1 0.0 0.09 0.039 0 0 0 0 0 0 0 0 0 0
            PROP RPM = 2000
            V J Pe Ct Cp PWR Torque Thrust PWR Torque Thrust THR/PWR Mach Reyn FOM
            0.0 0.0 0.0 0.20 0.080 0 0 0 0 0 0 0 0 0 0
            1.0 0.1 0.0 0.18 0.078 0 0 0 0 0 0 0 0 0 0
            """,
            diameter=(10.0, "in"),  # propeller diameter
            name="APC table-set protocol sample",
            source="PER3_10x5E.dat",
        )

        result = table_set.evaluate(
            airspeed=0.0,  # m/s
            rotational_speed=1750.0,  # rpm, nearest table is 2000 rpm
            density=1.225,  # kg/m^3
        )

        self.assertAlmostEqual(result.ct or 0.0, 0.20)
        self.assertTrue(any("nearest RPM table 2000" in note for note in result.notes))

    def test_motor_prop_operating_point_converges(self) -> None:
        """A simple coefficient-prop case should converge to torque balance."""
        motor = ElectricMotor(
            kv=(920.0, "rpm/V"),  # catalog speed constant
            resistance=0.09,  # ohm
            no_load_current=0.7,  # A
            max_current=60.0,  # A
        )
        battery = BatteryPack(
            nominal_voltage=14.8,  # V
            internal_resistance=0.03,  # ohm
            capacity=5.0,  # Ah
            max_current=80.0,  # A
        )
        esc = ElectronicSpeedController(
            efficiency=0.97,
            resistance=0.01,  # ohm
            max_current=80.0,  # A
        )
        propeller = CoefficientPropeller(
            diameter=0.305,  # m
            ct=0.095,
            cp=0.045,
        )

        result = solve_motor_prop_operating_point(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            throttle=0.8,
            airspeed=8.0,  # m/s
            density=1.225,  # kg/m^3
            rotational_speed_bounds=(1000.0, 20000.0),  # rpm
        )

        self.assertIsInstance(result, PropulsionOperatingPoint)
        self.assertTrue(result.converged, result.notes)
        self.assertAlmostEqual(result.residual_torque, 0.0, places=5)
        self.assertGreater(result.propeller.thrust, 0.0)
        self.assertGreater(result.motor.current, motor.no_load_current)

    def test_motor_prop_solver_accepts_apc_table_set(self) -> None:
        """Coupled motor-prop solving should accept an APC table set directly."""
        import tempfile
        from pathlib import Path

        motor = ElectricMotor(kv=(920.0, "rpm/V"), resistance=0.09, no_load_current=0.7)
        battery = BatteryPack(nominal_voltage=14.8, internal_resistance=0.03, capacity=5.0)
        esc = ElectronicSpeedController(efficiency=0.97, resistance=0.01)

        with tempfile.TemporaryDirectory() as tmpdir:
            apc_path = Path(tmpdir) / "PER3_10x5E.dat"
            apc_path.write_text(
                "PROP RPM = 1000\n"
                "V J Pe Ct Cp PWR Torque Thrust PWR Torque Thrust THR/PWR Mach Reyn FOM\n"
                "0.0 0.0 0.0 0.09 0.040 0 0 0 0 0 0 0 0 0 0\n"
                "10.0 0.9 0.0 0.02 0.020 0 0 0 0 0 0 0 0 0 0\n"
                "PROP RPM = 12000\n"
                "V J Pe Ct Cp PWR Torque Thrust PWR Torque Thrust THR/PWR Mach Reyn FOM\n"
                "0.0 0.0 0.0 0.09 0.040 0 0 0 0 0 0 0 0 0 0\n"
                "10.0 0.9 0.0 0.02 0.020 0 0 0 0 0 0 0 0 0 0\n",
                encoding="utf-8",
            )
            propeller = load_apc_performance_file(apc_path, extrapolation_mode="clip")

        result = solve_motor_prop_operating_point(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            throttle=0.8,
            airspeed=8.0,  # m/s
            density=1.225,  # kg/m^3
            rotational_speed_bounds=(1000.0, 20000.0),  # rpm
        )

        self.assertTrue(result.converged, result.notes)
        self.assertGreater(result.propeller.thrust, 0.0)
        self.assertGreater(result.motor.current, motor.no_load_current)

    def test_required_thrust_solver_accepts_uiuc_table_set(self) -> None:
        """Throttle solving should accept a UIUC table set directly."""
        import tempfile
        from pathlib import Path

        motor = ElectricMotor(kv=(920.0, "rpm/V"), resistance=0.09, no_load_current=0.7)
        battery = BatteryPack(nominal_voltage=14.8, internal_resistance=0.03, capacity=5.0)
        esc = ElectronicSpeedController(efficiency=0.97, resistance=0.01)

        with tempfile.TemporaryDirectory() as tmpdir:
            first = Path(tmpdir) / "apcsf_10x5_1000.txt"
            second = Path(tmpdir) / "apcsf_10x5_12000.txt"
            table_text = "J CT CP eta\n0.0 0.09 0.040 0.00\n0.9 0.02 0.020 0.40\n"
            first.write_text(table_text, encoding="utf-8")
            second.write_text(table_text, encoding="utf-8")
            propeller = load_uiuc_table_set([first, second], extrapolation_mode="clip")

        result = solve_throttle_for_required_thrust(
            motor=motor,
            propeller=propeller,
            required_thrust=0.5,  # N
            battery=battery,
            esc=esc,
            airspeed=8.0,  # m/s
            density=1.225,  # kg/m^3
            rotational_speed_bounds=(1000.0, 20000.0),  # rpm
            throttle_bounds=(0.1, 1.0),
        )

        self.assertTrue(result.converged, result.notes)
        self.assertAlmostEqual(result.propeller.thrust, 0.5, delta=0.05)

    def test_blank_rotational_speed_bounds_use_solver_defaults(self) -> None:
        """Blank RPM bounds should be accepted without changing caller payloads."""
        motor = ElectricMotor(kv=(920.0, "rpm/V"), resistance=0.09, no_load_current=0.7)
        battery = BatteryPack(nominal_voltage=14.8, internal_resistance=0.03, capacity=5.0)
        esc = ElectronicSpeedController(efficiency=0.97, resistance=0.01)
        propeller = CoefficientPropeller(diameter=0.254, ct=0.09, cp=0.04)
        bounds = (None, None)

        result = solve_throttle_for_required_thrust(
            motor=motor,
            propeller=propeller,
            required_thrust=0.5,  # N
            battery=battery,
            esc=esc,
            airspeed=8.0,  # m/s
            density=1.225,  # kg/m^3
            rotational_speed_bounds=bounds,
            throttle_bounds=(0.1, 1.0),
        )

        self.assertIsInstance(result, PropulsionOperatingPoint)
        self.assertEqual(bounds, (None, None))

    def test_battery_constant_voltage_remains_backward_compatible(self) -> None:
        """Default battery behavior should remain nominal-voltage minus IR sag."""
        battery = BatteryPack(
            nominal_voltage=14.8,  # V
            internal_resistance=0.03,  # ohm
            capacity=5.0,  # Ah
        )

        result = battery.evaluate(10.0)  # A

        self.assertAlmostEqual(result.open_circuit_voltage, 14.8)
        self.assertAlmostEqual(result.terminal_voltage, 14.8 - 10.0 * 0.03)
        self.assertAlmostEqual(result.power, result.terminal_voltage * 10.0)
        self.assertIsNone(result.soc)

    def test_generic_lipo_soc_voltage_curve_endpoints_and_midpoint(self) -> None:
        """Generic LiPo OCV should use approximate per-cell SOC interpolation."""
        full = BatteryPack(
            nominal_voltage=14.8,  # V, infers 4S LiPo if n_series is omitted
            chemistry="generic_lipo",
            soc=1.0,
        )
        empty = BatteryPack(
            nominal_voltage=14.8,  # V
            chemistry="generic_lipo",
            soc=0.0,
            n_series=4,
        )
        midpoint = BatteryPack(
            nominal_voltage=14.8,  # V
            chemistry="generic_lipo",
            soc=0.55,
            n_series=4,
        )

        self.assertEqual(full.n_series, 4)
        self.assertAlmostEqual(full.open_circuit_voltage(), 4.0 * 4.20)
        self.assertAlmostEqual(empty.open_circuit_voltage(), 4.0 * 3.30)
        self.assertAlmostEqual(midpoint.open_circuit_voltage(), 4.0 * 3.825)

    def test_generic_liion_soc_voltage_curve_endpoints_and_sag(self) -> None:
        """Generic Li-ion OCV and internal resistance sag should both apply."""
        battery = BatteryPack(
            nominal_voltage=10.8,  # V
            chemistry="generic_liion",
            soc=0.0,
            n_series=3,
            internal_resistance=0.05,  # ohm
        )
        full = BatteryPack(
            nominal_voltage=10.8,  # V
            chemistry="generic_liion",
            soc=1.0,
            n_series=3,
        )

        result = battery.evaluate(8.0)  # A

        self.assertAlmostEqual(full.open_circuit_voltage(), 3.0 * 4.20)
        self.assertAlmostEqual(battery.open_circuit_voltage(), 3.0 * 3.00)
        self.assertAlmostEqual(result.terminal_voltage, 3.0 * 3.00 - 8.0 * 0.05)

    def test_custom_battery_ocv_curve_and_mass_sizing(self) -> None:
        """Custom pack-level OCV curves and specific-energy mass sizing should work."""
        battery = BatteryPack(
            nominal_voltage=12.0,  # V
            chemistry="custom",
            soc=0.25,
            ocv_soc_curve=(
                [0.0, 0.5, 1.0],
                [(9.0, "V"), (11.0, "V"), (12.6, "V")],
            ),
            capacity=10.0,  # Ah
            specific_energy=200.0,  # Wh/kg
        )
        direct_mass = BatteryPack(
            nominal_voltage=12.0,  # V
            capacity=10.0,  # Ah
            mass=0.9,  # kg
            specific_energy=200.0,  # Wh/kg, ignored when direct mass is provided
        )

        self.assertAlmostEqual(battery.open_circuit_voltage(), 10.0)
        self.assertAlmostEqual(battery.energy_capacity or 0.0, 120.0)
        self.assertAlmostEqual(battery.mass_kg or 0.0, 0.6)
        self.assertAlmostEqual(direct_mass.mass_kg or 0.0, 0.9)

    def test_invalid_soc_and_custom_curve_errors_are_clear(self) -> None:
        """Malformed SOC inputs and custom curves should fail at construction."""
        with self.assertRaises(ValueError):
            BatteryPack(
                nominal_voltage=14.8,  # V
                chemistry="generic_lipo",
                soc=1.2,
            )

        with self.assertRaises(ValueError):
            BatteryPack(
                nominal_voltage=12.0,  # V
                chemistry="custom",
            )

        with self.assertRaises(ValueError):
            BatteryPack(
                nominal_voltage=12.0,  # V
                chemistry="custom",
                soc=0.5,
                ocv_soc_curve=([0.0, 0.5, 0.5, 1.0], [9.0, 10.0, 11.0, 12.0]),
            )

    def test_motor_prop_no_solution_reports_nonconvergence(self) -> None:
        """If torque residuals do not bracket a root, the solver should report it."""
        motor = ElectricMotor(
            kv=(700.0, "rpm/V"),  # catalog speed constant
            resistance=0.2,  # ohm
            no_load_current=0.5,  # A
        )
        propeller = CoefficientPropeller(
            diameter=0.5,  # m
            ct=0.1,
            cp=0.08,
        )

        result = solve_motor_prop_operating_point(
            motor=motor,
            propeller=propeller,
            voltage=12.0,  # V
            throttle=0.0,
            airspeed=0.0,  # m/s
            density=1.225,  # kg/m^3
            rotational_speed_bounds=(1000.0, 20000.0),  # rpm
        )

        self.assertFalse(result.converged)
        self.assertTrue(any("No torque-balance bracket" in note for note in result.notes))

    def test_optional_backend_imports_do_not_break_core(self) -> None:
        """Optional backend modules should import even if optional packages are absent."""
        self.assertTrue(callable(pyprop_backend.require_pyprop))

        if importlib.util.find_spec("pyprop") is None:
            with self.assertRaises(ModuleNotFoundError):
                pyprop_backend.require_pyprop()


if __name__ == "__main__":
    unittest.main()
