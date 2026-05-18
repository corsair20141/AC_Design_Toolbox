"""Smoke tests for the ACDT-owned AVL Dash app."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import unittest

from dash import Dash, Input

from ac_design_toolbox.apps.avl import create_avl_app, create_avl_page
from ac_design_toolbox.apps.avl.page import (
    _convert_between_display_units,
    _display_label,
    _normalized_result_payload,
    _to_canonical_value,
)


def _collect_component_ids(component) -> set[str]:
    """Collect string component IDs from a Dash layout tree."""

    if component is None:
        return set()
    collected_ids: set[str] = set()
    component_id = getattr(component, "id", None)
    if isinstance(component_id, str):
        collected_ids.add(component_id)
    children = getattr(component, "children", None)
    if isinstance(children, Iterable) and not isinstance(children, (str, bytes)):
        for child in children:
            collected_ids.update(_collect_component_ids(child))
    else:
        collected_ids.update(_collect_component_ids(children))
    return collected_ids


class AvlAppTests(unittest.TestCase):
    """Verify the reusable AVL app/page can be constructed without launching."""

    def test_standalone_app_layout_contains_upload_and_run_controls(self) -> None:
        """Standalone mode should require an uploaded aircraft JSON."""

        app = create_avl_app()
        app._setup_server()
        component_ids = _collect_component_ids(app.layout)

        self.assertEqual(app.title, "ACDT AVL")
        for required_id in {
            "avl-aircraft-upload",
            "avl-aircraft-definition-store",
            "avl-display-unit-dropdown",
            "avl-display-unit-system-store",
            "avl-exe-input",
            "avl-run-mode-dropdown",
            "avl-velocity-input-label",
            "avl-operating-point-section",
            "avl-trim-section",
            "avl-export-button",
            "avl-run-button",
            "avl-bundle-button",
            "avl-download",
            "avl-scalars-div",
            "avl-log-pre",
        }:
            self.assertIn(required_id, component_ids)

    def test_embedded_page_uses_scoped_ids_and_external_aircraft_input(self) -> None:
        """Embedded mode should expose scoped controls and register callbacks."""

        app = Dash(__name__, suppress_callback_exceptions=True)
        layout = create_avl_page(
            app=app,
            id_scope="host_avl",
            aircraft_definition_input=Input("host-aircraft-store", "data"),
            display_unit_input=Input("host-unit-store", "data"),
            allow_upload=False,
        )
        app.layout = layout
        app._setup_server()
        component_ids = _collect_component_ids(app.layout)

        self.assertIn("host_avl::avl-aircraft-definition-store", component_ids)
        self.assertIn("host_avl::avl-display-unit-dropdown", component_ids)
        self.assertIn("host_avl::avl-run-button", component_ids)
        self.assertIn("host_avl::avl-operating-point-section", component_ids)
        self.assertIn("host_avl::avl-trim-section", component_ids)
        self.assertNotIn("host_avl::avl-aircraft-upload", component_ids)
        self.assertTrue(app.callback_map)

    def test_display_units_convert_back_to_acdt_canonical_values(self) -> None:
        """Imperial display values should convert to the units expected by ACDT."""

        self.assertEqual(_display_label("avl-velocity-input", "imperial"), "Velocity [kts]")
        self.assertAlmostEqual(_to_canonical_value(38.8769, "m_s", "imperial"), 20.0, places=4)
        self.assertAlmostEqual(_to_canonical_value(328.084, "m", "imperial"), 100.0, places=4)
        self.assertAlmostEqual(_to_canonical_value(11.0231, "kg", "imperial"), 5.0, places=4)

    def test_display_values_convert_when_unit_system_changes(self) -> None:
        """Existing field values should stay physically equivalent after unit changes."""

        converted = _convert_between_display_units(20.0, "avl-velocity-input", "metric", "imperial")

        self.assertAlmostEqual(converted, 38.8769, places=4)

    def test_trim_result_is_normalized_for_display(self) -> None:
        """Trim workflows should render through the same result panels as cases."""

        result = _normalized_result_payload(
            {
                "alpha_trim_deg": 3.2,
                "elevator_trim_deg": -1.1,
                "CL": 0.44,
                "history": {"iter": []},
            },
            mode="trim",
            work_root=Path("missing-work-root"),
        )

        self.assertEqual(result["scalars"]["CL"], 0.44)
        self.assertIn("alpha_trim_deg", result["scalars"])
        self.assertIn("trim_result", result["raw"])


if __name__ == "__main__":
    unittest.main()
