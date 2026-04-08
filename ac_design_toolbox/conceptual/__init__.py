"""Grouped conceptual-design APIs for AC_Design_Toolbox."""

from ac_design_toolbox.atmosphere import SAC, mach, mach_number, reynolds, reynolds_number, standard_atmosphere
from ac_design_toolbox.conceptual import geometry_tools as _geometry_tools
from ac_design_toolbox.conceptual import lifting_line as _lifting_line
from ac_design_toolbox.conceptual import performance as _performance
from ac_design_toolbox.conceptual import range_endurance as _range_endurance
from ac_design_toolbox.conceptual import takeoff as _takeoff
from ac_design_toolbox.conceptual import weights as _weights
from ac_design_toolbox.conceptual.geometry_tools import *
from ac_design_toolbox.conceptual.lifting_line import *
from ac_design_toolbox.conceptual.performance import *
from ac_design_toolbox.conceptual.range_endurance import *
from ac_design_toolbox.conceptual.takeoff import *
from ac_design_toolbox.conceptual.weights import *

__all__ = (
    _takeoff.__all__
    + _weights.__all__
    + _range_endurance.__all__
    + _performance.__all__
    + _geometry_tools.__all__
    + _lifting_line.__all__
    + ["SAC", "mach", "mach_number", "reynolds", "reynolds_number", "standard_atmosphere"]
)
