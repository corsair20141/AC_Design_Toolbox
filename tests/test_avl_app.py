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
    _export_target,
    _normalized_result_payload,
    _normalized_sm_result_payload,
    _output_target_error,
    _user_output_path,
    _would_overwrite_output,
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
        self.assertEqual(_display_label("avl-sm-cl-target-input", "imperial"), "Target CL")
        self.assertAlmostEqual(_to_canonical_value(38.8769, "m_s", "imperial"), 20.0, places=4)
        self.assertAlmostEqual(_to_canonical_value(328.084, "m", "imperial"), 100.0, places=4)
        self.assertAlmostEqual(_to_canonical_value(11.0231, "kg", "imperial"), 5.0, places=4)

    def test_display_values_convert_when_unit_system_changes(self) -> None:
        """Existing field values should stay physically equivalent after unit changes."""

        converted = _convert_between_display_units(20.0, "avl-velocity-input", "metric", "imperial")

        self.assertAlmostEqual(converted, 38.8769, places=4)

    def test_export_path_helpers_accept_file_or_directory_targets(self) -> None:
        """Geometry export may target a specific .avl file or an output directory."""

        file_target = _user_output_path("out/custom.avl")
        self.assertIsNotNone(file_target)
        work_root, file_name, geom_path = _export_target(file_target)
        self.assertEqual(work_root, (Path.cwd() / "out").resolve(strict=False))
        self.assertEqual(file_name, "custom.avl")
        self.assertEqual(geom_path, (Path.cwd() / "out" / "custom.avl").resolve(strict=False))

        directory_target = _user_output_path("out_dir")
        self.assertIsNotNone(directory_target)
        work_root, file_name, geom_path = _export_target(directory_target)
        self.assertEqual(work_root, (Path.cwd() / "out_dir").resolve(strict=False))
        self.assertEqual(file_name, "Airplane.avl")
        self.assertEqual(geom_path, (Path.cwd() / "out_dir" / "Airplane.avl").resolve(strict=False))

    def test_user_output_path_resolves_relative_paths_from_app_cwd(self) -> None:
        """User output paths should be deterministic before writing files."""

        self.assertIsNone(_user_output_path(""))
        self.assertEqual(_user_output_path("'relative/case'"), (Path.cwd() / "relative" / "case").resolve(strict=False))

    def test_overwrite_detection_warns_for_existing_file_or_nonempty_directory(self) -> None:
        """User-provided outputs should warn before overwriting existing artifacts."""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            avl_path = tmp_path / "existing.avl"
            avl_path.write_text("old", encoding="utf-8")
            case_dir = tmp_path / "case"
            case_dir.mkdir()
            (case_dir / "old.txt").write_text("old", encoding="utf-8")

            self.assertTrue(_would_overwrite_output("avl-export-button", avl_path))
            self.assertTrue(_would_overwrite_output("avl-run-button", case_dir))
            self.assertFalse(_would_overwrite_output("avl-export-button", tmp_path / "new.avl"))

    def test_output_target_validation_rejects_file_where_directory_is_needed(self) -> None:
        """Output path validation should fail clearly before AVL writes files."""

        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            not_a_directory = tmp_path / "case_target"
            not_a_directory.write_text("old", encoding="utf-8")

            self.assertIn("not a directory", _output_target_error("avl-run-button", not_a_directory) or "")
            self.assertIn(
                "not a directory",
                _output_target_error("avl-export-button", not_a_directory / "aircraft.avl") or "",
            )

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

    def test_sm_target_metadata_is_added_to_trim_shaped_results(self) -> None:
        """SM mode should handle trim results that do not already have scalars."""

        result = _normalized_sm_result_payload(
            {
                "alpha_trim_deg": 3.2,
                "elevator_trim_deg": -1.1,
                "CL": 0.45,
            },
            mode="trim_sm",
            work_root=Path("missing-work-root"),
            sm_metadata={"SM_target": 0.1, "x_np": 0.55, "x_cg": 0.35},
        )

        self.assertEqual(result["scalars"]["CL"], 0.45)
        self.assertEqual(result["scalars"]["SM_target"], 0.1)
        self.assertEqual(result["scalars"]["x_np"], 0.55)
        self.assertEqual(result["scalars"]["x_cg"], 0.35)


if __name__ == "__main__":
    unittest.main()
