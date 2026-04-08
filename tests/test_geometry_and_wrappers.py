"""Import tests for the active geometry package layout."""

import unittest


class GeometryModuleTests(unittest.TestCase):
    """Ensure the active geometry modules remain importable when dependencies exist."""

    def test_geometry_modules_import_if_aerosandbox_is_available(self) -> None:
        try:
            import aerosandbox  # noqa: F401
        except ModuleNotFoundError:
            self.skipTest("AeroSandbox is not installed in this environment.")

        try:
            from ac_design_toolbox.geometry import PlanformSolve, patched_AVL, simple_aircraft
            from ac_design_toolbox.geometry.aircraft import simple_aircraft as direct_simple_aircraft
            from ac_design_toolbox.geometry.avl_patch import patched_AVL as direct_patched_avl
            from ac_design_toolbox.geometry.surfaces import make_ht, make_vt, make_wing
        except ModuleNotFoundError as exc:
            self.skipTest(f"Geometry dependencies are not installed: {exc}")

        self.assertIsNotNone(simple_aircraft)
        self.assertIs(simple_aircraft, direct_simple_aircraft)
        self.assertIs(patched_AVL, direct_patched_avl)
        self.assertIsNotNone(PlanformSolve)
        self.assertIsNotNone(make_wing)
        self.assertIsNotNone(make_ht)
        self.assertIsNotNone(make_vt)


if __name__ == "__main__":
    unittest.main()
