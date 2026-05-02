"""Tests for reusable aircraft energy component primitives."""

from __future__ import annotations

import unittest
import warnings

from ac_design_toolbox.energy import (
    AircraftEnergyConfig,
    BatteryPackConfig,
    ElectricalLoadConfig,
    EnergyLimitWarning,
    MassItem,
    PropulsionElectricalConfig,
    warn_for_violations,
)


class EnergyModelTests(unittest.TestCase):
    """Verify unit handling, mass buildup, and advisory limit checks."""

    def test_battery_normalizes_units_and_derives_mass(self) -> None:
        """Battery public fields should normalize to canonical scalar units."""
        battery = BatteryPackConfig(
            energy_capacity=(1.2, "kWh"),
            nominal_voltage=22.2,
            initial_soc=0.8,
            usable_soc_min=0.2,
            usable_soc_max=0.95,
            max_discharge_power=(0.6, "kW"),
            max_charge_current=12.0,
            specific_energy=(200.0, "Wh/kg"),
        )

        self.assertAlmostEqual(battery.energy_capacity, 1200.0)
        self.assertAlmostEqual(battery.initial_energy_wh, 960.0)
        self.assertAlmostEqual(battery.usable_energy_min_wh, 240.0)
        self.assertAlmostEqual(battery.max_discharge_power or 0.0, 600.0)
        self.assertAlmostEqual(battery.mass_kg, 6.0)

    def test_component_mass_buildup_includes_external_solar_mass(self) -> None:
        """Aircraft mass buildup should include battery, loads, propulsion, and external items."""
        config = AircraftEnergyConfig(
            base_aircraft_mass=(10.0, "kg"),
            battery=BatteryPackConfig(
                energy_capacity=1000.0,
                nominal_voltage=24.0,
                specific_energy=250.0,
            ),
            propulsion=PropulsionElectricalConfig(mass=(1.0, "kg")),
            loads=(
                ElectricalLoadConfig(name="payload", power=30.0, mass=(0.5, "kg")),
            ),
            extra_mass_items=(MassItem(name="avionics", mass=0.25, category="systems"),),
        )
        solar_mass = (MassItem(name="solar_array", mass=0.8, category="solar"),)

        breakdown = config.mass_breakdown(external_mass_items=solar_mass)

        self.assertAlmostEqual(breakdown["base_aircraft"], 10.0)
        self.assertAlmostEqual(breakdown["battery"], 4.0)
        self.assertAlmostEqual(breakdown["propulsion"], 1.0)
        self.assertAlmostEqual(breakdown["payload"], 0.5)
        self.assertAlmostEqual(breakdown["solar_array"], 0.8)
        self.assertAlmostEqual(config.total_mass(external_mass_items=solar_mass), 16.55)

    def test_battery_and_propulsion_limits_warn_and_flag_infeasible(self) -> None:
        """Optional current and power limits should return violations and advisory warnings."""
        battery = BatteryPackConfig(
            energy_capacity=1000.0,
            nominal_voltage=20.0,
            max_discharge_power=400.0,
            max_discharge_current=18.0,
            max_charge_power=150.0,
            specific_energy=200.0,
        )
        propulsion = PropulsionElectricalConfig(max_power=350.0, max_current=15.0)

        battery_result = battery.evaluate_power_limits(420.0)
        propulsion_result = propulsion.evaluate_power_limits(360.0, bus_voltage=battery.nominal_voltage)

        self.assertFalse(battery_result.feasible)
        self.assertFalse(propulsion_result.feasible)
        self.assertEqual(len(battery_result.violations), 2)
        self.assertEqual(len(propulsion_result.violations), 2)
        self.assertLess(battery_result.violations[0].margin, 0.0)

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            warn_for_violations(battery_result.violations + propulsion_result.violations)

        self.assertTrue(all(issubclass(item.category, EnergyLimitWarning) for item in caught))
        self.assertGreaterEqual(len(caught), 2)

    def test_battery_energy_step_applies_efficiencies_without_mission_logic(self) -> None:
        """Battery energy math should be a component primitive, not mission propagation."""
        battery = BatteryPackConfig(
            energy_capacity=1000.0,
            nominal_voltage=20.0,
            charge_efficiency=0.9,
            discharge_efficiency=0.8,
            specific_energy=200.0,
        )

        after_discharge = battery.apply_bus_power(500.0, 80.0, 360.0)
        after_charge = battery.apply_bus_power(after_discharge, -100.0, 360.0)

        self.assertAlmostEqual(after_discharge, 490.0)
        self.assertAlmostEqual(after_charge, 499.0)


if __name__ == "__main__":
    unittest.main()
