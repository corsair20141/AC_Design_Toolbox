"""Parsers for public propeller coefficient data files.

The parsers in this module are intentionally file-format adapters only. They
convert known UIUC and APC text files into ``TabulatedPropeller`` objects that
the core propulsion solver already understands. They do not download data,
cache remote files, or infer a single universal propeller model across RPM.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
import re
from typing import Iterable

from ac_design_toolbox.propulsion.propeller import TabulatedPropeller
from ac_design_toolbox.propulsion.units import QuantityInput, coerce_quantity

INCH_TO_M = 0.0254


@dataclass(frozen=True)
class PropellerTableSet:
    """Collection of coefficient tables parsed from one source file.

    ``tables_by_rpm`` stores one ``TabulatedPropeller`` per measured or
    simulated RPM. UIUC single-run files usually contain one RPM inferred from
    the filename; APC PER3 files usually contain many RPM blocks.
    """

    name: str
    source_format: str
    source: str
    diameter: float
    tables_by_rpm: dict[float, TabulatedPropeller]
    metadata: dict[str, object]

    def table_for_rpm(self, rpm: float, *, nearest: bool = False) -> TabulatedPropeller:
        """Return the exact or nearest table for an RPM."""
        if rpm in self.tables_by_rpm:
            return self.tables_by_rpm[rpm]
        if not nearest:
            available = ", ".join(f"{value:g}" for value in sorted(self.tables_by_rpm))
            raise ValueError(f"RPM {rpm:g} is unavailable. Available RPM values: {available}.")

        nearest_rpm = min(self.tables_by_rpm, key=lambda value: abs(value - rpm))
        return self.tables_by_rpm[nearest_rpm]

    def evaluate(
        self,
        *,
        airspeed: QuantityInput,
        rotational_speed: QuantityInput,
        density: QuantityInput = 1.225,
    ):
        """Evaluate with the nearest available RPM table.

        Motor-prop solvers own the continuous shaft-speed solve. Tabulated
        propeller data sets are discrete by RPM, so this adapter selects the
        closest measured/simulated table at each solver query and evaluates the
        coefficients at the requested shaft speed.
        """
        rotational_speed_rpm = coerce_quantity("rotational_speed", rotational_speed, "rpm", "rotational_speed")
        nearest_rpm = min(self.tables_by_rpm, key=lambda value: abs(value - rotational_speed_rpm))
        point = self.tables_by_rpm[nearest_rpm].evaluate(
            airspeed=airspeed,
            rotational_speed=rotational_speed_rpm,
            density=density,
        )
        if nearest_rpm == rotational_speed_rpm:
            return point
        return replace(
            point,
            notes=(
                f"Selected nearest RPM table {nearest_rpm:g} for requested {rotational_speed_rpm:g} rpm.",
            )
            + point.notes,
        )


def _read_text(path: str | Path) -> tuple[str, str]:
    """Return file text and a stable source string."""
    source_path = Path(path)
    return source_path.read_text(encoding="utf-8", errors="replace"), str(source_path)


def _numeric_rows(text: str, *, min_columns: int) -> list[list[float]]:
    """Return whitespace-separated numeric rows with at least min_columns."""
    rows: list[list[float]] = []
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens = stripped.split()
        try:
            values = [float(token) for token in tokens]
        except ValueError:
            continue
        if len(values) >= min_columns:
            rows.append(values)
    return rows


def _infer_inches_pair_from_name(name: str) -> tuple[float, float] | None:
    """Infer diameter and pitch in inches from common UIUC/APC filenames."""
    stem = Path(name).stem.lower()
    # APC filenames often encode decimals without dots, e.g. 105x45 -> 10.5x4.5.
    match = re.search(r"per3_(\d+)x(\d+)", stem)
    if match:
        def decode_apc_dimension(raw_value: str) -> float:
            if len(raw_value) >= 3:
                return float(raw_value[:-1] + "." + raw_value[-1])
            return float(raw_value)

        return decode_apc_dimension(match.group(1)), decode_apc_dimension(match.group(2))

    match = re.search(r"(?<!\d)(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)(?!\d)", stem)
    if match:
        return float(match.group(1)), float(match.group(2))
    return None


def infer_diameter_from_name(name: str) -> float | None:
    """Return inferred propeller diameter in meters from a filename."""
    inferred = _infer_inches_pair_from_name(name)
    if inferred is None:
        return None
    diameter_in, _pitch_in = inferred
    return diameter_in * INCH_TO_M


def _resolve_diameter(diameter: QuantityInput | None, source: str) -> float:
    """Return explicit or filename-inferred diameter in meters."""
    if diameter is not None:
        diameter_m = coerce_quantity("diameter", diameter, "m", "length")
        if diameter_m <= 0.0:
            raise ValueError("diameter must be positive.")
        return diameter_m

    inferred = infer_diameter_from_name(source)
    if inferred is None:
        raise ValueError(
            "Could not infer propeller diameter from source name. Pass diameter explicitly, "
            "for example diameter=(10.0, 'in') or diameter=0.254."
        )
    return inferred


def _rpm_from_uiuc_source(source: str) -> float | None:
    """Infer UIUC run RPM from filename fragments such as _4008.txt."""
    stem = Path(source).stem.lower()
    match = re.search(r"_(\d{4,5})$", stem)
    if match:
        return float(match.group(1))
    return None


def parse_uiuc_performance_text(
    text: str,
    *,
    diameter: QuantityInput,
    name: str = "",
    source: str = "",
    extrapolation_mode: str = "raise",
) -> TabulatedPropeller:
    """Parse one UIUC wind-tunnel ``J CT CP eta`` text table.

    Static UIUC files with ``RPM CT CP`` are intentionally rejected because they
    do not define a usable CT/CP-versus-advance-ratio table for the current
    ``TabulatedPropeller`` model.
    """
    header_line = next((line.strip().lower() for line in text.splitlines() if line.strip()), "")
    if "rpm" in header_line and " j " not in f" {header_line} ":
        raise ValueError("UIUC static RPM CT CP files are not supported as TabulatedPropeller inputs.")

    rows = _numeric_rows(text, min_columns=3)
    if not rows:
        raise ValueError("No numeric UIUC propeller rows were found.")

    advance_ratio: list[float] = []
    ct: list[float] = []
    cp: list[float] = []
    for row in rows:
        advance_ratio.append(row[0])
        ct.append(row[1])
        cp.append(row[2])

    return TabulatedPropeller.from_arrays(
        diameter=diameter,
        advance_ratio=advance_ratio,
        ct=ct,
        cp=cp,
        extrapolation_mode=extrapolation_mode,
        name=name,
        source=source,
    )


def load_uiuc_performance_file(
    path: str | Path,
    *,
    diameter: QuantityInput | None = None,
    extrapolation_mode: str = "raise",
    name: str = "",
) -> TabulatedPropeller:
    """Load one UIUC ``J CT CP eta`` file as a ``TabulatedPropeller``."""
    text, source = _read_text(path)
    diameter_m = _resolve_diameter(diameter, source)
    return parse_uiuc_performance_text(
        text,
        diameter=diameter_m,
        name=name or Path(source).stem,
        source=source,
        extrapolation_mode=extrapolation_mode,
    )


def load_uiuc_table_set(
    paths: Iterable[str | Path],
    *,
    diameter: QuantityInput | None = None,
    extrapolation_mode: str = "raise",
    name: str = "",
) -> PropellerTableSet:
    """Load multiple UIUC run files for one propeller into an RPM table set."""
    tables_by_rpm: dict[float, TabulatedPropeller] = {}
    source_paths: list[str] = []
    resolved_diameter: float | None = None

    for path in paths:
        text, source = _read_text(path)
        diameter_m = _resolve_diameter(diameter, source)
        if resolved_diameter is None:
            resolved_diameter = diameter_m
        elif abs(resolved_diameter - diameter_m) > 1e-12:
            raise ValueError("All UIUC files in one table set must have the same diameter.")

        rpm = _rpm_from_uiuc_source(source)
        if rpm is None:
            raise ValueError(f"Could not infer RPM from UIUC filename {source!r}.")
        if rpm in tables_by_rpm:
            raise ValueError(f"Duplicate UIUC RPM {rpm:g} in table set.")

        tables_by_rpm[rpm] = parse_uiuc_performance_text(
            text,
            diameter=diameter_m,
            name=f"{name or Path(source).stem} @ {rpm:g} rpm",
            source=source,
            extrapolation_mode=extrapolation_mode,
        )
        source_paths.append(source)

    if resolved_diameter is None:
        raise ValueError("At least one UIUC file is required.")

    return PropellerTableSet(
        name=name or "UIUC propeller table set",
        source_format="uiuc",
        source=";".join(source_paths),
        diameter=resolved_diameter,
        tables_by_rpm=dict(sorted(tables_by_rpm.items())),
        metadata={"file_count": len(source_paths)},
    )


def _split_apc_blocks(text: str) -> list[tuple[float, str]]:
    """Return APC ``PROP RPM =`` blocks as ``(rpm, block_text)`` pairs."""
    pattern = re.compile(r"PROP\s+RPM\s*=\s*([0-9.]+)", re.IGNORECASE)
    matches = list(pattern.finditer(text))
    blocks: list[tuple[float, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append((float(match.group(1)), text[start:end]))
    return blocks


def _parse_apc_block(block_text: str) -> tuple[list[float], list[float], list[float]]:
    """Parse one APC PER3 RPM block and return J, CT, and CP arrays."""
    rows = _numeric_rows(block_text, min_columns=5)
    if not rows:
        raise ValueError("No numeric APC rows were found in an RPM block.")

    advance_ratio: list[float] = []
    ct: list[float] = []
    cp: list[float] = []
    for row in rows:
        advance_ratio.append(row[1])
        ct.append(row[3])
        cp.append(row[4])
    return advance_ratio, ct, cp


def parse_apc_performance_text(
    text: str,
    *,
    diameter: QuantityInput,
    extrapolation_mode: str = "raise",
    name: str = "",
    source: str = "",
) -> PropellerTableSet:
    """Parse an APC PER3 performance text file into one table per RPM block."""
    tables_by_rpm: dict[float, TabulatedPropeller] = {}
    for rpm, block_text in _split_apc_blocks(text):
        advance_ratio, ct, cp = _parse_apc_block(block_text)
        tables_by_rpm[rpm] = TabulatedPropeller.from_arrays(
            diameter=diameter,
            advance_ratio=advance_ratio,
            ct=ct,
            cp=cp,
            extrapolation_mode=extrapolation_mode,
            name=f"{name or 'APC propeller'} @ {rpm:g} rpm",
            source=source,
        )

    if not tables_by_rpm:
        raise ValueError("No APC 'PROP RPM =' blocks were found.")

    diameter_m = coerce_quantity("diameter", diameter, "m", "length")
    return PropellerTableSet(
        name=name or "APC propeller table set",
        source_format="apc",
        source=source,
        diameter=diameter_m,
        tables_by_rpm=dict(sorted(tables_by_rpm.items())),
        metadata={"rpm_count": len(tables_by_rpm)},
    )


def load_apc_performance_file(
    path: str | Path,
    *,
    diameter: QuantityInput | None = None,
    extrapolation_mode: str = "raise",
    name: str = "",
) -> PropellerTableSet:
    """Load an APC PER3 performance file as a set of RPM-indexed tables."""
    text, source = _read_text(path)
    diameter_m = _resolve_diameter(diameter, source)
    return parse_apc_performance_text(
        text,
        diameter=diameter_m,
        extrapolation_mode=extrapolation_mode,
        name=name or Path(source).stem,
        source=source,
    )


def load_apc_table_for_rpm(
    path: str | Path,
    rpm: float,
    *,
    diameter: QuantityInput | None = None,
    nearest: bool = False,
    extrapolation_mode: str = "raise",
    name: str = "",
) -> TabulatedPropeller:
    """Load one APC table at an exact or nearest RPM from a PER3 file."""
    table_set = load_apc_performance_file(
        path,
        diameter=diameter,
        extrapolation_mode=extrapolation_mode,
        name=name,
    )
    return table_set.table_for_rpm(rpm, nearest=nearest)


__all__ = [
    "INCH_TO_M",
    "PropellerTableSet",
    "infer_diameter_from_name",
    "load_apc_performance_file",
    "load_apc_table_for_rpm",
    "load_uiuc_performance_file",
    "load_uiuc_table_set",
    "parse_apc_performance_text",
    "parse_uiuc_performance_text",
]
