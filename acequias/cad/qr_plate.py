"""The QR plate: a printed QR code to the online rulebook, glued inside the box.

``qr_plate(language)`` is a thin plate with the QR code's dark modules raised
on top and a small block-letter label ("REGLAS" or "RULES") under the code.
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

from build123d import Face, Pos, Solid, extrude

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
"""Thinnest wall in mm (two 0.4 mm nozzle widths): the plate and a label stroke."""

MIN_RAISE = 0.4
"""Lowest module height in mm: two 0.2 mm layers of the second color."""

LABEL_PIXELS_HIGH = 5
"""Each label letter is 3 x 5 square pixels (block strokes, no font file)."""

_LABEL_BAND_IN_PIXELS = 7.5
"""The band is this many pixels deep: the 5-pixel letters and a margin."""

_GROW = 0.01
"""Each raised square grows this much on every side, so squares that touch
only at a corner overlap and the mesh stays manifold."""

FONT: dict[str, tuple[str, ...]] = {
    "A": ("010", "101", "111", "101", "101"),
    "E": ("111", "100", "110", "100", "111"),
    "G": ("011", "100", "101", "101", "011"),
    "L": ("100", "100", "100", "100", "111"),
    "R": ("110", "101", "110", "101", "101"),
    "S": ("011", "100", "010", "001", "110"),
    "U": ("101", "101", "101", "101", "111"),
}
"""The block letters the labels need, top row first, ``1`` raised."""


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
    ``label_band`` at the south end, in block letters
    ``label_band / 7.5`` mm per pixel.

    Raises ``ValueError`` naming the parameter for an unknown ``language``,
    a size that is not finite or not above 0, a module under ``MIN_MODULE``,
    a ``base_height`` or label stroke under ``MIN_WALL``, a
    ``module_height`` under ``MIN_RAISE``, or a label wider than the plate.
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
    pixel = label_band / _LABEL_BAND_IN_PIXELS
    if pixel < MIN_WALL:
        raise ValueError(
            f"label_band must be >= {MIN_WALL * _LABEL_BAND_IN_PIXELS:g} mm for "
            f"{MIN_WALL} mm label strokes, got {label_band!r}"
        )
    label = QR_LABELS[language]
    label_width = (4 * len(label) - 1) * pixel
    if label_width > size:
        raise ValueError(f"size must be >= {label_width:g} mm to fit the label, got {size!r}")

    depth = size + label_band
    top = depth / 2
    squares: list[tuple[float, float, float, float]] = []  # x0, y0, width, height
    for i, row in enumerate(matrix):
        for j, length in _runs(row):
            squares.append((-size / 2 + j * module, top - (i + 1) * module, length * module, module))

    label_left = -label_width / 2
    label_top = -top + (label_band + LABEL_PIXELS_HIGH * pixel) / 2
    for k, letter in enumerate(label):
        for i, row in enumerate(FONT[letter]):
            for j, length in _runs([cell == "1" for cell in row]):
                x0 = label_left + (4 * k + j) * pixel
                squares.append((x0, label_top - (i + 1) * pixel, length * pixel, pixel))

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
    outline = faces[0].fuse(*faces[1:]).clean()
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
