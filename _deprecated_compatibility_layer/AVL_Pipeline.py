"""Compatibility wrapper for the refactored AVL pipeline helpers."""

from ac_design_toolbox.avl import pipeline as _pipeline

globals().update(
    {
        name: value
        for name, value in vars(_pipeline).items()
        if not name.startswith("__")
    }
)

__all__ = getattr(_pipeline, "__all__", [name for name in globals() if not name.startswith("__")])
