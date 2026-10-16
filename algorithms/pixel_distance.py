"""Measure health-bar-center observations in camera-relative image pixels."""
from dataclasses import dataclass
import math


def point(value):
    if value is None:
        return None
    if len(value) != 2 or any(not isinstance(x, (float, int)) or not math.isfinite(x) for x in value):
        raise ValueError('a point needs two finite coordinates, or None')
    return tuple(value)


@dataclass(frozen=True)
class Observation:
    time: float
    units: dict
    origin: tuple | None = None
    scale_id: str = 'unscaled_pixels'

    def __post_init__(self):
        if not isinstance(self.time, (int, float)) or not math.isfinite(self.time):
            raise ValueError('time must be finite')
        point(self.origin)
        for position in self.units.values():
            point(position)


def position(observation, unit):
    center = point(observation.units.get(unit))
    origin = point(observation.origin)
    if center is None or origin is None:
        return None
    return center[0]-origin[0], center[1]-origin[1]


def distance(observation, first, second):
    """Same-frame pair distance needs no ground landmark."""
    a, b = point(observation.units.get(first)), point(observation.units.get(second))
    return None if a is None or b is None else math.hypot(a[0]-b[0], a[1]-b[1])


def displacement(previous, current, unit):
    """Translation-corrected pixel displacement; not game-unit movement speed."""
    if current.time <= previous.time:
        raise ValueError('observation times must increase')
    if current.scale_id != previous.scale_id:
        raise ValueError('different scales/projections cannot be compared directly')
    a, b = position(previous, unit), position(current, unit)
    if a is None or b is None:
        return None
    dx, dy = b[0]-a[0], b[1]-a[1]
    return dict(dt=current.time-previous.time, dx_px=dx, dy_px=dy,
                distance_px=math.hypot(dx,dy))
