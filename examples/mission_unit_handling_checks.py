"""Runnable mission unit-handling checks and test-structure examples.

This script is meant to be a practical template for writing your own mission
boundary verification checks. It keeps many focused examples in one file so
you can see a few useful patterns:

- direct unit-helper conversion checks
- dataclass normalization checks
- equivalent-input invariance checks
- failure-case checks for unsupported units and removed legacy kwargs
- analytic-model result comparisons after normalization

The public mission API is the main focus. A few examples also import the
internal ``ac_design_toolbox.mission.units`` helpers directly because that is
sometimes convenient when debugging the boundary behavior itself.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Callable

# Allow the example to run directly from the repository without installation.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ac_design_toolbox.mission import (  # noqa: E402
    AnalyticMissionPerformanceModel,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
    MissionPerformancePoint,
)
from ac_design_toolbox.mission.units import (  # noqa: E402
    coerce_optional_quantity,
    coerce_quantity,
    convert_value,
    normalize_unit,
)


FT_TO_M = 0.3048
KTS_TO_M_S = 0.5144444444444445
FT2_TO_M2 = 0.09290304
LBM_TO_KG = 0.45359237
LBF_TO_N = 4.4482216152605


def assert_close(
    label: str,
    actual: float,
    expected: float,
    *,
    rel_tol: float = 1e-9,
    abs_tol: float = 1e-9,
) -> None:
    """Raise an informative assertion if two scalars are not close enough."""
    if not math.isclose(actual, expected, rel_tol=rel_tol, abs_tol=abs_tol):
        raise AssertionError(f"{label}: expected {expected:.12g}, got {actual:.12g}.")


def expect_exception(label: str, exception_type: type[BaseException], func: Callable[[], object]) -> None:
    """Verify that a callable raises the expected exception type."""
    try:
        func()
    except exception_type:
        return
    except Exception as exc:  # pragma: no cover - this is only for user-facing diagnostics.
        raise AssertionError(
            f"{label}: expected {exception_type.__name__}, got {type(exc).__name__}."
        ) from exc

    raise AssertionError(f"{label}: expected {exception_type.__name__}, but no exception was raised.")


def build_reference_config() -> MissionAircraftPerformanceConfig:
    """Return a reusable canonical aircraft config for the analytic examples."""
    return MissionAircraftPerformanceConfig(
        mass=12.0,
        wing_area=2.4,
        aspect_ratio=14.0,
        oswald_efficiency=0.85,
        zero_lift_drag_coefficient=0.03,
        propulsive_efficiency=0.75,
        max_lift_coefficient=1.5,
        max_bank=60.0,
        max_load_factor=3.0,
    )


def example_direct_unit_helper_conversions() -> None:
    """Check the small internal unit helper directly with explicit conversions."""
    exact_30_m_s_in_kts = 30.0 / KTS_TO_M_S

    assert normalize_unit("m/s") == "m_s"
    assert normalize_unit("KTS") == "kts"
    assert normalize_unit("sqft") == "ft2"
    assert normalize_unit("lb") == "lbm"
    assert normalize_unit("kg/m3") == "kg_m3"

    assert_close("1000 ft -> m", convert_value(1000.0, "ft", "m"), 1000.0 * FT_TO_M)
    assert_close("30 m/s -> kts", convert_value(30.0, "m_s", "kts"), 30.0 / KTS_TO_M_S)
    assert_close("500 ft/min -> m/s", convert_value(500.0, "ft_min", "m_s"), 500.0 * FT_TO_M / 60.0)
    assert_close("25 sqft -> m2", convert_value(25.0, "sqft", "m2"), 25.0 * FT2_TO_M2)
    assert_close("26 lbm -> kg", convert_value(26.0, "lbm", "kg"), 26.0 * LBM_TO_KG)
    assert_close("10 degC delta -> degF delta", convert_value(10.0, "degC", "degF"), 18.0)

    assert_close(
        "coerce_quantity speed",
        coerce_quantity("airspeed", (exact_30_m_s_in_kts, "kts"), "m_s", "speed"),
        30.0,
    )
    assert_close(
        "coerce_optional_quantity area",
        coerce_optional_quantity("wing_area", [25.0, "sqft"], "m2", "area") or 0.0,
        25.0 * FT2_TO_M2,
    )


def example_operating_point_normalization() -> None:
    """Check that mission operating-point inputs normalize immediately."""
    exact_30_m_s_in_kts = 30.0 / KTS_TO_M_S

    op = MissionOperatingPoint(
        phase_name="climb_turn",
        altitude=[8000.0, "ft"],
        airspeed=(exact_30_m_s_in_kts, "kts"),
        climb_rate=[500.0, "ft/min"],
        turn_radius=(500.0, "ft"),
        bank_hint=(30.0, "deg"),
        pitch_hint=[5.0, "deg"],
        temp_shift=(10.0, "degC"),
        metadata={"source": "unit-check"},
    )

    assert_close("op.altitude", op.altitude, 8000.0 * FT_TO_M)
    assert_close("op.airspeed", op.airspeed, 30.0)
    assert_close("op.climb_rate", op.climb_rate, 500.0 * FT_TO_M / 60.0)
    assert_close("op.turn_radius", op.turn_radius or 0.0, 500.0 * FT_TO_M)
    assert_close("op.bank_hint", op.bank_hint or 0.0, 30.0)
    assert_close("op.pitch_hint", op.pitch_hint or 0.0, 5.0)
    assert_close("op.temp_shift", op.temp_shift, 18.0)
    assert dict(op.metadata) == {"source": "unit-check"}

    def mutate_metadata() -> None:
        op.metadata["new_key"] = "should_fail"

    expect_exception("metadata is immutable", TypeError, mutate_metadata)


def example_aircraft_config_normalization() -> None:
    """Check that aircraft config inputs normalize into canonical units."""
    config = MissionAircraftPerformanceConfig(
        mass=(26.455, "lb"),
        wing_area=[25.8334, "sqft"],
        aspect_ratio=14.0,
        oswald_efficiency=0.85,
        zero_lift_drag_coefficient=0.03,
        propulsive_efficiency=0.75,
        max_lift_coefficient=1.5,
        max_bank=(55.0, "deg"),
        max_load_factor=2.5,
    )

    assert_close("config.mass", config.mass, 26.455 * LBM_TO_KG, abs_tol=5e-4)
    assert_close("config.wing_area", config.wing_area, 25.8334 * FT2_TO_M2, abs_tol=5e-5)
    assert_close("config.max_bank", config.max_bank or 0.0, 55.0)


def example_result_dataclass_normalization() -> None:
    """Check normalization on the public mission result dataclass too."""
    result = MissionPerformancePoint(
        feasible=True,
        bank=[25.0, "deg"],
        pitch=(4.0, "deg"),
        load_factor=1.2,
        propulsion_power=(1800.0, "w"),
        drag_force=(12.0, "lbf"),
        dynamic_pressure=(240.0, "pa"),
        air_density=(1.12, "kg/m3"),
        notes="manual check",
    )

    assert result.feasible is True
    assert_close("result.bank", result.bank, 25.0)
    assert_close("result.pitch", result.pitch, 4.0)
    assert_close("result.propulsion_power", result.propulsion_power, 1800.0)
    assert_close("result.drag_force", result.drag_force or 0.0, 12.0 * LBF_TO_N)
    assert_close("result.dynamic_pressure", result.dynamic_pressure or 0.0, 240.0)
    assert_close("result.air_density", result.air_density or 0.0, 1.12)


def example_equivalent_inputs_produce_same_normalized_objects() -> None:
    """Show how to compare bare canonical inputs against tuple/list inputs."""
    canonical_op = MissionOperatingPoint(
        phase_name="cruise",
        altitude=500.0,
        airspeed=22.0,
        climb_rate=0.0,
    )
    quantity_op = MissionOperatingPoint(
        phase_name="cruise",
        altitude=[500.0 / FT_TO_M, "ft"],
        airspeed=(22.0 / KTS_TO_M_S, "kts"),
        climb_rate=[0.0, "ft/min"],
    )

    canonical_config = build_reference_config()
    quantity_config = MissionAircraftPerformanceConfig(
        mass=(12.0 / LBM_TO_KG, "lb"),
        wing_area=[2.4 / FT2_TO_M2, "sqft"],
        aspect_ratio=14.0,
        oswald_efficiency=0.85,
        zero_lift_drag_coefficient=0.03,
        propulsive_efficiency=0.75,
        max_lift_coefficient=1.5,
        max_bank=(60.0, "deg"),
        max_load_factor=3.0,
    )

    assert_close("equivalent op altitude", quantity_op.altitude, canonical_op.altitude)
    assert_close("equivalent op airspeed", quantity_op.airspeed, canonical_op.airspeed)
    assert_close("equivalent op climb_rate", quantity_op.climb_rate, canonical_op.climb_rate)
    assert_close("equivalent config mass", quantity_config.mass, canonical_config.mass)
    assert_close("equivalent config wing_area", quantity_config.wing_area, canonical_config.wing_area)


def example_equivalent_inputs_produce_same_analytic_results() -> None:
    """Check that normalized-equivalent inputs give the same solver result."""
    canonical_model = AnalyticMissionPerformanceModel(build_reference_config())
    quantity_model = AnalyticMissionPerformanceModel(
        MissionAircraftPerformanceConfig(
            mass=(12.0 / LBM_TO_KG, "lb"),
            wing_area=[2.4 / FT2_TO_M2, "sqft"],
            aspect_ratio=14.0,
            oswald_efficiency=0.85,
            zero_lift_drag_coefficient=0.03,
            propulsive_efficiency=0.75,
            max_lift_coefficient=1.5,
            max_bank=(60.0, "deg"),
            max_load_factor=3.0,
        )
    )

    canonical_op = MissionOperatingPoint(
        phase_name="climb_turn",
        altitude=1200.0,
        airspeed=28.0,
        climb_rate=3.5,
        turn_radius=90.0,
        temp_shift=0.0,
    )
    quantity_op = MissionOperatingPoint(
        phase_name="climb_turn",
        altitude=[1200.0 / FT_TO_M, "ft"],
        airspeed=(28.0 / KTS_TO_M_S, "kts"),
        climb_rate=[3.5 / FT_TO_M * 60.0, "ft/min"],
        turn_radius=[90.0 / FT_TO_M, "ft"],
        temp_shift=(0.0, "degC"),
    )

    canonical_result = canonical_model.evaluate(canonical_op)
    quantity_result = quantity_model.evaluate(quantity_op)

    assert canonical_result.feasible == quantity_result.feasible
    assert_close("result.bank", quantity_result.bank, canonical_result.bank)
    assert_close("result.pitch", quantity_result.pitch, canonical_result.pitch)
    assert_close("result.load_factor", quantity_result.load_factor, canonical_result.load_factor)
    assert_close("result.drag_force", quantity_result.drag_force or 0.0, canonical_result.drag_force or 0.0)
    assert_close(
        "result.propulsion_power",
        quantity_result.propulsion_power,
        canonical_result.propulsion_power,
    )
    assert_close(
        "result.dynamic_pressure",
        quantity_result.dynamic_pressure or 0.0,
        canonical_result.dynamic_pressure or 0.0,
    )
    assert_close(
        "result.air_density",
        quantity_result.air_density or 0.0,
        canonical_result.air_density or 0.0,
    )


def example_invalid_inputs_fail_cleanly() -> None:
    """Show a few useful failure-case test patterns."""
    expect_exception(
        "unsupported speed unit",
        ValueError,
        lambda: MissionOperatingPoint(
            phase_name="bad_speed",
            altitude=0.0,
            airspeed=(20.0, "mph"),
            climb_rate=0.0,
        ),
    )
    expect_exception(
        "malformed quantity length",
        TypeError,
        lambda: MissionOperatingPoint(
            phase_name="bad_shape",
            altitude=[1000.0, "ft", "extra"],
            airspeed=20.0,
            climb_rate=0.0,
        ),
    )
    expect_exception(
        "legacy suffix kwargs removed",
        TypeError,
        lambda: MissionOperatingPoint(
            phase_name="legacy",
            altitude_m=0.0,
            true_airspeed_m_s=20.0,
            climb_rate_m_s=0.0,
        ),
    )
    expect_exception(
        "negative turn radius rejected",
        ValueError,
        lambda: MissionOperatingPoint(
            phase_name="bad_turn",
            altitude=0.0,
            airspeed=20.0,
            climb_rate=0.0,
            turn_radius=-10.0,
        ),
    )


def example_alias_spellings() -> None:
    """Demonstrate several accepted alias spellings in one place."""
    alias_config = MissionAircraftPerformanceConfig(
        mass=(12.0 / LBM_TO_KG, "lb"),
        wing_area=(2.4 / FT2_TO_M2, "sqft"),
        aspect_ratio=14.0,
        oswald_efficiency=0.85,
        zero_lift_drag_coefficient=0.03,
        propulsive_efficiency=0.75,
        max_bank=(45.0, "deg"),
    )
    alias_op = MissionOperatingPoint(
        phase_name="alias_demo",
        altitude=(1000.0 / FT_TO_M, "ft"),
        airspeed=(20.0, "m/s"),
        climb_rate=(200.0, "ft/min"),
        temp_shift=(5.0, "degC"),
    )
    alias_result = MissionPerformancePoint(
        feasible=True,
        bank=(10.0, "deg"),
        pitch=(2.0, "deg"),
        load_factor=1.0,
        propulsion_power=(500.0, "w"),
        drag_force=(5.0, "lbf"),
        dynamic_pressure=(123.0, "pa"),
        air_density=(1.2, "kg/m3"),
    )

    assert_close("alias config mass", alias_config.mass, 12.0)
    assert_close("alias config wing_area", alias_config.wing_area, 2.4)
    assert_close("alias op climb_rate", alias_op.climb_rate, 200.0 * FT_TO_M / 60.0)
    assert_close("alias op temp_shift", alias_op.temp_shift, 9.0)
    assert_close("alias result drag_force", alias_result.drag_force or 0.0, 5.0 * LBF_TO_N)


def run_example(name: str, func: Callable[[], None]) -> bool:
    """Run one example and print a readable pass/fail line."""
    try:
        func()
    except Exception as exc:
        print(f"[FAIL] {name}: {exc}")
        return False

    print(f"[PASS] {name}")
    return True


def main() -> int:
    """Run all example checks and return a process exit code."""
    examples: list[tuple[str, Callable[[], None]]] = [
        ("direct unit helper conversions", example_direct_unit_helper_conversions),
        ("operating point normalization", example_operating_point_normalization),
        ("aircraft config normalization", example_aircraft_config_normalization),
        ("result dataclass normalization", example_result_dataclass_normalization),
        ("equivalent normalized objects", example_equivalent_inputs_produce_same_normalized_objects),
        ("equivalent analytic results", example_equivalent_inputs_produce_same_analytic_results),
        ("invalid input failures", example_invalid_inputs_fail_cleanly),
        ("alias spellings", example_alias_spellings),
    ]

    print("Mission unit-handling checks")
    print(f"Repository root: {REPO_ROOT}")

    failures = 0
    for name, func in examples:
        if not run_example(name, func):
            failures += 1

    if failures:
        print(f"\nCompleted with {failures} failing example(s).")
        return 1

    print(f"\nCompleted successfully: {len(examples)} example(s) passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
