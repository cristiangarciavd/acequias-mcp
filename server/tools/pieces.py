"""The `generate_piece_stl` tool: the STL file of one printable piece.

The tool only checks input, picks the generator with
`acequias.cad.pieces.build_piece`, and writes the file with
`acequias.cad.hex_tile.export_stl` into the output folder of
`server.output`. build123d, trimesh, and `acequias.cad` come from the
optional `cad` extra, so they are imported inside the tool only: without the
extra the server still starts, and this tool returns an error naming it.
`server.app` registers it on the server.
"""

from __future__ import annotations

import os
import re
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from server.output import output_dir
from server.schemas import PIECE_VARIANT_FIELDS, PieceJSON, piece_params, piece_variant

CAD_EXTRA_MESSAGE = (
    "generate_piece_stl needs the optional 'cad' extra (build123d and trimesh), "
    "which is not installed; install it with: uv sync --extra cad"
)

FILE_NAME_PATTERN = re.compile(r"[a-z0-9_.-]+\.stl")
"""What every file name matches: only `a-z`, `0-9`, `_`, `-`, and `.`."""


class PieceSize(BaseModel):
    """A bounding box size in mm."""

    model_config = ConfigDict(extra="forbid", strict=True)

    x: float = Field(description="Size along x (east), in mm.")
    y: float = Field(description="Size along y (north), in mm.")
    z: float = Field(description="Height, in mm.")


class PieceResult(BaseModel):
    """What `generate_piece_stl` returns."""

    model_config = ConfigDict(extra="forbid", strict=True)

    path: str = Field(description="Absolute path of the STL file written.")
    piece: PieceJSON = Field(description="The piece as built, with every default filled in.")
    size: PieceSize = Field(description="Bounding box size of the mesh in mm, rounded to 0.01 mm.")
    volume: float = Field(description="Mesh volume in mm^3, rounded to 0.01.")
    triangles: int = Field(description="Number of triangles in the mesh.")
    watertight: bool = Field(description="Whether the mesh is watertight (closed).")


def format_number(value: float) -> str:
    """`value` in its shortest exact form, without a trailing `.0` or an exponent.

    16.0 -> "16", 1.5 -> "1.5", 0.15 -> "0.15", 1e-05 -> "0.00001".
    """
    text = format(Decimal(repr(float(value))), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def piece_file_name(piece: BaseModel) -> str:
    """The file name for a piece: `<type>[-<variant>]-<name><value>-...stl`.

    Built only from the type, the variant (terrain, canal kind, or debt
    value), and every size parameter in field order, defaults included, so
    the same piece always gets the same name and a different one a
    different name.
    """
    piece_type: str = piece.type  # type: ignore[attr-defined]
    parts = [piece_type]
    variant_field = PIECE_VARIANT_FIELDS.get(piece_type)
    if variant_field is not None:
        parts.append(str(getattr(piece, variant_field)))
    parts.extend(f"{name}{format_number(value)}" for name, value in piece_params(piece).items())
    name = "-".join(parts) + ".stl"
    if not FILE_NAME_PATTERN.fullmatch(name):
        raise ValueError(f"cannot build a safe file name for this piece, got {name!r}")
    return name


def generate_piece_stl(
    piece: Annotated[
        PieceJSON,
        Field(
            description=(
                'The piece to print, chosen by its "type": "terrain", "canal", "floodgate", '
                '"owner_token", "grape_cluster", or "debt_token". Sizes are in mm; any left '
                "out take their default."
            )
        ),
    ],
) -> PieceResult:
    """Write the STL file of one printable Acequias piece and measure it.

    Piece types: "terrain" (a hex tile; needs "terrain"), "canal" (a hex
    tile with a groove; needs "kind"), "floodgate", "owner_token",
    "grape_cluster", and "debt_token" (needs "value", 1 or 5). Every size is
    in mm and optional, with the defaults of the game's geometry profile.

    The file goes into the output folder (the ACEQUIAS_OUTPUT_DIR
    environment variable, or output/ in the server's working folder), named
    after the type, the variant, and every size; the same piece overwrites
    the same file. Returns the file's absolute path, the piece with every
    default filled in, and the mesh's bounding box size, volume, triangle
    count, and whether it is watertight, ready for a slicer. Needs the
    optional 'cad' extra (uv sync --extra cad).
    """
    try:
        import trimesh

        from acequias.cad.hex_tile import export_stl
        from acequias.cad.pieces import build_piece
    except ImportError as exc:
        raise ValueError(CAD_EXTRA_MESSAGE) from exc

    shape = build_piece(piece.type, piece_variant(piece), **piece_params(piece))
    name = piece_file_name(piece)
    folder = output_dir()
    target = folder / name
    if target.parent != folder:
        raise ValueError(f"the file {name!r} would not be directly inside {str(folder)!r}")

    # Write and measure a temporary file in the same folder, then move it
    # into place, so a failed call leaves the folder as it was.
    handle, temporary = tempfile.mkstemp(prefix=f".{name}.", suffix=".tmp", dir=folder)
    os.close(handle)
    try:
        export_stl(shape, temporary)
        measured = _measure(trimesh.load_mesh(temporary, file_type="stl"))
        os.replace(temporary, target)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise

    return PieceResult.model_validate(
        {"path": str(target), "piece": piece.model_dump(), **measured}
    )


def _measure(mesh: Any) -> dict[str, Any]:
    x, y, z = (round(float(extent), 2) for extent in mesh.extents)
    return {
        "size": {"x": x, "y": y, "z": z},
        "volume": round(float(mesh.volume), 2),
        "triangles": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
    }
