"""Canal pieces, the floodgate gate, and the owner token, built with build123d.

A canal piece is the terrain tile from ``acequias.cad.hex_tile`` with a
rectangular groove cut into its top face, plus a round hole for the owner
token. The groove is one straight spoke from the hex center to the midpoint
of each edge the piece's ``PieceKind`` opens at rotation 0, joined by a round
hub at the center, so water reaches every opening. Only rotation 0 is
modeled: players turn the printed piece by hand.

Same CAD frame as ``hex_tile``: ``x`` east, ``y`` north, ``z`` up, in mm,
with each ``Hex.corners`` point used as ``(x, -y)``. Pieces are centered at
``x = y = 0`` with their bottom face on ``z = 0``.

Default sizes are provisional until the first print (README, Geometry
profile). Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

import math

from build123d import Face, Shape, Solid, Vector, Wire

from acequias.cad.hex_tile import (
    DEFAULT_CLEARANCE,
    DEFAULT_HEIGHT,
    DEFAULT_SIDE,
    hex_tile,
)
from acequias.hex import Direction, Hex
from acequias.model import PieceKind

GROOVE_WIDTH = 6.0
"""Groove width in mm, across the water's path."""

GROOVE_DEPTH = 1.5
"""Groove depth in mm, from the tile's top face."""

HOLE_DIAMETER = 4.0
"""Diameter in mm of the owner-token hole in each canal piece."""

HOLE_DEPTH = 2.0
"""Depth in mm of the owner-token hole, from the top face."""

CAP_DIAMETER = 7.0
"""Diameter in mm of the owner token's cap, which rests on the top face."""

CAP_HEIGHT = 1.2
"""Height in mm of the owner token's cap."""

FIT_TOLERANCE = 0.15
"""Gap in mm on each side between a floodgate or token peg and its slot."""

FLOODGATE_THICKNESS = 2.0
"""Size in mm of the floodgate along the groove."""

MIN_WALL = 0.8
"""Thinnest printable wall in mm: two widths of a 0.4 mm nozzle."""

PEG_GAP = 0.2
"""How much shorter than ``HOLE_DEPTH`` the token peg is, in mm, so the cap
sits flat on the piece instead of the peg bottoming out in the hole."""

HOLE_DISTANCE = 0.65
"""Distance of the hole center from the piece center, as a fraction of the
(shrunk) center-to-edge distance."""

_CUT_OVERSHOOT = 1.0
"""How far cutting tools reach past the faces they cut, in mm, so the cut
never leaves a zero-thickness skin."""


# --- Edges -------------------------------------------------------------------


def edge_midpoints(
    side: float = DEFAULT_SIDE, clearance: float = DEFAULT_CLEARANCE
) -> dict[Direction, tuple[float, float]]:
    """The midpoint ``(x, y)`` of each tile edge in the CAD frame, by direction.

    Uses the outline ``hex_tile(side, height, clearance)`` builds: the edge
    facing ``list(Direction)[i]`` runs from corner ``i`` to corner ``i + 1``
    of ``Hex(0, 0).corners``, each corner used as ``(x, -y)``.
    """
    _check_positive("side", side)
    _check_finite("clearance", clearance)
    if clearance < 0:
        raise ValueError(f"clearance must be >= 0, got {clearance!r}")
    inner_side = _inner_side(side, clearance)
    corners = [(x, -y) for x, y in Hex(0, 0).corners(inner_side)]
    return {
        direction: (
            (corners[i][0] + corners[(i + 1) % 6][0]) / 2,
            (corners[i][1] + corners[(i + 1) % 6][1]) / 2,
        )
        for i, direction in enumerate(Direction)
    }


# --- Canal pieces ------------------------------------------------------------


def canal_piece(
    kind: PieceKind,
    side: float = DEFAULT_SIDE,
    height: float = DEFAULT_HEIGHT,
    clearance: float = DEFAULT_CLEARANCE,
    groove_width: float = GROOVE_WIDTH,
    groove_depth: float = GROOVE_DEPTH,
    *,
    hole_diameter: float = HOLE_DIAMETER,
    hole_depth: float = HOLE_DEPTH,
) -> Solid:
    """One canal piece of ``kind`` at rotation 0, all sizes in mm.

    The piece is ``hex_tile(side, height, clearance)`` with a groove
    ``groove_width`` wide and ``groove_depth`` deep opening on exactly
    ``kind.edges(0)``, and a flat-bottomed hole for the owner token at
    ``token_hole_center(kind, side, clearance)``.

    Raises ``TypeError`` if ``kind`` is not a ``PieceKind``, and
    ``ValueError`` for the floodgate (use ``floodgate()``), and naming the
    parameter for a size that is not finite or not above 0, or that would
    leave less than ``MIN_WALL`` of material: beside the groove at an edge,
    under the groove or the hole, or between the hole and the groove or the
    outer face. It also raises if the cap of a default owner token
    (``CAP_DIAMETER``) would overlap the groove or overhang the outline.
    """
    _check_canal_kind(kind)
    _check_piece_sizes(side, height, clearance, groove_width, groove_depth)
    _check_positive("hole_diameter", hole_diameter)
    _check_positive("hole_depth", hole_depth)
    if height - hole_depth < MIN_WALL:
        raise ValueError(
            f"hole_depth {hole_depth!r} leaves {height - hole_depth:.2f} mm under "
            f"the hole for height {height!r}; needs at least {MIN_WALL} mm"
        )
    hole = _hole_center(kind, side, clearance)
    _check_hole_room(kind, side, clearance, groove_width, hole, hole_diameter)

    tile = hex_tile(side, height, clearance)
    groove = _groove_tool(kind, side, height, clearance, groove_width, groove_depth)
    hole_tool = Solid.make_cylinder(
        hole_diameter / 2, hole_depth + _CUT_OVERSHOOT
    ).translate((hole[0], hole[1], height - hole_depth))
    return _single_solid(tile - groove - hole_tool)


def token_hole_center(
    kind: PieceKind,
    side: float = DEFAULT_SIDE,
    clearance: float = DEFAULT_CLEARANCE,
) -> tuple[float, float]:
    """The ``(x, y)`` of the owner-token hole of ``kind`` in the CAD frame.

    The hole sits toward the midpoint of the closed edge farthest (by
    angle) from every opened edge, the first in ``Direction`` order on a
    tie, at ``HOLE_DISTANCE`` of the way from the center to that edge.
    It depends only on ``kind``, ``side`` and ``clearance``.
    """
    _check_canal_kind(kind)
    _check_positive("side", side)
    _check_finite("clearance", clearance)
    if clearance < 0:
        raise ValueError(f"clearance must be >= 0, got {clearance!r}")
    _inner_side_checked(side, clearance)
    return _hole_center(kind, side, clearance)


def _hole_center(kind: PieceKind, side: float, clearance: float) -> tuple[float, float]:
    midpoints = edge_midpoints(side, clearance)
    opened = kind.edges(0)
    units = {d: _unit(midpoints[d]) for d in Direction}

    def closeness(d: Direction) -> float:
        # Largest cosine to any opened spoke: smaller is farther away.
        # Rounded so float noise cannot break a tie between equal angles.
        return round(max(_dot(units[d], units[o]) for o in opened), 9)

    closed = [d for d in Direction if d not in opened]
    target = min(closed, key=closeness)  # min keeps the first on a tie
    mx, my = midpoints[target]
    return (mx * HOLE_DISTANCE, my * HOLE_DISTANCE)


def _groove_tool(
    kind: PieceKind,
    side: float,
    height: float,
    clearance: float,
    groove_width: float,
    groove_depth: float,
) -> Shape:
    """The solid removed for the groove: one spoke per opened edge, plus a hub."""
    floor = height - groove_depth
    tall = groove_depth + _CUT_OVERSHOOT
    half = groove_width / 2
    midpoints = edge_midpoints(side, clearance)
    tool: Shape = Solid.make_cylinder(half, tall).translate((0, 0, floor))
    for direction in kind.edges(0):
        mx, my = midpoints[direction]
        ux, uy = _unit((mx, my))
        px, py = -uy * half, ux * half  # across the groove
        ex, ey = mx + ux * _CUT_OVERSHOOT, my + uy * _CUT_OVERSHOOT
        outline = [
            Vector(px, py, floor),
            Vector(-px, -py, floor),
            Vector(ex - px, ey - py, floor),
            Vector(ex + px, ey + py, floor),
        ]
        spoke = Solid.extrude(
            Face(Wire.make_polygon(outline, close=True)), Vector(0, 0, tall)
        )
        tool = tool + spoke
    return tool


def _check_hole_room(
    kind: PieceKind,
    side: float,
    clearance: float,
    groove_width: float,
    hole: tuple[float, float],
    hole_diameter: float,
) -> None:
    """Check the hole and the default token cap fit beside the groove."""
    hole_radius = hole_diameter / 2
    cap_radius = CAP_DIAMETER / 2
    if hole_radius >= cap_radius:
        raise ValueError(
            f"hole_diameter {hole_diameter!r} must be smaller than the token cap "
            f"({CAP_DIAMETER} mm), or the cap falls into the hole"
        )
    to_groove = _distance_to_groove(kind, side, clearance, groove_width, hole)
    to_face = _distance_to_outline(side, clearance, hole)
    if to_groove - hole_radius < MIN_WALL:
        raise ValueError(
            f"groove_width {groove_width!r} and hole_diameter {hole_diameter!r} "
            f"leave {to_groove - hole_radius:.2f} mm between the token hole and the "
            f"groove; needs at least {MIN_WALL} mm"
        )
    if to_face - hole_radius < MIN_WALL:
        raise ValueError(
            f"side {side!r} with clearance {clearance!r} and hole_diameter "
            f"{hole_diameter!r} leave {to_face - hole_radius:.2f} mm between the "
            f"token hole and the outer face; needs at least {MIN_WALL} mm"
        )
    if to_groove < cap_radius:
        raise ValueError(
            f"groove_width {groove_width!r} leaves no room for the owner token's "
            f"cap ({CAP_DIAMETER} mm across): it would overlap the groove"
        )
    if to_face < cap_radius:
        raise ValueError(
            f"side {side!r} with clearance {clearance!r} leaves no room for the "
            f"owner token's cap ({CAP_DIAMETER} mm across): it would overhang "
            f"the outline"
        )


def _distance_to_groove(
    kind: PieceKind,
    side: float,
    clearance: float,
    groove_width: float,
    point: tuple[float, float],
) -> float:
    """Distance in the top face from ``point`` to the nearest groove wall."""
    half = groove_width / 2
    px, py = point
    best = math.hypot(px, py) - half  # the hub
    midpoints = edge_midpoints(side, clearance)
    for direction in kind.edges(0):
        mid = midpoints[direction]
        length = math.hypot(*mid) + _CUT_OVERSHOOT
        ux, uy = _unit(mid)
        along = px * ux + py * uy
        across = abs(-px * uy + py * ux)
        d_along = max(-along, 0.0, along - length)
        d_across = max(across - half, 0.0)
        best = min(best, math.hypot(d_along, d_across))
    return best


def _distance_to_outline(
    side: float, clearance: float, point: tuple[float, float]
) -> float:
    """Distance in the top face from ``point`` (inside) to the nearest edge."""
    px, py = point
    best = math.inf
    for mid in edge_midpoints(side, clearance).values():
        apothem = math.hypot(*mid)
        ux, uy = _unit(mid)
        best = min(best, apothem - (px * ux + py * uy))
    return best


# --- Floodgate ---------------------------------------------------------------


def floodgate(
    tolerance: float = FIT_TOLERANCE,
    groove_width: float = GROOVE_WIDTH,
    groove_depth: float = GROOVE_DEPTH,
    thickness: float = FLOODGATE_THICKNESS,
) -> Solid:
    """A rectangular gate, modeled as it sits in a groove, all sizes in mm.

    Bottom face on ``z = 0``, centered at ``x = y = 0``: ``x`` is across the
    groove (``groove_width - 2 * tolerance``), ``y`` along it
    (``thickness``), and ``z`` its height (``groove_depth``, so its top is
    flush with the tile's top).

    Raises ``ValueError`` naming the parameter for a size that is not finite
    or not above 0, a negative tolerance, a gate narrower than ``MIN_WALL``,
    or a ``thickness`` below ``MIN_WALL``.
    """
    _check_positive("groove_width", groove_width)
    _check_positive("groove_depth", groove_depth)
    _check_positive("thickness", thickness)
    _check_tolerance(tolerance)
    width = groove_width - 2 * tolerance
    if width < MIN_WALL:
        raise ValueError(
            f"tolerance {tolerance!r} leaves the gate {width:.2f} mm wide in a "
            f"{groove_width!r} mm groove; needs at least {MIN_WALL} mm"
        )
    if thickness < MIN_WALL:
        raise ValueError(
            f"thickness must be at least {MIN_WALL} mm, got {thickness!r}"
        )
    return Solid.make_box(width, thickness, groove_depth).translate(
        (-width / 2, -thickness / 2, 0)
    )


# --- Owner token -------------------------------------------------------------


def owner_token(
    tolerance: float = FIT_TOLERANCE,
    cap_diameter: float = CAP_DIAMETER,
    cap_height: float = CAP_HEIGHT,
) -> Solid:
    """A round cap with a peg that fits the owner-token hole, sizes in mm.

    Modeled the way it prints, without supports: the cap flat on ``z = 0``
    and the peg pointing up, centered at ``x = y = 0``. The peg is
    ``HOLE_DIAMETER - 2 * tolerance`` across and ``HOLE_DEPTH - PEG_GAP``
    long. The cap shows the player's color through the filament, so the
    token is plain.

    Raises ``ValueError`` naming the parameter for a size that is not finite
    or not above 0, a negative tolerance, a peg thinner than ``MIN_WALL``,
    or a cap no wider than the hole.
    """
    _check_tolerance(tolerance)
    _check_positive("cap_diameter", cap_diameter)
    _check_positive("cap_height", cap_height)
    peg_diameter = HOLE_DIAMETER - 2 * tolerance
    if peg_diameter < MIN_WALL:
        raise ValueError(
            f"tolerance {tolerance!r} leaves the peg {peg_diameter:.2f} mm across; "
            f"needs at least {MIN_WALL} mm"
        )
    if cap_diameter <= HOLE_DIAMETER:
        raise ValueError(
            f"cap_diameter must be larger than the hole ({HOLE_DIAMETER} mm), "
            f"got {cap_diameter!r}"
        )
    cap = Solid.make_cylinder(cap_diameter / 2, cap_height)
    peg = Solid.make_cylinder(peg_diameter / 2, HOLE_DEPTH - PEG_GAP).translate(
        (0, 0, cap_height)
    )
    return _single_solid(cap + peg)


# --- Helpers -----------------------------------------------------------------


def _check_canal_kind(kind: object) -> None:
    if not isinstance(kind, PieceKind):
        raise TypeError(f"kind must be a PieceKind, got {kind!r}")
    if not kind.is_canal:
        raise ValueError(
            "the floodgate is not a canal piece; build it with floodgate()"
        )


def _check_piece_sizes(
    side: float,
    height: float,
    clearance: float,
    groove_width: float,
    groove_depth: float,
) -> None:
    _check_positive("side", side)
    _check_positive("height", height)
    _check_finite("clearance", clearance)
    if clearance < 0:
        raise ValueError(f"clearance must be >= 0, got {clearance!r}")
    _check_positive("groove_width", groove_width)
    _check_positive("groove_depth", groove_depth)
    inner_side = _inner_side_checked(side, clearance)
    if height - groove_depth < MIN_WALL:
        raise ValueError(
            f"groove_depth {groove_depth!r} leaves {height - groove_depth:.2f} mm "
            f"under the groove for height {height!r}; needs at least {MIN_WALL} mm"
        )
    # Each opened edge keeps (edge length - groove width) / 2 on either side
    # of the groove; the same wall separates two grooves at a shared corner.
    wall = (inner_side - groove_width) / 2
    if wall < MIN_WALL:
        raise ValueError(
            f"groove_width {groove_width!r} leaves {wall:.2f} mm of edge on each "
            f"side of the groove; needs at least {MIN_WALL} mm"
        )


def _check_tolerance(tolerance: float) -> None:
    _check_finite("tolerance", tolerance)
    if tolerance < 0:
        raise ValueError(f"tolerance must be >= 0, got {tolerance!r}")


def _check_positive(name: str, value: float) -> None:
    _check_finite(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value!r}")


def _check_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")


def _inner_side(side: float, clearance: float) -> float:
    # The same shrink as hex_tile: each edge moves in by ``clearance``.
    return side - 2 * clearance / math.sqrt(3)


def _inner_side_checked(side: float, clearance: float) -> float:
    inner_side = _inner_side(side, clearance)
    if inner_side <= 0:
        raise ValueError(
            f"clearance {clearance!r} leaves no hexagon for side {side!r}"
        )
    return inner_side


def _unit(v: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*v)
    return (v[0] / length, v[1] / length)


def _dot(a: tuple[float, float], b: tuple[float, float]) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _single_solid(shape: Shape) -> Solid:
    solids = shape.solids()
    if len(solids) != 1:
        raise RuntimeError(f"expected one solid, got {len(solids)}")
    return solids[0]
