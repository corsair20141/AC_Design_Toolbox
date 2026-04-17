"""Public planform and tail-volume sizing helpers for aircraft definitions.

This module provides a small public sizing surface over the lower-level
geometry helpers used internally by AC_Design_Toolbox. The goal is to keep
planform and volume-coefficient math canonical so downstream tools can reuse
the same assumptions without importing private modules.

The helpers here intentionally solve only simple trapezoidal planform and
first-pass tail-volume relationships. They do not attempt to replace a full
stability-and-control design workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, radians, sin, tan

from ac_design_toolbox.geometry._common import _chords_from_area_or_taper


@dataclass(frozen=True)
class PlanformSizingResult:
    """Solved trapezoidal planform metrics for one lifting surface."""

    span: float
    area: float
    aspect_ratio: float
    root_chord: float
    tip_chord: float
    taper: float
    mean_aerodynamic_chord: float


def solve_planform(
    *,
    span: float | None = None,
    area: float | None = None,
    aspect_ratio: float | None = None,
    root_chord: float | None = None,
    tip_chord: float | None = None,
    taper: float | None = None,
    n_sections: int = 2,
) -> PlanformSizingResult:
    """Solve one trapezoidal planform from a supported driver set.

    Parameters match the public naming used by the aircraft-config UI and are
    translated into the lower-level geometry solver. Exactly one valid driver
    set must be provided.
    """
    solve = _chords_from_area_or_taper(
        span=span,
        n_sections=max(int(n_sections), 2),
        area=area,
        AR=aspect_ratio,
        c_root=root_chord,
        c_tip=tip_chord,
        taper=taper,
    )
    return PlanformSizingResult(
        span=float(solve.b),
        area=float(solve.S),
        aspect_ratio=float(solve.AR),
        root_chord=float(solve.c_root),
        tip_chord=float(solve.c_tip),
        taper=float(solve.lam),
        mean_aerodynamic_chord=float(solve.MAC),
    )


def mean_aerodynamic_chord_spanwise_station(*, span: float, taper: float) -> float:
    """Return the spanwise station of the mean aerodynamic chord."""
    if span <= 0.0:
        raise ValueError("span must be positive.")
    if taper <= 0.0:
        raise ValueError("taper must be positive.")
    return float((span / 6.0) * (1.0 + 2.0 * taper) / (1.0 + taper))


def planform_quarter_chord_x(
    *,
    x_le_root: float,
    sweep_le_deg: float,
    span: float | None = None,
    area: float | None = None,
    aspect_ratio: float | None = None,
    root_chord: float | None = None,
    tip_chord: float | None = None,
    taper: float | None = None,
) -> float:
    """Return the x-location of the planform quarter-chord point.

    This uses a simple trapezoidal-planform approximation based on the leading
    edge sweep and the spanwise station of the mean aerodynamic chord.
    """
    result = solve_planform(
        span=span,
        area=area,
        aspect_ratio=aspect_ratio,
        root_chord=root_chord,
        tip_chord=tip_chord,
        taper=taper,
    )
    y_mac = mean_aerodynamic_chord_spanwise_station(
        span=result.span,
        taper=result.taper,
    )
    return float(x_le_root + y_mac * tan(radians(sweep_le_deg)) + 0.25 * result.mean_aerodynamic_chord)


def solve_horizontal_tail_area_from_volume_coefficient(
    *,
    volume_coefficient: float,
    wing_area: float,
    wing_mean_aerodynamic_chord: float,
    tail_arm: float,
) -> float:
    """Return horizontal-tail area from a first-pass horizontal volume coefficient."""
    if volume_coefficient <= 0.0:
        raise ValueError("volume_coefficient must be positive.")
    if wing_area <= 0.0:
        raise ValueError("wing_area must be positive.")
    if wing_mean_aerodynamic_chord <= 0.0:
        raise ValueError("wing_mean_aerodynamic_chord must be positive.")
    if tail_arm <= 0.0:
        raise ValueError("tail_arm must be positive.")
    return float(volume_coefficient * wing_area * wing_mean_aerodynamic_chord / tail_arm)


def solve_vertical_tail_area_from_volume_coefficient(
    *,
    volume_coefficient: float,
    wing_area: float,
    wing_span: float,
    tail_arm: float,
) -> float:
    """Return vertical-tail area from a first-pass vertical volume coefficient."""
    if volume_coefficient <= 0.0:
        raise ValueError("volume_coefficient must be positive.")
    if wing_area <= 0.0:
        raise ValueError("wing_area must be positive.")
    if wing_span <= 0.0:
        raise ValueError("wing_span must be positive.")
    if tail_arm <= 0.0:
        raise ValueError("tail_arm must be positive.")
    return float(volume_coefficient * wing_area * wing_span / tail_arm)


def canted_pair_projected_area_factor(*, cant_deg: float, axis: str) -> float:
    """Return the equivalent-area projection factor for a mirrored canted pair.

    The factor maps one single-surface geometric area into the total equivalent
    area of a mirrored pair. For example, a vertical-equivalent V-tail pair
    uses ``2 * sin(cant)^2``.
    """
    normalized_axis = str(axis).strip().lower()
    cant_rad = radians(abs(float(cant_deg)))
    if normalized_axis == "horizontal":
        factor = 2.0 * cos(cant_rad) ** 2
    elif normalized_axis == "vertical":
        factor = 2.0 * sin(cant_rad) ** 2
    else:
        raise ValueError("axis must be 'horizontal' or 'vertical'.")
    if factor <= 0.0:
        raise ValueError("Projected-area factor must be positive for the requested axis and cant angle.")
    return float(factor)


def solve_canted_pair_surface_area_from_horizontal_volume_coefficient(
    *,
    volume_coefficient: float,
    wing_area: float,
    wing_mean_aerodynamic_chord: float,
    tail_arm: float,
    cant_deg: float,
) -> float:
    """Return single-surface area for a mirrored canted pair sized by horizontal-equivalent volume."""
    total_equivalent_area = solve_horizontal_tail_area_from_volume_coefficient(
        volume_coefficient=volume_coefficient,
        wing_area=wing_area,
        wing_mean_aerodynamic_chord=wing_mean_aerodynamic_chord,
        tail_arm=tail_arm,
    )
    return float(
        total_equivalent_area
        / canted_pair_projected_area_factor(cant_deg=cant_deg, axis="horizontal")
    )


def solve_canted_pair_surface_area_from_vertical_volume_coefficient(
    *,
    volume_coefficient: float,
    wing_area: float,
    wing_span: float,
    tail_arm: float,
    cant_deg: float,
) -> float:
    """Return single-surface area for a mirrored canted pair sized by vertical-equivalent volume."""
    total_equivalent_area = solve_vertical_tail_area_from_volume_coefficient(
        volume_coefficient=volume_coefficient,
        wing_area=wing_area,
        wing_span=wing_span,
        tail_arm=tail_arm,
    )
    return float(
        total_equivalent_area
        / canted_pair_projected_area_factor(cant_deg=cant_deg, axis="vertical")
    )


def solve_twin_vertical_tail_surface_area_from_volume_coefficient(
    *,
    volume_coefficient: float,
    wing_area: float,
    wing_span: float,
    tail_arm: float,
) -> float:
    """Return single-fin area for a symmetric twin-fin vertical-tail family."""
    total_equivalent_area = solve_vertical_tail_area_from_volume_coefficient(
        volume_coefficient=volume_coefficient,
        wing_area=wing_area,
        wing_span=wing_span,
        tail_arm=tail_arm,
    )
    return float(total_equivalent_area / 2.0)


__all__ = [
    "PlanformSizingResult",
    "canted_pair_projected_area_factor",
    "mean_aerodynamic_chord_spanwise_station",
    "planform_quarter_chord_x",
    "solve_canted_pair_surface_area_from_horizontal_volume_coefficient",
    "solve_canted_pair_surface_area_from_vertical_volume_coefficient",
    "solve_horizontal_tail_area_from_volume_coefficient",
    "solve_planform",
    "solve_twin_vertical_tail_surface_area_from_volume_coefficient",
    "solve_vertical_tail_area_from_volume_coefficient",
]
