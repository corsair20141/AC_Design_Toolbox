"""Focused regression tests for the atmosphere API."""

import unittest

from ac_design_toolbox.atmosphere import SAC, mach_number, reynolds_number, standard_atmosphere


class AtmosphereApiTests(unittest.TestCase):
    """Validate atmosphere helpers and equivalent aliases."""

    def test_standard_atmosphere_returns_equivalent_viscosity_aliases(self) -> None:
        state = standard_atmosphere(altitude=0.0, units="si")

        self.assertIn("rho", state)
        self.assertIn("u", state)
        self.assertIn("mu", state)
        self.assertAlmostEqual(state["u"], state["mu"])

    def test_sac_alias_matches_standard_atmosphere(self) -> None:
        state_direct = standard_atmosphere(altitude=1000.0, units="si", temp_shift_F=5.0)
        state_alias = SAC(altitude=1000.0, SI_Imp="si", temp_shift_F=5.0)

        self.assertAlmostEqual(state_direct["rho"], state_alias["rho"])
        self.assertAlmostEqual(state_direct["a"], state_alias["a"])

    def test_reynolds_and_mach_helpers_produce_positive_values(self) -> None:
        reynolds_value = reynolds_number(altitude=0.0, velocity=30.0, mean_aerodynamic_chord=0.4, units="si")
        mach_value = mach_number(altitude=0.0, velocity=30.0, units="si")

        self.assertGreater(reynolds_value, 0.0)
        self.assertGreater(mach_value, 0.0)


if __name__ == "__main__":
    unittest.main()
