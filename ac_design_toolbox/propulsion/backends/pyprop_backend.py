"""Optional PyProp adapter scaffold for future propulsion comparisons."""

from __future__ import annotations


def require_pyprop():
    """Return the imported PyProp package or raise a clear optional-backend error."""
    try:
        import pyprop
    except ModuleNotFoundError as exc:
        raise ModuleNotFoundError(
            "PyProp is required for this optional backend. It is not a core "
            "AC_Design_Toolbox dependency, so install PyProp separately before "
            "using ac_design_toolbox.propulsion.backends.pyprop_backend."
        ) from exc
    return pyprop


class PyPropAdapter:
    """Placeholder adapter for future PyProp-backed propulsion workflows.

    PyProp has useful propulsion-unit workflows, but this first pass keeps the
    ACDT core independent and avoids reverse-engineering an unavailable package.
    This class records the intended adapter location and fails explicitly until
    a tested mapping from ACDT dataclasses to PyProp objects is added.
    """

    def __init__(self) -> None:
        """Verify PyProp is importable before constructing the placeholder."""
        self.pyprop = require_pyprop()

    def evaluate(self, *args, **kwargs):
        """Raise until a concrete PyProp mapping is implemented and tested."""
        raise NotImplementedError(
            "PyPropAdapter is a scaffold. Add a tested mapping from ACDT motor, ESC, battery, "
            "and propeller objects to PyProp before using this backend."
        )


__all__ = [
    "PyPropAdapter",
    "require_pyprop",
]
