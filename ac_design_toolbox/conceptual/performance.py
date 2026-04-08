"""Aerodynamic and propulsion performance approximations."""

import numpy as np
from scipy.optimize import fsolve


def LoD_max_est(K_LD, AR, Sw_Sref):
    """Estimate maximum lift-to-drag ratio from wetted-area scaling."""
    return K_LD * np.sqrt(AR / Sw_Sref)


def LoD_cruise_est(LoD_maximum, ac_type):
    """Estimate cruise lift-to-drag ratio from the maximum lift-to-drag ratio."""
    if ac_type == "jet":
        return 0.866 * LoD_maximum
    if ac_type == "prop":
        return LoD_maximum
    raise ValueError("ac_type must be 'jet' or 'prop'.")


def oswald_efficiency(AR, LE_sweep):
    """Estimate Oswald efficiency factor using Raymer's approximation."""
    if LE_sweep == 0:
        return 1.78 * (1 - 0.045 * AR**0.68) - 0.64
    if LE_sweep > 30:
        return 4.61 * (1 - 0.045 * AR**0.68) * (np.cos(np.radians(LE_sweep))) ** 0.15 - 3.1

    e1 = 1.78 * (1 - 0.045 * AR**0.68) - 0.64
    e2 = 4.61 * (1 - 0.045 * AR**0.68) * (np.cos(np.radians(LE_sweep))) ** 0.15 - 3.1
    return (LE_sweep / 30) * e2 + (1 - LE_sweep / 30) * e1


def CD_i_oswald(CL, AR, e):
    """Compute induced drag coefficient using Oswald efficiency."""
    K = 1 / (np.pi * AR * e)
    return K * CL**2


def classify_AR(AR, taper_ratio, LE_sweep):
    """Classify a wing as low- or high-aspect-ratio using Raymer's criterion."""
    lam = taper_ratio
    Lam_LE = LE_sweep

    if lam == 0:
        c1 = 0
    elif lam <= 0.23:
        c1 = (0.5 / 0.23) * lam
    else:
        c1 = (-0.5 / 1.0) * lam + 0.5

    test_value = 3 / ((c1 + 1) * np.cos(np.radians(Lam_LE)))
    AR_classification = "low" if AR <= test_value else "high"
    return test_value, AR_classification


def LoD_max(AR, e, CD_0):
    """Calculate maximum lift-to-drag ratio from a parabolic drag polar."""
    CD_min = 2 * CD_0
    K = 1 / (np.pi * AR * e)
    CL_min_drag = np.sqrt(CD_0 / K)
    return CL_min_drag / CD_min


def velocity_min_drag(W, S_ref, rho, CD_0, AR, e):
    """Compute airspeed for minimum drag and maximum lift-to-drag ratio."""
    K = 1 / (np.pi * AR * e)
    return np.sqrt((2 * W / (rho * S_ref)) * np.sqrt(K / CD_0))


def LoD_max_range_prop(AR, e, CD_0):
    """Return the propeller-aircraft lift-to-drag ratio for maximum range."""
    return LoD_max(AR, e, CD_0)


def velocity_min_power(W, S_ref, rho, CD_0, AR, e):
    """Compute airspeed for minimum power required in steady level flight."""
    K = 1 / (np.pi * AR * e)
    return np.sqrt(2 * W / (rho * S_ref) * np.sqrt(K / (3 * CD_0)))


def LoD_min_power(AR, e, CD_0):
    """Compute the lift-to-drag ratio corresponding to minimum power required."""
    K = 1 / (np.pi * AR * e)
    CL_min_power = np.sqrt(3 * CD_0 / K)
    CD_min_power = 4 * CD_0
    return CL_min_power / CD_min_power


def LoD_max_endurance_prop(AR, e, CD_0):
    """Return the propeller-aircraft lift-to-drag ratio for maximum endurance."""
    return LoD_min_power(AR, e, CD_0)


def velocity_max_range_prop(W, S_ref, rho, CD_0, AR, e):
    """Compute propeller-aircraft airspeed for maximum range."""
    return velocity_min_drag(W, S_ref, rho, CD_0, AR, e)


def velocity_max_endurance_prop(W, S_ref, rho, CD_0, AR, e):
    """Compute propeller-aircraft airspeed for maximum endurance."""
    return velocity_min_power(W, S_ref, rho, CD_0, AR, e)


def W_S_max_range_prop(AR, e, CD_0, rho, V):
    """Compute wing loading corresponding to maximum range for prop aircraft."""
    q = 0.5 * rho * V**2
    return q * np.sqrt(np.pi * AR * e * CD_0)


def W_S_max_endurance_prop(AR, e, CD_0, rho, V):
    """Compute wing loading corresponding to maximum endurance for prop aircraft."""
    q = 0.5 * rho * V**2
    return q * np.sqrt(3 * np.pi * AR * e * CD_0)


def flat_plate_skinfriction_equivalent_turbulent(Re):
    """Estimate turbulent equivalent flat-plate skin friction coefficient."""
    return 0.455 / (np.log10(Re) ** 2.58)


def prop_thrust_dynamic(eta_p, bhp, V):
    """Estimate propeller thrust from shaft power and freestream speed."""
    return 550 * bhp * eta_p / V


def flight_velocity_from_prop(weight, T_a, S_ref, CD_0, K, rho):
    """Solve the analytic thrust-balance speed estimate used in the legacy tool."""
    Ta_W = T_a / weight
    W_S = weight / S_ref
    return np.sqrt((Ta_W * W_S + W_S * np.sqrt(Ta_W**2 - 4 * CD_0 * K)) / (rho * CD_0))


def max_velocity_prop(W, P_max, eta_p, S_ref, AR, e, CD_0, rho_inf):
    """Solve for maximum propeller-aircraft speed from power-thrust balance."""
    initial_guess = [10.0]

    def residual(V):
        T_max = prop_thrust_dynamic(eta_p, P_max, V)

        K = 1 / (np.pi * AR * e)
        CL = 2 * W / (rho_inf * S_ref * V**2)
        CD_i = K * CL**2
        CD = CD_0 + CD_i
        D = 0.5 * rho_inf * V**2 * S_ref * CD

        return T_max - D

    V_max = fsolve(residual, initial_guess)[0]

    K = 1 / (np.pi * AR * e)
    CL = 2 * W / (rho_inf * S_ref * V_max**2)
    CD_i = K * CL**2
    CD = CD_0 + CD_i
    LoD = CL / CD
    return V_max, LoD

__all__ = [
    "CD_i_oswald",
    "LoD_cruise_est",
    "LoD_max",
    "LoD_max_endurance_prop",
    "LoD_max_est",
    "LoD_max_range_prop",
    "LoD_min_power",
    "W_S_max_endurance_prop",
    "W_S_max_range_prop",
    "classify_AR",
    "flat_plate_skinfriction_equivalent_turbulent",
    "flight_velocity_from_prop",
    "max_velocity_prop",
    "oswald_efficiency",
    "prop_thrust_dynamic",
    "velocity_max_endurance_prop",
    "velocity_max_range_prop",
    "velocity_min_drag",
    "velocity_min_power",
]
