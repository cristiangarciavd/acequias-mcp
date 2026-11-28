"""The QR plate: a printed QR code to the online rulebook, glued inside the box.

``qr_plate(language)`` is a thin plate with the QR code's dark modules raised
on top and a small label ("REGLAS" or "RULES") under the code, in the bundled
font (``acequias.cad.text``).
Change filament at ``base_height`` so the modules and the label print in a
second color.

The QR matrices are stored as text in ``acequias/cad/data/qr_<language>.txt``
(one row per line, ``1`` dark, ``0`` light, the 4-module quiet zone
included, ``#`` lines are comments). They were made once with ``uvx segno``
(not a project dependency); each file's header holds the exact command.

CAD frame (as in ``acequias.cad.hex_tile``): ``x`` east, ``y`` north, ``z``
up, in mm. The plate is centered at ``x = y = 0`` with its bottom face on
``z = 0``; the code is at the north end, the label in a band at the south.

Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

from importlib.resources import files

from build123d import Compound, Face, Pos, Solid, extrude

from acequias.cad.text import text_faces
from acequias.cad.tokens import _check_size, _single_solid

QR_LANGUAGES: tuple[str, ...] = ("reglas", "rules")
"""The plate variants: the Spanish and the English rulebook."""

QR_URLS: dict[str, str] = {
    "reglas": "https://cristiangarciavd.github.io/acequias-mcp/reglas/",
    "rules": "https://cristiangarciavd.github.io/acequias-mcp/rules/",
}
"""The URL each stored matrix encodes."""

QR_LABELS: dict[str, str] = {"reglas": "REGLAS", "rules": "RULES"}
"""The label printed under each code."""

QUIET_ZONE = 4
"""Light modules around the code, included in the stored matrix."""

DEFAULT_QR_SIZE = 45.0
"""Width in mm of the plate, which is also the side of the code with its quiet zone."""

DEFAULT_QR_BASE_HEIGHT = 1.0
"""Thickness in mm of the plate under the modules."""

DEFAULT_QR_MODULE_HEIGHT = 0.6
"""How far in mm the dark modules and the label rise above the plate."""

DEFAULT_QR_LABEL_BAND = 6.0
"""Depth in mm of the band under the code that holds the label."""

MIN_MODULE = 1.0
"""Smallest QR module in mm, so a phone reads the printed code."""

MIN_WALL = 0.8
"""Thinnest wall in mm (two 0.4 mm nozzle widths): the plate under the modules."""

MIN_RAISE = 0.4
"""Lowest module height in mm: two 0.2 mm layers of the second color."""

LABEL_FONT_RATIO = 0.9
"""The label's em size over ``label_band``: capitals about 0.6 of the band deep."""

MIN_LABEL_BAND = 6.0
"""Smallest label band in mm: below it the label's strokes get thinner than 0.8 mm."""

_GROW = 0.01
"""Each raised square grows this much on every side, so squares that touch
only at a corner overlap and the mesh stays manifold."""

def qr_matrix(language: str) -> list[list[bool]]:
    """The stored QR matrix for ``language``, top row first, ``True`` dark.

    Raises ``ValueError`` for an unknown language.
    """
    _check_language(language)
    text = (files("acequias.cad") / "data" / f"qr_{language}.txt").read_text(encoding="ascii")
    rows = [line.strip() for line in text.splitlines()]
    return [[cell == "1" for cell in row] for row in rows if row and not row.startswith("#")]


def qr_plate(
    language: str,
    size: float = DEFAULT_QR_SIZE,
    base_height: float = DEFAULT_QR_BASE_HEIGHT,
    module_height: float = DEFAULT_QR_MODULE_HEIGHT,
    label_band: float = DEFAULT_QR_LABEL_BAND,
) -> Solid:
    """The QR plate for ``language`` ("reglas" or "rules"), all sizes in mm.

    The plate is ``size`` wide (``x``), ``size + label_band`` deep (``y``),
    and ``base_height + module_height`` high. The code with its quiet zone
    fills the ``size`` x ``size`` square at the north end, so each module is
    ``size`` divided by the matrix side. The label is centered in the
    ``label_band`` at the south end, in the bundled font at an em size of
    ``LABEL_FONT_RATIO * label_band``.

    Raises ``ValueError`` naming the parameter for an unknown ``language``,
    a size that is not finite or not above 0, a module under ``MIN_MODULE``,
    a ``base_height`` under ``MIN_WALL``, a ``module_height`` under
    ``MIN_RAISE``, a ``label_band`` under ``MIN_LABEL_BAND``, or a label
    wider than the plate.
    """
    matrix = qr_matrix(language)
    for name, value in (
        ("size", size),
        ("base_height", base_height),
        ("module_height", module_height),
        ("label_band", label_band),
    ):
        _check_size(name, value)
    count = len(matrix)
    module = size / count
    if module < MIN_MODULE:
        raise ValueError(
            f"size must be >= {count * MIN_MODULE:g} mm for {MIN_MODULE} mm modules "
            f"({count} modules across), got {size!r}"
        )
    if base_height < MIN_WALL:
        raise ValueError(f"base_height must be >= {MIN_WALL} mm, got {base_height!r}")
    if module_height < MIN_RAISE:
        raise ValueError(f"module_height must be >= {MIN_RAISE} mm, got {module_height!r}")
    if label_band < MIN_LABEL_BAND:
        raise ValueError(
            f"label_band must be >= {MIN_LABEL_BAND:g} mm for 0.8 mm label strokes, "
            f"got {label_band!r}"
        )
    depth = size + label_band
    top = depth / 2
    letters = [
        Pos(0, -top + label_band / 2, 0) * face
        for face in text_faces(QR_LABELS[language], LABEL_FONT_RATIO * label_band)
    ]
    label_width = Compound(letters).bounding_box().size.X
    if label_width > size:
        raise ValueError(f"size must be >= {label_width:g} mm to fit the label, got {size!r}")

    squares: list[tuple[float, float, float, float]] = []  # x0, y0, width, height
    for i, row in enumerate(matrix):
        for j, length in _runs(row):
            squares.append((-size / 2 + j * module, top - (i + 1) * module, length * module, module))

    plate = Pos(-size / 2, -depth / 2, 0) * Solid.make_box(size, depth, base_height)
    # Union the squares in 2D first (much faster than fusing hundreds of
    # boxes), then extrude them from halfway into the plate, so the last
    # fuse is not coplanar.
    faces = [
        Pos(x0 - _GROW, y0 - _GROW, 0)
        * Face.make_rect(width + 2 * _GROW, height + 2 * _GROW).translate(
            (width / 2 + _GROW, height / 2 + _GROW, 0)
        )
        for x0, y0, width, height in squares
    ]
    outline = faces[0].fuse(*faces[1:], *letters).clean()
    bottom = base_height / 2
    raised = Pos(0, 0, bottom) * extrude(outline, base_height - bottom + module_height)
    return _single_solid(plate.fuse(raised).clean(), "qr_plate")


def _runs(row: list[bool]) -> list[tuple[int, int]]:
    """The ``(start, length)`` of each run of ``True`` cells in ``row``."""
    runs: list[tuple[int, int]] = []
    start = None
    for j, cell in enumerate([*row, False]):
        if cell and start is None:
            start = j
        elif not cell and start is not None:
            runs.append((start, j - start))
            start = None
    return runs


def _check_language(language: object) -> None:
    if language not in QR_LANGUAGES:
        allowed = ", ".join(f'"{name}"' for name in QR_LANGUAGES)
        raise ValueError(f"language must be one of {allowed}, got {language!r}")
