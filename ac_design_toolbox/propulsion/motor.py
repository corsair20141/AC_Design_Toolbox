"""First-order electric motor model for small aircraft propulsion matching."""

from __future__ import annotations

from dataclasses import dataclass

from ac_design_toolbox.propulsion.units import (
    QuantityInput,
    angular_speed_to_rotational_speed,
    coerce_fraction,
    coerce_optional_quantity,
    coerce_quantity,
    require_finite_scalar,
    rotational_speed_to_angular_speed,
)


@dataclass(frozen=True)
class MotorOperatingPoint:
    """Resolved motor state at one output-shaft operating point.

    Stored units are V, A, rpm, rad/s, N*m, and W. ``rotational_speed`` and
    ``angular_speed`` describe the output shaft, so they are also the propeller
    speed for a direct motor-prop coupling.
    """

    voltage: float
    current: float
    rotational_speed: float
    angular_speed: float
    torque: float
    shaft_power: float
    electrical_power: float
    efficiency: float
    waste_heat: float
    is_within_limits: bool
    limit_notes: tuple[str, ...]


@dataclass(frozen=True)
class ElectricMotor:
    """First-order BLDC/DC motor model with optional gearbox.

    Public dimensional inputs accept bare scalars in the stored computational
    unit or ``(value, "unit")`` pairs. After normalization this dataclass
    stores ``kv`` as rad/s/V, resistance as ohm, currents as A, voltage as V,
    power as W, optional mass as kg, and gear ratio as motor speed divided by
    output-shaft speed.

    The equations follow the transparent Drela/Ning first-order model:
    back EMF is proportional to angular speed, torque is proportional to
    current above no-load current, and winding resistance accounts for voltage
    drop. Generator operation is not modeled as a supported operating mode, but
    negative-current states are reported with limit notes instead of hidden.
    """

    kv: QuantityInput
    resistance: QuantityInput
    no_load_current: QuantityInput = 0.0
    max_current: QuantityInput | None = None
    max_voltage: QuantityInput | None = None
    max_power: QuantityInput | None = None
    mass: QuantityInput | None = None
    gear_ratio: float = 1.0
    gear_efficiency: float = 1.0
    name: str = ""

    def __post_init__(self) -> None:
        """Normalize motor constants and validate optional limits."""
        kv = coerce_quantity("kv", self.kv, "rad_s_v", "speed_constant")
        if kv <= 0.0:
            raise ValueError("kv must be positive.")
        object.__setattr__(self, "kv", kv)

        resistance = coerce_quantity("resistance", self.resistance, "ohm", "resistance")
        if resistance <= 0.0:
            raise ValueError("resistance must be positive.")
        object.__setattr__(self, "resistance", resistance)

        no_load_current = coerce_quantity("no_load_current", self.no_load_current, "a", "current")
        if no_load_current < 0.0:
            raise ValueError("no_load_current must be non-negative.")
        object.__setattr__(self, "no_load_current", no_load_current)

        max_current = coerce_optional_quantity("max_current", self.max_current, "a", "current")
        if max_current is not None and max_current <= 0.0:
            raise ValueError("max_current must be positive when provided.")
        object.__setattr__(self, "max_current", max_current)

        max_voltage = coerce_optional_quantity("max_voltage", self.max_voltage, "v", "voltage")
        if max_voltage is not None and max_voltage <= 0.0:
            raise ValueError("max_voltage must be positive when provided.")
        object.__setattr__(self, "max_voltage", max_voltage)

        max_power = coerce_optional_quantity("max_power", self.max_power, "w", "power")
        if max_power is not None and max_power <= 0.0:
            raise ValueError("max_power must be positive when provided.")
        object.__setattr__(self, "max_power", max_power)

        mass = coerce_optional_quantity("mass", self.mass, "kg", "mass")
        if mass is not None and mass <= 0.0:
            raise ValueError("mass must be positive when provided.")
        object.__setattr__(self, "mass", mass)

        gear_ratio = require_finite_scalar("gear_ratio", self.gear_ratio)
        if gear_ratio <= 0.0:
            raise ValueError("gear_ratio must be positive.")
        object.__setattr__(self, "gear_ratio", gear_ratio)

        gear_efficiency = coerce_fraction("gear_efficiency", self.gear_efficiency)
        if gear_efficiency <= 0.0:
            raise ValueError("gear_efficiency must be positive.")
        object.__setattr__(self, "gear_efficiency", gear_efficiency)
        object.__setattr__(self, "name", str(self.name))

    @property
    def speed_constant(self) -> float:
        """Return motor speed constant in rad/s/V."""
        return self.kv

    @property
    def torque_constant(self) -> float:
        """Return motor torque constant in N*m/A."""
        return 1.0 / self.speed_constant

    def estimate_current_for_torque(self, torque: QuantityInput) -> float:
        """Estimate motor current needed for a requested output-shaft torque."""
        output_torque = coerce_quantity("torque", torque, "n_m", "torque")
        if output_torque < 0.0:
            raise ValueError("torque must be non-negative for motor-mode estimates.")

        motor_torque = output_torque / (self.gear_ratio * self.gear_efficiency)
        return motor_torque / self.torque_constant + self.no_load_current

    def estimate_torque_for_current(self, current: QuantityInput) -> float:
        """Estimate output-shaft torque from motor current."""
        current_a = coerce_quantity("current", current, "a", "current")
        motor_torque = self.torque_constant * (current_a - self.no_load_current)
        return motor_torque * self.gear_ratio * self.gear_efficiency

    def evaluate_from_voltage_and_rotational_speed(
        self,
        voltage: QuantityInput,
        rotational_speed: QuantityInput,
        *,
        throttle: float = 1.0,
    ) -> MotorOperatingPoint:
        """Evaluate motor state from terminal voltage and output rotational speed.

        ``voltage`` is the motor-terminal voltage before the optional simple
        throttle scaling in this method. Most coupled analyses should pass
        ``throttle=1`` here and let the ESC model own throttle behavior.
        """
        voltage_v = coerce_quantity("voltage", voltage, "v", "voltage")
        throttle_fraction = coerce_fraction("throttle", throttle)
        effective_voltage = voltage_v * throttle_fraction
        output_rotational_speed = coerce_quantity("rotational_speed", rotational_speed, "rpm", "rotational_speed")
        if output_rotational_speed < 0.0:
            raise ValueError("rotational_speed must be non-negative.")

        output_omega = rotational_speed_to_angular_speed(output_rotational_speed)
        motor_omega = output_omega * self.gear_ratio
        back_emf_voltage = motor_omega / self.speed_constant
        current = (effective_voltage - back_emf_voltage) / self.resistance
        torque = self.estimate_torque_for_current(current)

        return self._make_operating_point(
            voltage=effective_voltage,
            current=current,
            rotational_speed=output_rotational_speed,
            angular_speed=output_omega,
            torque=torque,
        )

    def evaluate_from_voltage_and_torque(
        self,
        voltage: QuantityInput,
        torque: QuantityInput,
        *,
        throttle: float = 1.0,
    ) -> MotorOperatingPoint:
        """Evaluate motor state from terminal voltage and output-shaft torque."""
        voltage_v = coerce_quantity("voltage", voltage, "v", "voltage")
        throttle_fraction = coerce_fraction("throttle", throttle)
        effective_voltage = voltage_v * throttle_fraction
        output_torque = coerce_quantity("torque", torque, "n_m", "torque")
        if output_torque < 0.0:
            raise ValueError("torque must be non-negative for motor-mode estimates.")

        current = self.estimate_current_for_torque(output_torque)
        motor_omega = self.speed_constant * (effective_voltage - current * self.resistance)
        output_omega = motor_omega / self.gear_ratio
        output_rotational_speed = angular_speed_to_rotational_speed(output_omega)

        return self._make_operating_point(
            voltage=effective_voltage,
            current=current,
            rotational_speed=output_rotational_speed,
            angular_speed=output_omega,
            torque=output_torque,
        )

    def _make_operating_point(
        self,
        *,
        voltage: float,
        current: float,
        rotational_speed: float,
        angular_speed: float,
        torque: float,
    ) -> MotorOperatingPoint:
        """Build a result object and attach simple validity diagnostics."""
        shaft_power = torque * angular_speed
        electrical_power = voltage * current
        efficiency = shaft_power / electrical_power if electrical_power > 0.0 else 0.0
        waste_heat = electrical_power - shaft_power

        notes: list[str] = []
        if voltage <= 0.0:
            notes.append("Motor terminal voltage is non-positive.")
        if current < 0.0:
            notes.append("Motor current is negative; generator operation is not modeled as valid motor mode.")
        if torque < 0.0:
            notes.append("Motor torque is negative at this speed and voltage.")
        if rotational_speed < 0.0 or angular_speed < 0.0:
            notes.append("Motor speed is negative at this voltage and torque.")
        if electrical_power <= 0.0 and shaft_power > 0.0:
            notes.append("Shaft power is positive while electrical power is non-positive.")
        if efficiency < 0.0 or efficiency > 1.0:
            notes.append("Motor efficiency is outside the physical motor-mode interval [0, 1].")
        if waste_heat < -1e-9:
            notes.append("Computed motor waste heat is negative.")
        if self.max_current is not None and abs(current) > self.max_current:
            notes.append(f"Motor current {abs(current):.3g} A exceeds max_current {self.max_current:.3g} A.")
        if self.max_voltage is not None and abs(voltage) > self.max_voltage:
            notes.append(f"Motor voltage {abs(voltage):.3g} V exceeds max_voltage {self.max_voltage:.3g} V.")
        if self.max_power is not None and abs(electrical_power) > self.max_power:
            notes.append(
                f"Motor electrical power {abs(electrical_power):.3g} W exceeds max_power {self.max_power:.3g} W."
            )

        return MotorOperatingPoint(
            voltage=voltage,
            current=current,
            rotational_speed=rotational_speed,
            angular_speed=angular_speed,
            torque=torque,
            shaft_power=shaft_power,
            electrical_power=electrical_power,
            efficiency=efficiency,
            waste_heat=waste_heat,
            is_within_limits=not notes,
            limit_notes=tuple(notes),
        )


__all__ = [
    "ElectricMotor",
    "MotorOperatingPoint",
]
