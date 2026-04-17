# AC_Design_Toolbox

AC_Design_Toolbox is a research-oriented aircraft analysis toolbox focused on conceptual sizing, lightweight performance estimation, AeroSandbox-based geometry construction, and AVL-based aerodynamic and stability workflows.

The active package is organized so the public modules are also the modules that own the implementation. The goal is to make the toolbox easier to inspect, import, and integrate from other projects such as `Solar_UAS`.

## What The Toolbox Does

- Conceptual sizing and takeoff estimation
- Weight-fraction and first-pass sizing calculations
- Range, endurance, and simple propulsion/performance equations
- Mission-performance evaluation for prescribed air-relative operating points
- Standard-atmosphere utilities
- AeroSandbox aircraft geometry construction helpers
- AVL geometry export, case execution, parsing, neutral-point analysis, and longitudinal trim

## Preferred Module Layout

The new preferred import path is the `ac_design_toolbox` package:

- `ac_design_toolbox.atmosphere`
  - standard atmosphere, Reynolds number, and Mach number helpers
- `ac_design_toolbox.conceptual`
  - grouped conceptual-design equations
  - `takeoff.py`, `weights.py`, `range_endurance.py`, `performance.py`, `geometry_tools.py`, and `lifting_line.py` each contain the code implied by their names
- `ac_design_toolbox.mission`
  - mission-performance dataclasses and analytic operating-point evaluation
- `ac_design_toolbox.geometry`
  - package-level geometry entry points
- `ac_design_toolbox.geometry.aircraft`
  - `simple_aircraft(...)` for complete aircraft assembly
- `ac_design_toolbox.geometry.surfaces`
  - `make_wing(...)`, `make_ht(...)`, and `make_vt(...)`
- `ac_design_toolbox.geometry.avl_patch`
  - patched AeroSandbox AVL helpers
- `ac_design_toolbox.geometry.types`
  - shared geometry data structures such as `PlanformSolve`
- `ac_design_toolbox.avl`
  - package-level AVL entry points
- `ac_design_toolbox.avl.io`
  - geometry writing, case directories, keystrokes, and AVL process execution
- `ac_design_toolbox.avl.parsing`
  - total-force, strip-force, and stability-file parsing
- `ac_design_toolbox.avl.analysis`
  - operating-point runs plus neutral-point and static-margin utilities
- `ac_design_toolbox.avl.trim`
  - longitudinal trim workflow
- `ac_design_toolbox.avl.diagnostics`
  - diagnostic plotting for trim studies
- `ac_design_toolbox.api`
  - higher-level convenience API for common geometry + AVL workflows
- `ac_design_toolbox.avl.legacy_single_case`
  - preserved older single-case AVL path when that workflow is still useful

Small private helpers still exist where they reduce duplication cleanly:

- `ac_design_toolbox.geometry._common`
  - shared planform and geometry helpers used by multiple geometry builders
- `ac_design_toolbox.avl._helpers`
  - shared low-level AVL text parsing and axis-transform helpers

Archived compatibility copies live in [`_deprecated_compatibility_layer`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/_deprecated_compatibility_layer), but the supported interface for new work is the package namespace only.

## Recommended Entry Points

For conceptual equations:

```python
from ac_design_toolbox.conceptual import LoD_max, TO_ground_roll, wf_empty
from ac_design_toolbox.atmosphere import standard_atmosphere
```

For geometry generation:

```python
from ac_design_toolbox.geometry.aircraft import simple_aircraft
```

For programmatic AVL workflows:

```python
from ac_design_toolbox.api import AVLCaseConfig, prepare_avl_airplane, run_case
```

For air-relative mission-performance queries:

```python
from ac_design_toolbox.mission import (
    AnalyticMissionPerformanceModel,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
)
```

For lower-level AVL building blocks:

```python
from ac_design_toolbox.avl.analysis import run_avl_case
from ac_design_toolbox.avl.io import build_keystrokes, write_avl_files_asb
from ac_design_toolbox.avl.parsing import parse_stability_file, parse_strip_forces
```

## Typical Workflow

1. Build an aircraft with `simple_aircraft(...)`.
2. Prepare AVL geometry and control indexing with `prepare_avl_airplane(...)`.
3. Run an operating point with `run_case(...)` or call lower-level functions from `ac_design_toolbox.avl`.
4. Use `avl_neutral_point_and_SM(...)` or `avl_trim_longitudinal(...)` for stability and trim studies.

The `ac_design_toolbox.api` module exists specifically to reduce the hidden coupling between geometry generation and `control_index_map` handling inside AVL runs, while still keeping the lower-level geometry and AVL modules available when more control is needed.

## Mission Performance Interface

The mission-performance interface is the preferred way for an external mission
simulator to ask:

- for this air-relative operating point, what bank, pitch, load factor, drag,
  and propulsion power are implied?
- does that operating point violate simple aircraft-performance limits?

The interface is intentionally thin:

- inputs are air-relative operating points only
- wind models, ENU path propagation, and mission phase stepping remain external
- the default path is analytic and does not require AVL
- dimensional public inputs accept either bare scalars in canonical units,
  `(value, "unit")` tuples, or `[value, "unit"]` lists

Mission dataclasses normalize dimensional inputs immediately and then store
plain floats in the computational units used by the solver:

- `MissionOperatingPoint`
  - `altitude` in `m`
  - `airspeed` and `climb_rate` in `m_s`
  - `turn_radius` in `m`
  - `bank_hint` and `pitch_hint` in `deg`
  - `temp_shift` in `degF`
- `MissionAircraftPerformanceConfig`
  - `mass` in `kg`
  - `wing_area` in `m2`
  - `max_bank` in `deg`
- `MissionPerformancePoint`
  - `bank` and `pitch` in `deg`
  - `propulsion_power` in `w`
  - `drag_force` in `n`
  - `dynamic_pressure` in `pa`
  - `air_density` in `kg_m3`

The supported mission boundary units are intentionally small and explicit:

- length: `m`, `ft`
- speed/rate: `m_s`, `m/s`, `ft_s`, `ft/s`, `kts`, `kt`, `ft_min`, `ft/min`
- area: `m2`, `ft2`, `sqft`
- mass: `kg`, `lbm`, `lb`
- force: `n`, `lbf`
- power: `w`
- angle: `deg`
- time: `s`, `min`, `hr`
- pressure: `pa`
- density: `kg_m3`
- temperature delta: `degF`, `degC`

This is a clean-break public API change. The old suffix-based mission keyword
arguments such as `true_airspeed_m_s`, `turn_radius_m`, `mass_kg`, and
`max_bank_deg` are no longer accepted.

The analytic model currently assumes:

- atmospheric density comes from `standard_atmosphere(...)`
- bank comes from `bank_hint`, then turn radius, then coordinated straight
  flight
- pitch defaults to flight-path angle inferred from climb rate unless a pitch
  hint is provided for reporting
- drag follows a parabolic polar:
  `CD = CD0 + CL^2 / (pi * AR * e)`
- propulsion power follows drag plus climb-rate work divided by propulsive
  efficiency

An optional AVL-backed adapter is also available when AeroSandbox and AVL are
installed:

- `AVLMissionPerformanceModel` keeps the same air-relative operating-point
  interface
- bank angle and load factor still come from the prescribed mission state
- AVL is used to solve quasi-steady longitudinal trim at the required `CL`
- the current AVL path does not solve full banked-turn lateral trim, so turning
  effects enter through the target load factor rather than separate rudder or
  sideslip trim

Example:

```python
from ac_design_toolbox.mission import (
    AnalyticMissionPerformanceModel,
    MissionAircraftPerformanceConfig,
    MissionOperatingPoint,
)

config = MissionAircraftPerformanceConfig(
    mass=(26.455, "lbm"),
    wing_area=[25.8334, "sqft"],
    aspect_ratio=14.0,
    oswald_efficiency=0.85,
    zero_lift_drag_coefficient=0.03,
    propulsive_efficiency=0.75,
    max_lift_coefficient=1.3,
    max_bank=(55.0, "deg"),
    max_load_factor=2.5,
)
model = AnalyticMissionPerformanceModel(config)
result = model.evaluate(
    MissionOperatingPoint(
        phase_name="cruise",
        altitude=[2624.67, "ft"],
        airspeed=(24.0, "m/s"),
        climb_rate=[0.0, "ft/min"],
        temp_shift=(2.0, "degC"),
    )
)
```

If you want AVL-backed aerodynamic coefficients with the same external
interface:

```python
from ac_design_toolbox.mission import AVLMissionPerformanceModel
```

See [`examples/mission_performance_api.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/mission_performance_api.py)
for a runnable example.

## Example

See [`examples/refactored_toolbox_usage.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/refactored_toolbox_usage.py) for a geometry/AVL example and [`examples/mission_performance_api.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/mission_performance_api.py) for the new analytic mission-performance API.

## External Dependencies And Limitations

- Conceptual equations and atmosphere utilities use `numpy`, `scipy`, and `matplotlib`.
- The mission-performance analytic path uses the package atmosphere helper plus a transparent parabolic drag model.
- Geometry and AVL modules require `aerosandbox`.
- AVL execution requires a working AVL executable, such as [`avl.exe`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/avl.exe).
- Wind, ENU path propagation, and solar-power history are intentionally out of scope for `ac_design_toolbox`; those remain external mission-simulator responsibilities.
- The toolbox remains research-oriented. It is intended for transparent first-pass analysis, not production-grade multidisciplinary optimization.
