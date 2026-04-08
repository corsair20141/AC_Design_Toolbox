# AC_Design_Toolbox

AC_Design_Toolbox is a research-oriented aircraft analysis toolbox focused on conceptual sizing, lightweight performance estimation, AeroSandbox-based geometry construction, and AVL-based aerodynamic and stability workflows.

The active package is organized so the public modules are also the modules that own the implementation. The goal is to make the toolbox easier to inspect, import, and integrate from other projects such as `Solar_UAS`.

## What The Toolbox Does

- Conceptual sizing and takeoff estimation
- Weight-fraction and first-pass sizing calculations
- Range, endurance, and simple propulsion/performance equations
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

## Example

See [`examples/refactored_toolbox_usage.py`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/examples/refactored_toolbox_usage.py) for a simple end-to-end usage example.

## External Dependencies And Limitations

- Conceptual equations and atmosphere utilities use `numpy`, `scipy`, and `matplotlib`.
- Geometry and AVL modules require `aerosandbox`.
- AVL execution requires a working AVL executable, such as [`avl.exe`](/C:/Users/corsa/OneDrive%20-%20The%20University%20of%20Alabama/_PhD/99%20CODES/01%20Aero/AC_Design_Toolbox/avl.exe).
- The toolbox remains research-oriented. It is intended for transparent first-pass analysis, not production-grade multidisciplinary optimization.
