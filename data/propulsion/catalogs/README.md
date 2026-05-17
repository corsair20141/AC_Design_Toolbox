# Editable Propulsion Component Catalogs

This directory contains user-editable CSV catalogs for electric propulsion
components. The rows committed here are fictional examples, not validated
product recommendations.

The loader API lives in `ac_design_toolbox.propulsion.catalogs` and constructs
the existing propulsion dataclasses directly:

- `motors.csv` -> `ElectricMotor`
- `batteries.csv` -> `BatteryPack`
- `escs.csv` -> `ElectronicSpeedController`

Propeller data is intentionally not duplicated here. Use the APC and UIUC
propeller database loaders documented in `data/propellers/README.md`.

## Editing Rules

- Keep `catalog_id` stable and unique. Other tools use it as the dictionary key.
- Leave optional value/unit cells blank when the value is unknown.
- If a value has a unit, put the number in `*_value` and the unit in the
  adjacent `*_unit` column.
- Optional `mass_value` / `mass_unit` columns describe reusable component mass.
  Aircraft-specific component locations belong in the aircraft W&B workflow,
  not in these catalogs.
- Bare unitless columns such as `gear_ratio`, `gear_efficiency`, `soc`, and
  `efficiency` are fractions or scalar multipliers.
- The supported units are the same units accepted by
  `ac_design_toolbox.propulsion.units`.

Example:

```python
from ac_design_toolbox.propulsion import load_propulsion_catalogs

catalogs = load_propulsion_catalogs()
motor = catalogs.motors["example_920kv_outrunner"]
battery = catalogs.batteries["example_4s_lipo"]
esc = catalogs.escs["example_80a_esc"]
```
