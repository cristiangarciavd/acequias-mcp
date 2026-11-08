"""The functional base of every terrain piece: a hexagonal prism.

The tile follows the board's hex convention (``acequias.hex``): pointy-top,
with its outline taken from ``Hex(0, 0).corners``, so each edge faces the
same ``Direction`` as in the game model.

CAD frame: ``x`` east, ``y`` north, ``z`` up, in mm. ``Hex.corners`` has
``y`` growing south, so each corner ``(x, y)`` is used as ``(x, -y)``.
The tile is centered at ``x = y = 0``, with its bottom face on ``z = 0``.

Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

import math
import os
from pathlib import Path

from build123d import Face, Shape, Solid, Vector, Wire
from build123d import export_stl as _b3d_export_stl

from acequias.hex import Hex

DEFAULT_SIDE = 16.0
"""Hex side in mm (README, Geometry profile); 18 mm is the fallback."""

DEFAULT_HEIGHT = 4.0
"""Functional tile height in mm (README, Geometry profile)."""

DEFAULT_CLEARANCE = 0.0
"""Gap in mm that each edge moves in, between neighboring printed tiles."""


def hex_tile(
    side: float = DEFAULT_SIDE,
    height: float = DEFAULT_HEIGHT,
    clearance: float = DEFAULT_CLEARANCE,
) -> Solid:
    """A pointy-top hexagonal prism, all sizes in mm.

    ``side`` is the nominal hex side, ``height`` the prism height, and
    ``clearance`` how far each edge moves in, so the outline is the hexagon
    of side ``side - 2 * clearance / sqrt(3)``.

    Raises ``ValueError`` naming the parameter if a value is not finite,
    ``side`` or ``height`` is not above 0, ``clearance`` is negative, or
    the clearance leaves no hexagon.
    """
    _check_finite("side", side)
    _check_finite("height", height)
    _check_finite("clearance", clearance)
    if side <= 0:
        raise ValueError(f"side must be > 0, got {side!r}")
    if height <= 0:
        raise ValueError(f"height must be > 0, got {height!r}")
    if clearance < 0:
        raise ValueError(f"clearance must be >= 0, got {clearance!r}")
    inner_side = side - 2 * clearance / math.sqrt(3)
    if inner_side <= 0:
        raise ValueError(
            f"clearance {clearance!r} leaves no hexagon for side {side!r}: "
            f"the remaining side {inner_side!r} must be > 0"
        )

    # Flip y: Hex.corners grows south, the CAD frame grows north. The flip
    # also turns the board's counterclockwise order into a counterclockwise
    # outline in the CAD frame, so the face normal points up (+z).
    outline = [Vector(x, -y, 0) for x, y in Hex(0, 0).corners(inner_side)]
    base = Face(Wire.make_polygon(outline, close=True))
    return Solid.extrude(base, Vector(0, 0, height))


def export_stl(shape: Shape, path: str | os.PathLike[str]) -> Path:
    """Write ``shape`` as a binary STL in mm and return its path.

    Takes any build123d shape. Creates the parent folder if needed and
    overwrites an existing file.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if not _b3d_export_stl(shape, out, ascii_format=False):
        raise RuntimeError(f"build123d could not write the STL to {out}")
    return out


def _check_finite(name: str, value: float) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number, got {value!r}")
