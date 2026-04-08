"""Compatibility wrapper for the refactored AeroSandbox geometry helpers."""

from ac_design_toolbox.geometry import builders as _builders

globals().update(
    {
        name: value
        for name, value in vars(_builders).items()
        if not name.startswith("__")
    }
)

__all__ = getattr(_builders, "__all__", [name for name in globals() if not name.startswith("__")])
