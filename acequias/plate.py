"""Plate layout: place pieces on the printer's build plate.

Pieces come in as footprints (a hexagon, a circle, or a rectangle, in mm)
and are laid out on deterministic grids on a ``bed`` (default the Bambu Lab
A1's 256 x 256 mm), spilling onto more plates when one is full.

- Hexes go on a honeycomb grid: rows along x, every second row shifted by
  half a step, with centers from ``Hex.to_pixel(side + gap / sqrt(3))`` so
  every pair of neighboring hexes is exactly ``gap`` apart.
- Circles and rectangles go on a square grid of cells sized to their
  bounding box plus the gap.

Pieces are grouped by color group and grid type; each plate holds one group
only, so it prints with one filament. Coordinates are the footprint's center
in mm from the bed's front-left corner, x to the right and y to the back.

This module is pure layout math: standard library only, no CAD.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Union

from acequias.hex import SQRT3, Hex

DEFAULT_BED = (256.0, 256.0)
DEFAULT_MARGIN = 5.0
DEFAULT_GAP = 3.0

# Slack for floating-point error when counting how many cells fit.
_EPS = 1e-9


def _check_positive(name: str, value: float) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{name} must be a finite number > 0, got {value!r}")


def _check_non_negative(name: str, value: float) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
        or value < 0
    ):
        raise ValueError(f"{name} must be a finite number >= 0, got {value!r}")


# --- Footprints -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HexFootprint:
    """A pointy-top hexagon of side ``side`` mm.

    Corners point to the back and front (+-y) and flats face +-x, so it is
    ``sqrt(3) * side`` wide (x) and ``2 * side`` deep (y).
    """

    side: float

    def __post_init__(self) -> None:
        _check_positive("side", self.side)

    @property
    def width(self) -> float:
        return SQRT3 * self.side

    @property
    def depth(self) -> float:
        return 2 * self.side

    def outline(self, x: float, y: float) -> tuple[tuple[float, float], ...]:
        """The 6 corners of this hexagon centered at ``(x, y)``."""
        return tuple((x + cx, y + cy) for cx, cy in Hex(0, 0).corners(self.side))


@dataclass(frozen=True, slots=True)
class CircleFootprint:
    """A circle of diameter ``diameter`` mm."""

    diameter: float

    def __post_init__(self) -> None:
        _check_positive("diameter", self.diameter)

    @property
    def width(self) -> float:
        return self.diameter

    @property
    def depth(self) -> float:
        return self.diameter


@dataclass(frozen=True, slots=True)
class RectFootprint:
    """An axis-aligned rectangle ``width`` (x) by ``depth`` (y) mm."""

    width: float
    depth: float

    def __post_init__(self) -> None:
        _check_positive("width", self.width)
        _check_positive("depth", self.depth)


Footprint = Union[HexFootprint, CircleFootprint, RectFootprint]


@dataclass(frozen=True, slots=True)
class Piece:
    """A piece to place: a unique ``id``, its ``footprint``, and its color group."""

    id: str
    footprint: Footprint
    color_group: str

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError(f"piece id must be a non-empty string, got {self.id!r}")
        if not isinstance(self.footprint, (HexFootprint, CircleFootprint, RectFootprint)):
            raise ValueError(
                f"piece {self.id!r} footprint must be a HexFootprint, "
                f"CircleFootprint, or RectFootprint, got {self.footprint!r}"
            )
        if not isinstance(self.color_group, str):
            raise ValueError(
                f"piece {self.id!r} color_group must be a string, got {self.color_group!r}"
            )


# --- Output ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Placement:
    """Where a piece goes: its footprint's center in mm and its rotation.

    ``x`` and ``y`` are measured from the bed's front-left corner, x to the
    right and y to the back. ``rotation`` is in degrees about z, always 0
    here (pieces keep their modeled orientation).
    """

    piece_id: str
    x: float
    y: float
    rotation: float = 0.0


@dataclass(frozen=True, slots=True)
class Plate:
    """One build plate: its number (from 1), color group, and placements."""

    number: int
    color_group: str
    placements: tuple[Placement, ...]


# --- Grids ----------------------------------------------------------------


def _fit(available: float, item: float, step: float) -> int:
    """How many items of size ``item`` fit in ``available`` at pitch ``step``."""
    if available + _EPS < item:
        return 0
    return int(math.floor((available - item) / step + _EPS)) + 1


def _hex_cells(
    side: float, origin: tuple[float, float], room: tuple[float, float], gap: float
) -> list[tuple[float, float]]:
    """Honeycomb cell centers in fill order (left to right, front to back)."""
    pitch = side + gap / SQRT3
    width, depth = SQRT3 * side, 2 * side
    step_x = SQRT3 * pitch
    step_y = 1.5 * pitch
    rows = _fit(room[1], depth, step_y)
    per_row = (_fit(room[0], width, step_x), _fit(room[0] - step_x / 2, width, step_x))
    x0 = origin[0] + width / 2
    y0 = origin[1] + depth / 2
    cells = []
    for r in range(rows):
        for c in range(per_row[r % 2]):
            # Axial q = c - r // 2 keeps the even rows aligned and shifts the
            # odd rows by half a step to the right.
            px, py = Hex(c - r // 2, r).to_pixel(pitch)
            # to_pixel's y grows "south"; here row 0 is the frontmost and
            # rows go toward the back, so the offsets map straight onto +y.
            cells.append((x0 + px, y0 + py))
    return cells


def _square_cells(
    width: float, depth: float, origin: tuple[float, float], room: tuple[float, float], gap: float
) -> list[tuple[float, float]]:
    """Square-grid cell centers in fill order (left to right, front to back)."""
    cols = _fit(room[0], width, width + gap)
    rows = _fit(room[1], depth, depth + gap)
    return [
        (origin[0] + width / 2 + c * (width + gap), origin[1] + depth / 2 + r * (depth + gap))
        for r in range(rows)
        for c in range(cols)
    ]


# --- Layout ---------------------------------------------------------------


def layout_plates(
    pieces: Iterable[Piece],
    *,
    bed: tuple[float, float] = DEFAULT_BED,
    margin: float = DEFAULT_MARGIN,
    gap: float = DEFAULT_GAP,
) -> list[Plate]:
    """Lay ``pieces`` out on as many plates as needed, in order.

    Pieces are grouped by color group and grid type (hex, or square for
    circles and rectangles), and groups get plates in the order they first
    appear. Within a group every cell is sized to the largest footprint,
    smaller pieces sit centered in their cell, and pieces fill the grid in
    input order, one plate before the next.

    Raises ``ValueError`` for a bad bed, margin, or gap, a bed with no room
    inside the margins, a duplicate id, or a piece too big for an empty plate.
    """
    try:
        bed_w, bed_d = bed
    except (TypeError, ValueError):
        raise ValueError(f"bed must be a (width, depth) pair, got {bed!r}") from None
    _check_positive("bed width", bed_w)
    _check_positive("bed depth", bed_d)
    _check_non_negative("margin", margin)
    _check_non_negative("gap", gap)
    room = (bed_w - 2 * margin, bed_d - 2 * margin)
    if room[0] <= 0 or room[1] <= 0:
        raise ValueError(
            f"bed {bed!r} has no room inside a margin of {margin!r} "
            f"(room left: {room[0]!r} x {room[1]!r})"
        )
    origin = (float(margin), float(margin))

    pieces = list(pieces)
    seen: set[str] = set()
    for piece in pieces:
        if not isinstance(piece, Piece):
            raise ValueError(f"each piece must be a Piece, got {piece!r}")
        if piece.id in seen:
            raise ValueError(f"duplicate piece id {piece.id!r}")
        seen.add(piece.id)
        fp = piece.footprint
        if fp.width > room[0] + _EPS or fp.depth > room[1] + _EPS:
            raise ValueError(
                f"piece {piece.id!r} is too big for the plate: its footprint is "
                f"{fp.width:.2f} x {fp.depth:.2f} mm, the room inside the margins "
                f"is {room[0]:.2f} x {room[1]:.2f} mm"
            )

    groups: dict[tuple[str, str], list[Piece]] = {}
    for piece in pieces:
        kind = "hex" if isinstance(piece.footprint, HexFootprint) else "square"
        groups.setdefault((piece.color_group, kind), []).append(piece)

    plates: list[Plate] = []
    for (color, kind), members in groups.items():
        if kind == "hex":
            side = max(p.footprint.side for p in members)
            cells = _hex_cells(side, origin, room, gap)
        else:
            width = max(p.footprint.width for p in members)
            depth = max(p.footprint.depth for p in members)
            cells = _square_cells(width, depth, origin, room, gap)
        # Every piece fits on its own, so the largest one gives at least one cell.
        assert cells, "a fitting piece must leave at least one cell"
        for start in range(0, len(members), len(cells)):
            chunk = members[start : start + len(cells)]
            placements = tuple(
                Placement(piece.id, x, y, 0.0) for piece, (x, y) in zip(chunk, cells)
            )
            plates.append(Plate(len(plates) + 1, color, placements))
    return plates
