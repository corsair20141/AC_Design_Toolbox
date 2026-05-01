"""Package-first API for the refactored AC_Design_Toolbox."""

from ac_design_toolbox.aircraft_config import *
from ac_design_toolbox.atmosphere import *
from ac_design_toolbox.conceptual import *
from ac_design_toolbox.energy import *
from ac_design_toolbox.mission import *
from ac_design_toolbox.api import *

from ac_design_toolbox.aircraft_config import __all__ as _aircraft_config_all
from ac_design_toolbox.atmosphere import __all__ as _atmosphere_all
from ac_design_toolbox.api import __all__ as _api_all
from ac_design_toolbox.conceptual import __all__ as _conceptual_all
from ac_design_toolbox.energy import __all__ as _energy_all
from ac_design_toolbox.mission import __all__ as _mission_all

__all__ = (
    list(_aircraft_config_all)
    + list(_atmosphere_all)
    + list(_conceptual_all)
    + list(_energy_all)
    + list(_mission_all)
    + list(_api_all)
)

try:
    from ac_design_toolbox.avl import *
    from ac_design_toolbox.geometry import *

    from ac_design_toolbox.avl import __all__ as _avl_all
    from ac_design_toolbox.geometry import __all__ as _geometry_all

    __all__ += list(_geometry_all) + list(_avl_all)
except (ImportError, ModuleNotFoundError):
    # Geometry and AVL features depend on AeroSandbox and related tooling.
    pass
