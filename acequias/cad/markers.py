"""The Rules v3 board markers: the vineyard cluster and the bodega token.

- ``vineyard_cluster(varietal)``: the grape cluster the roulette plants on a
  vineyard corner. It stands on a small center foot, carries the owner's peg
  in a hole in its flat top, and shows the varietal's initials debossed on
  two flat sides (front and back, so both sides of the table read them).
  Clusters are printed in the varietal's color (``acequias.cad.piece_set``)
- ``bodega_token()``: a small building with a barrel-vault roof on a round
  base, one per player in the player's color

Both print without supports (the debossed letters and the door bridge only
a few mm). CAD frame as in ``acequias.cad.hex_tile``: ``x`` east, ``y``
north, ``z`` up, in mm, each piece centered at ``x = y = 0`` with its bottom
on ``z = 0``.

Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

import math

from build123d import Axis, Face, Plane, Pos, Solid, Vector, Wire, extrude

from acequias.cad.channel import HOLE_DEPTH, HOLE_DIAMETER
from acequias.cad.text import text_faces
from acequias.cad.tokens import _check_size, _single_solid
from acequias.model import Varietal

# --- Vineyard cluster ----------------------------------------------------------

VARIETAL_INITIALS: dict[Varietal, str] = {
    Varietal.MALBEC: "Ma",
    Varietal.SYRAH: "Sy",
    Varietal.BONARDA: "Bo",
    Varietal.CABERNET_SAUVIGNON: "CS",
    Varietal.MERLOT: "Me",
    Varietal.CABERNET_FRANC: "CF",
    Varietal.TORRONTES: "To",
    Varietal.CHARDONNAY: "Ch",
}
"""The initials each cluster shows."""

DEFAULT_CLUSTER_BASE_DIAMETER = 13.0
"""Width in mm of the vineyard cluster (its widest band)."""

DEFAULT_CLUSTER_HEIGHT = 13.0
"""Height in mm of the vineyard cluster, foot to flat top."""

CLUSTER_TOP_DIAMETER = 8.0
"""Diameter in mm of the flat top that holds the owner's peg."""

CLUSTER_FOOT_DIAMETER = 5.0
"""Diameter in mm of the center foot the cluster stands on."""

CLUSTER_FOOT_HEIGHT = 0.6
"""Height in mm of the foot's straight edge, under its flare."""

CLUSTER_FLAT_RATIO = 0.75
"""The two flat sides lie at ``+-CLUSTER_FLAT_RATIO * base_diameter / 2`` in ``y``,
so the piece is ``CLUSTER_FLAT_RATIO * base_diameter`` deep."""

INITIALS_DEPTH = 0.6
"""How deep in mm the initials are debossed into each flat side."""

INITIALS_FONT_SIZE = 5.0
"""Em size in mm of the initials at the default base; it scales with the base."""

MIN_CLUSTER_BASE = 11.0
"""Below this base the initials no longer fit the flat sides."""

MAX_CLUSTER_BASE = 20.0
"""Above this base the cluster covers too much of the hexes around its corner."""

MIN_CLUSTER_HEIGHT_V3 = 10.0
"""Below this height the band for the initials and the grapes no longer fit."""

MAX_CLUSTER_HEIGHT_V3 = 20.0
"""Above this height the cluster tips too easily on its small foot."""

_FLARE_RISE = 1.2
"""The flare under the band rises this many mm per mm out, a little steeper than
45 degrees, so its facets never overhang past 45 degrees."""

_BAND_SHARE = 0.25
"""Height of the smooth widest band, as a share of the height."""

_GRAPE_RADIUS = 1.4
"""Radius in mm of each grape on the upper cone (at the default base)."""

_GRAPE_CAP_ANGLE = math.radians(44)
"""Each grape shows a cap of this half-angle, so no face overhangs past 45 degrees."""

_GRAPE_PITCH = 1.7
"""Distance between grape centers in a ring and between rings, in grape radii."""

_OVERSHOOT = 1.0
"""How far in mm a cutting tool pokes past the face it cuts."""


def vineyard_cluster(
    varietal: Varietal,
    base_diameter: float = DEFAULT_CLUSTER_BASE_DIAMETER,
    height: float = DEFAULT_CLUSTER_HEIGHT,
) -> Solid:
    """The vineyard cluster of ``varietal``, sizes in mm, as printed.

    From the bed up: a center foot ``CLUSTER_FOOT_DIAMETER`` across, a flare
    (a little steeper than 45 degrees) out to the smooth band ``base_diameter`` across, then a
    cone of grapes that narrows to the flat top ``CLUSTER_TOP_DIAMETER``
    across, with the owner-peg hole (``HOLE_DIAMETER`` x ``HOLE_DEPTH``, the
    canal piece's) in its center. Two flat sides at
    ``y = +-CLUSTER_FLAT_RATIO * base_diameter / 2`` show the initials
    (``VARIETAL_INITIALS``) debossed ``INITIALS_DEPTH``. The bounding box is
    ``base_diameter`` x ``CLUSTER_FLAT_RATIO * base_diameter`` x ``height``.

    Raises ``ValueError`` naming the parameter for a varietal that is not a
    ``Varietal``, a size that is not finite or not above 0, or one outside
    ``MIN_CLUSTER_BASE``..``MAX_CLUSTER_BASE`` or
    ``MIN_CLUSTER_HEIGHT_V3``..``MAX_CLUSTER_HEIGHT_V3``.
    """
    if not isinstance(varietal, Varietal):
        raise ValueError(f"varietal must be a Varietal, got {varietal!r}")
    _check_size("base_diameter", base_diameter)
    _check_size("height", height)
    _check_range("base_diameter", base_diameter, MIN_CLUSTER_BASE, MAX_CLUSTER_BASE)
    _check_range("height", height, MIN_CLUSTER_HEIGHT_V3, MAX_CLUSTER_HEIGHT_V3)

    radius = base_diameter / 2
    scale = base_diameter / DEFAULT_CLUSTER_BASE_DIAMETER
    r = _GRAPE_RADIUS * scale
    protrusion = r * (1 - math.cos(_GRAPE_CAP_ANGLE))
    depth = r - protrusion  # how far each grape center lies inside the cone
    foot = CLUSTER_FOOT_DIAMETER / 2
    top = CLUSTER_TOP_DIAMETER / 2
    band_bottom = CLUSTER_FOOT_HEIGHT + _FLARE_RISE * (radius - foot)  # top of the flare
    band_top = band_bottom + _BAND_SHARE * height
    cone_bottom = radius - protrusion  # grapes on the cone stay inside the band's width
    if band_top + 2 * r > height:
        raise ValueError(
            f"height must leave room for the grapes above the band, got {height!r} "
            f"for base_diameter {base_diameter!r}"
        )

    profile = [
        Vector(0, 0, 0),
        Vector(foot, 0, 0),
        Vector(foot, 0, CLUSTER_FOOT_HEIGHT),
        Vector(radius, 0, band_bottom),
        Vector(radius, 0, band_top),
        Vector(cone_bottom, 0, band_top),
        Vector(top, 0, height),
        Vector(0, 0, height),
    ]
    core = Solid.revolve(Face(Wire.make_polygon(profile, close=True)), 360, Axis.Z)

    # Grapes in staggered rings along the cone, each center ``depth`` inside it.
    # Each sphere's axis runs along the cone's slope, so both poles stay buried.
    slope = Vector(top - cone_bottom, 0, height - band_top)
    length = slope.length
    along = slope / length
    inward = Vector(-along.Z, 0, along.X)  # points into the cone
    grapes: list[Solid] = []
    first, last = r, length - 0.6 * r
    rings = max(1, int((last - first) / (_GRAPE_PITCH * r)) + 1)
    for ring in range(rings):
        t = first + (last - first) * ring / max(1, rings - 1)
        rho = cone_bottom + along.X * t + inward.X * depth
        z = band_top + along.Z * t + inward.Z * depth
        count = max(4, int(2 * math.pi * rho / (_GRAPE_PITCH * r)))
        offset = math.pi * ring / count
        for i in range(count):
            phi = offset + 2 * math.pi * i / count
            c, s = math.cos(phi), math.sin(phi)
            axis = Vector(along.X * c, along.X * s, along.Z)
            grapes.append(Solid.make_sphere(r, Plane(origin=(rho * c, rho * s, z), z_dir=axis)))
    body = core.fuse(*grapes)

    # Trim to the flat top and the two flat sides, then the hole and the letters.
    flat = CLUSTER_FLAT_RATIO * radius
    big = base_diameter + 2 * _OVERSHOOT
    above = Pos(-big / 2, -big / 2, height) * Solid.make_box(big, big, big)
    sides = [
        Pos(-big / 2, y, -_OVERSHOOT) * Solid.make_box(big, big, height + 2 * _OVERSHOOT)
        for y in (flat, -flat - big)
    ]
    hole = Pos(0, 0, height - HOLE_DEPTH) * Solid.make_cylinder(
        HOLE_DIAMETER / 2, HOLE_DEPTH + _OVERSHOOT
    )
    text_z = (band_bottom + band_top) / 2
    letters = _initials_cutters(VARIETAL_INITIALS[varietal], INITIALS_FONT_SIZE * scale, flat, text_z)
    shape = body.cut(above, *sides, hole, *letters).clean()
    return _single_solid(shape, "vineyard_cluster")


def _initials_cutters(initials: str, font_size: float, flat: float, z: float) -> list[Solid]:
    """Cutters for the initials on both flat sides, centered at height ``z``.

    Each side reads upright from outside: on the south side (``y = -flat``)
    the letters run east, on the north side west.
    """
    faces = text_faces(initials, font_size)
    cutters = []
    for sign in (-1, 1):
        # The plane's normal points out of the side; its y_dir is up (+z).
        plane = Plane(
            origin=(0, sign * (flat + _OVERSHOOT), z),
            x_dir=(-sign, 0, 0),
            z_dir=(0, sign, 0),
        )
        placed = [plane.from_local_coords(face) for face in faces]
        cutters.append(extrude(placed, INITIALS_DEPTH + _OVERSHOOT, dir=(0, -sign, 0)))
    return cutters


# --- Bodega token --------------------------------------------------------------

DEFAULT_BODEGA_BASE_DIAMETER = 13.0
"""Diameter in mm of the bodega token's round base."""

DEFAULT_BODEGA_HEIGHT = 12.0
"""Height in mm of the bodega token, base to the top of the vault."""

BODEGA_BASE_THICKNESS = 1.2
"""Thickness in mm of the round base under the building."""

BODEGA_LENGTH_RATIO = 0.77
"""Length of the building (along ``x``, the vault's axis) over the base diameter."""

BODEGA_WIDTH_RATIO = 0.54
"""Width of the building (along ``y``) over the base diameter; the vault's radius
is half of it."""

DOOR_DEPTH = 0.6
"""How deep in mm the arched door is debossed into each gable end."""

MIN_BODEGA_BASE = 10.0
"""Below this base the walls around the door get thinner than 0.8 mm."""

MAX_BODEGA_BASE = 25.0
"""Above this base the token outgrows a hex."""


def bodega_token(
    base_diameter: float = DEFAULT_BODEGA_BASE_DIAMETER,
    height: float = DEFAULT_BODEGA_HEIGHT,
) -> Solid:
    """A bodega: a building with a barrel-vault roof on a round base, in mm.

    A disc ``base_diameter`` across and ``BODEGA_BASE_THICKNESS`` thick,
    with a block ``BODEGA_LENGTH_RATIO * base_diameter`` long (``x``) and
    ``BODEGA_WIDTH_RATIO * base_diameter`` wide (``y``) on it, topped by a
    half cylinder along ``x`` (the vault, which prints without supports),
    ``height`` high in all. An arched door is debossed ``DOOR_DEPTH`` into
    each gable end. The bounding box is ``base_diameter`` x
    ``base_diameter`` x ``height``.

    Raises ``ValueError`` naming the parameter for a size that is not finite
    or not above 0, a base outside ``MIN_BODEGA_BASE``..``MAX_BODEGA_BASE``,
    or a height that leaves the walls under the vault less than 1 mm.
    """
    _check_size("base_diameter", base_diameter)
    _check_size("height", height)
    _check_range("base_diameter", base_diameter, MIN_BODEGA_BASE, MAX_BODEGA_BASE)
    length = BODEGA_LENGTH_RATIO * base_diameter
    width = BODEGA_WIDTH_RATIO * base_diameter
    vault = width / 2
    wall = height - BODEGA_BASE_THICKNESS - vault
    if wall < 1.0:
        raise ValueError(
            f"height must be >= {BODEGA_BASE_THICKNESS + vault + 1.0:g} mm to leave 1 mm walls "
            f"under the vault, got {height!r}"
        )
    if height > 2 * base_diameter:
        raise ValueError(f"height must be <= 2 x base_diameter to stand, got {height!r}")

    base = Solid.make_cylinder(base_diameter / 2, BODEGA_BASE_THICKNESS)
    walls = Pos(-length / 2, -width / 2, 0) * Solid.make_box(
        length, width, BODEGA_BASE_THICKNESS + wall
    )
    roof = Solid.make_cylinder(
        vault, length, Plane(origin=(-length / 2, 0, BODEGA_BASE_THICKNESS + wall), z_dir=(1, 0, 0))
    )
    building = base.fuse(walls, roof)

    door_width = 0.4 * width
    door_square = min(0.5 * wall, wall - 0.8)  # straight part of the door, from the base
    cut_length = DOOR_DEPTH + _OVERSHOOT
    doors = []
    # Each door cutter starts DOOR_DEPTH inside its gable and pokes out past it.
    for x0 in (length / 2 - DOOR_DEPTH, -length / 2 - _OVERSHOOT):
        square = Pos(x0, -door_width / 2, BODEGA_BASE_THICKNESS) * Solid.make_box(
            cut_length, door_width, door_square
        )
        arch_plane = Plane(origin=(x0, 0, BODEGA_BASE_THICKNESS + door_square), z_dir=(1, 0, 0))
        doors += [square, Solid.make_cylinder(door_width / 2, cut_length, arch_plane)]
    return _single_solid(building.cut(*doors).clean(), "bodega_token")


def _check_range(name: str, value: float, low: float, high: float) -> None:
    if not low <= value <= high:
        raise ValueError(f"{name} must be {low:g} to {high:g} mm, got {value!r}")
