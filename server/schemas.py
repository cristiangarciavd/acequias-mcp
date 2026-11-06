"""The JSON shapes the MCP tools share, and their conversions to `acequias` types.

Every tool that sends or reads a board uses this module, so a board means the
same JSON everywhere (`generate_board` writes it, `calculate_score` reads it).

String mappings (`acequias` enum -> JSON string):

- `Terrain`: its value, `"river"`, `"vineyard"`, `"stone"`, or `"empty"`
- `Varietal`: its lowercase enum name, ASCII only: `"malbec"`, `"bonarda"`,
  `"torrontes"` (not the display name `"Torrontés"`)
- `Mode`: its value, `"normal"` or `"flash"`

A hex is `{"q": int, "r": int, "terrain": str, "varietal": str | null}`, where
`varietal` is a string only on vineyards. `board_to_hexes` writes one per
`Board.tiles` entry, in the board's order; `hexes_to_board` reads them back.

Reading JSON back leaves the checks to the model: `Hex`, `Tile`, and `Board`
raise `ValueError` or `TypeError` on a bad hex, and the `*_from_json`
functions raise `ValueError` on an unknown string, so a tool wrapped with
`tool_errors` reports them as tool errors. No game logic lives here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from acequias.assembly import AssemblyStep
from acequias.hex import Hex
from acequias.model import Board, Mode, Terrain, Tile, Varietal

TerrainName = Literal["river", "vineyard", "stone", "empty"]
VarietalName = Literal["malbec", "bonarda", "torrontes"]
ModeName = Literal["normal", "flash"]

HEX_KEYS = frozenset({"q", "r", "terrain", "varietal"})

_TERRAIN_BY_NAME = {terrain.value: terrain for terrain in Terrain}
_VARIETAL_BY_NAME = {varietal.name.lower(): varietal for varietal in Varietal}
_MODE_BY_NAME = {mode.value: mode for mode in Mode}


# --- String mappings --------------------------------------------------------


def terrain_to_json(terrain: Terrain) -> str:
    """The JSON string for `terrain`: its value, e.g. `"vineyard"`."""
    return terrain.value


def terrain_from_json(name: object) -> Terrain:
    """The `Terrain` for a JSON string; `ValueError` if it is not one."""
    return _lookup("terrain", name, _TERRAIN_BY_NAME)


def varietal_to_json(varietal: Varietal | None) -> str | None:
    """The JSON string for `varietal` (lowercase ASCII name), or None."""
    return None if varietal is None else varietal.name.lower()


def varietal_from_json(name: object) -> Varietal | None:
    """The `Varietal` for a JSON string, None for null; `ValueError` otherwise."""
    if name is None:
        return None
    return _lookup("varietal", name, _VARIETAL_BY_NAME)


def mode_to_json(mode: Mode) -> str:
    """The JSON string for `mode`: `"normal"` or `"flash"`."""
    return mode.value


def mode_from_json(name: object) -> Mode:
    """The `Mode` for a JSON string; `ValueError` if it is not one."""
    return _lookup("mode", name, _MODE_BY_NAME)


def _lookup(field: str, name: object, table: Mapping[str, Any]) -> Any:
    if isinstance(name, str) and name in table:
        return table[name]
    allowed = ", ".join(f'"{key}"' for key in table)
    raise ValueError(f"{field} must be one of {allowed}, got {name!r}")


# --- Pydantic shapes (published as JSON schemas) ----------------------------


class HexJSON(BaseModel):
    """One board hex: its axial coordinate, terrain, and varietal."""

    model_config = ConfigDict(extra="forbid", strict=True)

    q: int = Field(description="Axial q coordinate.")
    r: int = Field(description="Axial r coordinate; rows run north (smallest r) to south.")
    terrain: TerrainName = Field(description="The hex terrain.")
    varietal: VarietalName | None = Field(
        description="The grape on a vineyard (lowercase ASCII); null on every other terrain."
    )


class AssemblyStepJSON(BaseModel):
    """One step of the assembly instructions: a tile to lay on the table."""

    model_config = ConfigDict(extra="forbid", strict=True)

    row: int = Field(description="Row number, from 1 (north) down.")
    position: int = Field(description="Position in the row, from 1 (west) eastward.")
    q: int = Field(description="Axial q coordinate of the hex.")
    r: int = Field(description="Axial r coordinate of the hex.")
    terrain: TerrainName = Field(description="The hex terrain.")
    varietal: VarietalName | None = Field(
        description="The grape on a vineyard (lowercase ASCII); null on every other terrain."
    )
    text: str = Field(description='The step to read aloud, e.g. "Row 2, hex 3: vineyard, Malbec".')


# --- Board <-> JSON ---------------------------------------------------------


def tile_to_hex(tile: Tile) -> dict[str, Any]:
    """The hex JSON object for one `Tile`."""
    return {
        "q": tile.hex.q,
        "r": tile.hex.r,
        "terrain": terrain_to_json(tile.terrain),
        "varietal": varietal_to_json(tile.varietal),
    }


def hex_to_tile(item: Mapping[str, Any] | HexJSON) -> Tile:
    """The `Tile` for one hex JSON object (a mapping or a `HexJSON`).

    The object must have exactly the keys `q`, `r`, `terrain`, and
    `varietal`. Raises `ValueError` or `TypeError` if it is not a valid tile.
    """
    if isinstance(item, HexJSON):
        item = item.model_dump()
    if not isinstance(item, Mapping):
        raise TypeError(f"a hex must be an object, got {item!r}")
    keys = set(item)
    if keys != HEX_KEYS:
        missing = sorted(HEX_KEYS - keys)
        extra = sorted(str(key) for key in keys - HEX_KEYS)
        raise ValueError(
            f"a hex needs exactly the keys q, r, terrain, varietal; "
            f"missing {missing}, unexpected {extra}"
        )
    return Tile(
        hex=Hex(item["q"], item["r"]),
        terrain=terrain_from_json(item["terrain"]),
        varietal=varietal_from_json(item["varietal"]),
    )


def board_to_hexes(board: Board) -> list[dict[str, Any]]:
    """The `hexes` list for `board`: one object per `Board.tiles` entry, in order.

    Only tiles are written; canals, floodgates, and claims are not.
    """
    return [tile_to_hex(tile) for tile in board.tiles]


def hexes_to_board(hexes: Iterable[Mapping[str, Any] | HexJSON]) -> Board:
    """A `Board` with the tiles of a `hexes` list (no canals, floodgates, or claims).

    The inverse of `board_to_hexes`: `hexes_to_board(board_to_hexes(b))`
    equals `b` for a board with only tiles. Raises `ValueError` or
    `TypeError` on an unknown terrain or varietal, a vineyard without a
    varietal, a varietal on another terrain, or two hexes with the same `q`
    and `r` (the checks of `Tile` and `Board`).
    """
    if isinstance(hexes, (str, bytes, Mapping)) or not isinstance(hexes, Iterable):
        raise TypeError(f"hexes must be a list of hex objects, got {hexes!r}")
    return Board(tiles=tuple(hex_to_tile(item) for item in hexes))


def assembly_to_json(steps: Iterable[AssemblyStep]) -> list[dict[str, Any]]:
    """The `assembly` list: one object per `AssemblyStep`, in order, with the hex flattened."""
    return [
        {
            "row": step.row,
            "position": step.position,
            "q": step.hex.q,
            "r": step.hex.r,
            "terrain": terrain_to_json(step.terrain),
            "varietal": varietal_to_json(step.varietal),
            "text": step.text,
        }
        for step in steps
    ]
