"""Axial hex coordinates for the Acequias board.

Hexes are pointy-top, so east and west are direct neighbors and the river
can run along the west edge. ``q`` grows to the east and ``r`` to the south;
the implicit third cube coordinate is ``s = -q - r``.

This module is pure: it depends on nothing else in ``acequias``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

SQRT3 = math.sqrt(3)


@dataclass(frozen=True, slots=True, order=True)
class Hex:
    """An immutable axial hex coordinate, usable as a dict key.

    Ordering is lexicographic on ``(q, r)``, which gives a fixed
    deterministic order for tie-breaks.
    """

    q: int
    r: int

    def __post_init__(self) -> None:
        if type(self.q) is int and type(self.r) is int:
            return  # the common case; anything else is checked in full below
        for name in ("q", "r"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(f"Hex.{name} must be an int, got {value!r}")

    @property
    def s(self) -> int:
        """Third cube coordinate, so that ``q + r + s == 0``."""
        return -self.q - self.r

    def __add__(self, other: Hex) -> Hex:
        if not isinstance(other, Hex):
            return NotImplemented
        return Hex(self.q + other.q, self.r + other.r)

    def __sub__(self, other: Hex) -> Hex:
        if not isinstance(other, Hex):
            return NotImplemented
        return Hex(self.q - other.q, self.r - other.r)

    def neighbor(self, direction: Direction) -> Hex:
        """The adjacent hex in ``direction``."""
        step = _STEP.get(direction) if isinstance(direction, Direction) else None
        if step is None:
            return self + direction.offset  # not a Direction: fails as it always has
        return Hex(self.q + step[0], self.r + step[1])

    def neighbors(self) -> tuple[Hex, ...]:
        """The 6 adjacent hexes, in ``Direction`` order (E, NE, NW, W, SW, SE)."""
        return tuple(self.neighbor(d) for d in Direction)

    def distance(self, other: Hex) -> int:
        """Number of steps between two hexes."""
        d = self - other
        return max(abs(d.q), abs(d.r), abs(d.s))

    def to_cube(self) -> tuple[int, int, int]:
        """Cube coordinates ``(q, r, s)``."""
        return (self.q, self.r, self.s)

    @classmethod
    def from_cube(cls, q: int, r: int, s: int) -> Hex:
        """Build a hex from cube coordinates; they must sum to zero."""
        if q + r + s != 0:
            raise ValueError(f"cube coordinates must sum to 0, got ({q}, {r}, {s})")
        return cls(q, r)

    def to_pixel(self, size: float) -> tuple[float, float]:
        """Center of this hex in the plane, for hexes of side ``size``.

        The origin hex is at ``(0, 0)``; ``x`` grows east and ``y`` grows
        south, in the same units as ``size`` (e.g. mm).
        """
        _check_size(size)
        x = size * (SQRT3 * self.q + SQRT3 / 2 * self.r)
        y = size * (1.5 * self.r)
        return (x, y)

    @classmethod
    def from_pixel(cls, x: float, y: float, size: float) -> Hex:
        """The hex containing point ``(x, y)``, for hexes of side ``size``."""
        _check_size(size)
        q = (SQRT3 / 3 * x - y / 3) / size
        r = (2 / 3 * y) / size
        return _round(q, r)

    def corners(self, size: float) -> tuple[tuple[float, float], ...]:
        """The 6 corner points of this hex, for hexes of side ``size``.

        Points are in the same plane and units as ``to_pixel`` (``x`` east,
        ``y`` south). The hex is pointy-top, so one corner points straight
        north and one straight south.

        Corners go counterclockwise (as seen on the board, north up),
        starting just below east: corner ``i`` sits at ``60 * i - 30``
        degrees counterclockwise from east. So the order is ESE, ENE, N,
        WNW, WSW, S, and the edge from corner ``i`` to corner ``i + 1``
        (mod 6) faces ``list(Direction)[i]``: corners 0-1 face E, 1-2 NE,
        2-3 NW, 3-4 W, 4-5 SW, 5-0 SE.
        """
        _check_size(size)
        cx, cy = self.to_pixel(size)
        points = []
        for i in range(6):
            angle = math.radians(60 * i - 30)
            # y grows south, so counterclockwise on the board means -sin.
            points.append((cx + size * math.cos(angle), cy - size * math.sin(angle)))
        return tuple(points)


class Direction(Enum):
    """The 6 neighbor directions of a pointy-top hex, counterclockwise from east."""

    E = (1, 0)
    NE = (1, -1)
    NW = (0, -1)
    W = (-1, 0)
    SW = (-1, 1)
    SE = (0, 1)

    @property
    def offset(self) -> Hex:
        return _OFFSET[self]

    def opposite(self) -> Direction:
        """The direction pointing the other way (E <-> W, NE <-> SW, NW <-> SE)."""
        return _OPPOSITE[self]

    def rotated(self, steps: int) -> Direction:
        """This direction turned ``steps`` x 60 degrees counterclockwise.

        Counterclockwise follows ``Direction`` order (E -> NE -> NW -> W ->
        SW -> SE -> E); negative ``steps`` turn clockwise, and any multiple
        of 6 gives the same direction.
        """
        if not isinstance(steps, int) or isinstance(steps, bool):
            raise TypeError(f"steps must be an int, got {steps!r}")
        return _ROTATED[self][steps % 6]


# Static tables, so hot paths look directions up instead of searching them.
_MEMBERS = tuple(Direction)
_STEP: dict[Direction, tuple[int, int]] = {d: d.value for d in _MEMBERS}
_OFFSET: dict[Direction, Hex] = {d: Hex(*d.value) for d in _MEMBERS}
_OPPOSITE: dict[Direction, Direction] = {d: _MEMBERS[(i + 3) % 6] for i, d in enumerate(_MEMBERS)}
_ROTATED: dict[Direction, tuple[Direction, ...]] = {
    d: tuple(_MEMBERS[(i + k) % 6] for k in range(6)) for i, d in enumerate(_MEMBERS)
}


def _check_size(size: float) -> None:
    """Reject a hex size that is not a finite positive number."""
    if not (math.isfinite(size) and size > 0):
        raise ValueError(f"size must be a finite number > 0, got {size!r}")


def _round(q: float, r: float) -> Hex:
    """Round fractional axial coordinates to the nearest hex."""
    s = -q - r
    rq, rr, rs = round(q), round(r), round(s)
    dq, dr, ds = abs(rq - q), abs(rr - r), abs(rs - s)
    if dq > dr and dq > ds:
        rq = -rr - rs
    elif dr > ds:
        rr = -rq - rs
    return Hex(int(rq), int(rr))
