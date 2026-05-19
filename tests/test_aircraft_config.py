"""Tests for the canonical aircraft-configuration API."""

from __future__ import annotations

from pathlib import Path
import unittest

import matplotlib

from ac_design_toolbox import (
    AircraftDefinition,
    CenterOfGravityConfig,
    ControlSurfaceConfig,
    LiftingSurfaceConfig,
    LiftingSurfaceStationConfig,
    SurfaceAnchorConfig,
    build_aircraft,
    collect_component_ids,
    default_main_wing_surface,
    design_variable_records,
    render_aircraft_plotly,
    render_aircraft_three_view_image,
)
from ac_design_toolbox.aircraft_config import rendering as aircraft_rendering


def _surface_with_updates(**updates) -> LiftingSurfaceConfig:
    """Return a lifting surface seeded from the default main-wing fields."""
    surface = default_main_wing_surface().to_dict()
    surface.update(updates)
    return LiftingSurfaceConfig.from_dict(surface)


def _stationed_main_wing() -> LiftingSurfaceConfig:
    """Return a main wing with two explicit station segments."""
    return _surface_with_updates(
        geometry_mode="stationed",
        span=2.0,
        area=0.6,
        taper=0.5,
        root_chord=0.5,
        sweep_le_deg=0.0,
        dihedral_deg=0.0,
        twist_root_deg=1.0,
        root_airfoil="naca4412",
        stations=[
            LiftingSurfaceStationConfig(
                span=0.6,
                sweep_le_deg=10.0,
                dihedral_deg=3.0,
                taper=0.8,
                twist_deg=0.0,
                airfoil="naca4412",
            ),
            LiftingSurfaceStationConfig(
                span=0.4,
                sweep_le_deg=-5.0,
                dihedral_deg=6.0,
                chord=0.25,
                twist_deg=-2.0,
                airfoil="naca0012",
            ),
        ],
    )


def _max_trace_coordinate(figure) -> float:
    """Return the largest absolute rendered coordinate across all trace axes."""
    max_coordinate = 0.0
    for trace in figure.data:
        for axis_name in ("x", "y", "z"):
            values = getattr(trace, axis_name, None)
            if values is None:
                continue
            for value in values:
                if value is None:
                    continue
                max_coordinate = max(max_coordinate, abs(float(value)))
    return max_coordinate


@unittest.skipUnless(True, "Rendering-backed aircraft-config tests always apply in the configured environment.")
class AircraftConfigTests(unittest.TestCase):
    """Verify the surface-list aircraft schema and geometry helpers."""

    def test_schema_round_trip_is_stable(self) -> None:
        """Default aircraft definitions should survive JSON round-trip exactly."""
        definition = AircraftDefinition()
        round_tripped = AircraftDefinition.from_json(definition.to_json())
        self.assertEqual(round_tripped.to_dict(), definition.to_dict())

    def test_center_of_gravity_is_native_and_drives_airplane_reference(self) -> None:
        """Built AVL/AeroSandbox geometry should use native CG, not moment reference fields."""
        definition = AircraftDefinition(
            reference_geometry={"x_ref": 0.1, "y_ref": 0.2, "z_ref": 0.3},
            center_of_gravity=CenterOfGravityConfig(x_cg=0.4, y_cg=0.05, z_cg=-0.02),
        )

        round_tripped = AircraftDefinition.from_json(definition.to_json())
        airplane = build_aircraft(round_tripped)

        self.assertEqual(round_tripped.center_of_gravity.as_tuple(), (0.4, 0.05, -0.02))
        self.assertAlmostEqual(float(airplane.xyz_ref[0]), 0.4)
        self.assertAlmostEqual(float(airplane.xyz_ref[1]), 0.05)
        self.assertAlmostEqual(float(airplane.xyz_ref[2]), -0.02)

    def test_legacy_solar_uas_cg_extension_migrates_to_native_cg(self) -> None:
        """Older Solar_UAS aircraft JSON should hydrate CG into the native ACDT field."""
        payload = AircraftDefinition().to_dict()
        payload.pop("center_of_gravity", None)
        payload["extensions"] = {
            "solar_uas": {
                "center_of_gravity": {"x": 0.52, "y": 0.01, "z": 0.03},
            }
        }

        definition = AircraftDefinition.from_dict(payload)

        self.assertEqual(definition.center_of_gravity.as_tuple(), (0.52, 0.01, 0.03))

    def test_round_trip_supports_multiple_wings_and_zero_tails(self) -> None:
        """List-based definitions should support extra wings without any tail surfaces."""
        definition = AircraftDefinition(
            name="Flying Wing With Strake",
            lifting_surfaces=[
                default_main_wing_surface(),
                _surface_with_updates(
                    component_id="center_strake",
                    role="wing",
                    orientation="horizontal",
                    symmetric=False,
                    span=0.45,
                    area=0.06,
                    x_le=0.4,
                    y_le=0.08,
                    z_le=0.0,
                    dihedral_deg=0.0,
                ),
            ],
        )

        round_tripped = AircraftDefinition.from_json(definition.to_json())
        self.assertEqual(round_tripped.to_dict(), definition.to_dict())
        self.assertEqual(collect_component_ids(round_tripped), ["main_wing", "center_strake"])

    def test_stationed_surface_round_trip_and_derives_planform_summary(self) -> None:
        """Station-mode surfaces should store segments and derive summary scalars."""
        surface = _stationed_main_wing()
        definition = AircraftDefinition(lifting_surfaces=[surface])

        round_tripped = AircraftDefinition.from_json(definition.to_json())

        self.assertEqual(round_tripped.to_dict(), definition.to_dict())
        main_wing = round_tripped.main_wing_surface()
        self.assertEqual(main_wing.geometry_mode, "stationed")
        self.assertEqual(len(main_wing.stations), 2)
        self.assertAlmostEqual(float(main_wing.span), 2.0)
        self.assertAlmostEqual(float(main_wing.area), 0.8)
        self.assertAlmostEqual(float(main_wing.taper), 0.5)

    def test_stationed_surface_builds_expected_aerosandbox_xsecs(self) -> None:
        """Sweep drives X advance and dihedral drives Z advance in station mode."""
        surface = _stationed_main_wing()
        airplane = build_aircraft(AircraftDefinition(lifting_surfaces=[surface]))
        wing = airplane.wings[0]

        self.assertTrue(wing.symmetric)
        self.assertEqual(len(wing.xsecs), 3)
        self.assertAlmostEqual(float(wing.xsecs[0].chord), 0.5)
        self.assertAlmostEqual(float(wing.xsecs[1].chord), 0.4)
        self.assertAlmostEqual(float(wing.xsecs[2].chord), 0.25)
        self.assertAlmostEqual(float(wing.xsecs[1].xyz_le[1]), 0.6)
        self.assertAlmostEqual(float(wing.xsecs[2].xyz_le[1]), 1.0)
        self.assertGreater(float(wing.xsecs[1].xyz_le[0]), float(wing.xsecs[0].xyz_le[0]))
        self.assertLess(float(wing.xsecs[2].xyz_le[0]), float(wing.xsecs[1].xyz_le[0]))
        self.assertGreater(float(wing.xsecs[1].xyz_le[2]), float(wing.xsecs[0].xyz_le[2]))
        self.assertGreater(float(wing.xsecs[2].xyz_le[2]), float(wing.xsecs[1].xyz_le[2]))

    def test_stationed_surface_inserts_control_break_xsecs(self) -> None:
        """Station-mode controls should create AVL-visible section breaks."""
        surface_data = _stationed_main_wing().to_dict()
        surface_data["control_surfaces"] = [
            ControlSurfaceConfig(
                name="aileron",
                span_start_fraction=0.65,
                span_end_fraction=0.95,
                hinge_point=0.75,
                symmetric=True,
            ).to_dict()
        ]
        surface = LiftingSurfaceConfig.from_dict(surface_data)

        airplane = build_aircraft(AircraftDefinition(lifting_surfaces=[surface]))
        wing = airplane.wings[0]

        self.assertEqual(len(wing.xsecs), 5)
        control_xsecs = [
            xsec
            for xsec in wing.xsecs
            if any(control.name == "aileron" for control in getattr(xsec, "control_surfaces", []))
        ]
        self.assertEqual(len(control_xsecs), 2)
        self.assertAlmostEqual(float(control_xsecs[0].xyz_le[1]), 0.65)
        self.assertAlmostEqual(float(control_xsecs[1].xyz_le[1]), 0.95)

        panels = aircraft_rendering._control_surface_panels(airplane)
        self.assertTrue(
            any(
                panel["surface_name"] == "main_wing" and panel["control_name"] == "aileron"
                for panel in panels
            )
        )

    def test_stationed_surface_rejects_invalid_segments(self) -> None:
        """Station-mode validation should fail before bad geometry reaches ASB."""
        with self.assertRaisesRegex(ValueError, "station span must be positive"):
            LiftingSurfaceStationConfig(span=0.0)

        with self.assertRaisesRegex(ValueError, "either chord or taper"):
            LiftingSurfaceStationConfig(span=0.2, taper=None, chord=None)

        with self.assertRaisesRegex(ValueError, "require at least one station"):
            _surface_with_updates(geometry_mode="stationed", stations=[])

    def test_control_surfaces_round_trip_and_build_into_geometry(self) -> None:
        """Canonical control surfaces should serialize and build into AeroSandbox xsecs."""
        definition = AircraftDefinition(
            lifting_surfaces=[
                _surface_with_updates(
                    control_surfaces=[
                        ControlSurfaceConfig(
                            name="aileron",
                            span_start_fraction=0.65,
                            span_end_fraction=0.95,
                            hinge_point=0.72,
                            symmetric=False,
                            deflection_deg=3.0,
                        ),
                        ControlSurfaceConfig(
                            name="flap",
                            span_start_fraction=0.20,
                            span_end_fraction=0.55,
                            hinge_point=0.76,
                            symmetric=True,
                            deflection_deg=0.0,
                        ),
                    ],
                )
            ]
        )

        round_tripped = AircraftDefinition.from_json(definition.to_json())
        self.assertEqual(round_tripped.to_dict(), definition.to_dict())

        airplane = build_aircraft(round_tripped)
        control_names = {
            control.name
            for xsec in airplane.wings[0].xsecs
            for control in getattr(xsec, "control_surfaces", [])
        }
        self.assertEqual(control_names, {"aileron", "flap"})

    def test_control_surface_validation_rejects_invalid_ranges(self) -> None:
        """Control surface span and hinge definitions should reject invalid ranges."""
        with self.assertRaisesRegex(ValueError, "greater than span_start"):
            ControlSurfaceConfig(span_start_fraction=0.8, span_end_fraction=0.2)

        with self.assertRaisesRegex(ValueError, "hinge_point"):
            ControlSurfaceConfig(hinge_point=1.0)

    def test_render_helpers_include_control_surface_overlays(self) -> None:
        """Geometry renderers should draw control-surface footprint overlays."""
        definition = AircraftDefinition(
            lifting_surfaces=[
                _surface_with_updates(
                    control_surfaces=[
                        ControlSurfaceConfig(
                            name="aileron",
                            span_start_fraction=0.65,
                            span_end_fraction=0.95,
                            hinge_point=0.75,
                            symmetric=False,
                        )
                    ],
                )
            ]
        )

        figure = render_aircraft_plotly(definition)
        trace_names = [str(trace.name) for trace in figure.data]
        self.assertTrue(any("main_wing aileron panel" == name for name in trace_names))
        self.assertTrue(any("main_wing aileron hinge" == name for name in trace_names))

        axs = aircraft_rendering._build_three_view_axes(definition)
        self.assertGreaterEqual(len(axs[0, 0].collections), 2)
        self.assertGreaterEqual(len(axs[0, 0].lines), 1)
        axs[0, 0].figure.clf()

    def test_rejects_zero_or_multiple_main_wings(self) -> None:
        """Definitions must contain exactly one role='main_wing' surface."""
        with self.assertRaisesRegex(ValueError, "exactly one"):
            AircraftDefinition(
                lifting_surfaces=[
                    _surface_with_updates(component_id="canard", role="canard", orientation="horizontal"),
                ]
            )

        with self.assertRaisesRegex(ValueError, "exactly one"):
            AircraftDefinition(
                lifting_surfaces=[
                    default_main_wing_surface(),
                    _surface_with_updates(
                        component_id="second_main",
                        role="main_wing",
                        orientation="horizontal",
                        symmetric=True,
                        span=1.2,
                        area=0.2,
                    ),
                ]
            )

    def test_build_aircraft_supports_explicit_twin_fins_and_extra_wing(self) -> None:
        """Builder should iterate arbitrary explicit surfaces without family branching."""
        definition = AircraftDefinition(
            name="Twin Fin With Canard",
            lifting_surfaces=[
                default_main_wing_surface(),
                _surface_with_updates(
                    component_id="canard",
                    role="canard",
                    orientation="horizontal",
                    symmetric=True,
                    span=0.55,
                    area=0.08,
                    x_le=0.02,
                    z_le=0.04,
                    root_airfoil="naca0012",
                    tip_airfoil="naca0012",
                ),
                _surface_with_updates(
                    component_id="vertical_tail_right",
                    role="vertical_tail",
                    orientation="vertical",
                    symmetric=False,
                    span=0.28,
                    area=0.045,
                    x_le=0.95,
                    y_le=0.22,
                    z_le=0.0,
                    sweep_le_deg=22.0,
                    dihedral_deg=0.0,
                    root_airfoil="naca0010",
                    tip_airfoil="naca0010",
                ),
                _surface_with_updates(
                    component_id="vertical_tail_left",
                    role="vertical_tail",
                    orientation="vertical",
                    symmetric=False,
                    span=0.28,
                    area=0.045,
                    x_le=0.95,
                    y_le=-0.22,
                    z_le=0.0,
                    sweep_le_deg=22.0,
                    dihedral_deg=0.0,
                    root_airfoil="naca0010",
                    tip_airfoil="naca0010",
                ),
            ],
        )

        airplane = build_aircraft(definition)
        wing_names = [wing.name for wing in airplane.wings]
        self.assertEqual(wing_names, ["main_wing", "canard", "vertical_tail_right", "vertical_tail_left"])

    def test_anchored_joined_wing_connectors_round_trip_and_build(self) -> None:
        """Anchored connector surfaces should serialize and build as ordinary wings."""
        upper_wing = _surface_with_updates(
            component_id="upper_wing",
            role="wing",
            orientation="horizontal",
            symmetric=True,
            span=1.2,
            area=0.12,
            x_le=0.55,
            y_le=0.0,
            z_le=0.35,
            dihedral_deg=0.0,
        )
        right_connector = _surface_with_updates(
            component_id="joined_connector_right",
            role="other",
            orientation="vertical",
            geometry_mode="anchored_le",
            symmetric=False,
            span=0.4,
            area=0.035,
            taper=0.75,
            root_airfoil="naca0010",
            tip_airfoil="naca0010",
            root_anchor=SurfaceAnchorConfig(
                surface_id="main_wing",
                side="right",
                span_fraction=1.0,
                chord_fraction=0.0,
            ),
            tip_anchor=SurfaceAnchorConfig(
                surface_id="upper_wing",
                side="right",
                span_fraction=1.0,
                chord_fraction=0.0,
            ),
        )
        left_connector = _surface_with_updates(
            component_id="joined_connector_left",
            role="other",
            orientation="vertical",
            geometry_mode="anchored_le",
            symmetric=False,
            span=0.4,
            area=0.035,
            taper=0.75,
            root_airfoil="naca0010",
            tip_airfoil="naca0010",
            root_anchor=SurfaceAnchorConfig(
                surface_id="main_wing",
                side="left",
                span_fraction=1.0,
                chord_fraction=0.0,
            ),
            tip_anchor=SurfaceAnchorConfig(
                surface_id="upper_wing",
                side="left",
                span_fraction=1.0,
                chord_fraction=0.0,
            ),
        )
        definition = AircraftDefinition(
            name="Joined Wing",
            lifting_surfaces=[
                default_main_wing_surface(),
                upper_wing,
                right_connector,
                left_connector,
            ],
        )

        round_tripped = AircraftDefinition.from_json(definition.to_json())
        self.assertEqual(round_tripped.to_dict(), definition.to_dict())

        airplane = build_aircraft(round_tripped)
        wing_lookup = {wing.name: wing for wing in airplane.wings}
        self.assertEqual(
            list(wing_lookup),
            ["main_wing", "upper_wing", "joined_connector_right", "joined_connector_left"],
        )
        self.assertGreater(float(wing_lookup["joined_connector_right"].xsecs[0].xyz_le[1]), 0.0)
        self.assertLess(float(wing_lookup["joined_connector_left"].xsecs[0].xyz_le[1]), 0.0)
        self.assertFalse(bool(wing_lookup["joined_connector_right"].symmetric))

    def test_anchored_connectors_reject_unresolved_or_degenerate_anchors(self) -> None:
        """Connector anchors should fail clearly when they cannot produce AVL-safe geometry."""
        unresolved = AircraftDefinition(
            lifting_surfaces=[
                default_main_wing_surface(),
                _surface_with_updates(
                    component_id="bad_connector",
                    role="other",
                    orientation="vertical",
                    geometry_mode="anchored_le",
                    symmetric=False,
                    root_anchor=SurfaceAnchorConfig(surface_id="missing_surface"),
                    tip_anchor=SurfaceAnchorConfig(surface_id="main_wing"),
                ),
            ]
        )
        with self.assertRaisesRegex(ValueError, "has not been built"):
            build_aircraft(unresolved)

        degenerate = AircraftDefinition(
            lifting_surfaces=[
                default_main_wing_surface(),
                _surface_with_updates(
                    component_id="zero_connector",
                    role="other",
                    orientation="vertical",
                    geometry_mode="anchored_le",
                    symmetric=False,
                    root_anchor=SurfaceAnchorConfig(surface_id="main_wing"),
                    tip_anchor=SurfaceAnchorConfig(surface_id="main_wing"),
                ),
            ]
        )
        with self.assertRaisesRegex(ValueError, "coincident"):
            build_aircraft(degenerate)

    def test_collect_component_ids_expands_symmetric_vertical_pairs(self) -> None:
        """Symmetric vertical or canted surfaces should expose mirrored build IDs."""
        definition = AircraftDefinition(
            lifting_surfaces=[
                default_main_wing_surface(),
                _surface_with_updates(
                    component_id="v_tail_surface",
                    role="canted_tail",
                    orientation="vertical",
                    symmetric=True,
                    span=0.32,
                    area=0.05,
                    x_le=0.95,
                    y_le=0.0,
                    z_le=0.02,
                    sweep_le_deg=18.0,
                    dihedral_deg=35.0,
                    root_airfoil="naca0010",
                    tip_airfoil="naca0010",
                ),
            ]
        )

        self.assertEqual(
            collect_component_ids(definition),
            ["main_wing", "v_tail_surface_right", "v_tail_surface_left"],
        )
        airplane = build_aircraft(definition)
        self.assertEqual(
            [wing.name for wing in airplane.wings],
            ["main_wing", "v_tail_surface_right", "v_tail_surface_left"],
        )

    def test_design_variable_records_resolve_component_id_selector_paths(self) -> None:
        """Optimizer-facing records should resolve list-selector paths by component ID."""
        definition = AircraftDefinition()
        records = design_variable_records(definition)
        self.assertGreaterEqual(len(records), 1)
        self.assertEqual(records[0]["path"], "lifting_surfaces[main_wing].span")
        self.assertAlmostEqual(
            float(records[0]["current_value"]),
            definition.main_wing_surface().span,
        )

    def test_render_helpers_honor_metric_and_imperial_units(self) -> None:
        """Render helpers should scale Plotly coordinates and relabel orthographic three-view axes."""
        definition = AircraftDefinition()

        metric_figure = render_aircraft_plotly(definition, unit_system="metric")
        imperial_figure = render_aircraft_plotly(definition, unit_system="imperial")

        self.assertEqual(metric_figure.layout.scene.xaxis.title.text, "x (m)")
        self.assertEqual(imperial_figure.layout.scene.xaxis.title.text, "x (ft)")
        self.assertAlmostEqual(
            _max_trace_coordinate(imperial_figure),
            _max_trace_coordinate(metric_figure) * 3.280839895013123,
            places=6,
        )

        axs = aircraft_rendering._build_three_view_axes(definition, unit_system="imperial")
        first_axis = axs.flat[0]
        self.assertEqual(first_axis.name, "rectilinear")
        self.assertIn("(ft)", first_axis.get_xlabel())
        self.assertIn("(ft)", first_axis.get_ylabel())
        self.assertEqual(first_axis.xaxis.get_major_formatter()(1.0, 0), "3.28")
        self.assertEqual(tuple(round(value, 4) for value in first_axis.get_facecolor()), (1.0, 1.0, 1.0, 1.0))
        self.assertEqual(tuple(round(value, 9) for value in axs[0, 0].get_xlim()), tuple(round(value, 9) for value in axs[1, 0].get_xlim()))
        self.assertEqual(tuple(round(value, 9) for value in axs[0, 0].get_ylim()), tuple(round(value, 9) for value in axs[0, 1].get_ylim()))
        self.assertEqual(tuple(round(value, 9) for value in axs[0, 1].get_xlim()), tuple(round(value, 9) for value in axs[1, 0].get_ylim()))
        self.assertAlmostEqual(axs[0, 0].get_xlim()[1] - axs[0, 0].get_xlim()[0], axs[0, 0].get_ylim()[1] - axs[0, 0].get_ylim()[0])
        self.assertAlmostEqual(axs[0, 0].get_xlim()[1] - axs[0, 0].get_xlim()[0], axs[0, 1].get_xlim()[1] - axs[0, 1].get_xlim()[0])
        self.assertAlmostEqual(axs[0, 0].get_xlim()[1] - axs[0, 0].get_xlim()[0], axs[1, 0].get_ylim()[1] - axs[1, 0].get_ylim()[0])
        self.assertEqual(axs[1, 1].name, "3d")
        self.assertFalse(bool(axs[1, 1].axison))

        image_payload = render_aircraft_three_view_image(definition, unit_system="imperial")
        self.assertTrue(image_payload.startswith("data:image/png;base64,"))
        first_axis.figure.clf()

    def test_rendering_module_forces_agg_backend(self) -> None:
        """Rendering helpers should configure Matplotlib to use the Agg backend."""
        self.assertEqual(str(matplotlib.get_backend()).lower(), "agg")

    def test_package_metadata_exists_for_installation(self) -> None:
        """The repository should expose packaging metadata for later pip install."""
        repo_root = Path(__file__).resolve().parents[1]
        self.assertTrue((repo_root / "pyproject.toml").exists())


if __name__ == "__main__":
    unittest.main()
