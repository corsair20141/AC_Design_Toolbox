"""Minimal motor-prop operating-point example.

This example uses the import-light `ac_design_toolbox.propulsion` package. It
does not require PyProp, AeroSandbox, Solar_UAS, AVL, or GUI tooling.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow the example to run directly from the repository without installation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ac_design_toolbox.propulsion import (
    BatteryPack,
    CoefficientPropeller,
    ElectricMotor,
    ElectronicSpeedController,
    solve_motor_prop_operating_point,
)


def main() -> None:
    """Solve one coupled motor, ESC, battery, and propeller operating point."""
    motor = ElectricMotor(
        name="Example 920 Kv outrunner",
        kv=(920.0, "rpm/V"),  # catalog motor speed constant
        resistance=0.09,  # ohm winding resistance
        no_load_current=0.7,  # A
        max_current=60.0,  # A
        max_power=850.0,  # W
    )
    battery = BatteryPack(
        name="4S example LiPo",
        nominal_voltage=14.8,  # V
        internal_resistance=0.03,  # ohm pack equivalent resistance
        capacity=5.0,  # Ah
        max_current=80.0,  # A
    )
    esc = ElectronicSpeedController(
        name="Example ESC",
        efficiency=0.97,  # first-pass effective voltage scaling
        resistance=0.01,  # ohm series resistance
        max_current=80.0,  # A
        max_voltage=25.2,  # V
    )
    propeller = CoefficientPropeller(
        name="Example fixed coefficient prop",
        diameter=0.305,  # m, approximately 12 in
        ct=0.095,  # nondimensional thrust coefficient
        cp=0.045,  # nondimensional power coefficient
    )

    result = solve_motor_prop_operating_point(
        motor=motor,
        propeller=propeller,
        battery=battery,
        esc=esc,
        throttle=0.8,  # fraction of available ESC command
        airspeed=8.0,  # m/s
        density=1.225,  # kg/m^3
        rotational_speed_bounds=(1000.0, 20000.0),  # rpm
    )

    print("Electric propulsion operating point")
    print(f"  Converged: {result.converged}")
    print(f"  RPM: {result.motor.rotational_speed:,.1f}")
    print(f"  Thrust: {result.propeller.thrust:.3f} N")
    print(f"  Torque: {result.propeller.torque:.4f} N*m")
    print(f"  Current: {result.motor.current:.3f} A")
    print(f"  Motor electrical power: {result.motor.electrical_power:.1f} W")
    print(f"  Shaft power: {result.motor.shaft_power:.1f} W")
    print(f"  Motor efficiency: {result.motor.efficiency:.3f}")
    print(f"  Propeller efficiency: {result.propeller.efficiency}")
    print(f"  Torque residual: {result.residual_torque:.3e} N*m")
    if result.notes:
        print("  Notes:")
        for note in result.notes:
            print(f"    - {note}")
    else:
        print("  Notes: none")


if __name__ == "__main__":
    main()
