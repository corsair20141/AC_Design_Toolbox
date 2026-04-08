"""Atmospheric property helpers and package-level aliases."""

from __future__ import annotations

from typing import Any

import numpy as np


def _normalize_property_keys(result: Any) -> Any:
    """Normalize viscosity key names across the package API."""
    if isinstance(result, list):
        return [_normalize_property_keys(item) for item in result]

    if isinstance(result, dict):
        normalized = dict(result)
        if "u" in normalized and "mu" not in normalized:
            normalized["mu"] = normalized["u"]
        if "mu" in normalized and "u" not in normalized:
            normalized["u"] = normalized["mu"]
        return normalized

    return result


def standard_atmosphere(altitude, units: str = "si", temp_shift_F: float = 0.0):
    """Return standard-atmosphere properties with an optional temperature shift.

    Parameters
    ----------
    altitude
        Altitude in meters for SI mode or feet for Imperial mode. Lists and
        arrays are forwarded to the underlying calculator unchanged.
    units : str, optional
        Unit system selector. Use ``"si"`` or ``"imp"``.
    temp_shift_F : float, optional
        Uniform temperature deviation from ISA, expressed in degrees Fahrenheit.

    Returns
    -------
    dict or list[dict]
        Atmospheric properties containing temperature, pressure, density, speed
        of sound, and dynamic viscosity. Both ``"u"`` and ``"mu"`` keys are
        supplied as equivalent viscosity labels.
    """
    if units.lower() == "imp":
        if isinstance(altitude, (list, np.ndarray)):
            altitude = [alt * 0.3048 for alt in altitude]
        else:
            altitude = altitude * 0.3048

    g_0 = 9.807
    gas_constant = 287.05
    gamma = 1.4
    sutherland_constant = 110.4
    beta = 1.458e-6

    p_sl = 101325.0
    dT_K = temp_shift_F * (5.0 / 9.0)

    t_sl = 288.16 + dT_K
    t11_25 = 216.66 + dT_K
    t47_53 = 282.66 + dT_K
    t79_90 = 165.66 + dT_K

    a_1 = -0.0065
    a_2 = 0.003
    a_3 = -0.0045
    a_4 = 0.004

    rho_sl = p_sl / (gas_constant * t_sl)

    p_11 = p_sl * (t11_25 / t_sl) ** (-g_0 / (a_1 * gas_constant))
    rho_11 = rho_sl * (t11_25 / t_sl) ** (-(g_0 / (a_1 * gas_constant) + 1))

    p_25 = p_11 * np.exp(-g_0 / (gas_constant * t11_25) * (25000 - 11000))
    rho_25 = rho_11 * p_25 / p_11

    p_47 = p_25 * (t47_53 / t11_25) ** (-g_0 / (a_2 * gas_constant))
    rho_47 = rho_25 * (t47_53 / t11_25) ** (-(g_0 / (a_2 * gas_constant) + 1))

    p_53 = p_47 * np.exp(-g_0 / (gas_constant * t47_53) * (53000 - 47000))
    rho_53 = rho_47 * p_53 / p_47

    p_79 = p_53 * (t79_90 / t47_53) ** (-g_0 / (a_3 * gas_constant))
    rho_79 = rho_53 * (t79_90 / t47_53) ** (-(g_0 / (a_3 * gas_constant) + 1))

    p_90 = p_79 * np.exp(-g_0 / (gas_constant * t79_90) * (90000 - 79000))
    rho_90 = rho_79 * p_90 / p_79

    def calculate_conditions(alt):
        if alt <= 11000:
            t_alt = t_sl + a_1 * alt
            p_alt = p_sl * (t_alt / t_sl) ** (-g_0 / (a_1 * gas_constant))
            rho_alt = rho_sl * (t_alt / t_sl) ** (-(g_0 / (a_1 * gas_constant) + 1))
        elif alt <= 25000:
            t_alt = t11_25
            p_alt = p_11 * np.exp(-g_0 / (gas_constant * t11_25) * (alt - 11000))
            rho_alt = rho_11 * p_alt / p_11
        elif alt <= 47000:
            t_alt = t11_25 + a_2 * (alt - 25000)
            p_alt = p_25 * (t_alt / t11_25) ** (-g_0 / (a_2 * gas_constant))
            rho_alt = rho_25 * (t_alt / t11_25) ** (-(g_0 / (a_2 * gas_constant) + 1))
        elif alt <= 53000:
            t_alt = t47_53
            p_alt = p_47 * np.exp(-g_0 / (gas_constant * t47_53) * (alt - 47000))
            rho_alt = rho_47 * p_alt / p_47
        elif alt <= 79000:
            t_alt = t47_53 + a_3 * (alt - 53000)
            p_alt = p_53 * (t_alt / t47_53) ** (-g_0 / (a_3 * gas_constant))
            rho_alt = rho_53 * (t_alt / t47_53) ** (-(g_0 / (a_3 * gas_constant) + 1))
        elif alt <= 90000:
            t_alt = t79_90
            p_alt = p_79 * np.exp(-g_0 / (gas_constant * t79_90) * (alt - 79000))
            rho_alt = rho_79 * p_alt / p_79
        else:
            capped_alt = min(float(alt), 105000.0)
            t_alt = t79_90 + a_4 * (capped_alt - 90000)
            p_alt = p_90 * (t_alt / t79_90) ** (-g_0 / (a_4 * gas_constant))
            rho_alt = rho_90 * (t_alt / t79_90) ** (-(g_0 / (a_4 * gas_constant) + 1))

        a_alt = np.sqrt(gamma * gas_constant * t_alt)
        u_alt = beta * (t_alt**1.5) / (t_alt + sutherland_constant)

        if units.lower() == "imp":
            t_alt = t_alt * 1.8
            p_alt = p_alt * 0.020885434273039
            rho_alt = rho_alt * 0.0019403203
            a_alt = a_alt * 3.28084
            u_alt = u_alt * 0.020885401145657425

        return {"T": t_alt, "P": p_alt, "rho": rho_alt, "a": a_alt, "u": u_alt}

    if isinstance(altitude, (list, np.ndarray)):
        result = [calculate_conditions(alt) for alt in altitude]
    else:
        result = calculate_conditions(altitude)

    return _normalize_property_keys(result)


def SAC(altitude, SI_Imp, temp_shift_F: float = 0.0):
    """Alias for :func:`standard_atmosphere` that keeps the short historical name."""
    return standard_atmosphere(altitude=altitude, units=SI_Imp, temp_shift_F=temp_shift_F)


def reynolds_number(
    altitude: float,
    velocity: float,
    mean_aerodynamic_chord: float,
    units: str = "si",
    temp_shift_F: float = 0.0,
) -> float:
    """Compute Reynolds number from atmospheric state and mean aerodynamic chord."""
    properties = standard_atmosphere(altitude=altitude, units=units, temp_shift_F=temp_shift_F)
    if isinstance(properties, list):
        raise TypeError("reynolds_number expects a scalar altitude, not a list or array.")

    return float(mean_aerodynamic_chord) * float(velocity) * float(properties["rho"]) / float(properties["u"])


def reynolds(alt, V, MAC, SI_Imp, temp_shift_F: float = 0.0) -> float:
    """Alias wrapper around :func:`reynolds_number`."""
    return reynolds_number(
        altitude=alt,
        velocity=V,
        mean_aerodynamic_chord=MAC,
        units=SI_Imp,
        temp_shift_F=temp_shift_F,
    )


def mach_number(altitude: float, velocity: float, units: str = "si", temp_shift_F: float = 0.0) -> float:
    """Compute Mach number from atmospheric properties and freestream velocity."""
    properties = standard_atmosphere(altitude=altitude, units=units, temp_shift_F=temp_shift_F)
    if isinstance(properties, list):
        raise TypeError("mach_number expects a scalar altitude, not a list or array.")

    return float(velocity) / float(properties["a"])


def mach(alt, V, SI_Imp, temp_shift_F: float = 0.0) -> float:
    """Alias wrapper around :func:`mach_number`."""
    return mach_number(altitude=alt, velocity=V, units=SI_Imp, temp_shift_F=temp_shift_F)


__all__ = [
    "SAC",
    "mach",
    "mach_number",
    "reynolds",
    "reynolds_number",
    "standard_atmosphere",
]
