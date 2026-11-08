"""The small printed pieces: the grape cluster and the debt token.

Both are plain (the filament gives the player's color), print without
supports, and have a round footprint centered on the z axis.

CAD frame (as in ``acequias.cad.hex_tile``): ``x`` east, ``y`` north, ``z``
up, in mm. Each piece is centered at ``x = y = 0`` with its bottom face on
``z = 0``, the way it lies on the print plate.

Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

import math

from build123d import Axis, Face, Plane, Pos, Solid, Vector, Wire

# Grape cluster

DEFAULT_GRAPE_BASE_DIAMETER = 14.0
"""Diameter in mm of the grape cluster's round base (provisional)."""

DEFAULT_GRAPE_HEIGHT = 15.0
"""Total height in mm of the grape cluster, stem included (provisional)."""

MIN_GRAPE_DIAMETER = 2.0
"""Smallest grape sphere in mm: more than two 0.4 mm nozzle widths."""

MIN_GRAPE_TIERS = 3
"""The cluster always has at least this many tiers of grapes."""

MIN_CLUSTER_BASE_DIAMETER = 8.0
"""Below this base there is no room for 3 tiers of 2 mm grapes."""

MIN_CLUSTER_HEIGHT = 6.0
"""Below this height there is no room for 3 tiers of 2 mm grapes."""

MAX_CLUSTER_HEIGHT_RATIO = 1.5
"""The cluster may be at most this many times as tall as its base is wide."""

GRAPE_BASE_THICKNESS = 1.0
"""Height in mm of the flat disc the grapes stand on."""

STEM_DIAMETER = 1.2
"""Diameter in mm of the short stem on top of the cluster."""

_STEM_OUT = 0.5
"""How far the stem rises above the top grape, in grape radii."""

_BURY_ANGLE = math.radians(55)
"""Each grape's bottom cap, up to this angle from its lowest point, is buried
in the core. Faces steeper than 45 degrees past vertical are then never
exposed, with a margin for the mesh's facets."""

_TILT = math.radians(45)
"""Each ring grape's sphere axis leans this far from vertical toward the z
axis, so both of its poles lie inside the core (see ``_grape_centers``)."""

_POLE_MARGIN = 0.05
"""Minimum depth in mm of a buried pole inside the core."""

_EDGE_MARGIN = 0.1
"""Gap in mm between the outer grapes and the edge of the base."""

_POLE_LIFT = 0.2
"""How far in mm the bottom tier's lowest points sit above the plate."""

_TIER_PITCH = 1.15
"""Preferred vertical distance between tiers, in grape radii."""

_RING_PITCH = 1.5
"""Distance between neighboring grapes in a ring, in grape radii."""

_TOP_SHOULDER = 0.9
"""Radius of the core's flat top, in grape radii, so it hides in the top
grape."""


def grape_cluster(
    base_diameter: float = DEFAULT_GRAPE_BASE_DIAMETER,
    height: float = DEFAULT_GRAPE_HEIGHT,
) -> Solid:
    """A bunch of grapes on a flat round base, all sizes in mm.

    Round grapes (spheres of one size, at least ``MIN_GRAPE_DIAMETER``
    across) sit in rings, at least ``MIN_GRAPE_TIERS`` tiers, the widest at
    the bottom, with a single grape and a short stem on top. They are fused
    onto a hidden core (a disc ``GRAPE_BASE_THICKNESS`` thick under a cone)
    that buries the underside of every grape, so the piece prints without
    supports. The bounding box is ``base_diameter`` x ``base_diameter`` x
    ``height``.

    Raises ``ValueError`` naming the parameter if a size is not finite or
    not above 0, ``base_diameter`` is below ``MIN_CLUSTER_BASE_DIAMETER``,
    ``height`` is below ``MIN_CLUSTER_HEIGHT``, or ``height`` is above
    ``MAX_CLUSTER_HEIGHT_RATIO`` times ``base_diameter``.
    """
    _check_size("base_diameter", base_diameter)
    _check_size("height", height)
    if base_diameter < MIN_CLUSTER_BASE_DIAMETER:
        raise ValueError(
            f"base_diameter must be >= {MIN_CLUSTER_BASE_DIAMETER} mm to fit "
            f"{MIN_GRAPE_TIERS} tiers of grapes, got {base_diameter!r}"
        )
    if height < MIN_CLUSTER_HEIGHT:
        raise ValueError(
            f"height must be >= {MIN_CLUSTER_HEIGHT} mm to fit "
            f"{MIN_GRAPE_TIERS} tiers of grapes, got {height!r}"
        )
    if height > MAX_CLUSTER_HEIGHT_RATIO * base_diameter:
        raise ValueError(
            f"height must be <= {MAX_CLUSTER_HEIGHT_RATIO} x base_diameter "
            f"({MAX_CLUSTER_HEIGHT_RATIO * base_diameter!r} mm) to stand, "
            f"got {height!r}"
        )

    radius = base_diameter / 2
    r = grape_radius(base_diameter, height)
    top_z = height - r * (1 + _STEM_OUT)  # center of the single top grape
    shoulder = _TOP_SHOULDER * r

    core = _cluster_core(radius, shoulder, top_z)
    grapes = [
        Solid.make_sphere(r, Plane(origin=center, z_dir=axis))
        for center, axis in _grapes(radius, r, shoulder, top_z)
    ]
    # The stem starts inside the top grape and covers its upper pole.
    stem_bottom = top_z + r / 2
    stem = Pos(0, 0, stem_bottom) * Solid.make_cylinder(
        STEM_DIAMETER / 2, height - stem_bottom
    )
    return _single_solid(core.fuse(*grapes, stem).clean(), "grape_cluster")


def grape_radius(base_diameter: float, height: float) -> float:
    """The radius in mm of every grape of ``grape_cluster(base_diameter, height)``.

    A sixth of the base, limited to a fifth of the height. Within the
    limits that ``grape_cluster`` checks this is at least 1.2 mm, so every
    grape is at least ``MIN_GRAPE_DIAMETER`` across.
    """
    return max(min(base_diameter / 6, height / 5), MIN_GRAPE_DIAMETER / 2)


def _cluster_core(radius: float, shoulder: float, top_z: float) -> Solid:
    """The disc and cone that carry the grapes: a profile revolved about z.

    The profile runs from the axis out along the plate, up the disc's rim,
    along the cone to its flat top at the top grape's center, and back to
    the axis; the flat top lies inside the top grape.
    """
    profile = [
        Vector(0, 0, 0),
        Vector(radius, 0, 0),
        Vector(radius, 0, GRAPE_BASE_THICKNESS),
        Vector(shoulder, 0, top_z),
        Vector(0, 0, top_z),
    ]
    section = Face(Wire.make_polygon(profile, close=True))
    return Solid.revolve(section, 360, Axis.Z)


def _grapes(
    radius: float, r: float, shoulder: float, top_z: float
) -> list[tuple[Vector, Vector]]:
    """Center and sphere axis of every grape: rings in tiers, one on top.

    Two rules keep the piece printable and its STL clean:

    - Each grape's bottom cap, up to ``_BURY_ANGLE`` from its lowest point,
      lies inside the core, so no exposed face points down steeply. The
      core (disc plus cone) is convex, so it is enough that the outermost
      point of the cap's rim is under the cone's line and inside the disc.
    - Both poles of each sphere are buried (a sphere's poles mesh as
      degenerate triangles, which break the STL's watertightness). A ring
      grape's axis leans ``_TILT`` toward the z axis: its lower pole falls
      in the buried cap, its upper pole must be under the cone's line too.
      The top grape's axis is vertical: its lower pole is in the core, its
      upper pole in the stem.

    With the cone's slope ``k`` and ``h`` the height of its line at the
    axis, a point ``(rho, z)`` is under the line when ``z + k * rho <= h``.
    """
    k = (top_z - GRAPE_BASE_THICKNESS) / (radius - shoulder)
    h = top_z + k * shoulder
    margin = _POLE_MARGIN * math.hypot(1, k)
    sin_b, cos_b = math.sin(_BURY_ANGLE), math.cos(_BURY_ANGLE)
    sin_t, cos_t = math.sin(_TILT), math.cos(_TILT)

    bottom_z = r + _POLE_LIFT
    spread = top_z - bottom_z
    tiers = max(MIN_GRAPE_TIERS, int(spread / (_TIER_PITCH * r)) + 1)
    max_rho = radius - r - _EDGE_MARGIN

    grapes: list[tuple[Vector, Vector]] = []
    for tier in range(tiers - 1):
        z = bottom_z + spread * tier / (tiers - 1)
        rho = min(
            max_rho,
            # Bottom cap's outer rim point under the cone's line.
            (h - z + r * (cos_b - k * sin_b)) / k,
            # Upper pole (rho - r sin t, z + r cos t) under the cone's line.
            (h - margin - z - r * cos_t) / k + r * sin_t,
        )
        count = max(1, int(2 * math.pi * rho / (_RING_PITCH * r)))
        offset = math.pi * tier / count  # stagger the rings
        for i in range(count):
            phi = offset + 2 * math.pi * i / count
            cos_p, sin_p = math.cos(phi), math.sin(phi)
            center = Vector(rho * cos_p, rho * sin_p, z)
            axis = Vector(-sin_t * cos_p, -sin_t * sin_p, cos_t)
            grapes.append((center, axis))
    grapes.append((Vector(0, 0, top_z), Vector(0, 0, 1)))
    return grapes


# Debt token

DEFAULT_DEBT_DIAMETER = 12.0
"""Diameter in mm of a debt token (provisional)."""

DEFAULT_DEBT_THICKNESS = 2.0
"""Thickness in mm of a debt token (provisional)."""

DEBT_VALUES = (1, 5)
"""The values a debt token can show."""

PIP_DIAMETER = 2.0
"""Diameter in mm of a debossed pip."""

PIP_DEPTH = 0.6
"""Depth in mm of a debossed pip; each pip has a flat bottom."""

PIP_OFFSET = 0.2
"""The outer pips of a 5 sit at (+-PIP_OFFSET, +-PIP_OFFSET) x diameter."""

MIN_WALL = 0.8
"""Thinnest wall in mm: between pips and under a pip (two nozzle widths)."""

MIN_DEBT_DIAMETER = 9.9
"""Below this diameter the gap between the center and an outer pip of a 5
drops under ``MIN_WALL``."""

MIN_DEBT_THICKNESS = PIP_DEPTH + MIN_WALL
"""Below this thickness the floor under a pip is thinner than ``MIN_WALL``."""


def debt_token(
    value: int,
    diameter: float = DEFAULT_DEBT_DIAMETER,
    thickness: float = DEFAULT_DEBT_THICKNESS,
) -> Solid:
    """A flat disc with ``value`` (1 or 5) as debossed pips on top, in mm.

    Pips are ``PIP_DIAMETER`` round, ``PIP_DEPTH`` deep, flat-bottomed, laid
    out like a die face (see ``pip_positions``). No text: system fonts
    differ between machines.

    Raises ``ValueError`` naming the parameter if ``value`` is not exactly
    the int 1 or 5, a size is not finite or not above 0, ``diameter`` is
    below ``MIN_DEBT_DIAMETER``, or ``thickness`` is below
    ``MIN_DEBT_THICKNESS``.
    """
    if type(value) is not int or value not in DEBT_VALUES:
        raise ValueError(f"value must be the int 1 or 5, got {value!r}")
    _check_size("diameter", diameter)
    _check_size("thickness", thickness)
    if diameter < MIN_DEBT_DIAMETER:
        raise ValueError(
            f"diameter must be >= {MIN_DEBT_DIAMETER} mm to keep "
            f"{MIN_WALL} mm between pips, got {diameter!r}"
        )
    if thickness < MIN_DEBT_THICKNESS:
        raise ValueError(
            f"thickness must be >= {MIN_DEBT_THICKNESS:g} mm to keep "
            f"{MIN_WALL} mm under the pips, got {thickness!r}"
        )

    disc = Solid.make_cylinder(diameter / 2, thickness)
    # Each pip cutter starts at the pip's floor and pokes out above the top.
    pips = [
        Pos(x, y, thickness - PIP_DEPTH)
        * Solid.make_cylinder(PIP_DIAMETER / 2, PIP_DEPTH + 1.0)
        for x, y in pip_positions(value, diameter)
    ]
    return _single_solid(disc.cut(*pips).clean(), "debt_token")


def pip_positions(value: int, diameter: float) -> list[tuple[float, float]]:
    """The ``(x, y)`` pip centers in mm for ``value`` 1 or 5, like a die.

    One pip at the center, and for a 5 four more at
    ``(+-PIP_OFFSET * diameter, +-PIP_OFFSET * diameter)``.
    """
    if value == 1:
        return [(0.0, 0.0)]
    d = PIP_OFFSET * diameter
    return [(0.0, 0.0), (d, d), (-d, d), (-d, -d), (d, -d)]


# Shared helpers


def _check_size(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number, got {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
    if value <= 0:
        raise ValueError(f"{name} must be > 0, got {value!r}")


def _single_solid(shape, name: str) -> Solid:
    solids = shape.solids()
    if len(solids) != 1:
        raise RuntimeError(f"{name} came out as {len(solids)} solids, not 1")
    return solids[0]
