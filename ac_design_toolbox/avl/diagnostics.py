"""Diagnostic plotting helpers for AVL trim studies."""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import aerosandbox as asb
import matplotlib.pyplot as plt
import numpy as np

from ac_design_toolbox.avl.analysis import run_avl_case
from ac_design_toolbox.avl.io import isa_density


def plot_newton_history(tr, title="Newton trim diagnostics"):
    """Plot condition number, residual norm, and Newton step history."""
    hist = tr["history"]["iter"]

    iterations = [entry["iter"] for entry in hist]
    condJ = [entry.get("condJ", np.nan) for entry in hist]
    norm_f = [entry.get("norm_f", np.nan) for entry in hist]
    d_alpha_raw = [entry.get("d_alpha_raw", np.nan) for entry in hist]
    d_elev_raw = [entry.get("d_elev_raw", np.nan) for entry in hist]
    d_alpha = [entry.get("d_alpha", np.nan) for entry in hist]
    d_elev = [entry.get("d_elev", np.nan) for entry in hist]

    fig, axs = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)

    axs[0].plot(iterations, condJ, marker="o")
    axs[0].set_yscale("log")
    axs[0].set_xlabel("Iteration")
    axs[0].set_ylabel("cond(J)")
    axs[0].set_title("Jacobian condition number")

    axs[1].plot(iterations, norm_f, marker="o")
    axs[1].set_yscale("log")
    axs[1].set_xlabel("Iteration")
    axs[1].set_ylabel(r"$\|f\| = \sqrt{f_1^2 + f_2^2}$")
    axs[1].set_title("Residual norm")

    axs[2].plot(iterations, d_alpha_raw, "o--", label=r"$\Delta \alpha_{\rm raw}$")
    axs[2].plot(iterations, d_elev_raw, "s--", label=r"$\Delta \delta_{e,\rm raw}$")
    axs[2].plot(iterations, d_alpha, "o-", label=r"$\Delta \alpha$ (clamped)")
    axs[2].plot(iterations, d_elev, "s-", label=r"$\Delta \delta_e$ (clamped)")
    axs[2].set_xlabel("Iteration")
    axs[2].set_ylabel("Step [deg]")
    axs[2].set_title("Newton step sizes")
    axs[2].legend()

    fig.suptitle(title + "\n$f_1=CL-CL_\\text{target}$, $f_2=Cm$")
    plt.show()


def plot_trim_residual_surfaces(
    *,
    airplane: asb.Airplane,
    avl_exe: str | Path,
    working_directory: Path,
    case_name: str,
    CL_target: float,
    velocity: float,
    altitude: float | None,
    temp_shift_F: float,
    mach: float,
    control_index_map: Dict[str, int],
    baseline_controls: Dict[str, float],
    alpha_center_deg: float,
    elevator_center_deg: float,
    alpha_span_deg: float = 6.0,
    elev_span_deg: float = 10.0,
    n_alpha: int = 25,
    n_elev: int = 25,
    timeout_s: float | None = None,
    write_geom: bool = True,
    force_rewrite_geom: bool = False,
    geom_writer=None,
):
    """Plot ``CL-CL_target``, ``Cm``, and residual norm over ``(alpha, elevator)``."""
    if altitude is not None:
        rho = isa_density(altitude_m=float(altitude), temp_shift_F=float(temp_shift_F))
    else:
        rho = 1.225

    alpha_min = alpha_center_deg - 0.5 * alpha_span_deg
    alpha_max = alpha_center_deg + 0.5 * alpha_span_deg
    elev_min = elevator_center_deg - 0.5 * elev_span_deg
    elev_max = elevator_center_deg + 0.5 * elev_span_deg

    alpha_vec = np.linspace(alpha_min, alpha_max, n_alpha)
    elev_vec = np.linspace(elev_min, elev_max, n_elev)
    A_grid, E_grid = np.meshgrid(alpha_vec, elev_vec, indexing="xy")

    f1_grid = np.zeros_like(A_grid, dtype=float)
    f2_grid = np.zeros_like(A_grid, dtype=float)
    normf_grid = np.zeros_like(A_grid, dtype=float)

    for i in range(n_elev):
        for j in range(n_alpha):
            alpha_ij = float(A_grid[i, j])
            elev_ij = float(E_grid[i, j])

            ctrl = dict(baseline_controls)
            ctrl["elevator"] = elev_ij

            result = run_avl_case(
                airplane=airplane,
                avl_exe=avl_exe,
                working_directory=working_directory,
                case_name=f"{case_name}_surf",
                alpha=alpha_ij,
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

            scalars = result["scalars"]
            CL = float(scalars.get("CL", float("nan")))
            Cm = float(scalars.get("Cm", float("nan")))

            f1 = CL - CL_target
            f2 = Cm
            normf = np.sqrt(f1**2 + f2**2)

            f1_grid[i, j] = f1
            f2_grid[i, j] = f2
            normf_grid[i, j] = normf

    fig, axs = plt.subplots(1, 3, figsize=(15, 4), constrained_layout=True)

    cs1 = axs[0].contourf(A_grid, E_grid, f1_grid, levels=31)
    axs[0].contour(A_grid, E_grid, f1_grid, levels=[0.0], colors="k", linewidths=1.5)
    axs[0].scatter([alpha_center_deg], [elevator_center_deg], marker="x")
    axs[0].set_xlabel(r"$\alpha$ [deg]")
    axs[0].set_ylabel(r"$\delta_e$ [deg]")
    axs[0].set_title(r"$f_1 = CL - CL_{\rm target}$")
    fig.colorbar(cs1, ax=axs[0])

    cs2 = axs[1].contourf(A_grid, E_grid, f2_grid, levels=31)
    axs[1].contour(A_grid, E_grid, f2_grid, levels=[0.0], colors="k", linewidths=1.5)
    axs[1].scatter([alpha_center_deg], [elevator_center_deg], marker="x")
    axs[1].set_xlabel(r"$\alpha$ [deg]")
    axs[1].set_ylabel(r"$\delta_e$ [deg]")
    axs[1].set_title(r"$f_2 = Cm$")
    fig.colorbar(cs2, ax=axs[1])

    cs3 = axs[2].contourf(A_grid, E_grid, normf_grid, levels=31)
    axs[2].scatter([alpha_center_deg], [elevator_center_deg], marker="x")
    axs[2].set_xlabel(r"$\alpha$ [deg]")
    axs[2].set_ylabel(r"$\delta_e$ [deg]")
    axs[2].set_title(r"$\|f\| = \sqrt{f_1^2 + f_2^2}$")
    fig.colorbar(cs3, ax=axs[2])

    fig.suptitle("Trim residual surfaces around Newton solution")
    plt.show()


__all__ = ["plot_newton_history", "plot_trim_residual_surfaces"]
