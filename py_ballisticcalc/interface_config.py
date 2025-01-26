from typing_extensions import TypedDict, Optional
from py_ballisticcalc.trajectory_calc import (
    Config,
)
from py_ballisticcalc import trajectory_calc

__all__ = (
    "Config",
    "InterfaceConfigDict",
    "create_interface_config",
)


class InterfaceConfigDict(TypedDict, total=False):
    cGravityConstant: float
    cMaxStepSize: float
    cZeroFindingAccuracy: float
    cMaxIterations: int
    cMinimumVelocity: float
    cMinimumAltitude: float
    cMaximumDrop: float
    chart_resolution: float


def create_interface_config(interface_config: Optional[InterfaceConfigDict] = None) -> Config:
    config = InterfaceConfigDict(
        cGravityConstant=trajectory_calc.cGravityConstant,
        cMaxStepSize=trajectory_calc.cMaxStepSize,
        cMaxIterations=trajectory_calc.cMaxIterations,
        cZeroFindingAccuracy=trajectory_calc.cZeroFindingAccuracy,
        cMinimumVelocity=trajectory_calc.cMinimumVelocity,
        cMinimumAltitude=trajectory_calc.cMinimumAltitude,
        cMaximumDrop=trajectory_calc.cMaximumDrop,
        chart_resolution=trajectory_calc._globalChartResolution,
    )
    if interface_config is not None and isinstance(interface_config, dict):
        config.update(interface_config)
    return Config(**config)
