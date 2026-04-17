"""Rendering helpers for canonical aircraft definitions."""

from __future__ import annotations

import base64
from io import BytesIO
from typing import Any

import matplotlib.pyplot as plt
import plotly.graph_objects as go

from .builder import build_aircraft
from .models import AircraftDefinition


def _coerce_airplane(definition_or_airplane: AircraftDefinition | Any) -> Any:
    """Return an AeroSandbox airplane from either a definition or an airplane."""
    if isinstance(definition_or_airplane, AircraftDefinition):
        return build_aircraft(definition_or_airplane)
    return definition_or_airplane


def render_aircraft_plotly(definition_or_airplane: AircraftDefinition | Any) -> go.Figure:
    """Return a Plotly 3D rendering for the supplied aircraft definition."""
    airplane = _coerce_airplane(definition_or_airplane)
    figure = airplane.draw(backend="plotly", show=False)
    figure.update_layout(
        template="plotly_white",
        margin={"l": 0, "r": 0, "t": 40, "b": 0},
        scene_aspectmode="data",
        title=airplane.name,
    )
    return figure


def render_aircraft_three_view_image(
    definition_or_airplane: AircraftDefinition | Any,
    *,
    dpi: int = 200,
) -> str:
    """Return a base64 PNG data URI for the aircraft three-view image."""
    airplane = _coerce_airplane(definition_or_airplane)
    axs = airplane.draw_three_view(show=False)
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
