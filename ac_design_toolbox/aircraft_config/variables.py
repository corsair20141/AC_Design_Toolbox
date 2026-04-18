"""Helpers for optimizer-facing variables and stable component identifiers."""

from __future__ import annotations

from dataclasses import is_dataclass
import re
from typing import Any

from .models import AircraftDefinition


_PATH_SEGMENT_RE = re.compile(r"^(?P<name>[^\[\]]+?)(?:\[(?P<selector>[^\[\]]+)\])?$")


def _resolve_container_value(current: Any, part: str, path: str) -> Any:
    """Resolve one dotted path segment through a dataclass or dictionary."""
    if is_dataclass(current):
        if not hasattr(current, part):
            raise ValueError(f"Path {path!r} does not exist.")
        return getattr(current, part)
    if isinstance(current, dict):
        if part not in current:
            raise ValueError(f"Path {path!r} does not exist.")
        return current[part]
    raise ValueError(f"Path {path!r} cannot be resolved through non-container value {current!r}.")


def _resolve_list_selector(values: list[Any], selector: str, path: str) -> Any:
    """Resolve one list selector by index or by lifting-surface component ID."""
    normalized_selector = str(selector).strip()
    if not normalized_selector:
        raise ValueError(f"Invalid empty list selector in {path!r}.")

    if normalized_selector.isdigit():
        index = int(normalized_selector)
        try:
            return values[index]
        except IndexError as exc:
            raise ValueError(f"Path {path!r} index {index} is out of range.") from exc

    for value in values:
        component_id = getattr(value, "component_id", None)
        if component_id is None and isinstance(value, dict):
            component_id = value.get("component_id")
        if component_id == normalized_selector:
            return value

    raise ValueError(f"Path {path!r} does not contain component_id {normalized_selector!r}.")


def resolve_path_value(definition: AircraftDefinition, path: str) -> Any:
    """Resolve a dotted attribute path against an aircraft definition.

    List segments support either a numeric index or a lifting-surface component
    ID selector, for example ``lifting_surfaces[0].span`` or
    ``lifting_surfaces[main_wing].span``.
    """
    current: Any = definition
    for raw_part in path.split("."):
        if not raw_part:
            raise ValueError(f"Invalid empty path segment in {path!r}.")

        match = _PATH_SEGMENT_RE.match(raw_part)
        if match is None:
            raise ValueError(f"Unsupported path segment {raw_part!r} in {path!r}.")

        name = match.group("name")
        selector = match.group("selector")
        current = _resolve_container_value(current, name, path)
        if selector is not None:
            if not isinstance(current, list):
                raise ValueError(f"Path {path!r} selector {selector!r} targets a non-list value.")
            current = _resolve_list_selector(current, selector, path)
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
