"""Weight-fraction and first-pass sizing helpers."""

import numpy as np


def wf_empty(A, W_0, C):
    """Estimate empty-weight fraction using Raymer's empirical coefficients."""
    return A * W_0**C


def wf_TO():
    """Return the standard Raymer takeoff weight fraction."""
    return 0.97


def wf_climb():
    """Return the standard Raymer climb weight fraction."""
    return 0.985


def wf_landing():
    """Return the standard Raymer landing weight fraction."""
    return 0.995


def wf_cruise_segment(distance, sfc, velocity, LoD):
    """Estimate cruise-segment weight fraction using the Breguet form."""
    return np.exp(-distance * sfc / (velocity * LoD))


def sfc_prop_estimate(eta_prop, velocity, C_bhp):
    """Convert propeller brake-specific fuel consumption to equivalent jet SFC."""
    return (C_bhp * velocity / (550 * eta_prop)) / 3600


def wf_fuel(reserve, Wx_W0):
    """Compute total fuel fraction including reserve allowance."""
    return (1 + reserve) * (1 - Wx_W0)


def calc_weight_TO(W0_guess, weight_payload, Wfuel_W0, We_W0, A_wf_empty, C_wf_empty, iterations_max, print_select):
    """Iteratively solve for takeoff gross weight from payload and fractions."""
    iteration = 0
    while True:
        W0_calculated_1 = weight_payload / (1 - Wfuel_W0 - We_W0)
        W0_guess = W0_calculated_1
        We_W0 = wf_empty(A_wf_empty, W0_guess, C_wf_empty)

        W0_calculated_2 = weight_payload / (1 - Wfuel_W0 - We_W0)
        W0_guess = W0_calculated_2
        We_W0 = wf_empty(A_wf_empty, W0_guess, C_wf_empty)

        iteration += 1
        delta = abs(W0_calculated_2 - W0_calculated_1)

        if delta < 10:
            if print_select:
                print(
                    f"\nEmpty weight iterative loop closed after {iteration} iterations.\n"
                    f"W0 = {W0_calculated_2:.0f}lb, delta = {delta:.0f}lb\n"
                )
            break
        if iteration >= iterations_max:
            if print_select:
                print(f"\nMAX ITERATIONS {iterations_max} reached!!! delta = {delta:.0f}lb\n")
            break

    return W0_calculated_2, We_W0, delta

__all__ = [
    "calc_weight_TO",
    "sfc_prop_estimate",
    "wf_TO",
    "wf_climb",
    "wf_cruise_segment",
    "wf_empty",
    "wf_fuel",
    "wf_landing",
]
