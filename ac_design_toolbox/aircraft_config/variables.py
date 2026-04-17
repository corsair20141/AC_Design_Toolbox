"""Helpers for optimizer-facing variables and stable component identifiers."""

from __future__ import annotations

from dataclasses import is_dataclass
from typing import Any

from .models import AircraftDefinition


def resolve_path_value(definition: AircraftDefinition, path: str) -> Any:
    """Resolve a dotted attribute path against an aircraft definition."""
    current: Any = definition
    for part in path.split("."):
        if not part:
            raise ValueError(f"Invalid empty path segment in {path!r}.")
        if is_dataclass(current):
            if not hasattr(current, part):
                raise ValueError(f"Path {path!r} does not exist.")
            current = getattr(current, part)
            continue
        if isinstance(current, dict):
            if part not in current:
                raise ValueError(f"Path {path!r} does not exist.")
            current = current[part]
            continue
        raise ValueError(f"Path {path!r} cannot be resolved through non-container value {current!r}.")
    return current


def design_variable_records(definition: AircraftDefinition) -> list[dict[str, Any]]:
    """Return optimizer-variable records with current scalar values attached."""
    records: list[dict[str, Any]] = []
    for variable in definition.design_variables:
        current_value = resolve_path_value(definition, variable.path)
        records.append(
            {
                **variable.to_dict(),
                "current_value": current_value,
            }
        )
    return records


def collect_component_ids(definition: AircraftDefinition) -> list[str]:
    """Return stable buildable component IDs for the supplied definition."""
    return definition.active_component_ids()


__all__ = [
    "collect_component_ids",
    "design_variable_records",
    "resolve_path_value",
]
