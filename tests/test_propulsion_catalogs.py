"""Tests for editable CSV propulsion component catalogs."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ac_design_toolbox import (
    BatteryPack,
    CoefficientPropeller,
    ElectricMotor,
    ElectronicSpeedController,
    PropulsionCatalogs,
    load_battery_catalog,
    load_esc_catalog,
    load_motor_catalog,
    load_propulsion_catalogs,
    solve_motor_prop_operating_point,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
CATALOG_ROOT = REPO_ROOT / "data" / "propulsion" / "catalogs"


class PropulsionCatalogTests(unittest.TestCase):
    """Check CSV-backed catalog loading and solver compatibility."""

    def test_example_catalogs_load_existing_component_dataclasses(self) -> None:
        """The committed example CSVs should load into the public component classes."""
        catalogs = load_propulsion_catalogs(CATALOG_ROOT)

        self.assertIsInstance(catalogs, PropulsionCatalogs)
        self.assertIsInstance(catalogs.motors["example_920kv_outrunner"], ElectricMotor)
        self.assertIsInstance(catalogs.batteries["example_4s_lipo"], BatteryPack)
        self.assertIsInstance(catalogs.escs["example_80a_esc"], ElectronicSpeedController)
        self.assertAlmostEqual(catalogs.motors["example_920kv_outrunner"].max_current or 0.0, 60.0)
        self.assertAlmostEqual(catalogs.motors["example_920kv_outrunner"].mass or 0.0, 0.16)
        self.assertAlmostEqual(catalogs.batteries["example_4s_lipo"].mass_kg or 0.0, 0.62)
        self.assertAlmostEqual(catalogs.escs["example_80a_esc"].efficiency, 0.97)
        self.assertAlmostEqual(catalogs.escs["example_80a_esc"].mass or 0.0, 0.085)

    def test_blank_optional_cells_become_none_or_defaults(self) -> None:
        """Blank optional cells should not create bogus zero-valued limits."""
        with tempfile.TemporaryDirectory() as tmpdir:
            motor_path = Path(tmpdir) / "motors.csv"
            motor_path.write_text(
                "catalog_id,name,kv_value,kv_unit,resistance_value,resistance_unit,"
                "no_load_current_value,no_load_current_unit,max_current_value,max_current_unit,"
                "max_voltage_value,max_voltage_unit,max_power_value,max_power_unit,mass_value,mass_unit,gear_ratio,gear_efficiency\n"
                "minimal,Minimal Motor,900,rpm/V,0.1,ohm,,,,,,,,,,,,\n",
                encoding="utf-8",
            )

            motor = load_motor_catalog(motor_path)["minimal"]

        self.assertIsNone(motor.max_current)
        self.assertIsNone(motor.max_voltage)
        self.assertIsNone(motor.max_power)
        self.assertIsNone(motor.mass)
        self.assertAlmostEqual(motor.no_load_current, 0.0)
        self.assertAlmostEqual(motor.gear_ratio, 1.0)
        self.assertAlmostEqual(motor.gear_efficiency, 1.0)

    def test_invalid_catalog_rows_raise_clear_errors(self) -> None:
        """Common hand-editing mistakes should include row and column context."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            duplicate_path = tmp / "duplicate_motors.csv"
            duplicate_path.write_text(
                "catalog_id,name,kv_value,kv_unit,resistance_value,resistance_unit\n"
                "dupe,First,900,rpm/V,0.1,ohm\n"
                "dupe,Second,950,rpm/V,0.11,ohm\n",
                encoding="utf-8",
            )
            missing_path = tmp / "missing_motors.csv"
            missing_path.write_text(
                "catalog_id,name,kv_value,kv_unit,resistance_value,resistance_unit\n"
                "missing,Missing Kv,,rpm/V,0.1,ohm\n",
                encoding="utf-8",
            )
            bad_unit_path = tmp / "bad_batteries.csv"
            bad_unit_path.write_text(
                "catalog_id,name,nominal_voltage_value,nominal_voltage_unit\n"
                "bad_unit,Bad Unit,14.8,parsec\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "duplicate catalog_id"):
                load_motor_catalog(duplicate_path)
            with self.assertRaisesRegex(ValueError, "row 2.*kv_value"):
                load_motor_catalog(missing_path)
            with self.assertRaisesRegex(ValueError, "Unsupported unit"):
                load_battery_catalog(bad_unit_path)

    def test_loaded_catalog_components_solve_operating_point(self) -> None:
        """Catalog-loaded components should work with existing propulsion solvers."""
        motor = load_motor_catalog(CATALOG_ROOT / "motors.csv")["example_920kv_outrunner"]
        battery = load_battery_catalog(CATALOG_ROOT / "batteries.csv")["example_4s_lipo"]
        esc = load_esc_catalog(CATALOG_ROOT / "escs.csv")["example_80a_esc"]
        propeller = CoefficientPropeller(
            diameter=0.305,  # m, roughly 12 in
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

        self.assertTrue(result.converged, result.notes)
        self.assertGreater(result.propeller.thrust, 0.0)
        self.assertGreater(result.motor.current, motor.no_load_current)


if __name__ == "__main__":
    unittest.main()
