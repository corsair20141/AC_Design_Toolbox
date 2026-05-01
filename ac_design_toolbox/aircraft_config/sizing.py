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


def _solve_trapezoid_planform(
    *,
    span: float | None,
    area: float | None,
    aspect_ratio: float | None,
    root_chord: float | None,
    tip_chord: float | None,
    taper: float | None,
    n_sections: int,
) -> PlanformSizingResult:
    """Solve trapezoidal planform scalars without importing geometry builders."""
    if n_sections < 2:
        raise ValueError("n_sections must be >= 2.")

    has = {
        "span": span is not None,
        "area": area is not None,
        "AR": aspect_ratio is not None,
        "cr": root_chord is not None,
        "ct": tip_chord is not None,
        "lam": taper is not None,
    }
    provided_keys = {key for key, is_present in has.items() if is_present}
    spec_sets = {
        "cr_ct_span": {"cr", "ct", "span"},
        "cr_lam_span": {"cr", "lam", "span"},
        "ct_lam_span": {"ct", "lam", "span"},
        "area_span_lam": {"area", "span", "lam"},
        "AR_span_lam": {"AR", "span", "lam"},
        "area_AR_lam": {"area", "AR", "lam"},
        "area_span_cr": {"area", "span", "cr"},
        "area_span_ct": {"area", "span", "ct"},
    }
    patterns = {name: provided_keys == required for name, required in spec_sets.items()}
    matching_patterns = [name for name, is_match in patterns.items() if is_match]
    if len(matching_patterns) != 1:
        raise ValueError(
            "Provide exactly one valid trapezoidal planform driver set. "
            f"Received fields: {sorted(provided_keys)}."
        )

    pattern = matching_patterns[0]
    if pattern == "cr_ct_span":
        cr, ct, b = float(root_chord), float(tip_chord), float(span)
    elif pattern == "cr_lam_span":
        cr = float(root_chord)
        lam = float(taper)
        if lam <= 0.0:
            raise ValueError("taper must be positive.")
        ct, b = lam * cr, float(span)
    elif pattern == "ct_lam_span":
        ct = float(tip_chord)
        lam = float(taper)
        if lam <= 0.0:
            raise ValueError("taper must be positive.")
        cr, b = ct / lam, float(span)
    elif pattern == "area_span_lam":
        surface_area, b, lam = float(area), float(span), float(taper)
        if lam <= 0.0:
            raise ValueError("taper must be positive.")
        cr = 2.0 * surface_area / (b * (1.0 + lam))
        ct = lam * cr
    elif pattern == "AR_span_lam":
        b, lam = float(span), float(taper)
        if lam <= 0.0:
            raise ValueError("taper must be positive.")
        surface_area = b**2 / float(aspect_ratio)
        cr = 2.0 * surface_area / (b * (1.0 + lam))
        ct = lam * cr
    elif pattern == "area_AR_lam":
        surface_area, aspect_ratio_value, lam = float(area), float(aspect_ratio), float(taper)
        if lam <= 0.0:
            raise ValueError("taper must be positive.")
        b = (aspect_ratio_value * surface_area) ** 0.5
        cr = 2.0 * surface_area / (b * (1.0 + lam))
        ct = lam * cr
    elif pattern == "area_span_cr":
        surface_area, b, cr = float(area), float(span), float(root_chord)
        ct = 2.0 * surface_area / b - cr
    elif pattern == "area_span_ct":
        surface_area, b, ct = float(area), float(span), float(tip_chord)
        cr = 2.0 * surface_area / b - ct
    else:
        raise RuntimeError("Internal planform pattern selection error.")

    if cr <= 0.0 or ct <= 0.0 or b <= 0.0:
        raise ValueError("All solved planform quantities must be positive.")

    lam = ct / cr
    surface_area = 0.5 * b * (cr + ct)
    aspect_ratio_value = b**2 / surface_area
    mac = (2.0 / 3.0) * cr * (1.0 + lam + lam**2) / (1.0 + lam)
    return PlanformSizingResult(
        span=float(b),
        area=float(surface_area),
        aspect_ratio=float(aspect_ratio_value),
        root_chord=float(cr),
        tip_chord=float(ct),
        taper=float(lam),
        mean_aerodynamic_chord=float(mac),
    )


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
    return _solve_trapezoid_planform(
        span=span,
        area=area,
        aspect_ratio=aspect_ratio,
        root_chord=root_chord,
        tip_chord=tip_chord,
        taper=taper,
        n_sections=max(int(n_sections), 2),
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
