"""Electric propulsion models and motor-prop operating-point solvers."""

from ac_design_toolbox.propulsion.battery import BatteryOperatingPoint, BatteryPack
from ac_design_toolbox.propulsion.catalogs import (
    DEFAULT_CATALOG_ROOT,
    PropulsionCatalogs,
    load_battery_catalog,
    load_esc_catalog,
    load_motor_catalog,
    load_propulsion_catalogs,
)
from ac_design_toolbox.propulsion.data import (
    PropellerTableSet,
    infer_diameter_from_name,
    infer_propeller_size_from_name,
    load_apc_performance_file,
    load_apc_table_for_rpm,
    load_uiuc_performance_file,
    load_uiuc_table_set,
    parse_apc_performance_text,
    parse_uiuc_performance_text,
)
from ac_design_toolbox.propulsion.esc import ElectronicSpeedController, EscOperatingPoint
from ac_design_toolbox.propulsion.motor import ElectricMotor, MotorOperatingPoint
from ac_design_toolbox.propulsion.operating_point import (
    PropulsionOperatingPoint,
    solve_level_flight_operating_point,
    solve_motor_prop_operating_point,
    solve_throttle_for_required_thrust,
)
from ac_design_toolbox.propulsion.propeller import (
    CoefficientPropeller,
    PropellerModel,
    PropellerOperatingPoint,
    TabulatedPropeller,
)
from ac_design_toolbox.propulsion.units import QuantityInput, convert_value, normalize_unit

__all__ = [
    "BatteryOperatingPoint",
    "BatteryPack",
    "CoefficientPropeller",
    "DEFAULT_CATALOG_ROOT",
    "ElectricMotor",
    "ElectronicSpeedController",
    "EscOperatingPoint",
    "MotorOperatingPoint",
    "PropellerModel",
    "PropellerTableSet",
    "PropellerOperatingPoint",
    "PropulsionCatalogs",
    "PropulsionOperatingPoint",
    "QuantityInput",
    "TabulatedPropeller",
    "convert_value",
    "infer_diameter_from_name",
    "infer_propeller_size_from_name",
    "load_apc_performance_file",
    "load_apc_table_for_rpm",
    "load_battery_catalog",
    "load_esc_catalog",
    "load_motor_catalog",
    "load_propulsion_catalogs",
    "load_uiuc_performance_file",
    "load_uiuc_table_set",
    "normalize_unit",
    "parse_apc_performance_text",
    "parse_uiuc_performance_text",
    "solve_level_flight_operating_point",
    "solve_motor_prop_operating_point",
    "solve_throttle_for_required_thrust",
]
