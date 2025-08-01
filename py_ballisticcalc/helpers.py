import bisect
import math
from typing import Callable, Any, Final, List, Tuple, Optional

from py_ballisticcalc.conditions import Shot
from py_ballisticcalc.exceptions import RangeError
from py_ballisticcalc.interface import Calculator
from py_ballisticcalc.trajectory_data import HitResult, TrajFlag, TrajectoryData
from py_ballisticcalc.unit import Velocity, Distance

EARTH_GRAVITY_CONSTANT_IN_SI: Final[float] = 9.81  # Acceleration due to gravity (m/s^2)


def must_fire(interface: Calculator, shot: Shot, trajectory_range: Distance, extra_data: bool = False,
              **kwargs) -> Tuple[HitResult, Optional[RangeError]]:
    """wrapper function to resolve RangeError and get HitResult"""
    try:
        # try to get valid result
        return interface.fire(shot, trajectory_range, **kwargs, extra_data=extra_data), None
    except RangeError as err:
        # directly init hit result with incomplete data before exception occurred
        return HitResult(shot, err.incomplete_trajectory, extra=extra_data), err


def vacuum_range(
        velocity: float,
        angle_in_degrees: float,
        gravity: float = EARTH_GRAVITY_CONSTANT_IN_SI
) -> float:
    """
    Distance for a vacuum ballistic trajectory to return to its starting height.
       Vacuum means projectile flies with no drag force, so this distance will overestimate
       range in presence of atmospheric drag force.

    Args:
        velocity: Launch velocity in units of gravity*seconds.
        launch_angle_deg: Launch angle in degrees above horizontal.
        gravity: Acceleration due to gravity (default: EARTH_GRAVITY_CONSTANT_IN_SI).

    Returns:
        The horizontal range in units of velocity*seconds.
    """
    angle_rad = math.radians(angle_in_degrees)
    if gravity < 0:
        gravity = -gravity
    return (velocity ** 2 * math.sin(2 * angle_rad)) / gravity

def vacuum_time_to_zero(
        velocity: float,
        launch_angle_deg: float,
        gravity: float = EARTH_GRAVITY_CONSTANT_IN_SI
) -> float:
    """
    Time for a ballistic trajectory (in a vacuum) to return to its starting height.

    Args:
        velocity: Launch velocity in units of gravity*seconds.
        launch_angle_deg: Launch angle in degrees above horizontal.
        gravity: Acceleration due to gravity (default: EARTH_GRAVITY_CONSTANT_IN_SI).

    Returns:
        Time in seconds to return to starting height.
    """
    angle_rad = math.radians(launch_angle_deg)
    if gravity < 0:
        gravity = -gravity
    return 2 * velocity * math.sin(angle_rad) / gravity

def solve_velocity_for_vacuum_time_to_zero(
        time_to_zero: float,
        launch_angle_deg: float,
        gravity: float = EARTH_GRAVITY_CONSTANT_IN_SI
) -> float:
    """
    Solves for the launch velocity (m/s) needed for vacuum_time_to_zero to equal time_to_zero.

    Args:
        time_to_zero: Desired time to return to starting height (seconds).
        launch_angle_deg: Launch angle in degrees above horizontal.
        gravity: Acceleration due to gravity (default: EARTH_GRAVITY_CONSTANT_IN_SI).

    Returns:
        Launch velocity in units of gravity*seconds.
    """
    angle_rad = math.radians(launch_angle_deg)
    if gravity < 0:
        gravity = -gravity
    return (time_to_zero * gravity) / (2 * math.sin(angle_rad))


class BisectWrapper:
    """Wrapper for usage with bisect_for_condition."""

    def __init__(self, array: List, callable: Callable) -> None:
        self.array = array
        self.callable = callable

    def __getitem__(self, index: int) -> Any:
        return self.callable(self.array[index])

    def check_condition(self, index: int) -> bool:
        return self.callable(self.array[index])

    def __len__(self) -> int:
        return len(self.array)


def bisect_for_monotonic_condition(arr: List, wrapper: BisectWrapper) -> int:
    """ Perform search in the ordered array for the first point, satisfying monotonic condition.

        Monotonic condition is a condition, which is consistently increases or decreases.
        For a bisection algorithm, a monotonic condition means the function maintains a consistent direction:
        Monotonically increasing: Each subsequent value is greater than or equal to the previous
        Monotonically decreasing: Each subsequent value is less than or equal to the previous
        WARNING: if condition for which you are searching is not monotonic, use
        `find_first_index_matching_condition`.
    """
    idx = bisect.bisect_left(wrapper, True, 0, len(arr))
    if idx >= len(arr):
        return -1
    if wrapper.check_condition(idx):
        return idx
    return -1


def find_first_index_matching_condition(
        shot: HitResult, condition: Callable[[TrajectoryData], int]
) -> int:
    """Search sequentially for the index of first point in the trajectory, which matches condition.
       Returns:
            Index of the first point, matching condition, and 1 if no such point was found.
    """
    for i, e in enumerate(shot.trajectory):
        if condition(e):
            return i
    return -1


def find_index_of_point_with_flag(shot: HitResult, flag: int = TrajFlag.ZERO_DOWN) -> int:
    """Find index of first point, for which `flag` is set.
       Returns:
            Index of first point with TrajFlag.ZERO_DOWN `.
            -1 if no such point was found.
     """
    return find_first_index_matching_condition(shot, lambda p: p.flag & flag)


def find_mach_point_index(shot: HitResult) -> int:
    """Find index of point for which TrjFlag.MACH was set.
       Note - this requires calling calculator with extra_data=True.
       Returns:
            Index of first point with TrajFlag.ZERO_DOWN `.
            -1 if no such point was found.
    """
    return find_index_of_point_with_flag(shot, TrajFlag.MACH)


def find_touch_point_index(shot: HitResult) -> int:
    """Find index of point when earth was hit by the bullet.
       Note - this requires calling calculator with extra_data=True.
       Returns:
            Index of first point with TrajFlag.ZERO_DOWN `.
            -1 if no such point was found.
    """
    return find_index_of_point_with_flag(shot, TrajFlag.ZERO_DOWN)


def find_velocity_less_than_index(
        shot: HitResult, velocity_in_units: float, velocity_unit=Velocity.MPS
) -> int:
    """Find index of point where velocity became less than provided velocity.
       Note - this requires calling calculator with extra_data=True.
       Returns:
            Index of first point with velocity less  than `velocity_in_units`.
            -1  if no such point was found.
    """
    return find_first_index_matching_condition(
        shot, lambda p: (p.velocity >> velocity_unit) < velocity_in_units
    )


def find_first_index_satisfying_monotonic_condition(
        arr: List[TrajectoryData], monotonic_condition: Callable[[Any], bool]
) -> int:
    # Find the index where the condition first becomes true
    # Uses bisect to find the first index satisfying the condition.
    return bisect_for_monotonic_condition(arr, BisectWrapper(arr, monotonic_condition))


def find_nearest_index_satisfying_monotonic_condition(arr: List[TrajectoryData], target_value: float,
                                                      value_getter: Callable[[TrajectoryData], float]):
    """
    Finds the index of the object with the nearest value to the target value.
    This performs bisect search for target value, and then compares differences from target value
    to previous and next index, and select index with the smallest difference.
    In case of tie, the smaller index is returned.

    Args:
        arr: The sorted array of trajectory data (always true for time, and almost always
               true for distances (except for extreme cases)).
        target_value: int or float - The target value to find the nearest object for.
        value_getter: function which returns the compared value

    Returns:
        The index of the object with the nearest target value. In case of tie, the smaller index is returned.

    """
    # Find the position where target_time would fit
    pos = bisect.bisect_left(BisectWrapper(arr, value_getter), target_value)

    # Compare neighbors to find the nearest index
    if pos == 0:
        return 0
    if pos == len(arr):
        return len(arr) - 1
    before = pos - 1
    after = pos
    if abs(value_getter(arr[before]) - target_value) <= abs(
            value_getter(arr[after]) - target_value
    ):
        return before
    return after


def find_index_of_point_for_distance(
        shot: HitResult, distance: float, distance_unit=Distance.Meter
) -> int:
    """Find index of point, for which distance is bigger or equal to given `distance`.
       Returns:
            Index of point, where distance >= distance of point.
            -1 if no such point was found.
    """

    def distance_ge(p: TrajectoryData) -> bool:
        return (p.distance >> distance_unit) >= distance

    # return find_first_index_matching_condition(shot, distance_is_bigger_or_equal)
    return find_first_index_satisfying_monotonic_condition(
        shot.trajectory, distance_ge
    )


def find_index_for_time_point(
        shot: HitResult,
        time: float,
        strictly_bigger_or_equal: bool = True,
        max_time_deviation_in_seconds: float = 1,
) -> int:
    """Find index of time point with nearest time to provided `time`.
       If `strictly_bigger_or_equal` is set, then the first point with time equal to bigger than time is returned.
       Otherwise, the index with smaller deviation will be returned.
       Returns -1 if no such time point exists, or if points with existing time in shot.trajectory have deviation
       bigger than `max_time_deviation_in_seconds`.
    """
    if max_time_deviation_in_seconds < 0:
        raise ValueError(
            f"Max time deviation should be bigger then zero, but was {max_time_deviation_in_seconds}"
        )
    if time < 0:
        raise ValueError(f"Illegal searched time passed {time}")
    if strictly_bigger_or_equal:
        return find_first_index_satisfying_monotonic_condition(
            shot.trajectory, lambda e: e.time - time >= 0
        )
    else:
        index = find_nearest_index_satisfying_monotonic_condition(
            shot.trajectory, time, lambda e: e.time
        )
        if abs(shot.trajectory[index].time - time) <= max_time_deviation_in_seconds:
            return index
        return -1


def find_time_for_distance_in_shot(
        shot: HitResult, distance_in_unit: float, distance_unit=Distance.Meter
) -> float:
    """Finds time corresponding to certain distance being reached in shot.
    Distance exceed maximal distance in shoot (i.e., no information is available),
    then float('NaN') is returned.
    """
    point_index = find_index_of_point_for_distance(
        shot, distance_in_unit, distance_unit
    )
    if point_index >= 0:
        return shot[point_index].time
    return float("NaN")
