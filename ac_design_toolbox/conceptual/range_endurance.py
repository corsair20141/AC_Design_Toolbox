"""Range and endurance relations for fuel and electric aircraft."""

import numpy as np


def breguet_range_jet(V, LoD, C, Wi, Wf):
    """Compute jet range from the Breguet range equation."""
    return (V / C) * LoD * np.log(Wi / Wf)


def breguet_range_prop(eta_P, LoD, C_bhp, Wi, Wf):
    """Compute propeller-aircraft range from the Breguet range equation."""
    return (550 * eta_P / C_bhp) * LoD * np.log(Wi / Wf)


def endurance_electric(E_b, P_other, eta_sys, eta_p, W, V, LoD):
    """Estimate electric endurance and propulsion power for steady flight."""
    P_motor = (W / LoD) * V / eta_p
    P_used = P_motor + P_other
    E = E_b * eta_sys / P_used
    return E, P_motor


def breguet_range_electric(E_b, P_other, eta_sys, eta_p, W, V, LoD):
    """Estimate electric-aircraft range from endurance and cruise speed."""
    E, P_motor = endurance_electric(E_b, P_other, eta_sys, eta_p, W, V, LoD)
    R = E * V * 3600 / 1000
    return R, P_motor


def fuel_burn_fixed_range_jet(Wi, R, V, LoD, C):
    """Estimate jet fuel burn required to cover a fixed range."""
    Wf = Wi / np.exp(R / ((V / C) * LoD))
    return Wi - Wf

__all__ = [
    "breguet_range_electric",
    "breguet_range_jet",
    "breguet_range_prop",
    "endurance_electric",
    "fuel_burn_fixed_range_jet",
]
