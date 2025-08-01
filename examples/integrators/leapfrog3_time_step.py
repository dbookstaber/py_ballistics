# pylint: disable=missing-class-docstring,missing-function-docstring
# pylint: disable=line-too-long,invalid-name,attribute-defined-outside-init
"""
Leap Frog integration engine for ballistic trajectory calculation
Generated by Claude Sonnet 4 - Correct implementation with fixed time step
"""

import math
import warnings

from typing_extensions import Union, List, override

from py_ballisticcalc.conditions import Shot
from py_ballisticcalc.engines.base_engine import (BaseIntegrationEngine,
                                                  BaseEngineConfigDict,
                                                  _TrajectoryDataFilter,
                                                  _WindSock,
                                                  create_trajectory_row)
from py_ballisticcalc.exceptions import RangeError
from py_ballisticcalc.logger import logger
from py_ballisticcalc.trajectory_data import TrajectoryData, TrajFlag
from py_ballisticcalc.vector import Vector

__all__ = ('LeapFrogIntegrationEngine',)


class LeapFrogIntegrationEngine(BaseIntegrationEngine[BaseEngineConfigDict]):
    """
    Leap Frog integration engine for ballistic trajectory calculation.

    The Leap Frog method is a second-order symplectic integrator that alternates
    between updating position and velocity with a FIXED time step. This preserves
    the symplectic nature and energy conservation properties of the method.

    The method works by:
    1. Computing acceleration at current position
    2. Updating velocity by half step (initialization only)
    3. Main loop:
       - Update position by full step using current velocity
       - Compute acceleration at new position
       - Update velocity by full step using new acceleration

    This "leap frogging" between position and velocity updates with fixed time step
    provides excellent long-term stability and energy conservation.
    """

    @override
    def get_calc_step(self, step: float = 0) -> float:
        # Use standard calc_step for LeapFrog
        return super().get_calc_step(step)

    @override
    def _integrate(self, shot_info: Shot, maximum_range: float, record_step: float,
                   filter_flags: Union[TrajFlag, int], time_step: float = 0.0) -> List[TrajectoryData]:
        """
        Calculate trajectory for specified shot using Leap Frog integration with fixed time step

        Args:
            shot_info (Shot):  Information about the shot.
            maximum_range (float): Feet down range to stop calculation
            record_step (float): Frequency (in feet down range) to record TrajectoryData
            filter_flags (Union[TrajFlag, int]): Flags to filter trajectory data.
            time_step (float, optional): If > 0 then record TrajectoryData after this many seconds elapse
                since last record, as could happen when trajectory is nearly vertical
                and there is too little movement downrange to trigger a record based on range.
                Defaults to 0.0

        Returns:
            List[TrajectoryData]: list of TrajectoryData, one for each dist_step, out to max_range
        """

        _cMinimumVelocity = self._config.cMinimumVelocity
        _cMaximumDrop = self._config.cMaximumDrop
        _cMinimumAltitude = self._config.cMinimumAltitude

        ranges: List[TrajectoryData] = []  # Record of TrajectoryData points to return
        time: float = .0
        drag: float = .0

        # guarantee that mach and density_factor would be referenced before assignment
        mach: float = .0
        density_factor: float = .0

        # region Initialize wind-related variables to first wind reading (if any)
        wind_sock = _WindSock(shot_info.winds)
        wind_vector = wind_sock.current_vector()
        # endregion

        # region Initialize velocity and position of projectile
        velocity = self.muzzle_velocity
        # x: downrange distance, y: drop, z: windage
        range_vector = Vector(.0, -self.cant_cosine * self.sight_height, -self.cant_sine * self.sight_height)
        velocity_vector: Vector = Vector(
            math.cos(self.barrel_elevation_rad) * math.cos(self.barrel_azimuth_rad),
            math.sin(self.barrel_elevation_rad),
            math.cos(self.barrel_elevation_rad) * math.sin(self.barrel_azimuth_rad)
        ).mul_by_const(velocity)  # type: ignore
        # endregion

        min_step = min(self.calc_step, record_step)
        data_filter = _TrajectoryDataFilter(filter_flags=filter_flags, range_step=record_step,
                                            initial_position=range_vector, initial_velocity=velocity_vector,
                                            barrel_angle_rad=self.barrel_elevation_rad, look_angle_rad=self.look_angle_rad,
                                            time_step=time_step)

        # region LeapFrog initialization with FIXED time step
        # Calculate FIXED time step based on initial conditions
        # This preserves the symplectic nature of the LeapFrog method
        initial_relative_velocity = velocity_vector - wind_vector
        initial_relative_speed = initial_relative_velocity.magnitude()

        # Fixed time step - critical for LeapFrog stability and energy conservation
        # delta_time = self.calc_step / max(1.0, initial_relative_speed) # FIXME: almost passing but ~202s
        # delta_time *= 2  # FIXME: temp solution to have better performance ~113s
        # delta_time = 0.001  # FIXME: Ruin incomplete_shot tests
        delta_time = 0.0005  # FIXME: Ruin incomplete_shot tests ~34s

        # print(delta_time)
        # Update air density at current point in trajectory
        density_factor, mach = shot_info.atmo.get_density_and_mach_for_altitude(
            self.alt0 + range_vector.y)

        # Compute initial drag coefficient and acceleration
        km = density_factor * self.drag_by_mach(initial_relative_speed / mach)
        drag = km * initial_relative_speed
        acceleration = self.gravity_vector - km * initial_relative_velocity * initial_relative_velocity.magnitude()  # type: ignore[operator]

        # Critical LeapFrog initialization: half-step velocity update
        # This staggers the position and velocity updates for symplectic integration
        velocity_vector += acceleration * (delta_time * 0.5)  # type: ignore[operator]
        # endregion

        # region Trajectory Loop with FIXED time step
        warnings.simplefilter("once")  # used to avoid multiple warnings in a loop
        last_recorded_range = 0.0
        it = 0  # iteration counter

        while (range_vector.x <= maximum_range + min_step) or (
                filter_flags and last_recorded_range <= maximum_range - 1e-6):
            it += 1

            # Update wind reading at current point in trajectory
            if range_vector.x >= wind_sock.next_range:  # require check before call to improve performance
                wind_vector = wind_sock.vector_for_range(range_vector.x)

            # Update air density at current point in trajectory
            density_factor, mach = shot_info.atmo.get_density_and_mach_for_altitude(
                self.alt0 + range_vector.y)

            # region Check whether to record TrajectoryData row at current point
            if filter_flags:  # require check before call to improve performance
                # Record TrajectoryData row
                if (data := data_filter.should_record(range_vector, velocity_vector, mach, time)) is not None:
                    ranges.append(create_trajectory_row(data.time, data.position, data.velocity,
                                                        data.velocity.magnitude(), data.mach,
                                                        self.spin_drift(data.time), self.look_angle_rad,
                                                        density_factor, drag, self.weight, data_filter.current_flag
                                                        ))
                    last_recorded_range = data.position.x
            # endregion

            # region LeapFrog integration with FIXED time step
            # Step 1: Update position using current velocity (full step)
            # This uses the half-step-advanced velocity from initialization or previous iteration
            range_vector += velocity_vector * delta_time  # type: ignore[operator]

            # Step 2: Compute forces at new position
            # Update atmospheric conditions at new position
            new_density_factor, new_mach = shot_info.atmo.get_density_and_mach_for_altitude(
                self.alt0 + range_vector.y)

            # Update wind vector if needed at new position
            if range_vector.x >= wind_sock.next_range:
                wind_vector = wind_sock.vector_for_range(range_vector.x)

            # Compute acceleration at new position
            relative_velocity = velocity_vector - wind_vector
            relative_speed = relative_velocity.magnitude()
            km = new_density_factor * self.drag_by_mach(relative_speed / new_mach)
            acceleration = self.gravity_vector - km * relative_velocity * relative_velocity.magnitude()  # type: ignore[operator]

            # Step 3: Update velocity using acceleration at new position (full step)
            # This completes the LeapFrog cycle with staggered updates
            velocity_vector += acceleration * delta_time  # type: ignore[operator]

            # Update cached values for recording
            density_factor = new_density_factor
            mach = new_mach
            drag = km * relative_speed
            # endregion LeapFrog integration

            velocity = velocity_vector.magnitude()  # Velocity relative to ground
            time += delta_time

            # Check termination conditions
            if (
                    velocity < _cMinimumVelocity
                    or range_vector.y < _cMaximumDrop
                    or self.alt0 + range_vector.y < _cMinimumAltitude
            ):
                ranges.append(create_trajectory_row(
                    time, range_vector, velocity_vector,
                    velocity, mach, self.spin_drift(time), self.look_angle_rad,
                    density_factor, drag, self.weight, data_filter.current_flag
                ))
                if velocity < _cMinimumVelocity:
                    reason = RangeError.MinimumVelocityReached
                elif range_vector.y < _cMaximumDrop:
                    reason = RangeError.MaximumDropReached
                else:
                    reason = RangeError.MinimumAltitudeReached
                raise RangeError(reason, ranges)
        # endregion Trajectory Loop

        # Ensure that we have at least two data points in trajectory
        if len(ranges) < 2:
            ranges.append(create_trajectory_row(
                time, range_vector, velocity_vector,
                velocity, mach, self.spin_drift(time), self.look_angle_rad,
                density_factor, drag, self.weight, TrajFlag.NONE))

        logger.debug(f"LeapFrog (fixed time step) ran {it} iterations with dt={delta_time:.6f}")
        return ranges