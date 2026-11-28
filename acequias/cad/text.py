"""Text as build123d geometry, from the font bundled in the repo only.

The font is Atkinson Hyperlegible Bold (SIL Open Font License 1.1, see
``acequias/cad/fonts/OFL.txt``), taken from the google/fonts repository: a
bold sans made to stay legible small. ``text_faces`` renders with that file
and never with a system font, so every machine builds the same letters.

Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

from importlib.resources import as_file, files
from pathlib import Path

from build123d import Compound, Face, FontStyle, Pos

FONT_FILE = "AtkinsonHyperlegible-Bold.ttf"
"""The bundled font file, in ``acequias/cad/fonts/``."""

FONT_NAME = "Atkinson Hyperlegible"
"""The family name inside ``FONT_FILE``."""

FONT_STYLE = FontStyle.BOLD
"""The style of ``FONT_FILE`` (the file holds this one style)."""


def font_path() -> Path:
    """The path of the bundled font file.

    Raises ``FileNotFoundError`` if the file is missing from the package.
    """
    with as_file(files("acequias.cad") / "fonts" / FONT_FILE) as path:
        if not path.is_file():
            raise FileNotFoundError(f"the bundled font {FONT_FILE} is missing: {path}")
        return Path(path)


def text_faces(text: str, font_size: float) -> list[Face]:
    """The outline of ``text`` as flat faces on ``z = 0``, in mm.

    ``font_size`` is the em size in mm (capitals come out about 0.66 of it).
    The faces are centered on ``x = y = 0`` by their bounding box, letter
    holes (the inside of an "o") are cut out. Raises ``ValueError`` for
    empty text or a size that is not above 0, and ``RuntimeError`` if
    OpenCASCADE would render with anything but the bundled file.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"text must be a non-empty string, got {text!r}")
    if isinstance(font_size, bool) or not isinstance(font_size, (int, float)) or not font_size > 0:
        raise ValueError(f"font_size must be a number above 0, got {font_size!r}")
    path = font_path()
    _, resolved, _ = Compound.resolve_font(FONT_NAME, path, FONT_STYLE)
    if not resolved or Path(resolved).resolve() != path.resolve():
        raise RuntimeError(f"the font resolved to {resolved!r}, not the bundled {path}")
    shape = Compound.make_text(
        text, font_size, font=FONT_NAME, font_path=path, font_style=FONT_STYLE
    )
    faces = shape.faces()
    if not faces:
        raise RuntimeError(f"the bundled font rendered no outline for {text!r}")
    center = Compound(faces).bounding_box().center()
    return [Pos(-center.X, -center.Y, 0) * face for face in faces]
