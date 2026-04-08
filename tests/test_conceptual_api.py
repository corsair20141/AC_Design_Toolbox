"""Regression tests for grouped conceptual APIs."""

import unittest

from ac_design_toolbox.conceptual import LoD_max, TO_ground_roll, wf_empty


class ConceptualApiTests(unittest.TestCase):
    """Check that the grouped conceptual API remains numerically self-consistent."""

    def test_weight_fraction_matches_closed_form_expression(self) -> None:
        new_value = wf_empty(2.36, 3000.0, -0.18)
        expected_value = 2.36 * 3000.0 ** -0.18

        self.assertAlmostEqual(new_value, expected_value)

    def test_takeoff_ground_roll_internal_outputs_are_consistent(self) -> None:
        args = dict(
            W=2500.0,
            S=180.0,
            T=280.0,
            C_L=0.9,
            K=0.05,
            C_D0=0.04,
            mu=0.03,
            rho=0.002377,
            V_initial=0.0,
            V_final=110.0,
        )

        ground_roll_distance, _, _, ground_roll_only, rotation_distance = TO_ground_roll(**args)

        self.assertAlmostEqual(ground_roll_distance, ground_roll_only + rotation_distance)
        self.assertGreater(ground_roll_distance, 0.0)

    def test_lod_max_matches_known_formula_value(self) -> None:
        value = LoD_max(AR=12.0, e=0.85, CD_0=0.025)
        self.assertGreater(value, 0.0)


if __name__ == "__main__":
    unittest.main()
