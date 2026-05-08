"""Simple electronic speed controller model for motor-prop matching."""

from __future__ import annotations

from dataclasses import dataclass

from ac_design_toolbox.propulsion.units import (
    QuantityInput,
    coerce_fraction,
    coerce_optional_quantity,
    coerce_quantity,
)


@dataclass(frozen=True)
class EscOperatingPoint:
    """Resolved ESC state for one current and throttle setting.

    Stored units are V, A, and W. The model treats throttle as a linear scaling
    of the available bus voltage, then applies a simple efficiency factor and
    optional series-resistance drop.
    """

    input_voltage: float
    motor_voltage: float
    current: float
    throttle: float
    input_power: float
    motor_electrical_power: float
    loss_power: float
    is_within_limits: bool
    limit_notes: tuple[str, ...]


@dataclass(frozen=True)
class ElectronicSpeedController:
    """First-pass ESC model with linear throttle, efficiency, and resistance.

    The model is intentionally not a PWM switching simulation. It is meant to
    give the coupled motor-prop solver a transparent effective motor voltage
    and loss estimate while preserving a stable future adapter point.
    """

    efficiency: float = 1.0
    resistance: QuantityInput = 0.0
    max_current: QuantityInput | None = None
    max_voltage: QuantityInput | None = None
    name: str = ""

    def __post_init__(self) -> None:
        """Normalize ESC fields and validate limits."""
        efficiency = coerce_fraction("efficiency", self.efficiency)
        if efficiency <= 0.0:
            raise ValueError("efficiency must be positive.")
        object.__setattr__(self, "efficiency", efficiency)

        resistance = coerce_quantity("resistance", self.resistance, "ohm", "resistance")
        if resistance < 0.0:
            raise ValueError("resistance must be non-negative.")
        object.__setattr__(self, "resistance", resistance)

        max_current = coerce_optional_quantity("max_current", self.max_current, "a", "current")
        if max_current is not None and max_current <= 0.0:
            raise ValueError("max_current must be positive when provided.")
        object.__setattr__(self, "max_current", max_current)

        max_voltage = coerce_optional_quantity("max_voltage", self.max_voltage, "v", "voltage")
        if max_voltage is not None and max_voltage <= 0.0:
            raise ValueError("max_voltage must be positive when provided.")
        object.__setattr__(self, "max_voltage", max_voltage)
        object.__setattr__(self, "name", str(self.name))

    def motor_voltage(self, input_voltage: QuantityInput, current: QuantityInput, throttle: float = 1.0) -> float:
        """Return effective motor-side voltage for the given bus state."""
        input_voltage_v = coerce_quantity("input_voltage", input_voltage, "v", "voltage")
        current_a = coerce_quantity("current", current, "a", "current")
        throttle_fraction = coerce_fraction("throttle", throttle)
        return throttle_fraction * self.efficiency * input_voltage_v - current_a * self.resistance

    def evaluate(
        self,
        input_voltage: QuantityInput,
        current: QuantityInput,
        *,
        throttle: float = 1.0,
    ) -> EscOperatingPoint:
        """Return the ESC operating point and simple limit diagnostics."""
        input_voltage_v = coerce_quantity("input_voltage", input_voltage, "v", "voltage")
        current_a = coerce_quantity("current", current, "a", "current")
        throttle_fraction = coerce_fraction("throttle", throttle)
        motor_voltage = self.motor_voltage(input_voltage_v, current_a, throttle_fraction)
        input_power = input_voltage_v * current_a
        motor_electrical_power = motor_voltage * current_a
        loss_power = input_power - motor_electrical_power

        notes: list[str] = []
        if input_voltage_v <= 0.0:
            notes.append("ESC input voltage is non-positive.")
        if motor_voltage <= 0.0:
            notes.append("ESC motor-side voltage is non-positive.")
        if current_a < 0.0:
            notes.append("ESC current is negative; regenerative behavior is outside this model.")
        if loss_power < -1e-9:
            notes.append("ESC loss power is negative at this operating point.")
        if self.max_current is not None and abs(current_a) > self.max_current:
            notes.append(f"ESC current {abs(current_a):.3g} A exceeds max_current {self.max_current:.3g} A.")
        if self.max_voltage is not None and abs(input_voltage_v) > self.max_voltage:
            notes.append(f"ESC voltage {abs(input_voltage_v):.3g} V exceeds max_voltage {self.max_voltage:.3g} V.")

        return EscOperatingPoint(
            input_voltage=input_voltage_v,
            motor_voltage=motor_voltage,
            current=current_a,
            throttle=throttle_fraction,
            input_power=input_power,
            motor_electrical_power=motor_electrical_power,
            loss_power=loss_power,
            is_within_limits=not notes,
            limit_notes=tuple(notes),
        )


__all__ = [
    "ElectronicSpeedController",
    "EscOperatingPoint",
]
