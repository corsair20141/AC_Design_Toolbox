# -*- coding: utf-8 -*-
"""
Created on Sun Feb 26 22:20:24 2023

@author: corsa
"""
import warnings
import numpy as np
from scipy.interpolate import interp1d
from scipy.optimize import fsolve
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter



# ---- Takeoff Equations ----
def TO_ground_roll(W,S,T,C_L,K,C_D0,mu,rho,V_initial,V_final):
    """
    Accelerate from 0 (or V_initial) to takeoff speed (1.1*V_stall) and rotate.
    
    ASSUMES ENGLISH UNITS (g=32.175 ft/s^2)
    INPUTS:
        W = weight (lb)
        S = wing ref area (ft^2)
        T = thrust (lb)
        C_L = lift coefficient at ground roll orientation
        K = drag due to lift factor
        C_D0 = parasitic drag coefficient in takeoff configuration
        mu = rolling friction (see table 17.1)
        rho = density (slugs/ft^3)
        V_initial = starting velocity (ft/s)
        V_final = takeoff velocity, typically 1.1*V_stall  (ft/s)
        
    OUTPUTS:
        ground_roll_distance = total distance for ground roll phase (ft)
        
    Equation 17.102, 17.103, 17.104 from Raymer (6th ed)
    """
    
    # ADD AVERAGED THRUST CALCS BASED ON JET OR PROP, pg. 673
    
    g = 32.175      # gravity (ft/s^2)
    
    K_T = (T/W) - mu    # 17.103
    K_A = (rho/(2*(W/S)))*(mu*C_L - C_D0 - K*C_L**2)  #17.104
    
    S_G = (1/(2*g*K_A))*np.log((K_T + K_A*V_final**2)/(K_T + K_A*V_initial**2)) #17.102
    
    S_R = 3*V_final     # rotation distance is 3s*Vf approx, pg. 673
    
    ground_roll_distance = S_G + S_R # (ft)
    
    return ground_roll_distance, K_T, K_A, S_G, S_R


def TO_transition(W,T,LoD,V_stall,h_obstacle):
    """
    Accelerate from Takeoff speed (1.1*V_stall) to Climb speed (1.2*V_stall) and 
    rotate to climb angle.
    
    ASSUMES CL_avg = 0.9*CL_max
    ASSUMES V_transition_avg = 1.15*V_stall
    ASSUMES ENGLISH UNITS (g=32.175 ft/s^2)
    INPUTS:
        W = weight (lb)
        T = thrust (lb)
        LoD = Lift to Drag Ratio
        mu = rolling friction (see table 17.1)
        rho = density (slugs/ft^3)
        V_initial = starting velocity (ft/s)
        V_final = takeoff velocity, typically 1.1*V_stall  (ft/s)
        
    OUTPUTS:
        ground_roll_distance = total distance for ground roll phase (ft)
        
    Equation 17.105 - 17.111 from Raymer (6th ed)
    """
    
    g = 32.175      # gravity (ft/s^2)
    V_TR = 1.15*V_stall     # transition velocity (ft/s), pg.673
    
    #n = 1.2     # Load factor average during transition, eqn. 17.105
    R = V_TR**2 /(0.2*g)    # transition arc radius (ft), eqn. 17.107
    
    gamma_climb = np.arcsin((T/W)-1/LoD)  # climb angle, (radians), eqn. 17.108
    
    h_TR = R*(1-np.cos(gamma_climb))    # transition finish altitude (ft), eqn. 17.110
    
    if h_TR > h_obstacle:
        S_TR = np.sqrt(R**2 - (R - h_obstacle)**2)      # transition distance if h_obstacle is cleared
                                                        # during the transition (ft), eqn. 17.111
    else:
        S_TR = R*np.sin(gamma_climb)    # transition distance (ft), eqn. 17.109
        
    return S_TR, h_TR
 

def TO_climb_obstacle(gamma_climb,h_TR,h_obstacle):
    """
    Distance to clear obstacle after transition phase.
    Equation 17.112 from Raymer (6th ed).

    Args:
        gamma_climb (deg): angle of climb after transition 
        h_TR (ft): height at end of transition phase
        h_obstacle (ft): height of obstacle to clear (35ft commercial, 50ft small civil + military)

    Returns:
        S_C (ft): climb distance to clear obstacle h_obstacle (ft) tall
    """
    
    S_C = (h_obstacle - h_TR)/np.tan(np.radians(gamma_climb))
    
    return S_C





def climb_angle(T_climb, D_climb, W_climb):
    gamma_climb = np.degrees(np.arcsin((T_climb - D_climb)/W_climb)) #deg
    
    return gamma_climb




def simple_TO_prop(S_ref,CL_to,W_to,bhp,rho):
    """
    Simple takeoff distance estimation using Fig. 5.4 method for prop, 50ft obstacle clearance.
    Linearized, accurate enough up to 6,000ft takeoff distance.
    """
    rho_SL = 0.002377 #slugs/ft^3

    TOP = (W_to**2)/(S_ref*(rho/rho_SL)*CL_to*bhp)
    s_to_50ft = TOP*10 #ft, linearized, accurate enough up to 6000ft takeoff distance

    return s_to_50ft



# ---- WEIGHT FRACTION ESTIMATIONS ----
def wf_empty(A,W_0,C):
    """
    Empty weight fraction calculation (We/W0), Table 3.1 from Raymer (6th ed)
    
    ASSUMES ENGLISH UNITS
    
    --- From Table 3.1 for Imperial Units ---
    Homebuilt metal/wood: A = 1.19, C = -0.09
    Homebuilt composite: A = 1.15, C = -0.09
    Gen Av Single: A = 2.36, C = -0.18
    Gen Av Twin: A = 1.51, C = -0.10
    Twin Turboprop: A = 0.96, C = -0.05
    Mil Cargo/Bomber: A = 0.93, C = -0.07
    Jet Transport: A = 1.02, C = -0.06
    -----------------------------------------
    
    Args:
        A (float): Coefficient from table 3.1 curve fits
        W_0 (float, lb): Input total weight, lb
        C (float, negative): power given from Table 3.1 curve fits

    Returns:
        We_W0 (float): Empty weight fraction (We/W0)

    """
    
    # --- From Table 3.1 for Imperial Units ---
    # Homebuilt metal/wood: A = 1.19, C = -0.09
    # Homebuilt composite: A = 1.15, C = -0.09
    # Gen Av Single: A = 2.36, C = -0.18
    # Gen Av Twin: A = 1.51, C = -0.10
    # Twin Turboprop: A = 0.96, C = -0.05
    # Mil Cargo/Bomber: A = 0.93, C = -0.07
    # Jet Transport: A = 1.02, C = -0.06
    
    We_W0 = A*W_0**C    # empty weight fraction, table 3.1
    
    return We_W0



def wf_TO():
    Wto_W0 = 0.97 # Table 3.2, Raymer (6th ed)
    return Wto_W0 

def wf_climb():
    Wclimb_W0 = 0.985 # Table 3.2, Raymer (6th ed)
    return Wclimb_W0

def wf_landing():
    Wland_W0 = 0.995 # Table 3.2, Raymer (6th ed)
    return Wland_W0


def wf_cruise_segment(distance,sfc,velocity,LoD):
    """
    Cruise segment weight fraction estimation, from Raymer (6th ed).
    
    ---- L/D to Utilize ----
    Jet: L/D_cruise = 0.866*L/D_max
    Prop: L/D_cruise = L/D_max
    ------------------------

    Args:
        distance (float, ft): Distance of cruise leg
        sfc (float, ): Specific fuel consumption
        velocity (float, ft/s): Flight velocity at cruise
        LoD (float): L/D at cruise

    Returns:
        Wi1_Wi (float): Cruise segment weight fraction, Wi/Wi-1 (eqn. 3.6)

    """
    
    Wi1_Wi = np.exp(-distance*sfc/(velocity*LoD)) # cruise segment weight fraction, Wi/Wi-1
    
    return Wi1_Wi
    
 
def sfc_prop_estimate(eta_prop,velocity,C_bhp):
    """
    Calculates equivalent SFC (C) for prop aircraft, Table 3.4 from Raymer (6th ed).

    ASSUMES ENGLISH UNITS
    
    --- Typical C_bhp Values ----
    //// Cruise
    Piston-prop, fixed pitch: C_bhp = 0.4
    Piston-prop, variable pitch: C_bhp = 0.4
    Turboprop: C_bhp = 0.5
    
    //// Loiter
    Piston-prop, fixed pitch: C_bhp = 0.5
    Piston-prop, variable pitch: C_bhp = 0.5
    Turboprop: C_bhp = 0.6
    ------------------------------
    
    Args:
        eta_prop (float): Prop efficiency
        velocity (float, ft/s): Flight segment velocity
        C_bhp (float): prop engine SFC

    Returns:
        C (float, lb/lb-hr): jet equivalent SFC
    """
    
    C = (C_bhp*velocity/(550*eta_prop))/3600 # eqn. 3.10, converted to 1/s instead of lb/lb-hr
    
    return C
    

def LoD_max_est(K_LD,AR,Sw_Sref):
    """
    ---- Typical K_LD Values ---- from pg. 40, Raymer (6th ed)
    Civil Jet: 15.5
    Military Jet: 14
    Retractable gear Prop: 11
    Non-retractable gear Prop: 9
    High Aspect-Ratio: 13
    Sailplanes: 15
    ------------------------------
    
    ---- Reference S_wet/S_ref Values ---- from Fig 3.6 (Raymer, 6th ed)
    B-47: 7.9
    F-104: 5.5
    Beech Starship: 5.2
    F-4: 4.1
    Avro Vulcan: 3
    Beech Duchess: 5
    747: 6.1
    C172: 3.8
    --------------------------------------
    
    Args:
        K_LD (float): from pg. 40, Raymer (6th ed)
        A (float): Aspect ratio of aircraft. ---> !!!!!! A DESIGN CHOICE !!!!!! <---
        Sw_Sref (float): S_wet / S_ref of aircraft, estimated from Fig 3.6

    Returns:
        LoD_max (float): Lift/Drag max estimate

    """
    
    LoD_max = K_LD*np.sqrt(AR/Sw_Sref) #L/D_max estimate from eqn. 3.12
    
    return LoD_max



def LoD_cruise_est(LoD_max,ac_type):
    if ac_type == "jet":
        LoD_cruise = 0.866*LoD_max
    if ac_type == "prop":
        LoD_cruise = LoD_max
    
    return LoD_cruise




def wf_fuel(reserve,Wx_W0):
    """
    Calculate fuel weight fraction, Raymer equation 3.13 (6th ed)

    Args:
        reserve (float): Fuel reserve/trapped allowance (typically 0.06, 6%)
        Wx_W0 (float): Total mission weight fraction, Wx/W0 = product(Wi/Wi-1) for all i

    Returns:
        Wfuel_W0 (float): Fuel weight fraction, W_fuel/W0

    """
    
    Wfuel_W0 = (1+reserve)*(1-Wx_W0) # fuel weight fraction, eqn. 3.13
    
    return Wfuel_W0


def calc_weight_TO(W0_guess,weight_payload,Wfuel_W0,We_W0,A_wf_empty,C_wf_empty,iterations_max,print_select):
    iteration = 0
    while True:
        W0_calculated_1 = weight_payload/(1 - Wfuel_W0 - We_W0)
        # if W0_calculated_1 > W0_guess:
        #     W0_guess += 100
        # else:
        #     W0_guess -= 100
        W0_guess = W0_calculated_1
        #print(f"W0_guess={W0_guess}")
        We_W0 = wf_empty(A_wf_empty,W0_guess,C_wf_empty)
        
        W0_calculated_2 = weight_payload/(1 - Wfuel_W0 - We_W0)
        # if W0_calculated_2 > W0_guess:
        #     W0_guess += 100
        # else:
        #     W0_guess -= 100
        W0_guess = W0_calculated_2
        #print(f"W0_guess={W0_guess}")
        We_W0 = wf_empty(A_wf_empty,W0_guess,C_wf_empty)
           
        iteration += 1
        delta = abs(W0_calculated_2 - W0_calculated_1)
        #print(f"Calc1 = {W0_calculated_1:.2f}\nCalc2 = {W0_calculated_2:.2f}")
        
        if delta < 10: # if delta is less than 100lb, exit loop
            if print_select == True:
                print(f"\nEmpty weight iterative loop closed after {iteration} iterations.\nW0 = {W0_calculated_2:.0f}lb, delta = {delta:.0f}lb\n")    
            break;
        if iteration >= iterations_max:
            if print_select == True:
                print(f"\nMAX ITERATIONS {iterations_max} reached!!! delta = {delta:.0f}lb\n")
            break;
            
    return W0_calculated_2, We_W0, delta





# ---- Range and Endurance Equations ----

def breguet_range_jet(V,LoD,C,Wi,Wf):
    """
    INPUTS:
        V = flight velocity
        LoD = lift to drag ratio
        C = specific fuel consumption (SFC)
        Wi = initial weight
        Wf = final weight
    OUTPUTS:
        R_jet = range
    """
    
    R_jet = (V/C)*LoD*np.log(Wi/Wf)
    
    return R_jet


def breguet_range_prop(eta_P,LoD,C_bhp,Wi,Wf):
    """
    INPUTS:
        eta_P = propeller efficiency factor
        LoD = lift to drag ratio
        C_bhp = specific fuel consumption (SFC)
        Wi = initial weight
        Wf = final weight
    OUTPUTS:
        R_jet = range
    """
    
    R_prop = (550*eta_P/C_bhp)*LoD*np.log(Wi/Wf)
    
    return R_prop



def endurance_electric(E_b,P_other,eta_sys,eta_p,W,V,LoD):
    """
    **************WARNING**************
    This function utilizes SI units!!!
    ***********************************
    
    
    ***************** NOTE *****************
    W/LoD == TV == DV in steady level flight
    ****************************************
    
    
    
    INPUTS:
        E_b = battery energy (Watt hours, Wh)
        P_other = other energy consumption, from FPV, etc. (W)
        eta_sys = system efficiency, from battery to motor shaft
        eta_p = propeller efficiency
        W = aircraft weight (Newtons, N)
        V = cruise velocity (m/s)
        LoD = lift / drag (SHOULD USE L/D FOR MAX ENDURANCE)
        
    CALCULATIONS:
        P_used = average power used during that period of time (Watts, W)
    OUTPUTS:
        E = endurance (hrs)
    """
    
    # From Raymer pg. 756, eqn. 20.3.
    P_motor = (W/LoD)*V/eta_p  # watts, eqn. 20.2
    P_used = P_motor + P_other
    E = E_b*eta_sys/(P_used) # hrs, endurance
    # E = 3.6*LoD*E_b*eta_sys*eta_p/(W*V) # equivalent if using km/h
    
    # # From Gundlach pg. 73, eqn 3.46
    # CD = CL/LoD
    # P_used = W*np.sqrt(2*W/(rho_inf*S_ref))/(eta_p*eta_sys*((CL**(3/2))/CD)) # ft-lb/s
    # E = (E_b*3600/W)*eta_sys*eta_p*((CL**(3/2))/CD)*np.sqrt(.5*rho_inf/(W/S_ref)) # s

    
    return E, P_motor



def breguet_range_electric(E_b,P_other,eta_sys,eta_p,W,V,LoD):
    """
    **************WARNING**************
    This function utilizes SI units!!!
    ***********************************
    
    
    ***************** NOTE *****************
    W/LoD == TV == DV in steady level flight
    ****************************************
    
    INPUTS:
        E_b = battery energy (Watt hours, Wh)
        eta_sys = system efficiency, from battery to motor shaft
        eta_p = propeller efficiency
        W = aircraft weight (Newtons, N)
        V = cruise velocity (m/s)
        LoD = lift / drag (SHOULD USE L/D FOR MAX RANGE)
        
    CALCULATIONS:
        E = endurance at given conditions (hrs)
    OUTPUTS:
        R = range (km)
    """
    
    E,P_motor = endurance_electric(E_b,P_other,eta_sys,eta_p,W,V,LoD) # hrs, endurance
    R = E*V*3600/1000 # km, range
    
    return R, P_motor




# ---- Lift and Drag Equations ----

def oswald_efficiency(AR,LE_sweep):
    """
    Per Raymer (6th ed) eqn. 12.48, 12.49
    INPUTS:
        AR = aspect ratio
        LE_sweep = Leading edge sweep (deg)
    OUTPUS:
        e = Oswald Span Efficiency Factor
    """

    if LE_sweep == 0:
        e = 1.78*(1-0.045*AR**0.68)-0.64
    elif LE_sweep > 30:
        e = 4.61*(1-0.045*AR**0.68)*(np.cos(np.radians(LE_sweep)))**0.15 - 3.1
    else:
        e1 = 1.78*(1-0.045*AR**0.68)-0.64
        e2 = 4.61*(1-0.045*AR**0.68)*(np.cos(np.radians(LE_sweep)))**0.15 - 3.1
        e = (LE_sweep/30)*e2 + (1-LE_sweep/30)*e1 # Linearly interpolate between both calcs
    
    return e

        
    
def CD_i_oswald(CL,AR,e):
    """
    Per Raymer (6th ed) eqn. 12.47

    """
    
    K = 1/(np.pi *AR *e)
    CD_i = K*CL**2
    
    return CD_i




def fuel_burn_fixed_range_jet(Wi,R,V,LoD,C):
    """
    FOR JET POWERED AIRCRAFT ONLY!!!
    
    Derived from the Breguet Range equation, sovling for Wi/Wf term if given range.
    
    INPUTS:
        Wi = initial weight
        R = desired range
        V = flight velocity (constant)
        LoD = lift to drag ratio (constant)
        C = specific fuel consumption (SFC) (constant)
    OUTPUTS:
        fuel_burned = fuel burned during simple cruise flight over specified range (mass)
    """
    
    Wf = Wi/np.exp(R/((V/C)*LoD))
    fuel_burned = Wi - Wf
    
    return fuel_burned


def classify_AR(AR, taper_ratio, LE_sweep):
    """
    Determine if a wing has a high or low aspect ratio, as defined in
    Raymer (6ed) pg. 407, eqn. 12.18
    """
    lam = taper_ratio
    Lam_LE = LE_sweep
    
    if lam == 0:
        c1 = 0 
    elif lam > 0 and lam <= 0.23:
        c1 = (0.5/0.23)*lam
    elif lam > 0.23:
        c1 = (-0.5/1.0)*lam + 0.5
        
    test_value = 3/((c1+1)*np.cos(np.radians(Lam_LE)))
    
    if AR <= test_value:
        AR_classification = 'low'
    else:
        AR_classification = 'high'
    
    
    return test_value, AR_classification



def LoD_max(AR,e,CD_0):
    """
    Calculate the maximum Lift to Drag (L/D) ratio. From Raymer (6ed) pg. 640,
    equations 17.14 and 17.15.
    
    Parameters
    ----------
    AR : Float
        Aspect Ratio
    e : Float
        Oswald Efficiency
    CD_0 : Float
        Zero-lift (parasitic) drag

    Returns
    -------
    LoD_maximum : Float
        Maximum lift to drag ratio for given design

    """
    
    CD_min = 2*CD_0
    K = 1/(np.pi*AR*e)
    CL_min_drag = np.sqrt(CD_0/K)
    
    LoD_maximum = CL_min_drag/CD_min
    
    return LoD_maximum



def velocity_min_drag(W,S_ref,rho,CD_0,AR,e):
    """
    Calculate the flight velocity for minimum drag, maximum L/D ratio. From
    Raymer (6ed) pg. 640, eqn. 17.13.
    """
    K = 1/(np.pi*AR*e)
    V_min_drag = np.sqrt((2*W/(rho*S_ref)) *np.sqrt(K/CD_0))
    
    return V_min_drag



def LoD_max_range_prop(AR,e,CD_0):
    """
    For prop aircraft, L/D for max range (best cruise) is L/D max.
    """
    LoD_max_range = LoD_max(AR,e,CD_0)
    
    return LoD_max_range



def velocity_min_power(W,S_ref,rho,CD_0,AR,e):
    """
    The velocity for minimum power required to attain steady, level flight.
    From Raymer (6ed) pg. 647, eqns. 17.33 or 17.19.
    """
    
    K = 1/(np.pi*AR*e)
    V_min_power = np.sqrt(2*W/(rho*S_ref) *np.sqrt(K/(3*CD_0)))

    return V_min_power



def LoD_min_power(AR,e,CD_0):
    """
    The L/D for minimizing power required to attain steady, level flight.
    From Raymer (6ed) pg. 641, eqns. 17.20 and 17.21
    """
    
    K = 1/(np.pi*AR*e)
    CL_min_power = np.sqrt(3*CD_0/K)
    CD_min_power = 4*CD_0
    
    LoD_power_min = CL_min_power/CD_min_power
    
    return LoD_power_min



def LoD_max_endurance_prop(AR,e,CD_0):
    """
    For prop aircraft, L/D for max endurance (loiter) is L/D at velocity for
    minimum power, or about 0.866 * L/D_max. From Raymer (6ed) pg. 647.
    """
    
    LoD_max_endurance = LoD_min_power(AR,e,CD_0)
    
    return LoD_max_endurance




def velocity_max_range_prop(W,S_ref,rho,CD_0,AR,e):
    """
    Velocity for maximum range for prop aircraft is V_min_drag, from Raymer
    (6ed) pg. 646, and eqn. 17.13 (pg. 640).
    """
    
    V_max_range = velocity_min_drag(W, S_ref, rho, CD_0, AR, e)
    
    return V_max_range
    
    

def velocity_max_endurance_prop(W,S_ref,rho,CD_0,AR,e):
    """
    Velocity for maximum endurance (loiter) for prop aircraft is V_min_power,
    from Raymer (6ed) pg. 647, eqn. 17.33,
    """
    
    V_max_endurance = velocity_min_power(W,S_ref,rho,CD_0,AR,e)
    
    return V_max_endurance



def W_S_max_range_prop(AR,e,CD_0,rho,V):
    """
    The wing loading for maximum range of prop aircraft, from Raymer (6ed)
    pg. 135, eqn. 5.13.
    """
    
    q = 0.5*rho*V**2
    W_S_max_range = q*np.sqrt(np.pi*AR*e*CD_0)
    
    return W_S_max_range



def W_S_max_endurance_prop(AR,e,CD_0,rho,V):
    """
    The wing loading for maximum endurance (loiter) of prop aircraft, from Raymer (6ed)
    pg. 135, eqn. 5.16.
    """
    
    q = 0.5*rho*V**2
    W_S_max_endurance = q*np.sqrt(3*np.pi*AR*e*CD_0)
    
    return W_S_max_endurance



def flat_plate_skinfriction_equivalent_turbulent(Re):
    """
    Raymer (6ed) pg. 420, eqn. 12.27
    """
    # """
    # Turbulent flat plate skin friction coefficient (Cf) plot reverse engineer 
    # from Raymer pg 421, Fig 12.22
    # """
    
    # Re_list =            [.125e6,.25e6,.325e6,.5e6,.75e6,1e6,1.5e6,2e6]
    # Cf_turbulent_list =  [.0071,.0059,.0053,.005,.00465,.0045,.0041,.00397]
    
    # interp_func = interp1d(Re_list,Cf_turbulent_list,kind="linear",fill_value="extrapolate")
    # Cf_turbulent = float(interp_func(Re))
    
    Cf_turbulent = 0.455 / (np.log10(Re)**2.58)
    
    return Cf_turbulent




# ---- Thrust Equations
def prop_thrust_dynamic(eta_p,bhp,V):
    # eqn. 13.17
    # eta_p = prop efficiency (0.8 good guess)
    # bhp = engine brake horsepower (whatever setting being evaluated)
    # V = flight velocity, ft/s
    T = 550*bhp*eta_p/V #thrust, lb
    
    return T


def flight_velocity_from_prop(weight,T_a,S_ref,CD_0,K,rho):
    """
    Doesn't seem to work very well right now... not sure if this is correct or not.

    

    Parameters
    ----------
    weight : TYPE
        DESCRIPTION.
    drag : TYPE
        DESCRIPTION.
    S_ref : TYPE
        Wing reference area
    CD_0 : TYPE
        Parasitic drag coefficient
    K : TYPE
        1/(pi*AR*e)
    rho : TYPE
        Air density

    Returns
    -------
    V_inf: float
        Velocity from given available power

    """
    Ta_W = T_a/weight # thrust available / weight
    W_S = weight/S_ref # wing loading
    
    V_inf = np.sqrt((Ta_W*W_S + W_S*np.sqrt(Ta_W**2 - 4*CD_0*K))/(rho*CD_0))

    return V_inf


def max_velocity_prop(W,P_max,eta_p,S_ref,AR,e,CD_0,rho_inf):
    
    """
    Max flight velocity possible for prop aircraft, given motor power.
    Finds intersection between thrust required (drag) and thrust available.
    
    P_max = max power, bhp
    """

    initial_guess = [10.0]
    
    def tmp(V):
        T_max = prop_thrust_dynamic(eta_p,P_max,V)
        
        K = 1/(np.pi*AR*e)
        CL = 2*W/(rho_inf*S_ref*V**2)
        CD_i = K*CL**2
        CD = CD_0 + CD_i
        D = 0.5*rho_inf*(V**2)*S_ref*CD
        
        z = T_max-D
        
        return z


    V_max = fsolve(tmp, initial_guess)[0]  
    
    K = 1/(np.pi*AR*e)
    CL = 2*W/(rho_inf*S_ref*V_max**2)
    CD_i = K*CL**2
    CD = CD_0 + CD_i
    D = 0.5*rho_inf*(V_max**2)*S_ref*CD 
    
    LoD = CL/CD
    
    return V_max, LoD




# ---- SnC
def MAC(chord_root,lam,b):
    """
    Calculate wing mean aerodynamic chord and return MAC (cbar) and spanwise
    location (ybar). Raymer (6ed) eqn. 7.8, 7.9
    """
    cbar = (2/3)*chord_root*(1+lam+lam**2)/(1+lam)
    ybar = (b/6)*(1+2*lam)/(1+lam)
    
    return cbar,ybar






# ---- Utilities

def read_airfoil_dat_file(file_path):
    coordinates = []

    with open(file_path, 'r') as file:
        for line in file:
            if line.startswith('#'):
                continue  # Skip comments
            elif any(c.isalpha() for c in line):  # Check if the line contains letters
                continue  # Skip lines with letters
            elif line.strip():  # Check if the line is not empty
                x, y = map(float, line.split())
                coordinates.append((x, y))

    return coordinates

# file_path = r"C:\Users\corsa\Google Drive Streaming\My Drive\Engineering projects\_bAero\_Programs\XFOIL6.99\mh62.dat"  # Replace with the actual file path

# try:
#     data_points = read_airfoil_dat_file(file_path)
#     print("List of tuples of coordinates:")
#     print(data_points)
# except FileNotFoundError:
#     print(f"File not found: {file_path}")
# except Exception as e:
#     print(f"An error occurred: {e}")



def plot_planform(ax,vrp_x,vrp_y,chord_root,chord_tip,Lam_LE,b,color,label,legend_switch):
    LE_tip = -(b/2)*np.tan(np.radians(Lam_LE))
    
    ax.set_aspect('equal')

    ax.plot([vrp_x,vrp_x],[vrp_y,-chord_root],color=color) # plot root chord
    ax.plot([vrp_x + b/2, vrp_x + b/2],[LE_tip,LE_tip - chord_tip],color=color) # plot right tip chord
    ax.plot([vrp_x,vrp_x + b/2],[vrp_y,LE_tip],color=color) # plot right LE
    ax.plot([vrp_x,vrp_x + b/2],[-chord_root,LE_tip - chord_tip],color=color) # plot right TE
    ax.plot([vrp_x - b/2, vrp_x - b/2],[LE_tip,LE_tip - chord_tip],color=color) # plot left tip chord
    ax.plot([vrp_x,vrp_x - b/2],[vrp_y,LE_tip],color=color) # plot left LE
    ax.plot([vrp_x,vrp_x - b/2],[-chord_root,LE_tip - chord_tip],color=color,label=label) # plot left TE
    
    def format_ticks(value, pos):
        if value != 0.0:
            return f'{-value:.1f}'
        else:
            return f'{value:.1f}'

    ax.yaxis.set_major_formatter(FuncFormatter(format_ticks))
    
    # plt.xlim([-1.2,1.2])
    # plt.ylim([-1.2,0.2])
    plt.xlabel('spanwise')
    plt.ylabel('chordwise')
    plt.title("Planform Plot")
    # with warnings.catch_warnings():
    #     warnings.filterwarnings('ignore', category=UserWarning, module="matplotlib")
    #     ax.legend(loc="upper right")
    
    if legend_switch == True:
        plt.legend(loc="upper right")
    
    return None



def SAC(alt, SI_Imp):
    """
    Standard atmosphere calculator
    """

    #Convert to SI:
    if(SI_Imp == "imp"):
        alt = alt*0.3048 #Convert ft to m
    ##

    #General Constants:
    g_0 = 9.807 #Acceleration due to gravity; (m/s^2)
    R = 287.05 #Gas constant for air; (J/kg*K)
    gamma = 1.4 #Ratio of specific heats for air
    S = 110.4 #K, "Sutherland's Constant"
    beta = 1.458*10**-6 #kg/(s*m*sqrt(K)), constant

    #Sea Level Constants:
    p_sl = 101325 #Atmospheric pressure at sea level; (Pa)
    rho_sl = 1.2250 #Atmospheric density at sea level; (kg/m^3)
    t_sl = 288.16 #Atmospheric temperature at sea level; (K)

    #Isotherm Constants:
    t11_25 = 216.66 #Temp. between 11 km and 25 km alt.; (K)
    t47_53 = 282.66 #Temp. between 47 km and 53 km alt.; (K)
    t79_90 = 165.66 #Temp. between 79 km and 90 km alt.; (K)
    t_105 = 225.66 #Temp at 105 km alt.; (K)

    #Gradient Constants:
    a_1 = -0.0065 #Gradient constant from SL to 11 km alt.; (K/m)
    a_2 = 0.003 #Gradient constant from 25 km to 47 km alt.; (K/m)
    a_3 = -0.0045 #Gradient constant from 53 km to 79 km alt.; (K/m)
    a_4 = 0.004 #Gradient constant from 90 km to 105 km alt.; (K/m)
    ##

    #Isotherm Corner Pressures/Densities:
    p_11 = p_sl*(t11_25/t_sl)**(-g_0/(a_1*R))
    rho_11 = rho_sl*(t11_25/t_sl)**(-(g_0/(a_1*R) + 1))
    p_25 = p_11*np.exp(-g_0/(R*t11_25)*14000)
    rho_25 = rho_11*p_25/p_11

    p_47 = p_25*(t47_53/t11_25)**(-g_0/(a_2*R))
    rho_47 = rho_25*(t47_53/t11_25)**(-(g_0/(a_2*R) + 1))
    p_53 = p_47*np.exp(-g_0/(R*t47_53)*6000)
    rho_53 = rho_47*p_53/p_47

    p_79 = p_47*(t79_90/t47_53)**(-g_0/(a_3*R))
    rho_79 = rho_47*(t79_90/t47_53)**(-(g_0/(a_3*R) + 1))
    p_90 = p_79*np.exp(-g_0/(R*t79_90)*11000)
    rho_90 = rho_79*p_90/p_79
    ##

    #Calculate T, P, Rho at Altitude:
    if(alt <= 11000): #Sea level to 11 km gradient
        t_alt = t_sl + a_1*alt
        p_alt = p_sl*(t_alt/t_sl)**(-g_0/(a_1*R))
        rho_alt = rho_sl*(t_alt/t_sl)**(-(g_0/(a_1*R) + 1))
    elif(alt <= 25000): #11 km to 25 km isotherm
        t_alt = t11_25
        p_alt = p_11*np.exp(-g_0/(R*t11_25)*(alt - 11000))
        rho_alt = rho_11*p_alt/p_11
    elif(alt <= 47000): #25 km to 47 km gradient
        t_alt = t11_25 + a_2*(alt - 25000)
        p_alt = p_25*(t_alt/t11_25)**(-g_0/(a_2*R))
        rho_alt = rho_25*(t_alt/t11_25)**(-(g_0/(a_2*R) + 1))
    elif(alt <= 53000): #47 km to 53 km isotherm
        t_alt = t47_53
        p_alt = p_47*np.exp(-g_0/(R*t47_53)*(alt - 47000))
        rho_alt = rho_47*p_alt/p_47
    elif(alt <= 79000): #53 km to 79 km gradient
        t_alt = t47_53 + a_3*(alt - 53000)
        p_alt = p_53*(t_alt/t47_53)**(-g_0/(a_3*R))
        rho_alt = rho_53*(t_alt/t47_53)**(-(g_0/(a_3*R) + 1))
    elif(alt <= 90000): #79 km to 90 km isotherm
        t_alt = t79_90
        p_alt = p_79*np.exp(-g_0/(R*t79_90)*(alt - 79000))
        rho_alt = rho_79*p_alt/p_79
    elif(alt <= 105000): #Max 105 km alt.
        t_alt = t79_90 + a_4*(alt - 90000)
        p_alt = p_53*(t_alt/t79_90)**(-g_0/(a_4*R))
        rho_alt = rho_90*(t_alt/t79_90)**(-(g_0/(a_4*R) + 1))
    ##

    #Speed of Sound at Alt.:
    a_alt = np.sqrt(gamma*R*t_alt)

    #Dynamic Viscosity at Alt.:
    mu_alt = beta*(t_alt**(3/2))/(t_alt + S) #N*s/m^2

    ##################################################################################
    ## NOTE: Gives approximately 1.21% smaller value than 'Digital Dutch' calculator
    ## This equates to about a -7deg R/F shift in temperature from 'standard'
    ## This is very probably negligable...
    ##################################################################################

    #Convert to Imperial:
    if(SI_Imp == "imp"):
        t_alt = t_alt*1.8 #Convert K to deg. Rankine
        p_alt = p_alt*0.020885434273039 #Convert Pa to psf
        rho_alt = rho_alt*0.0019403203 #Convert kg/m^3 to slug/ft^3
        a_alt = a_alt*3.28084 #Convert m/s to ft/s
        mu_alt = mu_alt*0.020885401145657425 #Convert N*s/m^2 to lb*s/ft^2

    #Outputs:
    SAC_out = {"T": t_alt, "P": p_alt, "rho": rho_alt, "a": a_alt, "mu": mu_alt}
    #print("\nFor",SI_Imp,"units: ")
    #print("---------------------------------------------------------------------------------------------")
    #print("         R                    PSI                     slugs/ft^3                ft/s")
    return SAC_out




def reynolds(alt,V,MAC,SI_Imp):
    """
    Return the Reynolds number for a wing given flight velocity, altitude
    and wing MAC.
    """
    SAC_out = SAC(alt,SI_Imp)
    mu = SAC_out["u"]
    rho = SAC_out["rho"]
    
    Re = MAC*V*rho/mu
    
    return Re



def mach(alt,V,SI_Imp):
    """
    Calculate mach number.
    """
    SAC_out = SAC(alt,SI_Imp)
    a = SAC_out["a"]
    
    M = V/a
    
    return M





# ---- Lifting Line Theory
def LLCirc(N, theta, alpha, alpha_0, c, b, V_inf):
    """
    Method: Lifting Line Fourier Sine Series Solver (Circulation)
    
    OUTPUTS:
    A = Fourier Sine Series coefficients (per wing station)
    gamma = Circulation (per wing station)
    alpha_i = Induced angle of attack (per wing station)
    e = Oswald's efficiency ratio

    INPUTS:
    N = number of wing stations (equal to length of chord list 'c')
    theta = (deg) wing station sweep angles (imagine line sweeping from center out to each chord tip)
            Can be 0:180deg or 0:90deg (halfspan)
    alpha = (deg) angle of attack along wingspan (fullspan if using 0:180deg, halfspan if using 0:90deg)  
                -> int, float, np.ndarray, list
    alpha_0 = (deg) zero-lift angle of attack along wingspan
                -> int, float, np.ndarray, list
    c = chord length along wingspan      
                -> int, float, np.ndarray, list

    """

    if isinstance(alpha,np.ndarray) == 1:
        if len(alpha) == 1:
            alpha = alpha*np.ones(N)
    else:
        alpha = alpha*np.ones(N)
    if isinstance(alpha_0,np.ndarray) == 1:
        if len(alpha_0) == 1:
            alpha_0 = alpha_0*np.ones(N)
    else:
        alpha_0 = alpha_0*np.ones(N)
    if isinstance(c,np.ndarray) == 1:
        if len(c) == 1:
            c = c*np.ones(N)
    else:
        c = c*np.ones(N)
    
    alpha = alpha * np.pi/180. 
    alpha_0 = alpha_0 * np.pi/180. 
    theta = theta * np.pi/180.

    C = np.zeros((N,N)) 
    B = np.zeros(N) 

    for j in np.arange(0,N):
        for n in np.arange(0,N):
            C[j,n] = (2*b/(np.pi*c[j]))*np.sin((n+1)*theta[j]) + (n+1)*np.sin((n+1)*theta[j])/np.sin(theta[j])
        B[j] = alpha[j] - alpha_0[j]

    A = np.linalg.solve(C,B)
    gamma = np.zeros(N)
    alpha_i = np.zeros(N)

    for j in np.arange(0,N):
        for n in np.arange(0,N):
            gamma[j] = gamma[j] + 2*b*V_inf*A[n]*np.sin((n+1)*theta[j])
            alpha_i[j] = alpha_i[j] + (n+1)*A[n]*np.sin((n+1)*theta[j])/np.sin(theta[j])

    # Solve for Oswald's Efficiency Ratio
    d = 0.; e = 0.
    if A[0] == 0:
        d = 0
    else:   
        for j in np.arange(2,N):
            d = d + j*(A[j-1]/A[0])**2
    e = 1/(1+d)

    return (A, gamma, alpha_i, e)