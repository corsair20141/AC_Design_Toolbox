"""Geometry utilities and plotting helpers used by conceptual studies."""

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import FuncFormatter


def MAC(chord_root, lam, b):
    """Return mean aerodynamic chord and its spanwise station for a tapered wing."""
    cbar = (2 / 3) * chord_root * (1 + lam + lam**2) / (1 + lam)
    ybar = (b / 6) * (1 + 2 * lam) / (1 + lam)
    return cbar, ybar


def read_airfoil_dat_file(file_path):
    """Read a simple two-column airfoil DAT file into coordinate tuples."""
    coordinates = []

    with open(file_path, "r") as file:
        for line in file:
            if line.startswith("#"):
                continue
            if any(c.isalpha() for c in line):
                continue
            if line.strip():
                x, y = map(float, line.split())
                coordinates.append((x, y))

    return coordinates


def plot_planform(ax, vrp_x, vrp_y, chord_root, chord_tip, Lam_LE, b, color, label, legend_switch):
    """Plot a simple trapezoidal planform on a Matplotlib axes object."""
    LE_tip = -(b / 2) * np.tan(np.radians(Lam_LE))

    ax.set_aspect("equal")

    ax.plot([vrp_x, vrp_x], [vrp_y, -chord_root], color=color)
    ax.plot([vrp_x + b / 2, vrp_x + b / 2], [LE_tip, LE_tip - chord_tip], color=color)
    ax.plot([vrp_x, vrp_x + b / 2], [vrp_y, LE_tip], color=color)
    ax.plot([vrp_x, vrp_x + b / 2], [-chord_root, LE_tip - chord_tip], color=color)
    ax.plot([vrp_x - b / 2, vrp_x - b / 2], [LE_tip, LE_tip - chord_tip], color=color)
    ax.plot([vrp_x, vrp_x - b / 2], [vrp_y, LE_tip], color=color)
    ax.plot([vrp_x, vrp_x - b / 2], [-chord_root, LE_tip - chord_tip], color=color, label=label)

    def format_ticks(value, pos):
        return f"{-value:.1f}" if value != 0.0 else f"{value:.1f}"

    ax.yaxis.set_major_formatter(FuncFormatter(format_ticks))
    plt.xlabel("spanwise")
    plt.ylabel("chordwise")
    plt.title("Planform Plot")

    if legend_switch:
        plt.legend(loc="upper right")

    return None

__all__ = [
    "MAC",
    "plot_planform",
    "read_airfoil_dat_file",
]
