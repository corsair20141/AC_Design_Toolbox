"""Coupled motor, ESC, battery, and propeller operating-point solvers."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable

from ac_design_toolbox.propulsion.battery import BatteryOperatingPoint, BatteryPack
from ac_design_toolbox.propulsion.esc import ElectronicSpeedController, EscOperatingPoint
from ac_design_toolbox.propulsion.motor import ElectricMotor, MotorOperatingPoint
from ac_design_toolbox.propulsion.propeller import PropellerModel, PropellerOperatingPoint
from ac_design_toolbox.propulsion.units import (
    QuantityInput,
    coerce_fraction,
    coerce_quantity,
    rotational_speed_to_angular_speed,
)


@dataclass(frozen=True)
class PropulsionOperatingPoint:
    """Resolved coupled propulsion state for one flight condition."""

    battery: BatteryOperatingPoint | None
    esc: EscOperatingPoint | None
    motor: MotorOperatingPoint
    propeller: PropellerOperatingPoint
    throttle: float
    airspeed: float
    density: float
    residual_torque: float
    residual_thrust: float | None
    converged: bool
    notes: tuple[str, ...]


def _source_voltage(battery: BatteryPack | None, voltage: QuantityInput | None) -> float:
    """Return the open-circuit/source voltage for the coupled solve."""
    if battery is None and voltage is None:
        raise ValueError("Provide either battery or voltage.")
    if battery is not None and voltage is not None:
        raise ValueError("Provide either battery or voltage, not both.")
    if battery is not None:
        return battery.open_circuit_voltage()
    voltage_v = coerce_quantity("voltage", voltage, "v", "voltage")
    if voltage_v <= 0.0:
        raise ValueError("voltage must be positive.")
    return voltage_v


def _coerce_rotational_speed_bounds(bounds: tuple[QuantityInput | None, QuantityInput | None]) -> tuple[float, float]:
    """Return lower and upper rotational-speed bounds in rpm.

    ``None`` or blank entries mean "use the solver's default bound" for that
    side. This lets GUI/workflow payloads leave RPM bounds unspecified without
    having to write default values back into component configuration.
    """
    if len(bounds) != 2:
        raise TypeError("rotational_speed_bounds must contain exactly two values.")
    default_lower, default_upper = (100.0, 50000.0)
    lower_input = default_lower if bounds[0] in (None, "") else bounds[0]
    upper_input = default_upper if bounds[1] in (None, "") else bounds[1]
    lower = coerce_quantity("rotational_speed_bounds[0]", lower_input, "rpm", "rotational_speed")
    upper = coerce_quantity("rotational_speed_bounds[1]", upper_input, "rpm", "rotational_speed")
    if lower <= 0.0 or upper <= 0.0:
        raise ValueError("rotational_speed_bounds must be positive.")
    if lower >= upper:
        raise ValueError("rotational_speed_bounds lower bound must be less than upper bound.")
    return lower, upper


def _coerce_throttle_bounds(bounds: tuple[float, float]) -> tuple[float, float]:
    """Return validated throttle bounds."""
    if len(bounds) != 2:
        raise TypeError("throttle_bounds must contain exactly two values.")
    lower = coerce_fraction("throttle_bounds[0]", bounds[0])
    upper = coerce_fraction("throttle_bounds[1]", bounds[1])
    if lower >= upper:
        raise ValueError("throttle_bounds lower bound must be less than upper bound.")
    return lower, upper


def _component_notes(
    *,
    battery: BatteryOperatingPoint | None,
    esc: EscOperatingPoint | None,
    motor: MotorOperatingPoint,
    propeller: PropellerOperatingPoint,
) -> tuple[str, ...]:
    """Collect component diagnostics into a flat tuple of notes."""
    notes: list[str] = []
    if battery is not None:
        notes.extend(f"Battery: {note}" for note in battery.limit_notes)
    if esc is not None:
        notes.extend(f"ESC: {note}" for note in esc.limit_notes)
    notes.extend(f"Motor: {note}" for note in motor.limit_notes)
    notes.extend(f"Propeller: {note}" for note in propeller.notes)
    return tuple(notes)


def _current_and_motor_voltage_at_speed(
    *,
    motor: ElectricMotor,
    battery: BatteryPack | None,
    esc: ElectronicSpeedController | None,
    source_voltage: float,
    throttle: float,
    rotational_speed: float,
) -> tuple[float, float, float]:
    """Solve the linear voltage/current relation at one output-shaft speed."""
    output_omega = rotational_speed_to_angular_speed(rotational_speed)
    motor_omega = output_omega * motor.gear_ratio
    back_emf_voltage = motor_omega / motor.speed_constant

    battery_resistance = battery.internal_resistance if battery is not None else 0.0
    esc_efficiency = esc.efficiency if esc is not None else 1.0
    esc_resistance = esc.resistance if esc is not None else 0.0
    throttle_voltage_scale = throttle * esc_efficiency
    denominator = motor.resistance + throttle_voltage_scale * battery_resistance + esc_resistance
    current = (throttle_voltage_scale * source_voltage - back_emf_voltage) / denominator
    terminal_voltage = source_voltage - current * battery_resistance
    motor_voltage = throttle_voltage_scale * terminal_voltage - current * esc_resistance
    return current, terminal_voltage, motor_voltage


def _evaluate_at_rotational_speed(
    *,
    motor: ElectricMotor,
    propeller: PropellerModel,
    battery: BatteryPack | None,
    esc: ElectronicSpeedController | None,
    source_voltage: float,
    throttle: float,
    airspeed: float,
    density: float,
    rotational_speed: float,
    residual_thrust: float | None = None,
    converged: bool = True,
    notes: tuple[str, ...] = (),
) -> PropulsionOperatingPoint:
    """Evaluate all components at one output-shaft rotational speed."""
    current, terminal_voltage, motor_voltage = _current_and_motor_voltage_at_speed(
        motor=motor,
        battery=battery,
        esc=esc,
        source_voltage=source_voltage,
        throttle=throttle,
        rotational_speed=rotational_speed,
    )
    battery_result = battery.evaluate(current) if battery is not None else None
    esc_result = (
        esc.evaluate(terminal_voltage, current, throttle=throttle)
        if esc is not None
        else None
    )
    motor_result = motor.evaluate_from_voltage_and_rotational_speed(motor_voltage, rotational_speed)
    propeller_result = propeller.evaluate(
        airspeed=airspeed,
        rotational_speed=rotational_speed,
        density=density,
    )
    residual_torque = motor_result.torque - propeller_result.torque
    all_notes = list(notes)
    all_notes.extend(
        _component_notes(
            battery=battery_result,
            esc=esc_result,
            motor=motor_result,
            propeller=propeller_result,
        )
    )

    return PropulsionOperatingPoint(
        battery=battery_result,
        esc=esc_result,
        motor=motor_result,
        propeller=propeller_result,
        throttle=throttle,
        airspeed=airspeed,
        density=density,
        residual_torque=residual_torque,
        residual_thrust=residual_thrust,
        converged=converged,
        notes=tuple(all_notes),
    )


def _bisect_root(
    function: Callable[[float], float],
    lower: float,
    upper: float,
    *,
    tolerance: float,
    max_iterations: int,
) -> float:
    """Return a scalar root using a small local bisection fallback."""
    f_lower = function(lower)
    f_upper = function(upper)
    if f_lower == 0.0:
        return lower
    if f_upper == 0.0:
        return upper
    if f_lower * f_upper > 0.0:
        raise ValueError("Root is not bracketed.")

    lo = lower
    hi = upper
    flo = f_lower
    for _ in range(max_iterations):
        mid = 0.5 * (lo + hi)
        fmid = function(mid)
        if abs(fmid) <= tolerance or abs(hi - lo) <= tolerance:
            return mid
        if flo * fmid <= 0.0:
            hi = mid
        else:
            lo = mid
            flo = fmid
    return 0.5 * (lo + hi)


def _solve_bracketed_root(
    function: Callable[[float], float],
    lower: float,
    upper: float,
    *,
    tolerance: float,
    max_iterations: int,
) -> float:
    """Solve a bracketed scalar root with SciPy when available."""
    try:
        from scipy.optimize import brentq

        return float(brentq(function, lower, upper, xtol=tolerance, rtol=1e-10, maxiter=max_iterations))
    except ImportError:
        return _bisect_root(function, lower, upper, tolerance=tolerance, max_iterations=max_iterations)


def solve_motor_prop_operating_point(
    *,
    motor: ElectricMotor,
    propeller: PropellerModel,
    battery: BatteryPack | None = None,
    esc: ElectronicSpeedController | None = None,
    voltage: QuantityInput | None = None,
    throttle: float = 1.0,
    airspeed: QuantityInput = 0.0,
    density: QuantityInput = 1.225,
    rotational_speed_bounds: tuple[QuantityInput, QuantityInput] = (100.0, 50000.0),
    torque_tolerance: float = 1e-6,
    max_iterations: int = 80,
) -> PropulsionOperatingPoint:
    """Solve the RPM where motor output torque equals propeller torque."""
    source_voltage = _source_voltage(battery, voltage)
    throttle_fraction = coerce_fraction("throttle", throttle)
    airspeed_m_s = coerce_quantity("airspeed", airspeed, "m_s", "speed")
    density_kg_m3 = coerce_quantity("density", density, "kg_m3", "density")
    lower_speed, upper_speed = _coerce_rotational_speed_bounds(rotational_speed_bounds)

    if airspeed_m_s < 0.0:
        raise ValueError("airspeed must be non-negative.")
    if density_kg_m3 <= 0.0:
        raise ValueError("density must be positive.")

    def residual(rotational_speed: float) -> float:
        point = _evaluate_at_rotational_speed(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            source_voltage=source_voltage,
            throttle=throttle_fraction,
            airspeed=airspeed_m_s,
            density=density_kg_m3,
            rotational_speed=rotational_speed,
        )
        return point.residual_torque

    lower_residual = residual(lower_speed)
    upper_residual = residual(upper_speed)

    if abs(lower_residual) <= torque_tolerance:
        return _evaluate_at_rotational_speed(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            source_voltage=source_voltage,
            throttle=throttle_fraction,
            airspeed=airspeed_m_s,
            density=density_kg_m3,
            rotational_speed=lower_speed,
        )
    if abs(upper_residual) <= torque_tolerance:
        return _evaluate_at_rotational_speed(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            source_voltage=source_voltage,
            throttle=throttle_fraction,
            airspeed=airspeed_m_s,
            density=density_kg_m3,
            rotational_speed=upper_speed,
        )

    if lower_residual * upper_residual > 0.0:
        best_speed = lower_speed if abs(lower_residual) <= abs(upper_residual) else upper_speed
        note = (
            "No torque-balance bracket was found over rotational_speed_bounds; "
            f"residuals were {lower_residual:.6g} and {upper_residual:.6g} N*m."
        )
        return _evaluate_at_rotational_speed(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            source_voltage=source_voltage,
            throttle=throttle_fraction,
            airspeed=airspeed_m_s,
            density=density_kg_m3,
            rotational_speed=best_speed,
            converged=False,
            notes=(note,),
        )

    try:
        root_speed = _solve_bracketed_root(
            residual,
            lower_speed,
            upper_speed,
            tolerance=torque_tolerance,
            max_iterations=max_iterations,
        )
    except ValueError as exc:
        note = f"Torque-balance solver failed: {exc}"
        best_speed = lower_speed if abs(lower_residual) <= abs(upper_residual) else upper_speed
        return _evaluate_at_rotational_speed(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            source_voltage=source_voltage,
            throttle=throttle_fraction,
            airspeed=airspeed_m_s,
            density=density_kg_m3,
            rotational_speed=best_speed,
            converged=False,
            notes=(note,),
        )

    return _evaluate_at_rotational_speed(
        motor=motor,
        propeller=propeller,
        battery=battery,
        esc=esc,
        source_voltage=source_voltage,
        throttle=throttle_fraction,
        airspeed=airspeed_m_s,
        density=density_kg_m3,
        rotational_speed=root_speed,
    )


def solve_throttle_for_required_thrust(
    *,
    motor: ElectricMotor,
    propeller: PropellerModel,
    required_thrust: QuantityInput,
    battery: BatteryPack | None = None,
    esc: ElectronicSpeedController | None = None,
    voltage: QuantityInput | None = None,
    airspeed: QuantityInput = 0.0,
    density: QuantityInput = 1.225,
    rotational_speed_bounds: tuple[QuantityInput, QuantityInput] = (100.0, 50000.0),
    throttle_bounds: tuple[float, float] = (0.0, 1.0),
    thrust_tolerance: float = 1e-2,
    max_iterations: int = 60,
) -> PropulsionOperatingPoint:
    """Solve throttle so the coupled propeller thrust matches a target."""
    required_thrust_n = coerce_quantity("required_thrust", required_thrust, "n", "force")
    if required_thrust_n < 0.0:
        raise ValueError("required_thrust must be non-negative.")
    lower_throttle, upper_throttle = _coerce_throttle_bounds(throttle_bounds)

    def point_at(throttle: float) -> PropulsionOperatingPoint:
        point = solve_motor_prop_operating_point(
            motor=motor,
            propeller=propeller,
            battery=battery,
            esc=esc,
            voltage=voltage,
            throttle=throttle,
            airspeed=airspeed,
            density=density,
            rotational_speed_bounds=rotational_speed_bounds,
            max_iterations=max_iterations,
        )
        return replace(point, residual_thrust=point.propeller.thrust - required_thrust_n)

    def thrust_error(throttle: float) -> float:
        return point_at(throttle).residual_thrust or 0.0

    lower_point = point_at(lower_throttle)
    upper_point = point_at(upper_throttle)
    lower_error = lower_point.residual_thrust or 0.0
    upper_error = upper_point.residual_thrust or 0.0

    if abs(lower_error) <= thrust_tolerance:
        return lower_point
    if abs(upper_error) <= thrust_tolerance:
        return upper_point

    if lower_error * upper_error > 0.0:
        best_point = lower_point if abs(lower_error) <= abs(upper_error) else upper_point
        note = (
            "No thrust bracket was found over throttle_bounds; "
            f"thrust residuals were {lower_error:.6g} and {upper_error:.6g} N."
        )
        return replace(best_point, converged=False, notes=(note,) + best_point.notes)

    root_throttle = _solve_bracketed_root(
        thrust_error,
        lower_throttle,
        upper_throttle,
        tolerance=thrust_tolerance,
        max_iterations=max_iterations,
    )
    final_point = point_at(root_throttle)
    return replace(final_point, converged=final_point.converged and abs(final_point.residual_thrust or 0.0) <= thrust_tolerance)


def solve_level_flight_operating_point(
    *,
    motor: ElectricMotor,
    propeller: PropellerModel,
    battery: BatteryPack | None = None,
    esc: ElectronicSpeedController | None = None,
    voltage: QuantityInput | None = None,
    airspeed: QuantityInput,
    density: QuantityInput = 1.225,
    required_drag: QuantityInput | None = None,
    drag_model: Callable[..., float] | None = None,
    rotational_speed_bounds: tuple[QuantityInput, QuantityInput] = (100.0, 50000.0),
    throttle_bounds: tuple[float, float] = (0.0, 1.0),
) -> PropulsionOperatingPoint:
    """Solve a simple level-flight point where thrust equals drag.

    This helper intentionally does not perform trim, path propagation, or drag
    buildup. It only evaluates a provided drag value or callable at the given
    airspeed and density, then reuses ``solve_throttle_for_required_thrust``.
    """
    airspeed_m_s = coerce_quantity("airspeed", airspeed, "m_s", "speed")
    density_kg_m3 = coerce_quantity("density", density, "kg_m3", "density")
    if required_drag is None and drag_model is None:
        raise ValueError("Provide required_drag or drag_model.")
    if required_drag is not None and drag_model is not None:
        raise ValueError("Provide required_drag or drag_model, not both.")

    if required_drag is not None:
        drag_n = coerce_quantity("required_drag", required_drag, "n", "force")
    else:
        try:
            drag_n = float(drag_model(airspeed_m_s, density_kg_m3))
        except TypeError:
            drag_n = float(drag_model(airspeed_m_s))

    return solve_throttle_for_required_thrust(
        motor=motor,
        propeller=propeller,
        required_thrust=drag_n,
        battery=battery,
        esc=esc,
        voltage=voltage,
        airspeed=airspeed_m_s,
        density=density_kg_m3,
        rotational_speed_bounds=rotational_speed_bounds,
        throttle_bounds=throttle_bounds,
    )


__all__ = [
    "PropulsionOperatingPoint",
    "solve_level_flight_operating_point",
    "solve_motor_prop_operating_point",
    "solve_throttle_for_required_thrust",
]
