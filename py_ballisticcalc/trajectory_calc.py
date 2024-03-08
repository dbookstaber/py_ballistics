# pylint: disable=missing-class-docstring,missing-function-docstring,line-too-long,invalid-name
"""pure python trajectory calculation backend"""

import math
from dataclasses import dataclass
from typing import NamedTuple

from .conditions import Atmo, Shot, Wind
from .munition import Ammo
from .settings import Settings
from .trajectory_data import TrajectoryData, TrajFlag
from .unit import Distance, Angular, Velocity, Weight, Energy, Pressure, Temperature

__all__ = ('TrajectoryCalc', )

cZeroFindingAccuracy = 0.000005
cMinimumVelocity = 50.0
cMaximumDrop = -15000
cMaxIterations = 20
cGravityConstant = -32.17405


class CurvePoint(NamedTuple):
    a: float
    b: float
    c: float


@dataclass
class Vector:
    x: float
    y: float
    z: float

    def magnitude(self):
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def mul_by_const(self, a: float):
        return Vector(self.x * a, self.y * a, self.z * a)

    def mul_by_vector(self, b: 'Vector'):
        return self.x * b.x + self.y * b.y + self.z * b.z

    def add(self, b: 'Vector'):
        return Vector(self.x + b.x, self.y + b.y, self.z + b.z)

    def subtract(self, b: 'Vector'):
        return Vector(self.x - b.x, self.y - b.y, self.z - b.z)

    def negate(self):
        return Vector(-self.x, -self.y, -self.z)

    def normalize(self):
        m = self.magnitude()
        if math.fabs(m) < 1e-10:
            return Vector(self.x, self.y, self.z)
        return self.mul_by_const(1.0 / m)

    def __add__(self, other: 'Vector'):
        return self.add(other)

    def __radd__(self, other: 'Vector'):
        return self.add(other)

    def __iadd__(self, other: 'Vector'):
        return self.add(other)

    def __sub__(self, other: 'Vector'):
        return self.subtract(other)

    def __rsub__(self, other: 'Vector'):
        return self.subtract(other)

    def __isub__(self, other: 'Vector'):
        return self.subtract(other)

    def __mul__(self, other: [int, float, 'Vector']):
        if isinstance(other, (int, float)):
            return self.mul_by_const(other)
        if isinstance(other, Vector):
            return self.mul_by_vector(other)
        raise TypeError(other)

    def __rmul__(self, other: [int, float, 'Vector']):
        return self.__mul__(other)

    def __imul__(self, other):
        return self.__mul__(other)

    def __neg__(self):
        return self.negate()


class TrajectoryCalc:
    """All calculations are done in units of feet and fps"""

    def __init__(self, ammo: Ammo):
        self.ammo = ammo
        self._bc = self.ammo.dm.BC
        self._table_data = ammo.dm.drag_table
        self._curve = calculate_curve(self._table_data)

    def get_calc_step(self, step: float = 0):
        """Keep step under max_calc_step_size
        :param step: proposed step size
        :return: step size for calculations (in feet)
        """
        if step == 0:
            return Settings.get_max_calc_step_size() / 2.0
        return min(step, Settings.get_max_calc_step_size()) / 2.0

    def zero_angle(self, shot_info: Shot, distance: Distance):
        """Find barrel elevation to hit zero
        :param shot_info: Shot conditions
        :param distance: Zero distance
        """
        return self._zero_angle(shot_info, distance)

    def trajectory(self, shot_info: Shot, max_range: Distance, dist_step: Distance,
                   extra_data: bool = False):
        atmo = shot_info.atmo
        winds = shot_info.winds
        filter_flags = TrajFlag.RANGE

        if extra_data:
            #print('ext', extra_data)
            dist_step = Distance.Foot(0.2)
            filter_flags = TrajFlag.ALL
        return self._trajectory(self.ammo, atmo, shot_info, winds, max_range, dist_step, filter_flags)

    def _zero_angle(self, shot_info: Shot, distance: Distance):
        calc_step = self.get_calc_step()
        zero_distance = math.cos(shot_info.look_angle >> Angular.Radian) * (distance >> Distance.Foot)
        height_at_zero = math.sin(shot_info.look_angle >> Angular.Radian) * (distance >> Distance.Foot)
        maximum_range = zero_distance + calc_step
        sight_height = shot_info.weapon.sight_height >> Distance.Foot
        mach = shot_info.atmo.mach >> Velocity.FPS
        density_factor = shot_info.atmo.density_ratio
        cant_cosine = math.cos(shot_info.cant_angle >> Angular.Radian)
        cant_sine = math.sin(shot_info.cant_angle >> Angular.Radian)
        if Settings.USE_POWDER_SENSITIVITY:
            muzzle_velocity = shot_info.ammo.get_velocity_for_temp(shot_info.atmo.temperature) >> Velocity.FPS
        else:
            muzzle_velocity = shot_info.ammo.mv >> Velocity.FPS

        barrel_azimuth = 0.0
        barrel_elevation = math.atan(height_at_zero / zero_distance)
        iterations_count = 0
        zero_finding_error = cZeroFindingAccuracy * 2
        gravity_vector = Vector(.0, cGravityConstant, .0)

        # x - distance towards target, y - drop and z - windage
        while zero_finding_error > cZeroFindingAccuracy and iterations_count < cMaxIterations:
            velocity = muzzle_velocity
            time = 0.0
            range_vector = Vector(.0, -cant_cosine*sight_height, -cant_sine*sight_height)
            velocity_vector = Vector(
                math.cos(barrel_elevation) * math.cos(barrel_azimuth),
                math.sin(barrel_elevation),
                math.cos(barrel_elevation) * math.sin(barrel_azimuth)
            ) * velocity

            while range_vector.x <= maximum_range:
                if velocity < cMinimumVelocity or range_vector.y < cMaximumDrop:
                    break

                delta_time = calc_step / velocity_vector.x

                drag = density_factor * velocity * self.drag_by_mach(velocity / mach)
                velocity_vector -= (velocity_vector * drag - gravity_vector) * delta_time
                delta_range_vector = Vector(calc_step, velocity_vector.y * delta_time,
                                            velocity_vector.z * delta_time)
                range_vector += delta_range_vector
                velocity = velocity_vector.magnitude()
                time += delta_range_vector.magnitude() / velocity

                if math.fabs(range_vector.x - zero_distance) < 0.5 * calc_step:
                    zero_finding_error = math.fabs(range_vector.y - height_at_zero)
                    if zero_finding_error > cZeroFindingAccuracy:
                        barrel_elevation -= (range_vector.y - height_at_zero) / range_vector.x
                    break

            iterations_count += 1
        if zero_finding_error > cZeroFindingAccuracy:
            raise Exception(f'Zero vertical error {zero_finding_error} feet, after {iterations_count} iterations.')

        return Angular.Radian(barrel_elevation)

    def _trajectory(self, ammo: Ammo, atmo: Atmo,
                    shot_info: Shot, winds: list[Wind],
                    max_range: Distance, dist_step: Distance, filter_flags: TrajFlag):
        """Calculate trajectory for specified shot
        :return: list of TrajectoryData, one for each dist_step, out to max_range
        """
        time = 0
        look_angle = shot_info.look_angle >> Angular.Radian
        twist = shot_info.weapon.twist >> Distance.Inch
        length = ammo.dm.length >> Distance.Inch
        diameter = ammo.dm.diameter >> Distance.Inch
        weight = ammo.dm.weight >> Weight.Grain

        step = dist_step >> Distance.Foot
        calc_step = self.get_calc_step(step)

        maximum_range = (max_range >> Distance.Foot) + 1

        ranges_length = int(maximum_range / step) + 1
        len_winds = len(winds)
        current_wind = 0
        current_item = 0
        next_range_distance = .0
        previous_mach = .0
        ranges = []
        drag = 0
        stability_coefficient = 1.0
        twist_coefficient = 0
        next_wind_range = 1e7
        alt0 = atmo.altitude >> Distance.Foot

        barrel_elevation = shot_info.barrel_elevation >> Angular.Radian
        barrel_azimuth = shot_info.barrel_azimuth >> Angular.Radian
        sight_height = shot_info.weapon.sight_height >> Distance.Foot
        cant_cosine = math.cos(shot_info.cant_angle >> Angular.Radian)
        cant_sine = math.sin(shot_info.cant_angle >> Angular.Radian)
        range_vector = Vector(.0, -cant_cosine*sight_height, -cant_sine*sight_height)

        gravity_vector = Vector(.0, cGravityConstant, .0)

        if len_winds < 1:
            wind_vector = Vector(.0, .0, .0)
        else:
            if len_winds > 1:
                next_wind_range = winds[0].until_distance() >> Distance.Foot
            wind_vector = wind_to_vector(winds[0])

        if Settings.USE_POWDER_SENSITIVITY:
            velocity = ammo.get_velocity_for_temp(atmo.temperature) >> Velocity.FPS
        else:
            velocity = ammo.mv >> Velocity.FPS

        # x: downrange distance (towards target), y: drop, z: windage
        velocity_vector = Vector(math.cos(barrel_elevation) * math.cos(barrel_azimuth),
                                 math.sin(barrel_elevation),
                                 math.cos(barrel_elevation) * math.sin(barrel_azimuth)) * velocity

        if twist != 0 and length and diameter:
            stability_coefficient = calculate_stability_coefficient(shot_info.weapon.twist, ammo, atmo)
            twist_coefficient = 1 if twist > 0 else -1

        # With non-zero look_angle, rounding can suggest multiple adjacent zero-crossings
        seen_zero = TrajFlag.NONE  # Record when we see each zero crossing so we only register one
        if range_vector.y >= 0:
            seen_zero |= TrajFlag.ZERO_UP  # We're starting above zero; we can only go down
        elif range_vector.y < 0 and barrel_elevation < look_angle:
            seen_zero |= TrajFlag.ZERO_DOWN  # We're below and pointing down from look angle; no zeroes!

        while range_vector.x <= maximum_range + calc_step:
            _flag = TrajFlag.NONE

            if velocity < cMinimumVelocity or range_vector.y < cMaximumDrop:
                break

            if range_vector.x >= next_wind_range:
                current_wind += 1
                wind_vector = wind_to_vector(winds[current_wind])
                if current_wind == len_winds - 1:
                    next_wind_range = 1e7
                else:
                    next_wind_range = winds[current_wind].until_distance() >> Distance.Foot

            density_factor, mach = atmo.get_density_factor_and_mach_for_altitude(
                alt0 + range_vector.y)

            # Zero reference line is the sight line defined by look_angle
            reference_height = range_vector.x * math.tan(look_angle)

            # Zero-crossing checks
            if range_vector.x > 0:
                # If we haven't seen ZERO_UP, we look for that first
                if not seen_zero & TrajFlag.ZERO_UP:
                    if range_vector.y >= reference_height:
                        _flag |= TrajFlag.ZERO_UP
                        seen_zero |= TrajFlag.ZERO_UP
                # We've crossed above sight line; now look for crossing back through it
                elif not seen_zero & TrajFlag.ZERO_DOWN:
                    if range_vector.y < reference_height:
                        _flag |= TrajFlag.ZERO_DOWN
                        seen_zero |= TrajFlag.ZERO_DOWN

            # Mach crossing check
            if (velocity / mach <= 1) and (previous_mach > 1):
                _flag |= TrajFlag.MACH

            # Next range check
            if range_vector.x >= next_range_distance:
                _flag |= TrajFlag.RANGE
                next_range_distance += step
                current_item += 1

            if _flag & filter_flags:  # Record TrajectoryData row
                windage = range_vector.z
                if twist != 0:  # Add spin drift to windage
                    windage += (1.25 * (stability_coefficient + 1.2)
                                * math.pow(time, 1.83) * twist_coefficient) / 12
                ranges.append(create_trajectory_row(
                    time, range_vector, velocity_vector, velocity,
                    mach, windage, look_angle, reference_height,
                    density_factor, drag, weight, _flag.value
                ))
                if current_item == ranges_length:
                    break

            previous_mach = velocity / mach

            delta_time = calc_step / velocity_vector.x

            velocity_adjusted = velocity_vector - wind_vector
            velocity = velocity_adjusted.magnitude()
            drag = density_factor * velocity * self.drag_by_mach(velocity / mach)
            velocity_vector -= (velocity_adjusted * drag - gravity_vector) * delta_time
            delta_range_vector = Vector(calc_step,
                                        velocity_vector.y * delta_time,
                                        velocity_vector.z * delta_time)
            range_vector += delta_range_vector
            velocity = velocity_vector.magnitude()
            time += delta_range_vector.magnitude() / velocity

        return ranges

    def drag_by_mach(self, mach: float):
        """ Drag force = V^2 * Cd * AirDensity * S / 2m where:
            cStandardDensity of Air = 0.076474 lb/ft^3
            S is cross-section = d^2 pi/4, where d is bullet diameter in inches
            m is bullet mass in pounds
        BC contains m/d^2 in units lb/in^2, which we multiply by 144 to convert to lb/ft^2
        Thus: The magic constant found here = StandardDensity * pi / (4 * 2 * 144)
        """
        cd = calculate_by_curve(self._table_data, self._curve, mach)
        return cd * 2.08551e-04 / self._bc


def calculate_stability_coefficient(twist_rate: Distance, ammo: Ammo, atmo: Atmo):
    weight = ammo.dm.weight >> Weight.Grain
    diameter = ammo.dm.diameter >> Distance.Inch
    twist = math.fabs(twist_rate >> Distance.Inch) / diameter
    length = (ammo.dm.length >> Distance.Inch) / diameter
    ft = atmo.temperature >> Temperature.Fahrenheit
    mv = ammo.mv >> Velocity.FPS
    pt = atmo.pressure >> Pressure.InHg
    sd = 30 * weight / (
            math.pow(twist, 2) * math.pow(diameter, 3) * length * (1 + math.pow(length, 2))
    )
    fv = math.pow(mv / 2800, 1.0 / 3.0)
    ftp = ((ft + 460) / (59 + 460)) * (29.92 / pt)
    return sd * fv * ftp


def wind_to_vector(wind: Wind) -> Vector:
    """Calculate wind vector to add to projectile velocity vector each iteration:
        Aerodynamic drag is function of velocity relative to the air stream.

    Wind angle of zero is blowing from behind shooter
    Wind angle of 90-degree is blowing towards shooter's right

    NB: Presently we can only define Wind in the x-z plane, not any vertical component.
    """
    # Downrange (x-axis) wind velocity component:
    range_component = (wind.velocity >> Velocity.FPS) * math.cos(wind.direction_from >> Angular.Radian)
    # Cross (z-axis) wind velocity component:
    cross_component = (wind.velocity >> Velocity.FPS) * math.sin(wind.direction_from >> Angular.Radian)
    return Vector(range_component, 0, cross_component)


def create_trajectory_row(time: float, range_vector: Vector, velocity_vector: Vector, velocity: float,
                          mach: float, windage: float, look_angle: float, reference_height: float,
                          density_factor: float, drag: float, weight: float, flag: int):
    drop_adjustment = get_correction(range_vector.x, range_vector.y - reference_height)
    windage_adjustment = get_correction(range_vector.x, windage)
    trajectory_angle = math.atan(velocity_vector.y / velocity_vector.x)

    return TrajectoryData(
        time= time,
        distance= Distance.Foot(range_vector.x),
        velocity= Velocity.FPS(velocity),
        mach= velocity / mach,
        drop= Distance.Foot(range_vector.y),
        target_drop= Distance.Foot(range_vector.y - reference_height),
        drop_adj= Angular.Radian(drop_adjustment),
        windage= Distance.Foot(windage),
        windage_adj= Angular.Radian(windage_adjustment),
        look_distance= Distance.Foot(range_vector.x / math.cos(look_angle)),
        look_height= Distance.Foot(reference_height),
        angle = Angular.Radian(trajectory_angle),
        density_factor = density_factor-1,
        drag = drag,
        energy = Energy.FootPound(calculate_energy(weight, velocity)),
        ogw = Weight.Pound(calculate_ogw(weight, velocity)),
        flag = flag
    )


def get_correction(distance: float, offset: float):
    """:return: Sight adjustment in radians"""
    if distance != 0:
        return math.atan(offset / distance)
    return 0  # None


def calculate_energy(bullet_weight: float, velocity: float):
    """:return: energy in ft-lbs"""
    return bullet_weight * math.pow(velocity, 2) / 450400


def calculate_ogw(bullet_weight: float, velocity: float):
    """:return: Optimal Game Weight in pounds"""
    return math.pow(bullet_weight, 2) * math.pow(velocity, 3) * 1.5e-12


def calculate_curve(data_points):
    """
    :param DragTable: data_points
    :return: List[CurvePoints] to interpolate drag coefficient
    """
    # rate, x1, x2, x3, y1, y2, y3, a, b, c
    # curve = []
    # curve_point
    # num_points, len_data_points, len_data_range

    rate = (data_points[1]['CD'] - data_points[0]['CD']) \
           / (data_points[1]['Mach'] - data_points[0]['Mach'])
    curve = [CurvePoint(0, rate, data_points[0]['CD'] - data_points[0]['Mach'] * rate)]
    len_data_points = int(len(data_points))
    len_data_range = len_data_points - 1

    for i in range(1, len_data_range):
        x1 = data_points[i - 1]['Mach']
        x2 = data_points[i]['Mach']
        x3 = data_points[i + 1]['Mach']
        y1 = data_points[i - 1]['CD']
        y2 = data_points[i]['CD']
        y3 = data_points[i + 1]['CD']
        a = ((y3 - y1) * (x2 - x1) - (y2 - y1) * (x3 - x1)) / (
                (x3 * x3 - x1 * x1) * (x2 - x1) - (x2 * x2 - x1 * x1) * (x3 - x1))
        b = (y2 - y1 - a * (x2 * x2 - x1 * x1)) / (x2 - x1)
        c = y1 - (a * x1 * x1 + b * x1)
        curve_point = CurvePoint(a, b, c)
        curve.append(curve_point)

    num_points = len_data_points
    rate = (data_points[num_points - 1]['CD'] - data_points[num_points - 2]['CD']) / \
           (data_points[num_points - 1]['Mach'] - data_points[num_points - 2]['Mach'])
    curve_point = CurvePoint(
        0, rate, data_points[num_points - 1]['CD'] - data_points[num_points - 2]['Mach'] * rate
    )
    curve.append(curve_point)
    return curve


def calculate_by_curve(data: list, curve: list, mach: float):
    """Binary search for drag coefficient based on Mach number
    :param DragTable: data
    :param List: Output of calculate_curve(data)
    :return float: drag coefficient
    """
    num_points = int(len(curve))
    mlo = 0
    mhi = num_points - 2

    while mhi - mlo > 1:
        mid = int(math.floor(mhi + mlo) / 2.0)
        if data[mid]['Mach'] < mach:
            mlo = mid
        else:
            mhi = mid

    if data[mhi]['Mach'] - mach > mach - data[mlo]['Mach']:
        m = mlo
    else:
        m = mhi
    curve_m = curve[m]
    return curve_m.c + mach * (curve_m.b + curve_m.a * mach)
