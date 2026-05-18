"""Dash page for exporting aircraft geometry and running AVL cases.

The app layer is intentionally owned by AC_Design_Toolbox because AVL file
generation, command scripting, execution, and parsing are aircraft-analysis
concerns. Host applications can embed this page and provide canonical
``AircraftDefinition`` JSON as an external Dash input.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
import tempfile
import zipfile
from typing import Any

from dash import Dash, Input, Output, State, callback_context, dcc, html, no_update
from dash.dependencies import Input as DashInput
from dash.exceptions import PreventUpdate


PAGE_TITLE = "AVL"
DEFAULT_AVL_EXE = "avl"
DISPLAY_UNIT_SYSTEMS = ("metric", "metric_mm", "imperial", "imperial_in")
DEFAULT_DISPLAY_UNIT_SYSTEM = "metric"
DISPLAY_UNIT_SYSTEM_LABELS = {
    "metric": "Metric (m, kg, m/s)",
    "metric_mm": "Metric Aircraft mm",
    "imperial": "Imperial (ft, lbm, kts)",
    "imperial_in": "Imperial Aircraft in",
}
_DISPLAY_UNITS = {
    "metric": {},
    "metric_mm": {"m": "m", "m_s": "m_s", "kg": "kg", "kg_m3": "kg_m3"},
    "imperial": {"m": "ft", "m_s": "kts", "kg": "lbm", "kg_m3": "lbm_ft3"},
    "imperial_in": {"m": "ft", "m_s": "ft_s", "kg": "lbm", "kg_m3": "lbm_ft3"},
}
_UNIT_LABELS = {
    "deg": "deg",
    "deg_f": "deg F",
    "ft": "ft",
    "ft_s": "ft/s",
    "kg": "kg",
    "kg_m3": "kg/m^3",
    "kts": "kts",
    "lbm": "lbm",
    "lbm_ft3": "lbm/ft^3",
    "m": "m",
    "m_s": "m/s",
    "mach": "-",
    "rad_s": "rad/s",
    "s": "s",
}
_CONVERSION_TO_CANONICAL = {
    ("ft", "m"): 0.3048,
    ("kts", "m_s"): 0.5144444444444445,
    ("ft_s", "m_s"): 0.3048,
    ("lbm", "kg"): 0.45359237,
    ("lbm_ft3", "kg_m3"): 16.01846337396014,
}
_CONVERSION_FROM_CANONICAL = {
    (canonical_unit, display_unit): 1.0 / factor
    for (display_unit, canonical_unit), factor in _CONVERSION_TO_CANONICAL.items()
}
_DISPLAY_FIELD_UNITS = {
    "avl-velocity-input": ("Velocity", "m_s"),
    "avl-mach-input": ("Mach", "mach"),
    "avl-altitude-input": ("Altitude", "m"),
    "avl-temp-shift-input": ("Temperature Offset", "deg_f"),
    "avl-timeout-input": ("Timeout", "s"),
    "avl-alpha-input": ("Alpha", "deg"),
    "avl-beta-input": ("Beta", "deg"),
    "avl-density-input": ("Density", "kg_m3"),
    "avl-mass-input": ("Mass", "kg"),
    "avl-roll-rate-input": ("Roll Rate p", "rad_s"),
    "avl-pitch-rate-input": ("Pitch Rate q", "rad_s"),
    "avl-yaw-rate-input": ("Yaw Rate r", "rad_s"),
    "avl-aileron-input": ("Aileron", "deg"),
    "avl-elevator-input": ("Elevator", "deg"),
    "avl-rudder-input": ("Rudder", "deg"),
    "avl-flap-input": ("Flap", "deg"),
    "avl-cl-target-input": ("CL Target", None),
    "avl-elevator-lower-input": ("Elevator Lower", "deg"),
    "avl-elevator-upper-input": ("Elevator Upper", "deg"),
    "avl-alpha-seed-input": ("Alpha Seed", "deg"),
    "avl-elevator-seed-input": ("Elevator Seed", "deg"),
    "avl-tol-cl-input": ("CL Tolerance", None),
    "avl-tol-cm-input": ("Cm Tolerance", None),
    "avl-max-iter-input": ("Max Iterations", None),
}
_DISPLAY_FIELD_IDS = tuple(_DISPLAY_FIELD_UNITS)


def _sid(component_id: str, scope: str | None) -> str:
    """Return a component ID scoped for embedding when requested."""

    return component_id if not scope else f"{scope}::{component_id}"


def _local_triggered_id(scope: str | None) -> str | None:
    """Return the unscoped Dash ID that triggered the current callback."""

    triggered_id = callback_context.triggered_id
    if triggered_id is None:
        return None
    text = str(triggered_id)
    prefix = f"{scope}::" if scope else ""
    if prefix and text.startswith(prefix):
        return text[len(prefix) :]
    return text


def _label(text: str, *, component_id: str | None = None, scope: str | None = None) -> html.Label:
    """Return a compact form label."""

    props: dict[str, Any] = {"style": {"fontSize": "12px", "fontWeight": "600", "color": "#2f3b45"}}
    if component_id:
        props["id"] = _sid(component_id, scope)
    return html.Label(text, **props)


def _number_input(component_id: str, label: str, value: float | int | None, *, scope: str | None) -> html.Div:
    """Return a labeled numeric input with stable sizing."""

    return html.Div(
        [
            _label(label, component_id=f"{component_id}-label", scope=scope),
            dcc.Input(
                id=_sid(component_id, scope),
                type="number",
                value=value,
                debounce=True,
                style={"width": "100%", "boxSizing": "border-box"},
            ),
        ],
        style={"display": "grid", "gap": "4px"},
    )


def _text_input(component_id: str, label: str, value: str, *, scope: str | None) -> html.Div:
    """Return a labeled text input."""

    return html.Div(
        [
            _label(label),
            dcc.Input(
                id=_sid(component_id, scope),
                type="text",
                value=value,
                debounce=True,
                style={"width": "100%", "boxSizing": "border-box"},
            ),
        ],
        style={"display": "grid", "gap": "4px"},
    )


def _button_style(kind: str = "default") -> dict[str, Any]:
    """Return simple button styling for the AVL page."""

    colors = {
        "primary": ("#1f6feb", "white"),
        "run": ("#116329", "white"),
        "default": ("#ffffff", "#24292f"),
    }
    background, color = colors.get(kind, colors["default"])
    return {
        "border": "1px solid #b8c7d9",
        "borderRadius": "6px",
        "backgroundColor": background,
        "color": color,
        "padding": "8px 10px",
        "fontWeight": "600",
        "cursor": "pointer",
    }


def _decode_uploaded_json(contents: str) -> str:
    """Decode a Dash upload payload into JSON text."""

    _, encoded = contents.split(",", 1)
    return base64.b64decode(encoded).decode("utf-8")


def _validate_display_unit_system(unit_system: str | None) -> str:
    """Return a supported display-unit token."""

    normalized = str(unit_system or DEFAULT_DISPLAY_UNIT_SYSTEM).strip().lower()
    if normalized not in DISPLAY_UNIT_SYSTEMS:
        return DEFAULT_DISPLAY_UNIT_SYSTEM
    return normalized


def _display_unit(canonical_unit: str | None, unit_system: str | None) -> str | None:
    """Return the display unit for one canonical unit."""

    if canonical_unit is None:
        return None
    unit_system = _validate_display_unit_system(unit_system)
    return _DISPLAY_UNITS[unit_system].get(canonical_unit, canonical_unit)


def _unit_label(unit: str | None) -> str | None:
    """Return a compact unit label."""

    if unit is None:
        return None
    return _UNIT_LABELS.get(unit, unit)


def _display_label(field_id: str, unit_system: str | None) -> str:
    """Return a display label for one AVL numeric input."""

    base_label, canonical_unit = _DISPLAY_FIELD_UNITS[field_id]
    label = _unit_label(_display_unit(canonical_unit, unit_system))
    return base_label if label is None else f"{base_label} [{label}]"


def _to_display_value(value: Any, canonical_unit: str | None, unit_system: str | None) -> Any:
    """Convert one canonical value into the active display unit."""

    if value in (None, "") or canonical_unit is None:
        return value
    display_unit = _display_unit(canonical_unit, unit_system)
    if display_unit == canonical_unit:
        return value
    factor = _CONVERSION_FROM_CANONICAL.get((canonical_unit, str(display_unit)))
    return float(value) * factor if factor is not None else value


def _to_canonical_value(value: Any, canonical_unit: str | None, unit_system: str | None) -> Any:
    """Convert one display value back into the canonical unit ACDT expects."""

    if value in (None, "") or canonical_unit is None:
        return value
    display_unit = _display_unit(canonical_unit, unit_system)
    if display_unit == canonical_unit:
        return value
    factor = _CONVERSION_TO_CANONICAL.get((str(display_unit), canonical_unit))
    return round(float(value) * factor, 12) if factor is not None else value


def _convert_between_display_units(value: Any, field_id: str, old_unit_system: str | None, new_unit_system: str | None) -> Any:
    """Convert an existing field value from one display system to another."""

    _, canonical_unit = _DISPLAY_FIELD_UNITS[field_id]
    canonical_value = _to_canonical_value(value, canonical_unit, old_unit_system)
    return _to_display_value(canonical_value, canonical_unit, new_unit_system)


def _canonical_float(values: tuple[Any, ...], index: int, default: float, unit_system: str | None, field_id: str) -> float:
    """Read one display value from the action callback and return canonical float."""

    _, canonical_unit = _DISPLAY_FIELD_UNITS[field_id]
    return _float(_to_canonical_value(values[index], canonical_unit, unit_system), default)


def _aircraft_from_json(definition_json: str):
    """Build an AeroSandbox airplane from canonical AircraftDefinition JSON."""

    from ac_design_toolbox.aircraft_config import AircraftDefinition, build_aircraft

    definition = AircraftDefinition.from_json(definition_json)
    airplane = build_aircraft(definition)
    return definition, airplane


def _sanitize_case_name(value: str | None) -> str:
    """Return a filesystem-friendly AVL case name."""

    text = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in str(value or "avl_case"))
    return text.strip("_") or "avl_case"


def _case_work_root() -> Path:
    """Create a retained temporary case directory for later bundle download."""

    return Path(tempfile.mkdtemp(prefix="acdt_avl_app_"))


def _json_summary_payload(result: dict[str, Any], mode: str) -> bytes:
    """Return a compact JSON summary for bundle export."""

    payload = {
        "mode": mode,
        "paths": result.get("paths", {}),
        "scalars": result.get("scalars", {}),
        "stability": result.get("stability"),
        "strip_force_count": len(result.get("strip_forces") or []),
    }
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")


def _case_file_paths(work_root: Path) -> dict[str, str]:
    """Return generated AVL case files below a retained work root."""

    paths: dict[str, str] = {}
    if not work_root.exists():
        return paths
    for index, path in enumerate(sorted(item for item in work_root.rglob("*") if item.is_file())):
        paths[f"artifact_{index:03d}"] = str(path)
    return paths


def _normalized_result_payload(raw_result: dict[str, Any], *, mode: str, work_root: Path) -> dict[str, Any]:
    """Return a consistent app result shape for case and trim workflows."""

    if "scalars" in raw_result:
        result = dict(raw_result)
        result.setdefault("paths", _case_file_paths(work_root))
        result.setdefault("raw", "")
        return result

    scalars = {
        key: value
        for key, value in raw_result.items()
        if isinstance(value, (int, float)) and key not in {"history", "newton2d_history"}
    }
    return {
        "paths": _case_file_paths(work_root),
        "scalars": scalars,
        "stability": None,
        "strip_forces": [],
        "raw": json.dumps({"mode": mode, "trim_result": raw_result}, indent=2, sort_keys=True, default=str),
    }


def _zip_case_bundle(case_payload: dict[str, Any]) -> bytes:
    """Package known AVL result files plus a JSON summary into a ZIP archive."""

    result = dict(case_payload.get("result") or {})
    paths = dict(result.get("paths") or {})
    mode = str(case_payload.get("mode") or "avl_case")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("summary.json", _json_summary_payload(result, mode))
        for label, path_text in paths.items():
            if not path_text:
                continue
            path = Path(str(path_text))
            if path.is_file():
                archive.write(path, arcname=f"files/{label}_{path.name}")
    buffer.seek(0)
    return buffer.getvalue()


def _format_status(message: str, *, is_error: bool = False) -> html.Div:
    """Return a status message with clear success/error styling."""

    return html.Div(
        message,
        style={
            "padding": "8px 10px",
            "border": "1px solid #f0c36d" if is_error else "1px solid #b8c7d9",
            "backgroundColor": "#fff8c5" if is_error else "#f6f8fa",
            "borderRadius": "6px",
            "whiteSpace": "pre-wrap",
        },
    )


def _scalar_table(result_payload: dict[str, Any] | None) -> html.Div:
    """Render parsed AVL scalars as a compact table."""

    if not result_payload:
        return html.Div("Run an AVL case to populate parsed scalar results.")
    scalars = dict((result_payload.get("result") or {}).get("scalars") or {})
    if not scalars:
        return html.Div("No parsed scalar results were returned.")
    rows = [
        html.Tr([html.Th("Metric"), html.Th("Value")]),
        *[
            html.Tr([html.Td(str(key)), html.Td(f"{value:.6g}" if isinstance(value, (int, float)) else str(value))])
            for key, value in sorted(scalars.items())
        ],
    ]
    return html.Table(
        rows,
        style={"width": "100%", "borderCollapse": "collapse", "fontSize": "12px"},
    )


def _file_list(result_payload: dict[str, Any] | None) -> html.Ul:
    """Render the files generated by the latest AVL run."""

    paths = dict(((result_payload or {}).get("result") or {}).get("paths") or {})
    if not paths:
        return html.Ul([html.Li("No generated AVL case files yet.")])
    return html.Ul([html.Li(f"{label}: {path}") for label, path in paths.items() if path])


def _raw_log(result_payload: dict[str, Any] | None) -> str:
    """Return raw AVL stdout for the log panel."""

    if not result_payload:
        return "Run an AVL case to see captured output."
    result = dict(result_payload.get("result") or {})
    raw = str(result.get("raw") or "")
    paths = dict(result.get("paths") or {})
    stderr_path = paths.get("stderr")
    stderr_text = ""
    if stderr_path and Path(str(stderr_path)).is_file():
        stderr_text = Path(str(stderr_path)).read_text(encoding="utf-8", errors="replace")
    if stderr_text.strip():
        return f"{raw}\n\n--- STDERR ---\n{stderr_text}"
    return raw or "AVL completed without captured stdout."


def _layout(scope: str | None, *, allow_upload: bool) -> html.Div:
    """Return the AVL page layout."""

    upload_block = html.Div(
        [
            _label("AircraftDefinition JSON"),
            dcc.Upload(
                id=_sid("avl-aircraft-upload", scope),
                children=html.Button("Upload Aircraft JSON", style=_button_style()),
                multiple=False,
            ),
            html.Div(id=_sid("avl-aircraft-source-status", scope), style={"fontSize": "12px"}),
        ],
        style={"display": "grid", "gap": "6px"},
    )
    if not allow_upload:
        upload_block = html.Div(
            "Using the host workspace aircraft definition.",
            id=_sid("avl-aircraft-source-status", scope),
            style={"fontSize": "12px", "color": "#57606a"},
        )

    return html.Div(
        [
            dcc.Store(id=_sid("avl-aircraft-definition-store", scope)),
            dcc.Store(id=_sid("avl-last-result-store", scope)),
            dcc.Store(id=_sid("avl-display-unit-system-store", scope), data=DEFAULT_DISPLAY_UNIT_SYSTEM),
            dcc.Download(id=_sid("avl-download", scope)),
            html.H1(PAGE_TITLE, style={"marginTop": 0}),
            html.Div(
                [
                    html.Div(
                        [
                            upload_block,
                            _text_input("avl-exe-input", "AVL Executable", DEFAULT_AVL_EXE, scope=scope),
                            _text_input("avl-case-name-input", "Case Name", "avl_case", scope=scope),
                            html.Div(
                                [
                                    _label("Display Units"),
                                    dcc.Dropdown(
                                        id=_sid("avl-display-unit-dropdown", scope),
                                        options=[
                                            {"label": label, "value": value}
                                            for value, label in DISPLAY_UNIT_SYSTEM_LABELS.items()
                                        ],
                                        value=DEFAULT_DISPLAY_UNIT_SYSTEM,
                                        clearable=False,
                                    ),
                                ],
                                style={"display": "grid", "gap": "4px"},
                            ),
                            html.Div(
                                [
                                    _label("Run Mode"),
                                    dcc.Dropdown(
                                        id=_sid("avl-run-mode-dropdown", scope),
                                        options=[
                                            {"label": "Operating Point", "value": "operating_point"},
                                            {"label": "Longitudinal Trim", "value": "trim"},
                                        ],
                                        value="operating_point",
                                        clearable=False,
                                    ),
                                ],
                                style={"display": "grid", "gap": "4px"},
                            ),
                            _number_input("avl-velocity-input", _display_label("avl-velocity-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 20.0, scope=scope),
                            _number_input("avl-mach-input", _display_label("avl-mach-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                            _number_input("avl-altitude-input", _display_label("avl-altitude-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                            _number_input("avl-temp-shift-input", _display_label("avl-temp-shift-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                            _number_input("avl-timeout-input", _display_label("avl-timeout-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 120, scope=scope),
                        ],
                        style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(180px, 1fr))", "gap": "10px"},
                    ),
                    html.Div(
                        [
                            html.H2("Operating Point", style={"fontSize": "16px", "marginBottom": "8px"}),
                            html.Div(
                                [
                                    _number_input("avl-alpha-input", _display_label("avl-alpha-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-beta-input", _display_label("avl-beta-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-density-input", _display_label("avl-density-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 1.225, scope=scope),
                                    _number_input("avl-mass-input", _display_label("avl-mass-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-roll-rate-input", _display_label("avl-roll-rate-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-pitch-rate-input", _display_label("avl-pitch-rate-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-yaw-rate-input", _display_label("avl-yaw-rate-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-aileron-input", _display_label("avl-aileron-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-elevator-input", _display_label("avl-elevator-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-rudder-input", _display_label("avl-rudder-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-flap-input", _display_label("avl-flap-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                ],
                                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))", "gap": "10px"},
                            ),
                        ],
                        id=_sid("avl-operating-point-section", scope),
                        style={"display": "grid", "gap": "10px"},
                    ),
                    html.Div(
                        [
                            html.H2("Trim", style={"fontSize": "16px", "marginBottom": "8px"}),
                            html.Div(
                                [
                                    _number_input("avl-cl-target-input", _display_label("avl-cl-target-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.45, scope=scope),
                                    _number_input("avl-elevator-lower-input", _display_label("avl-elevator-lower-input", DEFAULT_DISPLAY_UNIT_SYSTEM), -20.0, scope=scope),
                                    _number_input("avl-elevator-upper-input", _display_label("avl-elevator-upper-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 20.0, scope=scope),
                                    _number_input("avl-alpha-seed-input", _display_label("avl-alpha-seed-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 4.0, scope=scope),
                                    _number_input("avl-elevator-seed-input", _display_label("avl-elevator-seed-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.0, scope=scope),
                                    _number_input("avl-tol-cl-input", _display_label("avl-tol-cl-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.01, scope=scope),
                                    _number_input("avl-tol-cm-input", _display_label("avl-tol-cm-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 0.001, scope=scope),
                                    _number_input("avl-max-iter-input", _display_label("avl-max-iter-input", DEFAULT_DISPLAY_UNIT_SYSTEM), 12, scope=scope),
                                ],
                                style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))", "gap": "10px"},
                            ),
                        ],
                        id=_sid("avl-trim-section", scope),
                        style={"display": "none"},
                    ),
                    html.Div(
                        [
                            html.Button("Export AVL Geometry", id=_sid("avl-export-button", scope), n_clicks=0, style=_button_style("primary")),
                            html.Button("Run Operating Point", id=_sid("avl-run-button", scope), n_clicks=0, style=_button_style("run")),
                            html.Button("Download Case Bundle", id=_sid("avl-bundle-button", scope), n_clicks=0, style=_button_style()),
                        ],
                        style={"display": "flex", "gap": "8px", "flexWrap": "wrap", "marginTop": "14px"},
                    ),
                    html.Div(id=_sid("avl-status-div", scope), children=_format_status("Upload or provide an aircraft definition to begin."), style={"marginTop": "12px"}),
                    html.H2("Parsed Results", style={"fontSize": "16px"}),
                    html.Div(id=_sid("avl-scalars-div", scope), children=_scalar_table(None)),
                    html.H2("Generated Files", style={"fontSize": "16px"}),
                    html.Div(id=_sid("avl-files-div", scope), children=_file_list(None)),
                    html.H2("Captured Log", style={"fontSize": "16px"}),
                    html.Pre(
                        id=_sid("avl-log-pre", scope),
                        children=_raw_log(None),
                        style={"backgroundColor": "#0d1117", "color": "#c9d1d9", "padding": "12px", "overflowX": "auto", "maxHeight": "360px"},
                    ),
                ],
                style={"display": "grid", "gap": "12px"},
            ),
        ],
        style={"padding": "16px", "fontFamily": "Segoe UI, Helvetica, Arial, sans-serif"},
    )


def _float(value: Any, default: float = 0.0) -> float:
    """Coerce a Dash numeric value to float."""

    if value in (None, ""):
        return float(default)
    return float(value)


def _int(value: Any, default: int = 0) -> int:
    """Coerce a Dash numeric value to int."""

    return int(round(_float(value, float(default))))


def create_avl_page(
    *,
    app: Dash,
    id_scope: str | None = None,
    aircraft_definition_input: DashInput | None = None,
    display_unit_input: DashInput | None = None,
    allow_upload: bool = True,
) -> html.Div:
    """Create an embeddable AVL page and register its callbacks.

    Parameters
    ----------
    app:
        Dash app that will own the callbacks.
    id_scope:
        Optional string prefix used to avoid ID collisions when embedded.
    aircraft_definition_input:
        Optional external Dash input carrying canonical ``AircraftDefinition``
        JSON from a host app. When omitted, standalone mode relies on upload.
    display_unit_input:
        Optional external Dash input carrying a Solar_UAS-compatible display
        unit token. Values entered in the page are converted back to the
        canonical units required by ACDT before AVL APIs are called.
    allow_upload:
        Whether to show the upload control. Solar_UAS can disable upload if it
        wants the host workspace aircraft to be the only source.
    """

    if not allow_upload and aircraft_definition_input is None:
        raise ValueError("create_avl_page requires upload support or an external aircraft_definition_input.")

    page_layout = _layout(id_scope, allow_upload=allow_upload)

    unit_inputs = [Input(_sid("avl-display-unit-dropdown", id_scope), "value")]
    if display_unit_input is not None:
        unit_inputs.append(display_unit_input)

    @app.callback(
        Output(_sid("avl-display-unit-system-store", id_scope), "data"),
        Output(_sid("avl-display-unit-dropdown", id_scope), "value"),
        *[Output(_sid(f"{field_id}-label", id_scope), "children") for field_id in _DISPLAY_FIELD_IDS],
        *[Output(_sid(field_id, id_scope), "value") for field_id in _DISPLAY_FIELD_IDS],
        *unit_inputs,
        State(_sid("avl-display-unit-system-store", id_scope), "data"),
        *[State(_sid(field_id, id_scope), "value") for field_id in _DISPLAY_FIELD_IDS],
    )
    def sync_display_units(*values: Any):
        """Synchronize labels and numeric values with the active display unit system."""

        input_count = len(unit_inputs)
        input_values = values[:input_count]
        old_unit_system = _validate_display_unit_system(values[input_count])
        field_values = values[input_count + 1 :]
        requested_unit = input_values[-1] if display_unit_input is not None else input_values[0]
        new_unit_system = _validate_display_unit_system(requested_unit)
        labels = [_display_label(field_id, new_unit_system) for field_id in _DISPLAY_FIELD_IDS]
        converted_values = [
            _convert_between_display_units(value, field_id, old_unit_system, new_unit_system)
            for field_id, value in zip(_DISPLAY_FIELD_IDS, field_values, strict=False)
        ]
        return [new_unit_system, new_unit_system, *labels, *converted_values]

    sync_inputs = []
    sync_states = []
    if allow_upload:
        sync_inputs.append(Input(_sid("avl-aircraft-upload", id_scope), "contents"))
        sync_states.append(State(_sid("avl-aircraft-upload", id_scope), "filename"))
    if aircraft_definition_input is not None:
        sync_inputs.append(aircraft_definition_input)

    @app.callback(
        Output(_sid("avl-aircraft-definition-store", id_scope), "data"),
        Output(_sid("avl-aircraft-source-status", id_scope), "children"),
        sync_inputs,
        sync_states,
    )
    def sync_aircraft_definition(*values: Any):
        """Keep the AVL page aircraft JSON in sync with upload or host state."""

        value_index = 0
        upload_contents = values[value_index] if allow_upload else None
        if allow_upload:
            value_index += 1
        external_json = values[value_index] if aircraft_definition_input is not None else None
        if aircraft_definition_input is not None:
            value_index += 1
        upload_filename = values[value_index] if allow_upload else None
        triggered_id = _local_triggered_id(id_scope)
        try:
            if triggered_id == "avl-aircraft-upload" and upload_contents:
                definition_json = _decode_uploaded_json(str(upload_contents))
                definition, _ = _aircraft_from_json(definition_json)
                return definition.to_json(), f'Loaded "{upload_filename or definition.name}".'
            if external_json:
                definition, _ = _aircraft_from_json(str(external_json))
                return definition.to_json(), f'Using host aircraft "{definition.name}".'
            raise PreventUpdate
        except PreventUpdate:
            raise
        except Exception as exc:
            return no_update, f"Aircraft definition error: {exc}"

    export_states = [
        State(_sid("avl-aircraft-definition-store", id_scope), "data"),
        State(_sid("avl-exe-input", id_scope), "value"),
        State(_sid("avl-case-name-input", id_scope), "value"),
        State(_sid("avl-run-mode-dropdown", id_scope), "value"),
        State(_sid("avl-display-unit-system-store", id_scope), "data"),
        State(_sid("avl-velocity-input", id_scope), "value"),
        State(_sid("avl-mach-input", id_scope), "value"),
        State(_sid("avl-altitude-input", id_scope), "value"),
        State(_sid("avl-temp-shift-input", id_scope), "value"),
        State(_sid("avl-timeout-input", id_scope), "value"),
        State(_sid("avl-alpha-input", id_scope), "value"),
        State(_sid("avl-beta-input", id_scope), "value"),
        State(_sid("avl-density-input", id_scope), "value"),
        State(_sid("avl-mass-input", id_scope), "value"),
        State(_sid("avl-roll-rate-input", id_scope), "value"),
        State(_sid("avl-pitch-rate-input", id_scope), "value"),
        State(_sid("avl-yaw-rate-input", id_scope), "value"),
        State(_sid("avl-aileron-input", id_scope), "value"),
        State(_sid("avl-elevator-input", id_scope), "value"),
        State(_sid("avl-rudder-input", id_scope), "value"),
        State(_sid("avl-flap-input", id_scope), "value"),
        State(_sid("avl-cl-target-input", id_scope), "value"),
        State(_sid("avl-elevator-lower-input", id_scope), "value"),
        State(_sid("avl-elevator-upper-input", id_scope), "value"),
        State(_sid("avl-alpha-seed-input", id_scope), "value"),
        State(_sid("avl-elevator-seed-input", id_scope), "value"),
        State(_sid("avl-tol-cl-input", id_scope), "value"),
        State(_sid("avl-tol-cm-input", id_scope), "value"),
        State(_sid("avl-max-iter-input", id_scope), "value"),
        State(_sid("avl-last-result-store", id_scope), "data"),
    ]

    @app.callback(
        Output(_sid("avl-download", id_scope), "data"),
        Output(_sid("avl-last-result-store", id_scope), "data"),
        Output(_sid("avl-status-div", id_scope), "children"),
        Input(_sid("avl-export-button", id_scope), "n_clicks"),
        Input(_sid("avl-run-button", id_scope), "n_clicks"),
        Input(_sid("avl-bundle-button", id_scope), "n_clicks"),
        export_states,
        prevent_initial_call=True,
    )
    def handle_avl_action(export_clicks: int, run_clicks: int, bundle_clicks: int, *values: Any):
        """Export geometry, run AVL, or download the latest case bundle."""

        del export_clicks
        del run_clicks
        del bundle_clicks
        triggered_id = _local_triggered_id(id_scope)
        last_result = values[-1]
        if triggered_id == "avl-bundle-button":
            if not last_result:
                return no_update, no_update, _format_status("No AVL run is available for bundle download.", is_error=True)
            data = _zip_case_bundle(dict(last_result))
            filename = f"{_sanitize_case_name((last_result or {}).get('case_name'))}_bundle.zip"
            return dcc.send_bytes(data, filename), no_update, _format_status(f'Prepared "{filename}".')

        definition_json = values[0]
        if not definition_json:
            return no_update, no_update, _format_status("Provide an AircraftDefinition JSON before using AVL.", is_error=True)

        try:
            from ac_design_toolbox.api import AVLCaseConfig, AVLTrimConfig, prepare_avl_airplane, run_case, trim_longitudinal_case

            definition, airplane = _aircraft_from_json(str(definition_json))
            case_name = _sanitize_case_name(values[2])
            work_root = _case_work_root()

            if triggered_id == "avl-export-button":
                prepared = prepare_avl_airplane(airplane=airplane, working_directory=work_root, file_name="Airplane.avl")
                geom_path = Path(prepared["geom"])
                filename = f"{definition.name or 'aircraft'}_{case_name}.avl"
                return (
                    dcc.send_bytes(geom_path.read_bytes(), filename),
                    no_update,
                    _format_status(f'Exported AVL geometry "{filename}". Control map: {prepared.get("control_index_map", {})}'),
                )

            mode = str(values[3] or "operating_point")
            unit_system = _validate_display_unit_system(values[4])
            avl_exe = str(values[1] or DEFAULT_AVL_EXE)
            altitude = _canonical_float(values, 7, 0.0, unit_system, "avl-altitude-input")
            altitude_arg = altitude if altitude > 0.0 else None
            timeout_s = _int(values[9], 120)
            if mode == "trim":
                config = AVLTrimConfig(
                    case_name=case_name,
                    CL_target=_canonical_float(values, 21, 0.45, unit_system, "avl-cl-target-input"),
                    velocity=_canonical_float(values, 5, 20.0, unit_system, "avl-velocity-input"),
                    altitude=altitude_arg,
                    temp_shift_F=_canonical_float(values, 8, 0.0, unit_system, "avl-temp-shift-input"),
                    mach=_canonical_float(values, 6, 0.0, unit_system, "avl-mach-input"),
                    baseline_controls={
                        "aileron": _canonical_float(values, 17, 0.0, unit_system, "avl-aileron-input"),
                        "elevator": _canonical_float(values, 18, 0.0, unit_system, "avl-elevator-input"),
                        "rudder": _canonical_float(values, 19, 0.0, unit_system, "avl-rudder-input"),
                        "flap": _canonical_float(values, 20, 0.0, unit_system, "avl-flap-input"),
                    },
                    elevator_bounds=(
                        _canonical_float(values, 22, -20.0, unit_system, "avl-elevator-lower-input"),
                        _canonical_float(values, 23, 20.0, unit_system, "avl-elevator-upper-input"),
                    ),
                    alpha_seed_deg=_canonical_float(values, 24, 4.0, unit_system, "avl-alpha-seed-input"),
                    elevator_seed_deg=_canonical_float(values, 25, 0.0, unit_system, "avl-elevator-seed-input"),
                    tol_CL=_canonical_float(values, 26, 0.01, unit_system, "avl-tol-cl-input"),
                    tol_Cm=_canonical_float(values, 27, 0.001, unit_system, "avl-tol-cm-input"),
                    max_iter=_int(values[28], 12),
                    timeout_s=timeout_s,
                )
                result = trim_longitudinal_case(airplane=airplane, avl_exe=avl_exe, working_directory=work_root, config=config)
            else:
                config = AVLCaseConfig(
                    case_name=case_name,
                    alpha=_canonical_float(values, 10, 0.0, unit_system, "avl-alpha-input"),
                    beta=_canonical_float(values, 11, 0.0, unit_system, "avl-beta-input"),
                    mach=_canonical_float(values, 6, 0.0, unit_system, "avl-mach-input"),
                    velocity=_canonical_float(values, 5, 20.0, unit_system, "avl-velocity-input"),
                    density=_canonical_float(values, 12, 1.225, unit_system, "avl-density-input"),
                    aircraft_mass=_canonical_float(values, 13, 0.0, unit_system, "avl-mass-input"),
                    roll_rate=_canonical_float(values, 14, 0.0, unit_system, "avl-roll-rate-input"),
                    pitch_rate=_canonical_float(values, 15, 0.0, unit_system, "avl-pitch-rate-input"),
                    yaw_rate=_canonical_float(values, 16, 0.0, unit_system, "avl-yaw-rate-input"),
                    control_deflections={
                        "aileron": _canonical_float(values, 17, 0.0, unit_system, "avl-aileron-input"),
                        "elevator": _canonical_float(values, 18, 0.0, unit_system, "avl-elevator-input"),
                        "rudder": _canonical_float(values, 19, 0.0, unit_system, "avl-rudder-input"),
                        "flap": _canonical_float(values, 20, 0.0, unit_system, "avl-flap-input"),
                    },
                    altitude=altitude_arg,
                    temp_shift_F=_canonical_float(values, 8, 0.0, unit_system, "avl-temp-shift-input"),
                    timeout_s=timeout_s,
                )
                result = run_case(airplane=airplane, avl_exe=avl_exe, working_directory=work_root, config=config)

            result_payload = {
                "mode": mode,
                "case_name": case_name,
                "work_root": str(work_root),
                "result": _normalized_result_payload(dict(result), mode=mode, work_root=work_root),
            }
            return no_update, result_payload, _format_status(f'Completed AVL {mode.replace("_", " ")} case "{case_name}".')
        except Exception as exc:
            return no_update, no_update, _format_status(f"AVL action failed: {exc}", is_error=True)

    @app.callback(
        Output(_sid("avl-scalars-div", id_scope), "children"),
        Output(_sid("avl-files-div", id_scope), "children"),
        Output(_sid("avl-log-pre", id_scope), "children"),
        Input(_sid("avl-last-result-store", id_scope), "data"),
    )
    def render_avl_results(result_payload: dict[str, Any] | None):
        """Render result details from the latest AVL run."""

        return _scalar_table(result_payload), _file_list(result_payload), _raw_log(result_payload)

    @app.callback(
        Output(_sid("avl-operating-point-section", id_scope), "style"),
        Output(_sid("avl-trim-section", id_scope), "style"),
        Output(_sid("avl-run-button", id_scope), "children"),
        Input(_sid("avl-run-mode-dropdown", id_scope), "value"),
    )
    def toggle_run_mode_sections(run_mode: str | None):
        """Show only the input group used by the selected AVL workflow."""

        if str(run_mode or "operating_point") == "trim":
            return {"display": "none"}, {"display": "grid", "gap": "10px"}, "Run Trim"
        return {"display": "grid", "gap": "10px"}, {"display": "none"}, "Run Operating Point"

    return page_layout


def create_avl_app() -> Dash:
    """Create the standalone ACDT AVL Dash app."""

    app = Dash(__name__, suppress_callback_exceptions=True)
    app.title = "ACDT AVL"
    app.layout = create_avl_page(app=app, allow_upload=True)
    return app


__all__ = ["create_avl_app", "create_avl_page"]
