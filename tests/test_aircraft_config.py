"""Tests for the canonical aircraft-configuration API."""

from __future__ import annotations

from pathlib import Path
import unittest

from ac_design_toolbox import (
    AircraftDefinition,
    build_aircraft,
    collect_component_ids,
    design_variable_records,
    render_aircraft_plotly,
    render_aircraft_three_view_image,
)


class AircraftConfigTests(unittest.TestCase):
    """Verify the new aircraft-definition schema and geometry helpers."""

    def test_schema_round_trip_is_stable(self) -> None:
        """Default aircraft definitions should survive JSON round-trip exactly."""
        definition = AircraftDefinition()
        round_tripped = AircraftDefinition.from_json(definition.to_json())
        self.assertEqual(round_tripped.to_dict(), definition.to_dict())

    def test_component_ids_reflect_tail_family(self) -> None:
        """Stable component IDs should track the active tail family cleanly."""
        v_tail_definition = AircraftDefinition.from_dict({"tail_assembly": {"tail_type": "v_tail"}})
        self.assertEqual(
            collect_component_ids(v_tail_definition),
            ["main_wing", "v_tail_surface_right", "v_tail_surface_left"],
        )

    def test_build_aircraft_supports_all_v1_tail_types(self) -> None:
        """All supported tail families should build an AeroSandbox airplane."""
        for tail_type in ("conventional", "t_tail", "v_tail"):
            definition = AircraftDefinition.from_dict({"tail_assembly": {"tail_type": tail_type}})
            airplane = build_aircraft(definition)
            self.assertEqual(airplane.name, definition.name)
            self.assertGreaterEqual(len(airplane.wings), 3)

    def test_design_variable_records_include_current_values(self) -> None:
        """Optimizer-facing variable helpers should expose resolved current values."""
        definition = AircraftDefinition()
        records = design_variable_records(definition)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]["path"], "main_wing.span")
        self.assertAlmostEqual(float(records[0]["current_value"]), definition.main_wing.span)

    def test_render_helpers_return_dash_friendly_payloads(self) -> None:
        """Plotly and three-view render helpers should return embeddable outputs."""
        definition = AircraftDefinition()
        figure = render_aircraft_plotly(definition)
        image_payload = render_aircraft_three_view_image(definition)
        self.assertGreaterEqual(len(figure.data), 1)
        self.assertTrue(image_payload.startswith("data:image/png;base64,"))

    def test_package_metadata_exists_for_installation(self) -> None:
        """The repository should expose packaging metadata for later pip install."""
        repo_root = Path(__file__).resolve().parents[1]
        self.assertTrue((repo_root / "pyproject.toml").exists())


if __name__ == "__main__":
    unittest.main()
