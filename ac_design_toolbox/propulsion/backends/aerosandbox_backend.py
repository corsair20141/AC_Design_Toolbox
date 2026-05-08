"""Optional AeroSandbox comparison helpers for propulsion models."""

from __future__ import annotations

from ac_design_toolbox.propulsion.motor import ElectricMotor
from ac_design_toolbox.propulsion.units import QuantityInput, convert_value, coerce_optional_quantity


def _motor_kv_as_rpm_per_volt(motor: ElectricMotor) -> float:
    """Return the motor speed constant in AeroSandbox's expected rpm/V unit."""
    return convert_value(motor.kv, "rad/s/V", "rpm/V")


def evaluate_motor_with_aerosandbox(
    motor: ElectricMotor,
    *,
    voltage: QuantityInput | None = None,
    current: QuantityInput | None = None,
    rotational_speed: QuantityInput | None = None,
    torque: QuantityInput | None = None,
) -> dict[str, float]:
    """Evaluate a direct-drive motor with AeroSandbox's Drela-style helper.

    This function is for validation and comparison only. The core propulsion
    solver does not call AeroSandbox. The adapter is deliberately direct-drive
    because AeroSandbox's helper models motor terminals, not a downstream
    gearbox output shaft.
    """
    if motor.gear_ratio != 1.0 or motor.gear_efficiency != 1.0:
        raise ValueError("AeroSandbox motor comparison currently supports direct-drive motors only.")

    try:
        from aerosandbox.library.propulsion_electric import motor_electric_performance
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "AeroSandbox is required for this optional backend. Install aerosandbox or use the core "
            "ac_design_toolbox.propulsion models without this adapter."
        ) from exc

    voltage_v = coerce_optional_quantity("voltage", voltage, "v", "voltage")
    current_a = coerce_optional_quantity("current", current, "a", "current")
    rpm = coerce_optional_quantity("rotational_speed", rotational_speed, "rpm", "rotational_speed")
    torque_n_m = coerce_optional_quantity("torque", torque, "n_m", "torque")

    result = motor_electric_performance(
        voltage=voltage_v,
        current=current_a,
        rpm=rpm,
        torque=torque_n_m,
        kv=_motor_kv_as_rpm_per_volt(motor),
        resistance=motor.resistance,
        no_load_current=motor.no_load_current,
    )
    return {str(key): float(value) for key, value in result.items()}


__all__ = [
    "evaluate_motor_with_aerosandbox",
]
