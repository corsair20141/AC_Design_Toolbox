"""Tests for the canonical aircraft-configuration API."""

from __future__ import annotations

from pathlib import Path
import unittest

from ac_design_toolbox import (
    AircraftDefinition,
    build_aircraft,
    canted_pair_projected_area_factor,
    collect_component_ids,
    design_variable_records,
    render_aircraft_plotly,
    render_aircraft_three_view_image,
    solve_canted_pair_surface_area_from_horizontal_volume_coefficient,
    solve_canted_pair_surface_area_from_vertical_volume_coefficient,
    solve_horizontal_tail_area_from_volume_coefficient,
    solve_planform,
    solve_twin_vertical_tail_surface_area_from_volume_coefficient,
    solve_vertical_tail_area_from_volume_coefficient,
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
        h_tail_definition = AircraftDefinition.from_dict({"tail_assembly": {"tail_type": "h_tail"}})
        self.assertEqual(
            collect_component_ids(h_tail_definition),
            ["main_wing", "horizontal_tail", "vertical_tail_right", "vertical_tail_left"],
        )
        y_tail_definition = AircraftDefinition.from_dict({"tail_assembly": {"tail_type": "y_tail"}})
        self.assertEqual(
            collect_component_ids(y_tail_definition),
            ["main_wing", "vertical_tail", "v_tail_surface_right", "v_tail_surface_left"],
        )

    def test_build_aircraft_supports_all_v1_tail_types(self) -> None:
        """All supported tail families should build an AeroSandbox airplane."""
        for tail_type in ("conventional", "t_tail", "v_tail", "h_tail", "y_tail"):
            definition = AircraftDefinition.from_dict({"tail_assembly": {"tail_type": tail_type}})
            airplane = build_aircraft(definition)
            self.assertEqual(airplane.name, definition.name)
            self.assertGreaterEqual(len(airplane.wings), 3)

    def test_h_tail_builds_tip_mounted_twin_vertical_tails(self) -> None:
        """H-tail builds should emit mirrored tip-mounted vertical tails."""
        definition = AircraftDefinition.from_dict({"tail_assembly": {"tail_type": "h_tail"}})
        airplane = build_aircraft(definition)
        wing_lookup = {wing.name: wing for wing in airplane.wings}

        self.assertIn("horizontal_tail", wing_lookup)
        self.assertIn("vertical_tail_right", wing_lookup)
        self.assertIn("vertical_tail_left", wing_lookup)
        self.assertAlmostEqual(
            float(wing_lookup["vertical_tail_right"].xsecs[0].xyz_le[1]),
            -float(wing_lookup["vertical_tail_left"].xsecs[0].xyz_le[1]),
        )

    def test_y_tail_builds_center_fin_and_canted_pair(self) -> None:
        """Y-tail builds should include one center fin plus mirrored canted surfaces."""
        definition = AircraftDefinition.from_dict({"tail_assembly": {"tail_type": "y_tail"}})
        airplane = build_aircraft(definition)
        wing_names = {wing.name for wing in airplane.wings}

        self.assertIn("vertical_tail", wing_names)
        self.assertIn("v_tail_surface_right", wing_names)
        self.assertIn("v_tail_surface_left", wing_names)

    def test_negative_v_tail_dihedral_builds_inverted_tail_geometry(self) -> None:
        """Negative V-tail cant should remain a valid mirrored canted-tail build."""
        definition = AircraftDefinition.from_dict(
            {
                "tail_assembly": {
                    "tail_type": "v_tail",
                    "v_tail_surface": {
                        "component_id": "v_tail_surface",
                        "span": 2.1,
                        "area": 0.28,
                        "taper": 0.8,
                        "sweep_le_deg": 18.0,
                        "dihedral_deg": -35.0,
                        "x_le": 2.5,
                        "y_le": 0.0,
                        "z_le": 0.0,
                    },
                }
            }
        )
        airplane = build_aircraft(definition)
        right_surface = next(wing for wing in airplane.wings if wing.name == "v_tail_surface_right")
        self.assertLess(float(right_surface.xsecs[-1].xyz_le[2]), float(right_surface.xsecs[0].xyz_le[2]))

    def test_v_tail_builder_preserves_single_surface_planform_metrics(self) -> None:
        """Each built canted-tail surface should honor the stored one-surface span and area."""
        definition = AircraftDefinition.from_dict(
            {
                "tail_assembly": {
                    "tail_type": "v_tail",
                    "v_tail_surface": {
                        "component_id": "v_tail_surface",
                        "span": 2.1,
                        "area": 0.28,
                        "taper": 0.8,
                        "sweep_le_deg": 18.0,
                        "dihedral_deg": 35.0,
                        "x_le": 2.5,
                        "y_le": 0.0,
                        "z_le": 0.0,
                    },
                }
            }
        )
        airplane = build_aircraft(definition)
        right_surface = next(wing for wing in airplane.wings if wing.name == "v_tail_surface_right")
        expected_planform = solve_planform(span=2.1, area=0.28, taper=0.8)

        self.assertAlmostEqual(
            float(right_surface.xsecs[-1].xyz_le[1] - right_surface.xsecs[0].xyz_le[1]),
            2.1,
        )
        self.assertAlmostEqual(float(right_surface.xsecs[0].chord), expected_planform.root_chord)
        self.assertAlmostEqual(float(right_surface.xsecs[-1].chord), expected_planform.tip_chord)

    def test_solve_planform_supports_all_public_driver_sets(self) -> None:
        """Each supported public driver set should converge to the same planform."""
        expected = dict(
            span=10.0,
            area=12.0,
            aspect_ratio=100.0 / 12.0,
            root_chord=1.6,
            tip_chord=0.8,
            taper=0.5,
        )
        driver_sets = [
            dict(root_chord=1.6, tip_chord=0.8, span=10.0),
            dict(root_chord=1.6, taper=0.5, span=10.0),
            dict(tip_chord=0.8, taper=0.5, span=10.0),
            dict(area=12.0, span=10.0, taper=0.5),
            dict(aspect_ratio=100.0 / 12.0, span=10.0, taper=0.5),
            dict(area=12.0, aspect_ratio=100.0 / 12.0, taper=0.5),
            dict(area=12.0, span=10.0, root_chord=1.6),
            dict(area=12.0, span=10.0, tip_chord=0.8),
        ]

        for driver_set in driver_sets:
            with self.subTest(driver_set=driver_set):
                result = solve_planform(**driver_set)
                self.assertAlmostEqual(result.span, expected["span"])
                self.assertAlmostEqual(result.area, expected["area"])
                self.assertAlmostEqual(result.aspect_ratio, expected["aspect_ratio"])
                self.assertAlmostEqual(result.root_chord, expected["root_chord"])
                self.assertAlmostEqual(result.tip_chord, expected["tip_chord"])
                self.assertAlmostEqual(result.taper, expected["taper"])

    def test_tail_volume_helpers_return_expected_first_pass_areas(self) -> None:
        """Tail-volume helpers should match the intended coefficient formulas."""
        horizontal_area = solve_horizontal_tail_area_from_volume_coefficient(
            volume_coefficient=0.5,
            wing_area=10.0,
            wing_mean_aerodynamic_chord=1.2,
            tail_arm=4.0,
        )
        vertical_area = solve_vertical_tail_area_from_volume_coefficient(
            volume_coefficient=0.04,
            wing_area=10.0,
            wing_span=12.0,
            tail_arm=4.0,
        )
        twin_vertical_surface_area = solve_twin_vertical_tail_surface_area_from_volume_coefficient(
            volume_coefficient=0.04,
            wing_area=10.0,
            wing_span=12.0,
            tail_arm=4.0,
        )

        self.assertAlmostEqual(horizontal_area, 1.5)
        self.assertAlmostEqual(vertical_area, 1.2)
        self.assertAlmostEqual(twin_vertical_surface_area, 0.6)

    def test_canted_pair_volume_helpers_use_projected_equivalent_area(self) -> None:
        """Mirrored canted-pair sizing should use projected equivalent area on both axes."""
        vertical_factor = canted_pair_projected_area_factor(cant_deg=60.0, axis="vertical")
        vertical_area = solve_canted_pair_surface_area_from_vertical_volume_coefficient(
            volume_coefficient=0.04,
            wing_area=10.0,
            wing_span=12.0,
            tail_arm=4.0,
            cant_deg=60.0,
        )
        horizontal_factor = canted_pair_projected_area_factor(cant_deg=60.0, axis="horizontal")
        horizontal_area = solve_canted_pair_surface_area_from_horizontal_volume_coefficient(
            volume_coefficient=0.5,
            wing_area=10.0,
            wing_mean_aerodynamic_chord=1.2,
            tail_arm=4.0,
            cant_deg=60.0,
        )

        self.assertAlmostEqual(vertical_factor, 1.5)
        self.assertAlmostEqual(vertical_area, 0.8)
        self.assertAlmostEqual(horizontal_factor, 0.5)
        self.assertAlmostEqual(horizontal_area, 3.0)

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

    def test_render_helpers_support_mirrored_tail_families(self) -> None:
        """Render helpers should accept mirrored tail-family builds without vector-type errors."""
        test_cases = [
            ("v_tail", 35.0),
            ("v_tail", -35.0),
            ("h_tail", 0.0),
            ("y_tail", 35.0),
        ]

        for tail_type, dihedral_deg in test_cases:
            with self.subTest(tail_type=tail_type, dihedral_deg=dihedral_deg):
                definition_dict = AircraftDefinition().to_dict()
                definition_dict["tail_assembly"]["tail_type"] = tail_type
                definition_dict["tail_assembly"]["v_tail_surface"]["dihedral_deg"] = dihedral_deg
                definition_dict["tail_assembly"]["vertical_tail"]["dihedral_deg"] = dihedral_deg
                definition = AircraftDefinition.from_dict(definition_dict)

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
