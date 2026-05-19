"""AeroSandbox AVL patch helpers used by the geometry workflow."""

from pathlib import Path
import re

import aerosandbox as asb


def _iter_controls_from_geometry(airplane):
    """Collect control deflections from geometry sections and coalesce by name."""
    name_to_defl = {}
    for wing in getattr(airplane, "wings", []):
        for xs in getattr(wing, "xsecs", []):
            for cs in getattr(xs, "control_surfaces", []):
                name = str(getattr(cs, "name", "")).strip()
                if not name:
                    continue
                deflection = float(getattr(cs, "deflection", 0.0) or 0.0)
                if abs(deflection) > 0 or name not in name_to_defl:
                    name_to_defl[name] = deflection
    return name_to_defl


def _custom_keystrokes(self):
    """Build patched AVL keystrokes using geometry-derived control settings."""
    run = ["oper"]

    mach_attr = getattr(self.op_point, "mach", None)
    if callable(mach_attr):
        mach_value = float(mach_attr())
    elif mach_attr is not None:
        mach_value = float(mach_attr)
    else:
        speed_of_sound = float(self.op_point.atmosphere.speed_of_sound())
        mach_value = float(self.op_point.velocity) / speed_of_sound

    run += [
        "m",
        f"mn {mach_value}",
        f"v {float(self.op_point.velocity)}",
        f"d {float(self.op_point.atmosphere.density())}",
        "g 9.81",
        "",
    ]

    p_bar = self.op_point.p * self.airplane.b_ref / (2 * self.op_point.velocity)
    q_bar = self.op_point.q * self.airplane.c_ref / (2 * self.op_point.velocity)
    r_bar = self.op_point.r * self.airplane.b_ref / (2 * self.op_point.velocity)
    run += [
        f"a a {float(self.op_point.alpha)}",
        f"b b {float(self.op_point.beta)}",
        f"r r {float(p_bar)}",
        f"p p {float(q_bar)}",
        f"y y {float(r_bar)}",
    ]

    for name, deflection in _iter_controls_from_geometry(self.airplane).items():
        if name:
            run += [f"d {name} {float(deflection)}"]

    run += ["x"]
    return run


def apply_avl_keystroke_patch():
    """Patch AeroSandbox's AVL wrapper to use this module's keystroke builder."""
    import aerosandbox as asb

    asb.AVL._default_keystroke_file_contents = _custom_keystrokes
    try:
        from aerosandbox.aerodynamics.aero_3D import avl as asb_avl_mod

        asb_avl_mod.AVL._default_keystroke_file_contents = _custom_keystrokes
    except Exception:
        pass


class patched_AVL(asb.AVL):
    """Patched AeroSandbox AVL subclass with reliable control-surface handling."""

    def write_avl(self, file_name="airplane.avl", write_cdcl=False, write_fuselage=False):
        """Write AVL geometry and record control-index ordering for later runs."""
        directory = Path(self.working_directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (file_name if isinstance(file_name, str) else str(file_name))
        
        original_fuselages = getattr(self.airplane, "fuselages", [])
        if not write_fuselage:
            self.airplane.fuselages = []
        try:
            super().write_avl(path)
        finally:
            if not write_fuselage:
                self.airplane.fuselages = original_fuselages

        axis_idx = {}
        for wing in getattr(self.airplane, "wings", []):
            surf = str(getattr(wing, "name", "")).strip().lower()
            for xs in getattr(wing, "xsecs", []):
                for cs in getattr(xs, "control_surfaces", []):
                    cname = str(getattr(cs, "name", "")).strip().lower()
                    axis = getattr(cs, "_avl_hinge_axis", None)
                    if axis is None:
                        axis = (0.0, 0.0, 1.0) if ("rudder" in cname or "vertical" in surf) else (0.0, 1.0, 0.0)
                    axis_idx[(surf, cname)] = tuple(float(x) for x in axis)

        lines = path.read_text().splitlines()
        current_surface = None

        def _first_data_line(index):
            while index < len(lines):
                stripped = lines[index].strip()
                if stripped and not stripped.startswith("#"):
                    return index
                index += 1
            return None

        control_order = []
        i = 0
        while i < len(lines):
            line = lines[i]

            if re.match(r"^\s*SURFACE\s*$", line, re.IGNORECASE):
                j = _first_data_line(i + 1)
                if j is not None:
                    current_surface = lines[j].strip().lower()
                    i = j
            elif re.match(r"^\s*CONTROL\s*$", line, re.IGNORECASE):
                j = _first_data_line(i + 1)
                if j is not None:
                    tokens = lines[j].split()
                    if len(tokens) >= 7:
                        cname = tokens[0].strip()
                        cname_l = cname.lower()
                        if cname not in control_order:
                            control_order.append(cname)

                        key = ((current_surface or ""), cname_l)
                        axis = axis_idx.get(key)
                        if axis is None:
                            axis = (0.0, 0.0, 1.0) if ("rudder" in cname_l or "vertical" in (current_surface or "")) else (0.0, 1.0, 0.0)
                        tokens[3] = f"{axis[0]:g}"
                        tokens[4] = f"{axis[1]:g}"
                        tokens[5] = f"{axis[2]:g}"
                        lines[j] = " ".join(tokens)
            i += 1

        if not write_cdcl:
            new_lines = []
            skip = 0
            for line in lines:
                if skip > 0:
                    skip -= 1
                    continue
                if line.strip() == "CDCL":
                    skip = 2
                    continue
                new_lines.append(line)
            lines = new_lines

        path.write_text("\n".join(lines))
        self._control_index_map = {name: idx + 1 for idx, name in enumerate(control_order)}

    def _default_keystroke_file_contents(self):
        """Build keystrokes that drive AVL controls by discovered index."""
        run = ["oper"]

        mach_attr = getattr(self.op_point, "mach", None)
        if callable(mach_attr):
            mach_value = float(mach_attr())
        elif mach_attr is not None:
            mach_value = float(mach_attr)
        else:
            speed_of_sound = float(self.op_point.atmosphere.speed_of_sound())
            mach_value = float(self.op_point.velocity) / speed_of_sound

        run += [
            "m",
            f"mn {mach_value}",
            f"v {float(self.op_point.velocity)}",
            f"d {float(self.op_point.atmosphere.density())}",
            "g 9.81",
            "",
        ]

        p_bar = self.op_point.p * self.airplane.b_ref / (2 * self.op_point.velocity)
        q_bar = self.op_point.q * self.airplane.c_ref / (2 * self.op_point.velocity)
        r_bar = self.op_point.r * self.airplane.b_ref / (2 * self.op_point.velocity)
        run += [
            f"a a {float(self.op_point.alpha)}",
            f"b b {float(self.op_point.beta)}",
            f"r r {float(p_bar)}",
            f"p p {float(q_bar)}",
            f"y y {float(r_bar)}",
        ]

        name_to_defl = {}
        for wing in getattr(self.airplane, "wings", []):
            for xs in getattr(wing, "xsecs", []):
                for cs in getattr(xs, "control_surfaces", []):
                    name = str(getattr(cs, "name", "")).strip()
                    if not name:
                        continue
                    deflection = float(getattr(cs, "deflection", 0.0) or 0.0)
                    if abs(deflection) > 0 or name not in name_to_defl:
                        name_to_defl[name] = deflection

        control_map = getattr(self, "_control_index_map", {})
        if not control_map:
            self.write_avl("airplane.avl")
            control_map = getattr(self, "_control_index_map", {})

        for name, deflection in name_to_defl.items():
            idx = control_map.get(name)
            if idx is not None:
                run += [f"d{idx} {float(deflection)}"]

        run += ["x"]
        return run

__all__ = ["apply_avl_keystroke_patch", "patched_AVL"]
