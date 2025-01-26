"""Bootstrap to load binary TrajectoryCalc extensions"""
from typing_extensions import Union, Final

from py_ballisticcalc.unit import Distance, PreferredUnits

from py_ballisticcalc.logger import logger
from py_ballisticcalc.trajectory_calc._trajectory_calc import (
    Config,
    get_correction,
    calculate_energy,
    calculate_ogw,
    create_trajectory_row,
    _TrajectoryDataFilter,
    _WindSock
)

cGravityConstant: Final[float] = -32.17405  # ft/s^2

#region Calculator settings
cMaxStepSize: Final[float] = 0.1  # Max integration step size in seconds
cMaxIterations: Final[int] = 20  # Max iterations to find TrajectoryCalc.zero_angle()
cZeroFindingAccuracy: Final[float] = 0.000005  # Vertical error in ft at zero distance
#endregion

#region Settings that control how far ballistic trajectory is calculated
cMinimumVelocity: Final[float] = 50.0  # fps
cMinimumAltitude: Final[float] = -1500.0  # ft above sea level
cMaximumDrop: Final[float] = -15000.0  # ft from firing altitude
#endregion

_globalUsePowderSensitivity: bool = False
_globalChartResolution: float = 0.2  # Feet

def reset_globals() -> None:
    # pylint: disable=global-statement
    global _globalUsePowderSensitivity
    _globalUsePowderSensitivity = False


try:
    # replace with cython based implementation
    from py_ballisticcalc_exts.trajectory_calc import TrajectoryCalc  # type: ignore
except ImportError as err:
    """Fallback to pure python"""
    from py_ballisticcalc.trajectory_calc._trajectory_calc import TrajectoryCalc

    logger.debug(err)

__all__ = (
    'TrajectoryCalc',
    'reset_globals',
    'cGravityConstant',
    'cMaxStepSize',
    'cMaxIterations',
    'cZeroFindingAccuracy',
    'cMinimumVelocity',
    'cMinimumAltitude',
    'cMaximumDrop',
    'Config',
    'calculate_energy',
    'calculate_ogw',
    'get_correction',
    'create_trajectory_row',
    '_TrajectoryDataFilter',
    '_WindSock'
)
