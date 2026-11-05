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
        return self + direction.offset

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
        x = size * (SQRT3 * self.q + SQRT3 / 2 * self.r)
        y = size * (1.5 * self.r)
        return (x, y)

    @classmethod
    def from_pixel(cls, x: float, y: float, size: float) -> Hex:
        """The hex containing point ``(x, y)``, for hexes of side ``size``."""
        q = (SQRT3 / 3 * x - y / 3) / size
        r = (2 / 3 * y) / size
        return _round(q, r)


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
        return Hex(*self.value)

    def opposite(self) -> Direction:
        """The direction pointing the other way (E <-> W, NE <-> SW, NW <-> SE)."""
        members = list(Direction)
        return members[(members.index(self) + 3) % 6]


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
