"""Takeoff-analysis helpers from the Level 1 conceptual toolbox."""

import numpy as np


def TO_ground_roll(W, S, T, C_L, K, C_D0, mu, rho, V_initial, V_final):
    """Estimate ground-roll distance to takeoff rotation using Raymer's method.

    All inputs are assumed to use English units. The function returns the total
    ground-roll distance along with the intermediate constants used in the
    Raymer formulation.
    """
    g = 32.175

    K_T = (T / W) - mu
    K_A = (rho / (2 * (W / S))) * (mu * C_L - C_D0 - K * C_L**2)

    S_G = (1 / (2 * g * K_A)) * np.log((K_T + K_A * V_final**2) / (K_T + K_A * V_initial**2))
    S_R = 3 * V_final
    ground_roll_distance = S_G + S_R

    return ground_roll_distance, K_T, K_A, S_G, S_R


def TO_transition(W, T, LoD, V_stall, h_obstacle):
    """Estimate the takeoff transition distance and height during rotation.

    The implementation follows Raymer's transition-phase approximation and
    assumes English units throughout.
    """
    g = 32.175
    V_TR = 1.15 * V_stall

    R = V_TR**2 / (0.2 * g)
    gamma_climb = np.arcsin((T / W) - 1 / LoD)
    h_TR = R * (1 - np.cos(gamma_climb))

    if h_TR > h_obstacle:
        S_TR = np.sqrt(R**2 - (R - h_obstacle) ** 2)
    else:
        S_TR = R * np.sin(gamma_climb)

    return S_TR, h_TR


def TO_climb_obstacle(gamma_climb, h_TR, h_obstacle):
    """Compute climb distance required to clear an obstacle after transition."""
    return (h_obstacle - h_TR) / np.tan(np.radians(gamma_climb))


def climb_angle(T_climb, D_climb, W_climb):
    """Compute climb angle in degrees from thrust, drag, and aircraft weight."""
    return np.degrees(np.arcsin((T_climb - D_climb) / W_climb))


def simple_TO_prop(S_ref, CL_to, W_to, bhp, rho):
    """Estimate propeller-aircraft takeoff distance using the Raymer TOP method."""
    rho_SL = 0.002377
    TOP = (W_to**2) / (S_ref * (rho / rho_SL) * CL_to * bhp)
    return TOP * 10

__all__ = [
    "TO_climb_obstacle",
    "TO_ground_roll",
    "TO_transition",
    "climb_angle",
    "simple_TO_prop",
]
