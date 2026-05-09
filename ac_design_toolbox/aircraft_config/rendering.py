"""Rendering helpers for canonical aircraft definitions."""

from __future__ import annotations

import base64
from io import BytesIO
from numbers import Real
from typing import Any

import matplotlib
import numpy as np

# Force a non-interactive backend before importing pyplot so command-line runs
# do not emit GUI-backend warnings in headless or terminal-only environments.
matplotlib.use("Agg")

from matplotlib.collections import PolyCollection
from matplotlib.ticker import FuncFormatter
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import plotly.graph_objects as go

from ac_design_toolbox.mission.units import convert_value

from .builder import build_aircraft
from .models import AircraftDefinition


CONTROL_PANEL_FACE_COLOR = "rgba(37, 99, 235, 0.28)"
CONTROL_PANEL_LINE_COLOR = "#1d4ed8"


def _coerce_airplane(definition_or_airplane: AircraftDefinition | Any) -> Any:
    """Return an AeroSandbox airplane from either a definition or an airplane."""
    if isinstance(definition_or_airplane, AircraftDefinition):
        return build_aircraft(definition_or_airplane)
    return definition_or_airplane


def _validate_unit_system(unit_system: str) -> str:
    """Return a supported rendering unit system token."""
    normalized = str(unit_system).strip().lower() or "metric"
    if normalized not in {"metric", "imperial"}:
        raise ValueError(f"unit_system must be 'metric' or 'imperial', got {unit_system!r}.")
    return normalized


def _display_length_scale(unit_system: str) -> float:
    """Return the coordinate scale factor from meters into the display unit."""
    normalized = _validate_unit_system(unit_system)
    if normalized == "metric":
        return 1.0
    return float(convert_value(1.0, "m", "ft"))


def _display_length_unit(unit_system: str) -> str:
    """Return the rendered display unit for aircraft lengths."""
    return "m" if _validate_unit_system(unit_system) == "metric" else "ft"


def _scaled_axis_values(values: Any, scale: float) -> Any:
    """Return numeric Plotly coordinate arrays multiplied by a display scale."""
    if values is None or scale == 1.0:
        return values

    if isinstance(values, (list, tuple)):
        return [float(value) * scale if isinstance(value, Real) else value for value in values]
    return values


def _apply_plotly_units(figure: go.Figure, *, unit_system: str) -> go.Figure:
    """Return a Plotly figure with coordinates and labels expressed in display units."""
    scale = _display_length_scale(unit_system)
    unit_label = _display_length_unit(unit_system)

    for trace in figure.data:
        for axis_name in ("x", "y", "z"):
            if hasattr(trace, axis_name):
                setattr(trace, axis_name, _scaled_axis_values(getattr(trace, axis_name), scale))

    figure.update_scenes(
        xaxis_title=f"x ({unit_label})",
        yaxis_title=f"y ({unit_label})",
        zaxis_title=f"z ({unit_label})",
    )
    return figure


def _xsec_control_names(xsec: Any) -> set[str]:
    """Return the control names attached to one AeroSandbox wing section."""
    return {
        str(control.name)
        for control in getattr(xsec, "control_surfaces", [])
        if str(getattr(control, "name", "")).strip()
    }


def _control_by_name(xsec: Any, name: str) -> Any | None:
    """Return the first control with ``name`` on one wing section."""
    for control in getattr(xsec, "control_surfaces", []):
        if str(getattr(control, "name", "")) == name:
            return control
    return None


def _control_chord_points(xsec: Any, hinge_point: float) -> tuple[np.ndarray, np.ndarray]:
    """Return hinge and trailing-edge points for a control on one wing section."""
    xyz_le = np.asarray(xsec.xyz_le, dtype=float)
    chord = float(xsec.chord)
    hinge = xyz_le + np.asarray([float(hinge_point) * chord, 0.0, 0.0])
    trailing = xyz_le + np.asarray([chord, 0.0, 0.0])
    return hinge, trailing


def _mirrored_control_panel(panel: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of a control panel mirrored about the body XZ plane."""
    mirrored_polygon = np.asarray(panel["polygon"], dtype=float).copy()
    mirrored_hinge = np.asarray(panel["hinge"], dtype=float).copy()
    mirrored_polygon[:, 1] *= -1.0
    mirrored_hinge[:, 1] *= -1.0
    return {
        **panel,
        "surface_name": f'{panel["surface_name"]}_mirrored',
        "polygon": mirrored_polygon,
        "hinge": mirrored_hinge,
    }


def _control_surface_panels(airplane: Any) -> list[dict[str, Any]]:
    """Return undeflected control-surface panel footprints from built wing xsecs."""
    panels: list[dict[str, Any]] = []
    for wing in getattr(airplane, "wings", []):
        wing_panels: list[dict[str, Any]] = []
        xsecs = list(getattr(wing, "xsecs", []))
        for index in range(len(xsecs) - 1):
            inner = xsecs[index]
            outer = xsecs[index + 1]
            for control_name in sorted(_xsec_control_names(inner) & _xsec_control_names(outer)):
                inner_control = _control_by_name(inner, control_name)
                outer_control = _control_by_name(outer, control_name)
                if inner_control is None or outer_control is None:
                    continue

                hinge_point = 0.5 * (
                    float(getattr(inner_control, "hinge_point", 0.75))
                    + float(getattr(outer_control, "hinge_point", 0.75))
                )
                inner_hinge, inner_trailing = _control_chord_points(inner, hinge_point)
                outer_hinge, outer_trailing = _control_chord_points(outer, hinge_point)
                wing_panels.append(
                    {
                        "surface_name": str(getattr(wing, "name", "surface")),
                        "control_name": control_name,
                        "polygon": np.asarray(
                            [inner_hinge, outer_hinge, outer_trailing, inner_trailing],
                            dtype=float,
                        ),
                        "hinge": np.asarray([inner_hinge, outer_hinge], dtype=float),
                    }
                )

        panels.extend(wing_panels)
        if bool(getattr(wing, "symmetric", False)):
            panels.extend([_mirrored_control_panel(panel) for panel in wing_panels])
    return panels


def _add_plotly_control_overlays(figure: go.Figure, airplane: Any) -> None:
    """Add translucent control-panel overlays and hinge lines to a Plotly figure."""
    for panel in _control_surface_panels(airplane):
        polygon = np.asarray(panel["polygon"], dtype=float)
        hinge = np.asarray(panel["hinge"], dtype=float)
        trace_name = f'{panel["surface_name"]} {panel["control_name"]}'
        figure.add_trace(
            go.Mesh3d(
                x=polygon[:, 0],
                y=polygon[:, 1],
                z=polygon[:, 2],
                i=[0, 0],
                j=[1, 2],
                k=[2, 3],
                color=CONTROL_PANEL_FACE_COLOR,
                opacity=0.32,
                name=f"{trace_name} panel",
                hoverinfo="name",
                showlegend=True,
            )
        )
        figure.add_trace(
            go.Scatter3d(
                x=hinge[:, 0],
                y=hinge[:, 1],
                z=hinge[:, 2],
                mode="lines",
                line={"color": CONTROL_PANEL_LINE_COLOR, "width": 5},
                name=f"{trace_name} hinge",
                hoverinfo="name",
                showlegend=True,
            )
        )


def render_aircraft_plotly(
    definition_or_airplane: AircraftDefinition | Any,
    *,
    unit_system: str = "metric",
) -> go.Figure:
    """Return a Plotly 3D rendering for the supplied aircraft definition.

    The returned figure uses geometry coordinates and axis labels in the
    requested display unit system while leaving the canonical aircraft
    definition itself in meters.
    """
    airplane = _coerce_airplane(definition_or_airplane)
    figure = airplane.draw(backend="plotly", show=False)
    figure.update_layout(
        template="plotly_white",
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        scene_aspectmode="data",
        title=airplane.name,
    )
    _add_plotly_control_overlays(figure, airplane)
    return _apply_plotly_units(figure, unit_system=unit_system)


def _formatted_length_tick(value: float, _: float | None, *, scale: float) -> str:
    """Return a concise tick label in the requested display unit."""
    scaled_value = float(value) * scale
    formatted = f"{scaled_value:.2f}".rstrip("0").rstrip(".")
    return "0" if formatted in {"-0", ""} else formatted


def _axis_label_with_unit(label: str, unit_label: str) -> str:
    """Return an axis label stripped of any prior unit suffix and relabeled."""
    base_label = str(label or "").split("(")[0].strip() or "axis"
    return f"{base_label} ({unit_label})"


def _apply_three_view_units(axs: Any, *, unit_system: str) -> Any:
    """Apply unit-aware labels and tick formatters to a three-view axes grid."""
    scale = _display_length_scale(unit_system)
    unit_label = _display_length_unit(unit_system)
    formatter = FuncFormatter(lambda value, position: _formatted_length_tick(value, position, scale=scale))

    for ax in getattr(axs, "flat", [axs]):
        ax.set_xlabel(_axis_label_with_unit(ax.get_xlabel(), unit_label))
        ax.set_ylabel(_axis_label_with_unit(ax.get_ylabel(), unit_label))
        ax.xaxis.set_major_formatter(formatter)
        ax.yaxis.set_major_formatter(formatter)
        if hasattr(ax, "get_zlabel") and hasattr(ax, "zaxis"):
            ax.set_zlabel(_axis_label_with_unit(ax.get_zlabel(), unit_label))
            ax.zaxis.set_major_formatter(formatter)
    return axs


def _project_mesh_faces(
    points: np.ndarray,
    faces: np.ndarray,
    *,
    horizontal_axis: int,
    vertical_axis: int,
    depth_axis: int,
) -> tuple[list[np.ndarray], np.ndarray]:
    """Return projected polygon faces and painter-order depths for one orthographic view."""
    projected_polygons: list[np.ndarray] = []
    mean_depths: list[float] = []

    for face in faces:
        face_points = np.asarray(points[np.asarray(face, dtype=int)], dtype=float)
        polygon = face_points[:, [horizontal_axis, vertical_axis]]
        projected_polygons.append(polygon)
        mean_depths.append(float(np.mean(face_points[:, depth_axis])))

    return projected_polygons, np.asarray(mean_depths, dtype=float)


def _shared_coordinate_limits(
    points: np.ndarray,
    *,
    padding_fraction: float = 0.05,
) -> dict[int, tuple[float, float]]:
    """Return shared global-span coordinate limits for consistent orthographic views."""
    raw_limits: dict[int, tuple[float, float]] = {}
    axis_spans: list[float] = []

    for axis_index in (0, 1, 2):
        values = np.asarray(points[:, axis_index], dtype=float)
        axis_min = float(np.min(values))
        axis_max = float(np.max(values))
        raw_limits[axis_index] = (axis_min, axis_max)
        axis_spans.append(max(axis_max - axis_min, 1e-9))

    dominant_span = max(axis_spans)
    padding = dominant_span * padding_fraction
    half_span = 0.5 * dominant_span + padding

    limits: dict[int, tuple[float, float]] = {}
    for axis_index, (axis_min, axis_max) in raw_limits.items():
        axis_center = 0.5 * (axis_min + axis_max)
        limits[axis_index] = (axis_center - half_span, axis_center + half_span)

    return limits


def _set_projected_axis_limits(
    ax: Any,
    *,
    horizontal_limits: tuple[float, float],
    vertical_limits: tuple[float, float],
) -> None:
    """Apply shared orthographic limits while preserving equal aspect."""
    ax.set_xlim(*horizontal_limits)
    ax.set_ylim(*vertical_limits)
    ax.set_aspect("equal", adjustable="box")


def _style_three_view_axis(ax: Any) -> None:
    """Apply a clean drafting-style appearance to a 2D three-view axis."""
    ax.set_facecolor("#ffffff")
    ax.set_axisbelow(True)
    ax.grid(True, color="#d7dbe2", linewidth=0.7)
    ax.tick_params(colors="#3f444b", labelsize=10, width=0.8)
    for spine in ax.spines.values():
        spine.set_color("#b8c0cc")
        spine.set_linewidth(0.8)


def _draw_projected_view(
    ax: Any,
    points: np.ndarray,
    faces: np.ndarray,
    *,
    horizontal_axis: int,
    vertical_axis: int,
    depth_axis: int,
    shared_limits: dict[int, tuple[float, float]],
    x_label: str,
    y_label: str,
) -> None:
    """Draw one orthographic aircraft view using projected mesh-face polygons."""
    projected_polygons, mean_depths = _project_mesh_faces(
        points,
        faces,
        horizontal_axis=horizontal_axis,
        vertical_axis=vertical_axis,
        depth_axis=depth_axis,
    )
    draw_order = np.argsort(mean_depths)
    ordered_polygons = [projected_polygons[int(index)] for index in draw_order]

    collection = PolyCollection(
        ordered_polygons,
        facecolors="#b9bec7",
        edgecolors="#7a8088",
        linewidths=0.20,
        closed=True,
        zorder=3,
    )
    ax.add_collection(collection)
    _set_projected_axis_limits(
        ax,
        horizontal_limits=shared_limits[horizontal_axis],
        vertical_limits=shared_limits[vertical_axis],
    )
    _style_three_view_axis(ax)
    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)


def _draw_projected_control_overlays(
    ax: Any,
    panels: list[dict[str, Any]],
    *,
    horizontal_axis: int,
    vertical_axis: int,
) -> None:
    """Draw control-panel footprints on one orthographic three-view axis."""
    if not panels:
        return

    polygons = [
        np.asarray(panel["polygon"], dtype=float)[:, [horizontal_axis, vertical_axis]]
        for panel in panels
    ]
    collection = PolyCollection(
        polygons,
        facecolors="#60a5fa",
        edgecolors=CONTROL_PANEL_LINE_COLOR,
        linewidths=0.65,
        alpha=0.35,
        closed=True,
        zorder=6,
    )
    ax.add_collection(collection)

    for panel in panels:
        hinge = np.asarray(panel["hinge"], dtype=float)[:, [horizontal_axis, vertical_axis]]
        ax.plot(
            hinge[:, 0],
            hinge[:, 1],
            color=CONTROL_PANEL_LINE_COLOR,
            linewidth=1.0,
            zorder=7,
        )


def _draw_isometric_control_overlays(ax: Any, panels: list[dict[str, Any]]) -> None:
    """Draw control-panel overlays on the isometric three-view panel."""
    if not panels:
        return

    collection = Poly3DCollection(
        [np.asarray(panel["polygon"], dtype=float) for panel in panels],
        facecolors="#60a5fa",
        edgecolors=CONTROL_PANEL_LINE_COLOR,
        linewidths=0.6,
        alpha=0.35,
        zorder=8,
    )
    ax.add_collection3d(collection)
    for panel in panels:
        hinge = np.asarray(panel["hinge"], dtype=float)
        ax.plot(
            hinge[:, 0],
            hinge[:, 1],
            hinge[:, 2],
            color=CONTROL_PANEL_LINE_COLOR,
            linewidth=0.9,
            zorder=9,
        )


def _style_isometric_axis(ax: Any) -> None:
    """Apply a clean presentation-only style to the isometric subplot."""
    ax.set_facecolor("#ffffff")
    ax.set_axis_off()


def _set_isometric_limits(
    ax: Any,
    points: np.ndarray,
    *,
    padding_fraction: float = 0.005,
) -> None:
    """Apply tighter per-axis 3D limits for the isometric panel."""
    axis_limits: list[tuple[float, float]] = []
    axis_spans: list[float] = []

    for axis_index in (0, 1, 2):
        values = np.asarray(points[:, axis_index], dtype=float)
        axis_min = float(np.min(values))
        axis_max = float(np.max(values))
        axis_span = max(axis_max - axis_min, 1e-9)
        # Keep the iso panel visually tighter than the orthographic views so it
        # reads like a presentation inset rather than a drafting viewport.
        padding = axis_span * padding_fraction
        axis_limits.append((axis_min - padding, axis_max + padding))
        axis_spans.append(axis_span)

    ax.set_xlim(*axis_limits[0])
    ax.set_ylim(*axis_limits[1])
    ax.set_zlim(*axis_limits[2])
    ax.set_box_aspect(tuple(axis_spans))


def _build_three_view_axes(
    definition_or_airplane: AircraftDefinition | Any,
    *,
    unit_system: str = "metric",
) -> Any:
    """Return unit-aware orthographic three-view axes for the supplied aircraft definition."""
    airplane = _coerce_airplane(definition_or_airplane)
    points, faces = airplane.mesh_body(method="quad", thin_wings=False, stack_meshes=True)
    shared_limits = _shared_coordinate_limits(points)
    control_panels = _control_surface_panels(airplane)

    figure, axs = plt.subplots(
        2,
        2,
        figsize=(10.2, 9.4),
        gridspec_kw={"wspace": 0.18, "hspace": 0.20},
    )
    figure.patch.set_facecolor("#ffffff")
    figure.subplots_adjust(left=0.07, right=0.98, bottom=0.07, top=0.94)

    _draw_projected_view(
        axs[0, 0],
        points,
        faces,
        horizontal_axis=0,
        vertical_axis=2,
        depth_axis=1,
        shared_limits=shared_limits,
        x_label="x",
        y_label="z",
    )
    _draw_projected_control_overlays(
        axs[0, 0],
        control_panels,
        horizontal_axis=0,
        vertical_axis=2,
    )
    _draw_projected_view(
        axs[0, 1],
        points,
        faces,
        horizontal_axis=1,
        vertical_axis=2,
        depth_axis=0,
        shared_limits=shared_limits,
        x_label="y",
        y_label="z",
    )
    _draw_projected_control_overlays(
        axs[0, 1],
        control_panels,
        horizontal_axis=1,
        vertical_axis=2,
    )
    _draw_projected_view(
        axs[1, 0],
        points,
        faces,
        horizontal_axis=0,
        vertical_axis=1,
        depth_axis=2,
        shared_limits=shared_limits,
        x_label="x",
        y_label="y",
    )
    _draw_projected_control_overlays(
        axs[1, 0],
        control_panels,
        horizontal_axis=0,
        vertical_axis=1,
    )

    axs[0, 0].set_title("Side", fontsize=12, color="#31353b", pad=10)
    axs[0, 1].set_title("Front", fontsize=12, color="#31353b", pad=10)
    axs[1, 0].set_title("Top", fontsize=12, color="#31353b", pad=10)

    figure.delaxes(axs[1, 1])
    iso_ax = figure.add_subplot(2, 2, 4, projection="3d")
    airplane.draw(
        backend="matplotlib",
        ax=iso_ax,
        use_preset_view_angle="left_isometric",
        set_background_pane_color=(1.0, 1.0, 1.0),
        set_background_pane_alpha=1.0,
        show=False,
    )
    _style_isometric_axis(iso_ax)
    _set_isometric_limits(iso_ax, points)
    _draw_isometric_control_overlays(iso_ax, control_panels)
    iso_ax.set_title("Iso", fontsize=12, color="#31353b", pad=12)
    axs[1, 1] = iso_ax

    return _apply_three_view_units(axs, unit_system=unit_system)


def render_aircraft_three_view_image(
    definition_or_airplane: AircraftDefinition | Any,
    *,
    dpi: int = 200,
    unit_system: str = "metric",
) -> str:
    """Return a base64 PNG data URI for the aircraft three-view image.

    Axis labels and tick labels are expressed in the requested display unit
    system. The underlying aircraft definition remains canonical in meters.
    """
    axs = _build_three_view_axes(definition_or_airplane, unit_system=unit_system)
    figure = axs[0, 0].figure
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi, bbox_inches="tight")
    plt.close(figure)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


__all__ = [
    "render_aircraft_plotly",
    "render_aircraft_three_view_image",
]
