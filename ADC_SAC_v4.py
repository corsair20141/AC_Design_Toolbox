#ADC STANDARD ATMOSPHERE CALCULATOR v2
#Original Author: Benjamin Jackson (< 2021)
#Revision 2: Colton Campbell (2021-02-03)
#Revision 3: Colton Campbell (2024-01-04)
#Revision 4: Colton Campbell (2025-01-30)
#Revision 4.2: Colton Campbell (2025-10-09) - Added ability to specify temperature shift from standard atmosphere


################################################################################
#Documentation:

#Inputs:
#(alt) == Altitude in feet or in meters
#(SI_Imp) == Text input; select 'imp' or 'si' to select standard units

#Outputs:
#(t_alt) == Temperature at altitude
#(p_alt) == Pressure at altitude
#(rho_alt) == Atmospheric density at altitude
#(a_alt) == Speed of sound at altitude
#(u_alt) == Dynamic viscocity at altitude (mew)
################################################################################


import numpy as np

def SAC(altitude, SI_Imp, temp_shift_F: float = 0.0):
    """
    Standard Atmosphere with an optional uniform temperature deviation (°F).
    Positive = warmer-than-ISA, Negative = colder-than-ISA.
    """

    # Convert to SI if needed
    if SI_Imp.lower() == "imp":
        if isinstance(altitude, (list, np.ndarray)):
            altitude = [alt * 0.3048 for alt in altitude]  # ft -> m
        else:
            altitude = altitude * 0.3048

    # ---- Constants
    g_0 = 9.807       # m/s^2
    R = 287.05        # J/(kg*K)
    gamma = 1.4
    S = 110.4         # K, Sutherland
    beta = 1.458e-6   # kg/(s*m*sqrt(K))

    # Sea Level reference pressure (kept fixed)
    p_sl = 101325.0   # Pa

    # Temperature deviation (°F -> K) as a difference (no offset):
    dT_K = temp_shift_F * (5.0 / 9.0)

    # ---- ISA Base Temperatures (shifted by dT_K)
    t_sl    = 288.16 + dT_K   # K
    t11_25  = 216.66 + dT_K   # K
    t47_53  = 282.66 + dT_K   # K
    t79_90  = 165.66 + dT_K   # K
    t_105   = 225.66 + dT_K   # K  # (not used explicitly below, kept for completeness)

    # Lapse rates (unchanged)
    a_1 = -0.0065   # K/m, 0–11 km
    a_2 =  0.003    # K/m, 25–47 km
    a_3 = -0.0045   # K/m, 53–79 km
    a_4 =  0.004    # K/m, 90–105 km

    # With shifted sea-level temperature, recompute sea-level density
    rho_sl = p_sl / (R * t_sl)

    # ---- Corner pressures/densities with shifted temps
    # 0–11 km (gradient) end:
    p_11  = p_sl  * (t11_25 / t_sl   ) ** (-g_0 / (a_1 * R))
    rho_11 = rho_sl * (t11_25 / t_sl ) ** (-(g_0 / (a_1 * R) + 1))

    # 11–25 km (isotherm) end:
    p_25  = p_11 * np.exp(-g_0 / (R * t11_25) * (25000 - 11000))
    rho_25 = rho_11 * p_25 / p_11

    # 25–47 km (gradient) end:
    p_47  = p_25 * (t47_53 / t11_25 ) ** (-g_0 / (a_2 * R))
    rho_47 = rho_25 * (t47_53 / t11_25) ** (-(g_0 / (a_2 * R) + 1))

    # 47–53 km (isotherm) end:
    p_53  = p_47 * np.exp(-g_0 / (R * t47_53) * (53000 - 47000))
    rho_53 = rho_47 * p_53 / p_47

    # 53–79 km (gradient) end:
    p_79  = p_53 * (t79_90 / t47_53 ) ** (-g_0 / (a_3 * R))
    rho_79 = rho_53 * (t79_90 / t47_53) ** (-(g_0 / (a_3 * R) + 1))

    # 79–90 km (isotherm) end:
    p_90  = p_79 * np.exp(-g_0 / (R * t79_90) * (90000 - 79000))
    rho_90 = rho_79 * p_90 / p_79

    def calculate_conditions(alt):
        # Temperature / Pressure / Density by layer with shifted temperatures
        if alt <= 11000:  # 0–11 km, gradient
            t_alt = t_sl + a_1 * alt
            p_alt = p_sl * (t_alt / t_sl) ** (-g_0 / (a_1 * R))
            rho_alt = rho_sl * (t_alt / t_sl) ** (-(g_0 / (a_1 * R) + 1))

        elif alt <= 25000:  # 11–25 km, isotherm
            t_alt = t11_25
            p_alt = p_11 * np.exp(-g_0 / (R * t11_25) * (alt - 11000))
            rho_alt = rho_11 * p_alt / p_11

        elif alt <= 47000:  # 25–47 km, gradient
            t_alt = t11_25 + a_2 * (alt - 25000)
            p_alt = p_25 * (t_alt / t11_25) ** (-g_0 / (a_2 * R))
            rho_alt = rho_25 * (t_alt / t11_25) ** (-(g_0 / (a_2 * R) + 1))

        elif alt <= 53000:  # 47–53 km, isotherm
            t_alt = t47_53
            p_alt = p_47 * np.exp(-g_0 / (R * t47_53) * (alt - 47000))
            rho_alt = rho_47 * p_alt / p_47

        elif alt <= 79000:  # 53–79 km, gradient
            t_alt = t47_53 + a_3 * (alt - 53000)
            p_alt = p_53 * (t_alt / t47_53) ** (-g_0 / (a_3 * R))
            rho_alt = rho_53 * (t_alt / t47_53) ** (-(g_0 / (a_3 * R) + 1))

        elif alt <= 90000:  # 79–90 km, isotherm
            t_alt = t79_90
            p_alt = p_79 * np.exp(-g_0 / (R * t79_90) * (alt - 79000))
            rho_alt = rho_79 * p_alt / p_79

        elif alt <= 105000:  # 90–105 km, gradient
            t_alt = t79_90 + a_4 * (alt - 90000)
            # Base should be 90 km (fix from p_53 -> p_90)
            p_alt = p_90 * (t_alt / t79_90) ** (-g_0 / (a_4 * R))
            rho_alt = rho_90 * (t_alt / t79_90) ** (-(g_0 / (a_4 * R) + 1))
        else:
            # Outside model bounds; clamp to 105 km gradient extrapolation
            t_alt = t79_90 + a_4 * (105000 - 90000)
            p_alt = p_90 * (t_alt / t79_90) ** (-g_0 / (a_4 * R))
            rho_alt = rho_90 * (t_alt / t79_90) ** (-(g_0 / (a_4 * R) + 1))

        # Speed of sound
        a_alt = np.sqrt(gamma * R * t_alt)
        # Dynamic viscosity (Sutherland)
        u_alt = beta * (t_alt ** 1.5) / (t_alt + S)

        # Convert to Imperial if requested
        if SI_Imp.lower() == "imp":
            t_alt = t_alt * 1.8                       # K -> °R
            p_alt = p_alt * 0.020885434273039         # Pa -> psf
            rho_alt = rho_alt * 0.0019403203          # kg/m^3 -> slug/ft^3
            a_alt = a_alt * 3.28084                   # m/s -> ft/s
            u_alt = u_alt * 0.020885401145657425      # N*s/m^2 -> lb*s/ft^2

        return {"T": t_alt, "P": p_alt, "rho": rho_alt, "a": a_alt, "u": u_alt}

    if isinstance(altitude, (list, np.ndarray)):
        return [calculate_conditions(alt) for alt in altitude]
    else:
        return calculate_conditions(altitude)