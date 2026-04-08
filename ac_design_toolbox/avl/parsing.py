"""AVL text-output parsing helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List

from ac_design_toolbox.avl._helpers import _find_section, _matvec, _parse_kv_blocks, _rot_wind_to_body


def parse_avl_stdout_like_asb(
    text: str,
    *,
    velocity: float,
    rho: float,
    Sref: float,
    Cref: float,
    Bref: float,
    alpha_deg: float,
    beta_deg: float,
) -> Dict:
    """Parse AVL stdout into a flat dictionary similar to AeroSandbox output."""
    kv = _parse_kv_blocks(text, data_identifier=" = ", cast_to_float=True, overwrite=True)

    for old in ["Alpha", "Beta", "Mach"]:
        if old in kv:
            kv[old.lower()] = kv.pop(old)

    for key in list(kv.keys()):
        if "tot" in key:
            kv[key.replace("tot", "")] = kv.pop(key)

    velocity = float(velocity)
    q_dyn = 0.5 * rho * velocity * velocity

    if "pb/2V" in kv:
        kv["p"] = kv["pb/2V"] * (2.0 * velocity / Bref)
    if "qc/2V" in kv:
        kv["q_rate"] = kv["qc/2V"] * (2.0 * velocity / Cref)
    if "rb/2V" in kv:
        kv["r"] = kv["rb/2V"] * (2.0 * velocity / Bref)

    if "CL" in kv:
        kv["L"] = q_dyn * Sref * kv["CL"]
    if "CY" in kv:
        kv["Y"] = q_dyn * Sref * kv["CY"]
    if "CD" in kv:
        kv["D"] = q_dyn * Sref * kv["CD"]
    if "Cl" in kv:
        kv["l_b"] = q_dyn * Sref * Bref * kv["Cl"]
    if "Cm" in kv:
        kv["m_b"] = q_dyn * Sref * Cref * kv["Cm"]
    if "Cn" in kv:
        kv["n_b"] = q_dyn * Sref * Bref * kv["Cn"]

    if all(key in kv for key in ["L", "Y", "D"]):
        F_w = [-kv["D"], kv["Y"], -kv["L"]]
        rotation = _rot_wind_to_body(alpha_deg, beta_deg)
        Fx_b, Fy_b, Fz_b = _matvec(rotation, F_w)
        kv["F_w"] = F_w
        kv["F_b"] = [Fx_b, Fy_b, Fz_b]
        kv["F_g"] = kv["F_b"]

    try:
        kv["Clb Cnr / Clr Cnb"] = kv["Clb"] * kv["Cnr"] / (kv["Clr"] * kv["Cnb"])
    except Exception:
        pass

    return kv


def parse_strip_forces(text: str) -> List[Dict[str, float]]:
    """Parse AVL ``FS`` output into per-strip rows."""
    section = _find_section(text, r"^Strip Forces\b")
    if not section:
        return []

    start, end = section
    lines = text.splitlines()[start:end]

    rows: List[Dict[str, float]] = []
    current_surface_name = ""
    header_cols: List[str] = []
    header_idx = -1
    float_token = re.compile(r"^[+-]?(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?$")

    def is_separator(line: str) -> bool:
        stripped = line.strip()
        return len(stripped) > 0 and all(char in "-=_" for char in stripped)

    for index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.lower().startswith("surface"):
            match = re.search(r"Surface\s*#?\s*\d*\s*:\s*(.+)$", stripped, re.IGNORECASE)
            current_surface_name = match.group(1).strip() if match else stripped
            continue

        if header_cols == [] and re.search(
            r"\b(i|Yle|Chord|Area|c_cl|cl|ai|cd|cm|Xle|Zle|C.P.)\b", stripped, re.IGNORECASE
        ):
            header_cols = re.split(r"\s+", stripped)
            header_idx = index
            continue

        if is_separator(stripped):
            continue
        if re.match(r"^[A-Z][A-Z \t\.\(\)/-]{3,}$", stripped):
            continue

        if header_cols and index > header_idx:
            parts = re.split(r"\s+", stripped)
            if not parts:
                continue
            numeric_like = sum(1 for part in parts if float_token.match(part))
            if numeric_like < max(2, len(parts) - 1):
                continue

            row: Dict[str, float] = {}
            for header, value in zip(header_cols, parts):
                try:
                    row[header] = float(value)
                except ValueError:
                    pass

            if row:
                if current_surface_name:
                    row["Surface"] = current_surface_name
                rows.append(row)

    return rows


def parse_stability_file(stab_path: Path) -> Dict[str, float]:
    """Parse an AVL ``.stability`` file into a flat derivative dictionary."""
    text = stab_path.read_text(encoding="utf-8", errors="replace")
    derivs: Dict[str, float] = {}

    for name, value in re.findall(r"([A-Za-z][A-Za-z0-9']*)\s*=\s*([-+0-9.eE]+)", text):
        if name not in derivs:
            try:
                derivs[name] = float(value)
            except ValueError:
                continue

    match = re.search(r"Clb Cnr / Clr Cnb\s*=\s*([-+0-9.eE]+)", text)
    if match:
        derivs["ClbCnr_over_ClrCnb"] = float(match.group(1))

    return derivs


__all__ = [
    "parse_avl_stdout_like_asb",
    "parse_stability_file",
    "parse_strip_forces",
]
