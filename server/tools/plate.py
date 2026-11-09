"""The `build_plate` tool: the A1 print plates for a list of pieces, as 3MF files.

The tool only checks input, gives every piece an id, hashes the request,
picks the file names, and builds the result. The rest comes from the
library: each piece's footprint from `acequias.cad.footprints`, its solid
from `acequias.cad.pieces.build_piece`, the positions from
`acequias.plate.layout_plates`, and the files from
`acequias.cad.plate_export.export_plate`. build123d and `acequias.cad` come
from the optional `cad` extra, so they are imported inside the tool only:
without the extra the server still starts, and this tool returns an error
naming it. `server.app` registers it on the server.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

from acequias.plate import Piece, Plate, layout_plates
from server.output import output_dir
from server.schemas import (
    MAX_PLATE_COUNT,
    PIECE_VARIANT_FIELDS,
    PieceJSON,
    PlateEntryJSON,
    piece_params,
    piece_variant,
)
from server.tools.pieces import cad_extra_message

TOOL_NAME = "build_plate"

CAD_EXTRA_MESSAGE = cad_extra_message(TOOL_NAME)

MAX_ENTRIES = 50
"""The most entries one request takes."""

MAX_BED_MM = 1000.0
"""The largest bed width or depth, in mm."""

MAX_MARGIN_MM = 50.0
"""The largest margin, in mm."""

MAX_GAP_MM = 20.0
"""The largest gap, in mm."""

DEFAULT_BED_MM = 256.0
"""The default bed width and depth in mm: the Bambu Lab A1."""

DEFAULT_MARGIN_MM = 5.0
DEFAULT_GAP_MM = 3.0

JOB_DIGITS = 12
"""How many hex digits of the request's SHA-256 name its folder."""


# --- Result -----------------------------------------------------------------


class PlacementJSON(BaseModel):
    """One piece on a plate."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(description="The piece id, <type>[-<variant>]-<nn>; the 3MF object's name.")
    entry: int = Field(description="Index of the piece's entry in the request, from 0.")
    piece: PieceJSON = Field(description="The piece as built, with every default filled in.")
    x: float = Field(
        description="Center in mm from the bed's front-left corner, to the right; rounded to 0.01."
    )
    y: float = Field(
        description="Center in mm from the bed's front-left corner, to the back; rounded to 0.01."
    )
    rotation: float = Field(description="Rotation in degrees about z; always 0.")


class PlateJSON(BaseModel):
    """One print plate and its 3MF file."""

    model_config = ConfigDict(extra="forbid", strict=True)

    number: int = Field(description="Plate number, from 1.")
    color: str = Field(description="The color group (filament) of every piece on the plate.")
    path: str = Field(description="Absolute path of the plate's 3MF file.")
    placements: list[PlacementJSON] = Field(description="The pieces on the plate, in layout order.")


class PlateSummaryJSON(BaseModel):
    """Totals for a `build_plate` request."""

    model_config = ConfigDict(extra="forbid", strict=True)

    pieces: int = Field(description="Total pieces on all plates.")
    plates: int = Field(description="Total plates.")
    plates_per_color: dict[str, int] = Field(
        description="Number of plates per color, in the order the colors first appear."
    )


class BuildPlateResult(BaseModel):
    """What `build_plate` returns."""

    model_config = ConfigDict(extra="forbid", strict=True)

    folder: str = Field(description="Absolute path of the plates-<job> folder holding the 3MF files.")
    job: str = Field(
        description="First 12 hex digits of the SHA-256 of the request with every default filled in."
    )
    plates: list[PlateJSON] = Field(description="The plates, in layout order.")
    summary: PlateSummaryJSON = Field(description="Totals: pieces, plates, and plates per color.")


# --- Helpers ----------------------------------------------------------------


def id_prefix(piece: BaseModel) -> str:
    """`<type>[-<variant>]`: the type, then the terrain, canal kind, or debt value."""
    piece_type: str = piece.type  # type: ignore[attr-defined]
    variant_field = PIECE_VARIANT_FIELDS.get(piece_type)
    if variant_field is None:
        return piece_type
    return f"{piece_type}-{getattr(piece, variant_field)}"


def piece_ids(entries: list[PlateEntryJSON]) -> list[list[str]]:
    """The ids of each entry's pieces: `<prefix>-<nn>`, `nn` counting from 01 per prefix."""
    counters: dict[str, int] = {}
    ids: list[list[str]] = []
    for entry in entries:
        prefix = id_prefix(entry.piece)
        start = counters.get(prefix, 0)
        counters[prefix] = start + entry.count
        ids.append([f"{prefix}-{n:02d}" for n in range(start + 1, start + entry.count + 1)])
    return ids


def _canonical(value: Any) -> Any:
    """`value` with every float written the same way, so 16 and 16.0 hash alike."""
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        return float(value)
    return value


def _piece_key(piece: BaseModel) -> str:
    """The same string for equal pieces with defaults filled in."""
    return json.dumps(_canonical(piece.model_dump()), sort_keys=True, separators=(",", ":"))


def job_id(
    entries: list[PlateEntryJSON],
    bed_width: float,
    bed_depth: float,
    margin: float,
    gap: float,
) -> str:
    """First 12 hex digits of the SHA-256 of the request's canonical JSON, defaults filled in."""
    request = {
        "entries": [
            {"piece": entry.piece.model_dump(), "count": entry.count, "color": entry.color}
            for entry in entries
        ],
        "bed_width": float(bed_width),
        "bed_depth": float(bed_depth),
        "margin": float(margin),
        "gap": float(gap),
    }
    text = json.dumps(_canonical(request), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:JOB_DIGITS]


def plate_file_name(plate: Plate) -> str:
    """`plate-<number>-<color>.3mf`."""
    return f"plate-{plate.number}-{plate.color_group}.3mf"


# --- The tool ---------------------------------------------------------------


def build_plate(
    entries: Annotated[
        list[PlateEntryJSON],
        Field(
            min_length=1,
            max_length=MAX_ENTRIES,
            description=(
                f"The pieces to print: 1 to {MAX_ENTRIES} entries, each a piece, a count "
                f"(1 to {MAX_PLATE_COUNT}), and a color. At most {MAX_PLATE_COUNT} pieces "
                "in all."
            ),
        ),
    ],
    bed_width: Annotated[
        float,
        Field(
            strict=True,
            gt=0,
            le=MAX_BED_MM,
            description=f"Bed width (x) in mm, above 0 and at most {MAX_BED_MM:g}; the A1's is 256.",
        ),
    ] = DEFAULT_BED_MM,
    bed_depth: Annotated[
        float,
        Field(
            strict=True,
            gt=0,
            le=MAX_BED_MM,
            description=f"Bed depth (y) in mm, above 0 and at most {MAX_BED_MM:g}; the A1's is 256.",
        ),
    ] = DEFAULT_BED_MM,
    margin: Annotated[
        float,
        Field(
            strict=True,
            ge=0,
            le=MAX_MARGIN_MM,
            description=f"Empty border around the bed's edges in mm, 0 to {MAX_MARGIN_MM:g}.",
        ),
    ] = DEFAULT_MARGIN_MM,
    gap: Annotated[
        float,
        Field(
            strict=True,
            ge=0,
            le=MAX_GAP_MM,
            description=f"Space between neighboring pieces in mm, 0 to {MAX_GAP_MM:g}.",
        ),
    ] = DEFAULT_GAP_MM,
) -> BuildPlateResult:
    """Lay pieces out on Bambu Lab A1 print plates and write one 3MF file per plate.

    Each entry is a piece (the same objects as generate_piece_stl: "terrain",
    "canal", "floodgate", "owner_token", "grape_cluster", or "debt_token",
    sizes in mm with their defaults), a count, and a color. Each plate holds
    one color and one kind of grid (hexes, or round and flat pieces), so it
    prints with one filament.

    Every piece gets an id, <type>[-<variant>]-<nn> (for example
    terrain-river-01), which names its object in the 3MF file. The files go
    into a plates-<job> folder inside the output folder (the
    ACEQUIAS_OUTPUT_DIR environment variable, or output/ in the server's
    working folder), named plate-<number>-<color>.3mf; the same request
    overwrites the same files. Returns the folder, and for each plate its
    number, color, file path, and every piece's id, entry, full parameters,
    and center in mm from the bed's front-left corner. Needs the optional
    'cad' extra (uv sync --extra cad).
    """
    try:
        from acequias.cad.footprints import piece_footprint
        from acequias.cad.pieces import build_piece
        from acequias.cad.plate_export import export_plate
    except ImportError as exc:
        raise ValueError(CAD_EXTRA_MESSAGE) from exc

    total = sum(entry.count for entry in entries)
    if total > MAX_PLATE_COUNT:
        raise ValueError(
            f"the entries ask for {total} pieces in total; the limit is {MAX_PLATE_COUNT}"
        )
    bed = (float(bed_width), float(bed_depth))

    # Build each distinct piece once; the CAD functions check the combinations.
    solid_by_key: dict[str, Any] = {}
    footprint_by_key: dict[str, Any] = {}
    for entry in entries:
        key = _piece_key(entry.piece)
        if key not in solid_by_key:
            variant = piece_variant(entry.piece)
            params = piece_params(entry.piece)
            solid_by_key[key] = build_piece(entry.piece.type, variant, **params)
            footprint_by_key[key] = piece_footprint(entry.piece.type, variant, **params)

    ids = piece_ids(entries)
    pieces: list[Piece] = []
    solids: dict[str, Any] = {}
    entry_of: dict[str, int] = {}
    for index, (entry, entry_ids) in enumerate(zip(entries, ids)):
        key = _piece_key(entry.piece)
        for piece_id in entry_ids:
            pieces.append(Piece(piece_id, footprint_by_key[key], entry.color))
            solids[piece_id] = solid_by_key[key]
            entry_of[piece_id] = index

    plates = layout_plates(pieces, bed=bed, margin=margin, gap=gap)

    job = job_id(entries, bed_width, bed_depth, margin, gap)
    folder = output_dir()
    target = (folder / f"plates-{job}").resolve()
    paths = [(target / plate_file_name(plate)).resolve() for plate in plates]
    for path in paths:
        if path.parent != target or not path.is_relative_to(folder):
            raise ValueError(f"the file {str(path)!r} would not be inside {str(folder)!r}")

    # Write every plate into a temporary folder first, then move the files
    # into place, so a failed call leaves the output folder as it was.
    staging = Path(tempfile.mkdtemp(prefix=f".plates-{job}.", suffix=".tmp", dir=folder))
    try:
        for plate, path in zip(plates, paths):
            export_plate(plate, solids, staging / path.name, bed=bed)
        target.mkdir(exist_ok=True)
        for path in paths:
            os.replace(staging / path.name, path)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    plates_per_color: dict[str, int] = {}
    for plate in plates:
        plates_per_color[plate.color_group] = plates_per_color.get(plate.color_group, 0) + 1
    return BuildPlateResult.model_validate(
        {
            "folder": str(target),
            "job": job,
            "plates": [
                {
                    "number": plate.number,
                    "color": plate.color_group,
                    "path": str(path),
                    "placements": [
                        {
                            "id": placement.piece_id,
                            "entry": entry_of[placement.piece_id],
                            "piece": entries[entry_of[placement.piece_id]].piece.model_dump(),
                            "x": round(placement.x, 2),
                            "y": round(placement.y, 2),
                            "rotation": float(placement.rotation),
                        }
                        for placement in plate.placements
                    ],
                }
                for plate, path in zip(plates, paths)
            ],
            "summary": {
                "pieces": len(pieces),
                "plates": len(plates),
                "plates_per_color": plates_per_color,
            },
        }
    )
