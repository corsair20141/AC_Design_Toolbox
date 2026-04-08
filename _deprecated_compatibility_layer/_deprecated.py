"""Compatibility wrapper for the preserved legacy AVL workflow."""

from ac_design_toolbox.legacy import deprecated_avl as _deprecated_avl

globals().update(
    {
        name: value
        for name, value in vars(_deprecated_avl).items()
        if not name.startswith("__")
    }
)

__all__ = getattr(_deprecated_avl, "__all__", [name for name in globals() if not name.startswith("__")])
