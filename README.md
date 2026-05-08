# AC_Design_Toolbox

AC_Design_Toolbox is a research-oriented aircraft analysis toolbox focused on conceptual sizing, lightweight performance estimation, AeroSandbox-based geometry construction, and AVL-based aerodynamic and stability workflows.

The active package is organized so the public modules are also the modules that own the implementation. The goal is to make the toolbox easier to inspect, import, and integrate from other projects such as `Solar_UAS`.

## What The Toolbox Does

- Conceptual sizing and takeoff estimation
- Weight-fraction and first-pass sizing calculations
- Range, endurance, and simple propulsion/performance equations
- Mission-performance evaluation for prescribed air-relative operating points
- Non-solar battery, propulsion-electrical, load, and component-mass primitives
- Electric motor, ESC, battery, propeller, and operating-point matching primitives
- Canonical aircraft-definition schemas with JSON import/export and rendering helpers
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
- `ac_design_toolbox.energy`
  - battery energy-bucket parameters, propulsion/load electrical limits, and component mass buildup
- `ac_design_toolbox.propulsion`
  - electric motor, ESC, battery voltage-sag, propeller, and motor-prop matching models
- `ac_design_toolbox.aircraft_config`
  - canonical aircraft definitions, JSON helpers, geometry assembly, optimizer-variable metadata, and rendering helpers
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

For canonical aircraft-definition workflows:

```python
from ac_design_toolbox.aircraft_config import (
    AircraftDefinition,
    build_aircraft,
    render_aircraft_plotly,
)
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

For electric motor-prop operating-point matching:

```python
from ac_design_toolbox.propulsion import (
    BatteryPack,
    CoefficientPropeller,
    ElectricMotor,
    ElectronicSpeedController,
    solve_motor_prop_operating_point,
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

## Aircraft Configuration Interface

The aircraft-configuration interface is the preferred way to define an aircraft
when the object needs to be:

- saved and reloaded as JSON
- edited through an external GUI such as the `Solar_UAS` configurator
- compared across multiple candidate designs
- tagged with optimizer-facing variable metadata

The public interface is centered on:

- `AircraftDefinition`
- `LiftingSurfaceConfig`
- `DesignVariableSpec`
- `build_aircraft(...)`
- `render_aircraft_plotly(...)`
- `render_aircraft_three_view_image(...)`

`AircraftDefinition` is versioned and JSON-round-trippable. It stores:

- canonical geometry for the reference point, explicit `lifting_surfaces`, and a simple fuselage
- stable component IDs for buildable lifting surfaces, including mirrored right/left IDs for symmetric vertical surfaces
- optimizer-facing variable metadata through `design_variables`
- extension data under `extensions`

The canonical aircraft schema is now a hard-break explicit surface-list model:

- `AircraftDefinition.main_wing` and `AircraftDefinition.tail_assembly` were removed from the canonical JSON shape.
- All wing-like geometry lives in `AircraftDefinition.lifting_surfaces: list[LiftingSurfaceConfig]`.
- `LiftingSurfaceConfig.role` records the design intent for each surface:
  - `main_wing`
  - `wing`
  - `horizontal_tail`
  - `vertical_tail`
  - `canted_tail`
  - `canard`
  - `other`
- `LiftingSurfaceConfig.orientation` is either `horizontal` or `vertical`.
- Exactly one `role="main_wing"` surface is required.
- Tail surfaces are optional, so tailless aircraft are valid.
- Symmetry is explicit metadata:
  - symmetric horizontal surfaces build as mirrored AeroSandbox wings
  - symmetric vertical surfaces build as right/left mirrored component pairs
  - non-symmetric surfaces are literal one-side components

The aircraft-config package also exposes public first-pass sizing helpers for
external tools that need to stay aligned with the canonical geometry math:

- `solve_planform(...)`
- `planform_quarter_chord_x(...)`
- `solve_horizontal_tail_area_from_volume_coefficient(...)`
- `solve_vertical_tail_area_from_volume_coefficient(...)`
- mirrored canted-tail and twin-fin area helpers for projected-equivalent
  volume sizing

That interface is intentionally shared across repos. `Solar_UAS` owns only its
own extension namespace, currently `extensions["solar_uas"]`, while ACDT owns
the canonical aircraft-definition schema itself.

Example:

```python
from ac_design_toolbox.aircraft_config import (
    AircraftDefinition,
    LiftingSurfaceConfig,
    build_aircraft,
    render_aircraft_three_view_image,
)

definition = AircraftDefinition(
    name="Tailless Testbed",
    lifting_surfaces=[
        LiftingSurfaceConfig(
            component_id="main_wing",
            role="main_wing",
            orientation="horizontal",
            symmetric=True,
            span=6.0,
            area=2.4,
            taper=0.6,
            sweep_le_deg=4.0,
            dihedral_deg=6.0,
            x_le=0.3,
            y_le=0.0,
            z_le=0.05,
            root_airfoil="naca4412",
            tip_airfoil="naca4412",
        )
    ],
)
airplane = build_aircraft(definition)
three_view_png = render_aircraft_three_view_image(definition, unit_system="imperial")
```

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

## Energy Component API

`ac_design_toolbox.energy` owns non-solar aircraft energy primitives that can
be reused by external mission tools without importing Solar_UAS, Dash, or
mission propagation code. The first-pass API includes:

- `BatteryPackConfig`
  - energy capacity in Wh, usable SOC bounds, initial SOC, voltage,
    charge/discharge efficiency, optional power/current limits, and mass or
    specific energy
- `PropulsionElectricalConfig`
  - propulsion bus-power/current limits and propulsion component mass
- `ElectricalLoadConfig`
  - named reusable payload/hotel-load definitions and optional load mass
- `AircraftEnergyConfig`
  - base mass, battery, propulsion, loads, extra mass items, and mass breakdown
- `EnergyLimitViolation`
  - optimizer-facing component-limit diagnostics with signed margins

The energy package deliberately does not simulate missions, wind, solar
generation, or path geometry. External tools such as `Solar_UAS` schedule loads
over a mission history and feed solar panel mass back as an external mass item.

## Electric Propulsion Operating-Point API

`ac_design_toolbox.propulsion` owns first-pass motor, ESC, battery, and
propeller operating-point analysis for off-the-shelf small aircraft and UAS
propulsion components. It is meant for matching known components, not designing
new propellers.

The public API follows the repo's semantic unit-boundary convention:

- public field names use domain names such as `voltage`, `current`, `torque`,
  `rotational_speed`, `thrust`, `diameter`, and `density`
- dimensional inputs accept bare scalars in the documented canonical unit or
  `(value, "unit")` / `[value, "unit"]` pairs
- public boundaries normalize immediately, then solver math uses plain floats
- catalog motor Kv should be passed explicitly, for example
  `kv=(920.0, "rpm/V")`; internally the motor equations use rad/s/V

Stored computational units are V, A, ohm, N*m, rad/s, rpm for reported shaft
speed, N, W, m/s, kg/m3, m, and Ah. The first-pass equations are intentionally
transparent:

- motor speed/back-EMF: `omega = Kv * v_back_emf`
- motor torque: `Q = Kt * (i - i0)`, with `Kt = 1 / Kv`
- motor terminal voltage: `v = v_back_emf + iR`
- propeller advance ratio: `J = V / (nD)`
- propeller thrust and power: `T = CT*rho*n^2*D^4` and
  `P = CP*rho*n^3*D^5`
- coupled motor-prop RPM is the root where motor output torque equals
  propeller torque

The first-pass battery model supports both fixed pack voltage and simple
SOC-dependent open-circuit voltage:

- `chemistry="constant"` keeps the original behavior:
  `terminal_voltage = nominal_voltage - current * internal_resistance`
- `chemistry="generic_lipo"` and `chemistry="generic_liion"` interpolate
  approximate default V/cell curves versus SOC, multiply by `n_series`, then
  apply the same internal-resistance sag
- `chemistry="custom"` accepts a user-provided pack-level OCV-SOC curve for
  manufacturer or measured data
- `mass` can be specified directly for a known pack, or derived from
  `capacity * nominal_voltage / specific_energy` for rubber-battery sizing

Default OCV-SOC curves are approximate first-order placeholders. Replace them
with manufacturer or measured cell data for validation-quality predictions.

The first-pass component models are deliberately limited:

- `BatteryPack` does not integrate SOC over time
- battery voltage does not include temperature effects, aging, hysteresis, or
  advanced equivalent-circuit dynamics
- `ElectronicSpeedController` uses linear throttle, efficiency, and optional
  resistance, not detailed PWM switching physics
- `CoefficientPropeller` is for smoke tests and conceptual estimates
- `TabulatedPropeller` interpolates CT/CP versus advance ratio and is the
  intended future home for UIUC, APC, or static-test coefficient data
- `ac_design_toolbox.propulsion.data` parses UIUC `J CT CP eta` files and APC
  `PER3_*.dat` RPM blocks into `TabulatedPropeller` tables

Optional backend adapters live under `ac_design_toolbox.propulsion.backends`.
They import PyProp or AeroSandbox lazily so the core propulsion package remains
usable without those packages. The current AeroSandbox adapter is for motor
model comparison; the PyProp adapter is a scaffold for a future tested mapping.

External mission tools such as `Solar_UAS` should call the propulsion solver at
their own air-relative operating points and keep mission path propagation, wind,
solar history, and battery SOC scheduling outside ACDT.

See [`examples/run_propulsion_operating_point_demo.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/run_propulsion_operating_point_demo.py)
for a minimal runnable motor, ESC, battery, and propeller operating-point
example.

For third-party propeller data downloads and local layout guidance, see
[`data/propellers/README.md`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/data/propellers/README.md).

## Example

See [`examples/refactored_toolbox_usage.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/refactored_toolbox_usage.py) for a geometry/AVL example, [`examples/mission_performance_api.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/mission_performance_api.py) for the analytic mission-performance API, and [`examples/run_propulsion_operating_point_demo.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/run_propulsion_operating_point_demo.py) for the electric propulsion operating-point API.

## External Dependencies And Limitations

- Conceptual equations and atmosphere utilities use `numpy`, `scipy`, and `matplotlib`.
- The mission-performance analytic path uses the package atmosphere helper plus a transparent parabolic drag model.
- The aircraft-config builder and geometry/AVL modules require `aerosandbox`.
- The core propulsion package does not require PyProp or AeroSandbox; optional
  comparison adapters import those packages lazily.
- The aircraft-config rendering helpers use `plotly` plus Matplotlib image export for three-view payloads.
- AVL execution requires a working AVL executable, such as [`avl.exe`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/avl.exe).
- Wind, ENU path propagation, and solar-power history are intentionally out of scope for `ac_design_toolbox`; those remain external mission-simulator responsibilities.
- The toolbox remains research-oriented. It is intended for transparent first-pass analysis, not production-grade multidisciplinary optimization.
