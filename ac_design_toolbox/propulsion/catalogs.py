"""CSV-backed catalogs for editable electric propulsion components.

The catalog layer is intentionally thin: it reads user-editable CSV files and
constructs the existing propulsion dataclasses. It does not introduce a second
component model, database, or dependency-heavy schema system.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping, TypeVar

from ac_design_toolbox.propulsion.battery import BatteryPack
from ac_design_toolbox.propulsion.esc import ElectronicSpeedController
from ac_design_toolbox.propulsion.motor import ElectricMotor
from ac_design_toolbox.propulsion.units import QuantityInput


ComponentT = TypeVar("ComponentT")
DEFAULT_CATALOG_ROOT = Path(__file__).resolve().parents[2] / "data" / "propulsion" / "catalogs"
"""Default repository-local directory for editable propulsion catalog CSVs."""


@dataclass(frozen=True)
class PropulsionCatalogs:
    """Loaded propulsion component catalogs keyed by stable catalog IDs."""

    motors: dict[str, ElectricMotor]
    batteries: dict[str, BatteryPack]
    escs: dict[str, ElectronicSpeedController]


def _normalized_cell(row: Mapping[str, str | None], column: str) -> str:
    """Return a stripped CSV cell value, treating missing or blank cells as empty."""
    value = row.get(column)
    if value is None:
        return ""
    return str(value).strip()


def _required_text(row: Mapping[str, str | None], column: str, *, path: Path, row_number: int) -> str:
    """Return a required text field or raise a row-specific catalog error."""
    value = _normalized_cell(row, column)
    if not value:
        raise ValueError(f"{path}: row {row_number} is missing required column {column!r}.")
    return value


def _optional_text(row: Mapping[str, str | None], column: str) -> str:
    """Return an optional text field with surrounding whitespace removed."""
    return _normalized_cell(row, column)


def _optional_float(row: Mapping[str, str | None], column: str, *, path: Path, row_number: int) -> float | None:
    """Return an optional numeric CSV value, mapping blanks to ``None``."""
    text = _normalized_cell(row, column)
    if not text:
        return None
    try:
        return float(text)
    except ValueError as exc:
        raise ValueError(f"{path}: row {row_number} column {column!r} must be numeric, got {text!r}.") from exc


def _optional_int(row: Mapping[str, str | None], column: str, *, path: Path, row_number: int) -> int | None:
    """Return an optional integer CSV value, mapping blanks to ``None``."""
    value = _optional_float(row, column, path=path, row_number=row_number)
    if value is None:
        return None
    if int(value) != value:
        raise ValueError(f"{path}: row {row_number} column {column!r} must be an integer, got {value!r}.")
    return int(value)


def _quantity(
    row: Mapping[str, str | None],
    base_column: str,
    *,
    path: Path,
    row_number: int,
    required: bool,
) -> QuantityInput | None:
    """Return a scalar or ``(value, unit)`` pair from adjacent value/unit columns."""
    value_column = f"{base_column}_value"
    unit_column = f"{base_column}_unit"
    value = _optional_float(row, value_column, path=path, row_number=row_number)
    unit = _normalized_cell(row, unit_column)

    if value is None:
        if required:
            raise ValueError(f"{path}: row {row_number} is missing required column {value_column!r}.")
        if unit:
            raise ValueError(f"{path}: row {row_number} has {unit_column!r} without {value_column!r}.")
        return None

    if unit:
        return (value, unit)
    return value


def _catalog_id(row: Mapping[str, str | None], *, path: Path, row_number: int) -> str:
    """Return a stable non-empty catalog ID from a CSV row."""
    component_id = _required_text(row, "catalog_id", path=path, row_number=row_number)
    if any(char.isspace() for char in component_id):
        raise ValueError(f"{path}: row {row_number} catalog_id must not contain whitespace.")
    return component_id


def _load_catalog(
    path: str | Path,
    row_loader: Callable[[Mapping[str, str | None], Path, int], tuple[str, ComponentT]],
) -> dict[str, ComponentT]:
    """Load a catalog CSV with duplicate-ID checks and row-specific errors."""
    catalog_path = Path(path)
    components: dict[str, ComponentT] = {}

    with catalog_path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{catalog_path}: catalog file is empty.")

        for row_number, row in enumerate(reader, start=2):
            if not any(_normalized_cell(row, column) for column in reader.fieldnames):
                continue

            component_id, component = row_loader(row, catalog_path, row_number)
            if component_id in components:
                raise ValueError(f"{catalog_path}: duplicate catalog_id {component_id!r} at row {row_number}.")
            components[component_id] = component

    return components


def _load_motor_row(row: Mapping[str, str | None], path: Path, row_number: int) -> tuple[str, ElectricMotor]:
    """Build one :class:`ElectricMotor` from a motor catalog row."""
    component_id = _catalog_id(row, path=path, row_number=row_number)
    no_load_current = _quantity(row, "no_load_current", path=path, row_number=row_number, required=False)
    gear_ratio = _optional_float(row, "gear_ratio", path=path, row_number=row_number)
    gear_efficiency = _optional_float(row, "gear_efficiency", path=path, row_number=row_number)
    motor = ElectricMotor(
        name=_optional_text(row, "name") or component_id,
        kv=_quantity(row, "kv", path=path, row_number=row_number, required=True),
        resistance=_quantity(row, "resistance", path=path, row_number=row_number, required=True),
        no_load_current=no_load_current if no_load_current is not None else 0.0,
        max_current=_quantity(row, "max_current", path=path, row_number=row_number, required=False),
        max_voltage=_quantity(row, "max_voltage", path=path, row_number=row_number, required=False),
        max_power=_quantity(row, "max_power", path=path, row_number=row_number, required=False),
        mass=_quantity(row, "mass", path=path, row_number=row_number, required=False),
        gear_ratio=gear_ratio if gear_ratio is not None else 1.0,
        gear_efficiency=gear_efficiency if gear_efficiency is not None else 1.0,
    )
    return component_id, motor


def _load_battery_row(row: Mapping[str, str | None], path: Path, row_number: int) -> tuple[str, BatteryPack]:
    """Build one :class:`BatteryPack` from a battery catalog row."""
    component_id = _catalog_id(row, path=path, row_number=row_number)
    internal_resistance = _quantity(row, "internal_resistance", path=path, row_number=row_number, required=False)
    battery = BatteryPack(
        name=_optional_text(row, "name") or component_id,
        nominal_voltage=_quantity(row, "nominal_voltage", path=path, row_number=row_number, required=True),
        internal_resistance=internal_resistance if internal_resistance is not None else 0.0,
        capacity=_quantity(row, "capacity", path=path, row_number=row_number, required=False),
        max_current=_quantity(row, "max_current", path=path, row_number=row_number, required=False),
        soc=_optional_float(row, "soc", path=path, row_number=row_number),
        chemistry=_optional_text(row, "chemistry") or "constant",
        n_series=_optional_int(row, "n_series", path=path, row_number=row_number),
        mass=_quantity(row, "mass", path=path, row_number=row_number, required=False),
        specific_energy=_quantity(row, "specific_energy", path=path, row_number=row_number, required=False),
    )
    return component_id, battery


def _load_esc_row(
    row: Mapping[str, str | None],
    path: Path,
    row_number: int,
) -> tuple[str, ElectronicSpeedController]:
    """Build one :class:`ElectronicSpeedController` from an ESC catalog row."""
    component_id = _catalog_id(row, path=path, row_number=row_number)
    efficiency = _optional_float(row, "efficiency", path=path, row_number=row_number)
    resistance = _quantity(row, "resistance", path=path, row_number=row_number, required=False)
    esc = ElectronicSpeedController(
        name=_optional_text(row, "name") or component_id,
        efficiency=efficiency if efficiency is not None else 1.0,
        resistance=resistance if resistance is not None else 0.0,
        max_current=_quantity(row, "max_current", path=path, row_number=row_number, required=False),
        max_voltage=_quantity(row, "max_voltage", path=path, row_number=row_number, required=False),
        mass=_quantity(row, "mass", path=path, row_number=row_number, required=False),
    )
    return component_id, esc


def load_motor_catalog(path: str | Path = DEFAULT_CATALOG_ROOT / "motors.csv") -> dict[str, ElectricMotor]:
    """Load editable motor definitions from a CSV catalog file."""
    return _load_catalog(path, _load_motor_row)


def load_battery_catalog(path: str | Path = DEFAULT_CATALOG_ROOT / "batteries.csv") -> dict[str, BatteryPack]:
    """Load editable battery-pack definitions from a CSV catalog file."""
    return _load_catalog(path, _load_battery_row)


def load_esc_catalog(path: str | Path = DEFAULT_CATALOG_ROOT / "escs.csv") -> dict[str, ElectronicSpeedController]:
    """Load editable electronic-speed-controller definitions from a CSV catalog file."""
    return _load_catalog(path, _load_esc_row)


def load_propulsion_catalogs(root: str | Path = DEFAULT_CATALOG_ROOT) -> PropulsionCatalogs:
    """Load the standard motor, battery, and ESC catalogs from one directory."""
    root_path = Path(root)
    return PropulsionCatalogs(
        motors=load_motor_catalog(root_path / "motors.csv"),
        batteries=load_battery_catalog(root_path / "batteries.csv"),
        escs=load_esc_catalog(root_path / "escs.csv"),
    )


__all__ = [
    "DEFAULT_CATALOG_ROOT",
    "PropulsionCatalogs",
    "load_battery_catalog",
    "load_esc_catalog",
    "load_motor_catalog",
    "load_propulsion_catalogs",
]
