"""Longitudinal trim workflows built on the AVL case runner."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional, Tuple

import aerosandbox as asb
import numpy as np

from ac_design_toolbox.avl.analysis import run_avl_case
from ac_design_toolbox.avl.io import isa_density


def _avl_trim_longitudinal_1D(
    airplane: asb.Airplane,
    *,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str = "trim_case",
    CL_target: float,
    velocity: float,
    altitude: float | None = None,
    temp_shift_F: float = 0.0,
    mach: float = 0.0,
    control_index_map: Dict[str, int],
    baseline_controls: Optional[Dict[str, float]] = None,
    elevator_bounds: Tuple[float, float] = (-20.0, 20.0),
    alpha_seed_deg: float = 4.0,
    tol_CL: float = 1e-2,
    tol_Cm: float = 1e-3,
    max_alpha_iter: int = 20,
    max_elev_iter: int = 20,
    timeout_s: float | None = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True,
    geom_writer=None,
) -> Dict:
    """Fallback nested 1D longitudinal trim solve for ``CL`` and ``Cm``."""
    if altitude is not None:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
    else:
        rho = 1.225

    baseline_controls = dict(baseline_controls) if baseline_controls is not None else {}
    for key in ("aileron", "elevator", "rudder", "flap"):
        baseline_controls.setdefault(key, 0.0)

    history: Dict[str, list] = {
        "elevator_iter": [],
        "alpha_iter": [],
    }
    avl_calls = 0

    def solve_alpha_for_CL(elevator_deg: float, alpha_seed_prev: float | None = None) -> Dict[str, float]:
        nonlocal avl_calls
        ctrl = dict(baseline_controls)
        ctrl["elevator"] = float(elevator_deg)

        def eval_at(alpha_deg: float):
            nonlocal avl_calls
            result = run_avl_case(
                airplane=airplane,
                avl_exe=avl_exe,
                working_directory=working_directory,
                case_name=case_name,
                alpha=float(alpha_deg),
                beta=0.0,
                mach=float(mach),
                velocity=float(velocity),
                density=float(rho),
                altitude=float(altitude) if altitude is not None else None,
                temp_shift_F=float(temp_shift_F),
                control_deflections=ctrl,
                control_index_map=control_index_map,
                timeout_s=timeout_s,
                write_geom=write_geom,
                force_rewrite_geom=force_rewrite_geom,
                geom_writer=geom_writer,
            )
            avl_calls += 1
            CL = result["scalars"].get("CL", float("nan"))
            return CL, result

        if alpha_seed_prev is not None:
            alpha_test = float(alpha_seed_prev)
            CL_test, res_test = eval_at(alpha_test)
            f_test = CL_test - CL_target

            if abs(f_test) < tol_CL:
                return {
                    "alpha_deg": float(alpha_test),
                    "CL": float(CL_test),
                    "Cm": float(res_test["scalars"].get("Cm", float("nan"))),
                    "CD": float(res_test["scalars"].get("CD", float("nan"))),
                    "CDi": float(res_test["scalars"].get("CDind", float("nan"))),
                    "res": res_test,
                }

            a_low = alpha_test - 0.3
            a_high = alpha_test + 0.3
            CL_low, res_low = eval_at(a_low)
            CL_high, res_high = eval_at(a_high)
            f_low = CL_low - CL_target
            f_high = CL_high - CL_target

            if f_low * f_high <= 0.0:
                a, fa = a_low, f_low
                b, fb = a_high, f_high
                alpha_hit, res_hit = b, res_high

                for _ in range(max_alpha_iter):
                    if abs(b - a) < 1e-9 or abs(fb - fa) < 1e-9:
                        alpha_new = 0.5 * (a + b)
                    else:
                        slope = (fb - fa) / (b - a)
                        alpha_new = b - fb / slope
                    alpha_new = 0.7 * alpha_new + 0.3 * b

                    CL_new, res_new = eval_at(alpha_new)
                    f_new = CL_new - CL_target

                    alpha_hit, res_hit = alpha_new, res_new
                    if abs(f_new) < tol_CL:
                        break

                    if fa * f_new <= 0.0:
                        b, fb = alpha_new, f_new
                    else:
                        a, fa = alpha_new, f_new

                scalars = res_hit["scalars"]
                return {
                    "alpha_deg": float(alpha_hit),
                    "CL": float(scalars.get("CL", float("nan"))),
                    "Cm": float(scalars.get("Cm", float("nan"))),
                    "CD": float(scalars.get("CD", float("nan"))),
                    "CDi": float(scalars.get("CDind", float("nan"))),
                    "res": res_hit,
                }

        a_low = float(alpha_seed_deg) - 2.0
        a_high = float(alpha_seed_deg) + 2.0
        CL_low, res_low = eval_at(a_low)
        CL_high, res_high = eval_at(a_high)
        f_low = CL_low - CL_target
        f_high = CL_high - CL_target

        tries = 0
        while f_low * f_high > 0.0 and tries < 5:
            a_low -= 2.0
            a_high += 2.0
            CL_low, res_low = eval_at(a_low)
            CL_high, res_high = eval_at(a_high)
            f_low = CL_low - CL_target
            f_high = CL_high - CL_target
            tries += 1

        if f_low * f_high > 0.0:
            raise RuntimeError("Full bracket failed in solve_alpha_for_CL.")

        a, fa = a_low, f_low
        b, fb = a_high, f_high
        alpha_hit, res_hit = b, res_high

        for _ in range(max_alpha_iter):
            if abs(b - a) < 1e-9 or abs(fb - fa) < 1e-9:
                alpha_new = 0.5 * (a + b)
            else:
                slope = (fb - fa) / (b - a)
                alpha_new = b - fb / slope
            alpha_new = 0.7 * alpha_new + 0.3 * b

            CL_new, res_new = eval_at(alpha_new)
            f_new = CL_new - CL_target

            alpha_hit, res_hit = alpha_new, res_new
            if abs(f_new) < tol_CL:
                break

            if fa * f_new <= 0.0:
                b, fb = alpha_new, f_new
            else:
                a, fa = alpha_new, f_new

        scalars = res_hit["scalars"]
        return {
            "alpha_deg": float(alpha_hit),
            "CL": float(scalars.get("CL", float("nan"))),
            "Cm": float(scalars.get("Cm", float("nan"))),
            "CD": float(scalars.get("CD", float("nan"))),
            "CDi": float(scalars.get("CDind", float("nan"))),
            "res": res_hit,
        }

    de_low, de_high = float(elevator_bounds[0]), float(elevator_bounds[1])
    if de_low >= de_high:
        raise ValueError("elevator_bounds must satisfy lower < upper.")

    sol_low = solve_alpha_for_CL(de_low)
    Cm_low = sol_low["Cm"]
    sol_high = solve_alpha_for_CL(de_high)
    Cm_high = sol_high["Cm"]

    tries = 0
    while Cm_low * Cm_high > 0.0 and tries < 5:
        span = de_high - de_low
        de_low -= 0.5 * span
        de_high += 0.5 * span
        sol_low = solve_alpha_for_CL(de_low)
        Cm_low = sol_low["Cm"]
        sol_high = solve_alpha_for_CL(de_high)
        Cm_high = sol_high["Cm"]
        tries += 1

    if Cm_low * Cm_high > 0.0:
        raise RuntimeError("Failed to bracket elevator for Cm=0 in avl_trim_longitudinal.")

    a_e, fa_e = de_low, Cm_low
    b_e, fb_e = de_high, Cm_high
    de_hit, sol_hit = b_e, sol_high

    for iteration in range(max_elev_iter):
        if abs(b_e - a_e) < 1e-9 or abs(fb_e - fa_e) < 1e-9:
            de_new = 0.5 * (a_e + b_e)
        else:
            slope = (fb_e - fa_e) / (b_e - a_e)
            de_new = b_e - fb_e / slope
        de_new = 0.7 * de_new + 0.3 * b_e

        sol_new = solve_alpha_for_CL(de_new, alpha_seed_prev=sol_hit["alpha_deg"])
        Cm_new = sol_new["Cm"]

        history["elevator_iter"].append(
            {
                "iter": int(iteration),
                "elevator_deg": float(de_new),
                "Cm": float(Cm_new),
            }
        )

        de_hit, sol_hit = de_new, sol_new
        if abs(Cm_new) < tol_Cm:
            break

        if fa_e * Cm_new <= 0.0:
            b_e, fb_e = de_new, Cm_new
        else:
            a_e, fa_e = de_new, Cm_new

    alpha_trim = sol_hit["alpha_deg"]
    CL_trim = sol_hit["CL"]
    Cm_trim = sol_hit["Cm"]
    CD_trim = sol_hit["CD"]
    CDi_trim = sol_hit["CDi"]
    K_trim = CDi_trim / max(CL_trim**2, 1e-12)

    return {
        "alpha_trim_deg": float(alpha_trim),
        "elevator_trim_deg": float(de_hit),
        "CL": float(CL_trim),
        "Cm": float(Cm_trim),
        "CD": float(CD_trim),
        "CDi": float(CDi_trim),
        "K": float(K_trim),
        "rho": float(rho),
        "V": float(velocity),
        "avl_calls": int(avl_calls),
        "history": history,
    }


def avl_trim_longitudinal(
    airplane: asb.Airplane,
    *,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str = "trim_case",
    CL_target: float,
    velocity: float,
    altitude: float | None = None,
    temp_shift_F: float = 0.0,
    mach: float = 0.0,
    control_index_map: Dict[str, int],
    baseline_controls: Optional[Dict[str, float]] = None,
    elevator_bounds: Tuple[float, float] = (-20.0, 20.0),
    alpha_seed_deg: float = 4.0,
    elevator_seed_deg: float = 0.0,
    tol_CL: float = 1e-2,
    tol_Cm: float = 1e-3,
    max_iter: int = 12,
    jac_step_alpha: float = 0.2,
    jac_step_elev: float = 0.5,
    max_step_alpha: float = 3.0,
    max_step_elev: float = 5.0,
    max_cond_J: float = 1e6,
    residual_growth_factor: float = 2.0,
    timeout_s: float | None = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = True,
    geom_writer=None,
) -> Dict:
    """Solve longitudinal trim in ``(alpha, elevator)`` with a Newton method plus fallback."""
    if altitude is not None:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
    else:
        rho = 1.225

    baseline_controls = dict(baseline_controls) if baseline_controls is not None else {}
    for key in ("aileron", "elevator", "rudder", "flap"):
        baseline_controls.setdefault(key, 0.0)

    avl_calls = 0

    def eval_state(alpha_deg: float, elevator_deg: float) -> Dict[str, float]:
        nonlocal avl_calls

        ctrl = dict(baseline_controls)
        ctrl["elevator"] = float(elevator_deg)

        result = run_avl_case(
            airplane=airplane,
            avl_exe=avl_exe,
            working_directory=working_directory,
            case_name=case_name,
            alpha=float(alpha_deg),
            beta=0.0,
            mach=float(mach),
            velocity=float(velocity),
            density=float(rho),
            altitude=float(altitude) if altitude is not None else None,
            temp_shift_F=float(temp_shift_F),
            control_deflections=ctrl,
            control_index_map=control_index_map,
            timeout_s=timeout_s,
            write_geom=write_geom,
            force_rewrite_geom=force_rewrite_geom,
            geom_writer=geom_writer,
        )
        avl_calls += 1

        scalars = result["scalars"]
        return {
            "alpha_deg": float(alpha_deg),
            "elevator_deg": float(elevator_deg),
            "CL": float(scalars.get("CL", float("nan"))),
            "Cm": float(scalars.get("Cm", float("nan"))),
            "CD": float(scalars.get("CD", float("nan"))),
            "CDi": float(scalars.get("CDind", float("nan"))),
            "res": result,
        }

    alpha = float(alpha_seed_deg)
    elevator = float(np.clip(elevator_seed_deg, elevator_bounds[0], elevator_bounds[1]))
    history: Dict[str, list] = {"iter": []}

    converged = False
    failure_reason = ""
    norm_f_prev = None

    for iteration in range(max_iter):
        state = eval_state(alpha, elevator)
        f1 = state["CL"] - CL_target
        f2 = state["Cm"]
        norm_f = float(np.sqrt(f1**2 + f2**2))

        history["iter"].append(
            {
                "iter": int(iteration),
                "alpha_deg": float(alpha),
                "elevator_deg": float(elevator),
                "CL": float(state["CL"]),
                "Cm": float(state["Cm"]),
                "CD": float(state["CD"]),
                "CDi": float(state["CDi"]),
                "f_CL": float(f1),
                "f_Cm": float(f2),
                "norm_f": norm_f,
                "avl_calls": int(avl_calls),
            }
        )

        if abs(f1) < tol_CL and abs(f2) < tol_Cm:
            converged = True
            break

        if norm_f_prev is not None and norm_f > residual_growth_factor * norm_f_prev:
            failure_reason = "residual_increasing"
            break
        norm_f_prev = norm_f

        state_da = eval_state(alpha + jac_step_alpha, elevator)
        state_de = eval_state(alpha, elevator + jac_step_elev)

        J = np.array(
            [
                [(state_da["CL"] - state["CL"]) / jac_step_alpha, (state_de["CL"] - state["CL"]) / jac_step_elev],
                [(state_da["Cm"] - state["Cm"]) / jac_step_alpha, (state_de["Cm"] - state["Cm"]) / jac_step_elev],
            ],
            dtype=float,
        )
        f_vec = np.array([f1, f2], dtype=float)

        try:
            condJ = float(np.linalg.cond(J))
        except np.linalg.LinAlgError:
            condJ = float("inf")

        try:
            detJ = float(np.linalg.det(J))
        except np.linalg.LinAlgError:
            detJ = float("nan")

        history["iter"][-1]["condJ"] = condJ
        history["iter"][-1]["detJ"] = detJ

        if not np.isfinite(condJ) or condJ > max_cond_J:
            failure_reason = "ill_conditioned_J"
            break

        try:
            dx = np.linalg.solve(J, -f_vec)
        except np.linalg.LinAlgError:
            failure_reason = "singular_J"
            break

        d_alpha_raw, d_elev_raw = float(dx[0]), float(dx[1])
        d_alpha = float(np.clip(d_alpha_raw, -max_step_alpha, max_step_alpha))
        d_elev = float(np.clip(d_elev_raw, -max_step_elev, max_step_elev))

        history["iter"][-1]["d_alpha_raw"] = d_alpha_raw
        history["iter"][-1]["d_elev_raw"] = d_elev_raw
        history["iter"][-1]["d_alpha"] = d_alpha
        history["iter"][-1]["d_elev"] = d_elev

        alpha = alpha + d_alpha
        elevator = np.clip(elevator + d_elev, elevator_bounds[0], elevator_bounds[1])

    if not converged:
        print(
            f"[WARN] avl_trim_longitudinal (newton2d) fallback to 1d solver: reason={failure_reason}, "
            f"alpha_seed={alpha_seed_deg}, elevator_seed={elevator_seed_deg}"
        )

        fallback = _avl_trim_longitudinal_1D(
            airplane=airplane,
            avl_exe=avl_exe,
            working_directory=working_directory,
            case_name=f"{case_name}_fallback",
            CL_target=CL_target,
            velocity=velocity,
            altitude=altitude,
            temp_shift_F=temp_shift_F,
            mach=mach,
            control_index_map=control_index_map,
            baseline_controls=baseline_controls,
            elevator_bounds=elevator_bounds,
            alpha_seed_deg=alpha_seed_deg,
            tol_CL=tol_CL,
            tol_Cm=tol_Cm,
        )

        if "avl_calls" in fallback:
            fallback["avl_calls"] = int(fallback["avl_calls"]) + int(avl_calls)

        fallback.setdefault("newton2d_failure_reason", failure_reason)
        fallback.setdefault("newton2d_history", history)
        return fallback

    state_final = eval_state(alpha, elevator)
    CL_trim = state_final["CL"]
    Cm_trim = state_final["Cm"]
    CD_trim = state_final["CD"]
    CDi_trim = state_final["CDi"]
    K_trim = CDi_trim / max(CL_trim**2, 1e-12)

    return {
        "alpha_trim_deg": float(state_final["alpha_deg"]),
        "elevator_trim_deg": float(state_final["elevator_deg"]),
        "CL": float(CL_trim),
        "Cm": float(Cm_trim),
        "CD": float(CD_trim),
        "CDi": float(CDi_trim),
        "K": float(K_trim),
        "rho": float(rho),
        "V": float(velocity),
        "avl_calls": int(avl_calls),
        "history": history,
        "newton2d_failure_reason": "",
    }


__all__ = ["avl_trim_longitudinal"]
