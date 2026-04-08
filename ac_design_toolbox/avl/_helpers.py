"""Small private helpers shared across AVL text parsing and transforms."""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Tuple


def _parse_kv_blocks(
    text: str,
    data_identifier: str = " = ",
    cast_to_float: bool = True,
    overwrite: bool = True,
) -> Dict[str, float]:
    """Extract repeated ``<key> = <value>`` pairs from AVL text output."""
    out: Dict[str, float] = {}
    idx = text.find(data_identifier)
    while idx != -1:
        i = idx - 1
        while i >= 0 and text[i] == " ":
            i -= 1
        key = ""
        while i >= 0 and text[i] not in (" ", "\n"):
            key = text[i] + key
            i -= 1

        j = idx + len(data_identifier)
        while j < len(text) and text[j] == " ":
            j += 1
        value = ""
        while j < len(text) and text[j] not in (" ", "\n"):
            value += text[j]
            j += 1

        if cast_to_float:
            try:
                value = float(value)
            except Exception:
                value = float("nan")

        if key not in out or overwrite:
            out[key] = value

        text = text[idx + len(data_identifier) :]
        idx = text.find(data_identifier)

    return out


def _rot_wind_to_body(alpha_deg: float, beta_deg: float) -> List[List[float]]:
    """Return the direction cosine matrix that maps wind axes to body axes."""
    alpha = math.radians(alpha_deg)
    beta = math.radians(beta_deg)
    cos_alpha, sin_alpha = math.cos(alpha), math.sin(alpha)
    cos_beta, sin_beta = math.cos(beta), math.sin(beta)

    Rz = [
        [cos_beta, -sin_beta, 0.0],
        [sin_beta, cos_beta, 0.0],
        [0.0, 0.0, 1.0],
    ]
    Ry = [
        [cos_alpha, 0.0, sin_alpha],
        [0.0, 1.0, 0.0],
        [-sin_alpha, 0.0, cos_alpha],
    ]
    return [
        [
            Ry[0][0] * Rz[0][0] + Ry[0][1] * Rz[1][0] + Ry[0][2] * Rz[2][0],
            Ry[0][0] * Rz[0][1] + Ry[0][1] * Rz[1][1] + Ry[0][2] * Rz[2][1],
            Ry[0][0] * Rz[0][2] + Ry[0][1] * Rz[1][2] + Ry[0][2] * Rz[2][2],
        ],
        [
            Ry[1][0] * Rz[0][0] + Ry[1][1] * Rz[1][0] + Ry[1][2] * Rz[2][0],
            Ry[1][0] * Rz[0][1] + Ry[1][1] * Rz[1][1] + Ry[1][2] * Rz[2][1],
            Ry[1][0] * Rz[0][2] + Ry[1][1] * Rz[1][2] + Ry[1][2] * Rz[2][2],
        ],
        [
            Ry[2][0] * Rz[0][0] + Ry[2][1] * Rz[1][0] + Ry[2][2] * Rz[2][0],
            Ry[2][0] * Rz[0][1] + Ry[2][1] * Rz[1][1] + Ry[2][2] * Rz[2][1],
            Ry[2][0] * Rz[0][2] + Ry[2][1] * Rz[1][2] + Ry[2][2] * Rz[2][2],
        ],
    ]


def _matvec(matrix: List[List[float]], vector: List[float]) -> List[float]:
    """Multiply a 3x3 matrix by a 3-vector."""
    return [
        matrix[0][0] * vector[0] + matrix[0][1] * vector[1] + matrix[0][2] * vector[2],
        matrix[1][0] * vector[0] + matrix[1][1] * vector[1] + matrix[1][2] * vector[2],
        matrix[2][0] * vector[0] + matrix[2][1] * vector[1] + matrix[2][2] * vector[2],
    ]


def _find_section(text: str, heading_regex: str) -> Optional[Tuple[int, int]]:
    """Locate a text section that starts at a heading and ends at the next heading."""
    lines = text.splitlines()
    heading_pattern = re.compile(heading_regex, re.IGNORECASE)
    caps_heading = re.compile(r"^[A-Z][A-Z \t\.\(\)/-]{3,}$")

    start = None
    for index, line in enumerate(lines):
        if heading_pattern.search(line):
            start = index
            break
    if start is None:
        return None

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if caps_heading.match(lines[index]) and index > start + 1:
            end = index
            break
    return (start, end)
