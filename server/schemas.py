"""The JSON shapes the MCP tools share, and their conversions to `acequias` types.

Every tool that sends or reads a board uses this module, so a board means the
same JSON everywhere (`generate_board` writes it, `calculate_score` reads it).

String mappings (`acequias` enum -> JSON string):

- `Terrain`: its value, `"river"`, `"vineyard"`, `"stone"`, or `"empty"`
- `Varietal`: its lowercase enum name, ASCII only: `"malbec"`, `"bonarda"`,
  `"torrontes"` (not the display name `"Torrontés"`)
- `Mode`: its value, `"normal"` or `"flash"`
- `PieceKind` (canal shapes only): its lowercase enum name, ASCII only:
  `"straight"`, `"gentle_curve"`, `"sharp_curve"`, `"symmetric_y"`,
  `"t_branch"`, `"claw"` (not the values `"gentle curve"` or `"T branch"`).
  The floodgate is not a canal kind and has no string here
- `Direction`: its name, case-sensitive: `"E"`, `"NE"`, `"NW"`, `"W"`,
  `"SW"`, `"SE"`

A hex is `{"q": int, "r": int, "terrain": str, "varietal": str | null}`, where
`varietal` is a string only on vineyards. `board_to_hexes` writes one per
`Board.tiles` entry, in the board's order; `hexes_to_board` reads them back.

The other shapes, read and written by `calculate_score`:

- canal: `{"q", "r", "kind", "rotation", "owner"}`, one `PlacedCanal`
- floodgate: `{"q", "r", "direction"}`, a `Floodgate` on the canal at `q`,
  `r`, closing its opening `direction`
- claim: `{"q", "r", "player"}`, one vineyard claim
- player: `{"id", "debt"}`; the list order is the seat order (seats 1 to N)
- score: one `Score`, its `watered_vineyards` each with the canal path in the
  canal shape

The preset shape, written by `simulate_game` (the `preset` of
`SimResult.to_json()`) and read back as its `overrides`: `mode` by value,
`rounds` keyed by player count as a string (`"2"` to `"5"`), `bag_mix` keyed
by the lowercase `PieceKind` name (`"straight"` ... `"floodgate"`, the
floodgate included), `vineyard_distance` as `[low, high]`, the rest as ints.
`overrides_from_json` turns those keys back into `int` and `PieceKind` and
the pair into a tuple; every value check is left to `Preset`.

Reading JSON back leaves the checks to the model: `Hex`, `Tile`, and `Board`
raise `ValueError` or `TypeError` on a bad hex, and the `*_from_json`
functions raise `ValueError` on an unknown string, so a tool wrapped with
`tool_errors` reports them as tool errors. No game logic lives here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt, with_config
from typing_extensions import TypedDict

from acequias.assembly import AssemblyStep
from acequias.config import PLAYER_COUNTS
from acequias.hex import Direction, Hex
from acequias.model import (
    ROTATIONS,
    Board,
    Floodgate,
    Mode,
    PieceKind,
    PlacedCanal,
    Player,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import Score, WateredVineyard

TerrainName = Literal["river", "vineyard", "stone", "empty"]
VarietalName = Literal["malbec", "bonarda", "torrontes"]
ModeName = Literal["normal", "flash"]
KindName = Literal["straight", "gentle_curve", "sharp_curve", "symmetric_y", "t_branch", "claw"]
DirectionName = Literal["E", "NE", "NW", "W", "SW", "SE"]
# Built from the library, so they follow `PLAYER_COUNTS` and `PieceKind`.
PlayerCountName = Literal[tuple(str(players) for players in PLAYER_COUNTS)]  # type: ignore[valid-type]
PieceName = Literal[tuple(kind.name.lower() for kind in PieceKind)]  # type: ignore[valid-type]

HEX_KEYS = frozenset({"q", "r", "terrain", "varietal"})

_TERRAIN_BY_NAME = {terrain.value: terrain for terrain in Terrain}
_VARIETAL_BY_NAME = {varietal.name.lower(): varietal for varietal in Varietal}
_MODE_BY_NAME = {mode.value: mode for mode in Mode}
_KIND_BY_NAME = {kind.name.lower(): kind for kind in PieceKind if kind.is_canal}
_DIRECTION_BY_NAME = {direction.name: direction for direction in Direction}
_PIECE_BY_NAME = {kind.name.lower(): kind for kind in PieceKind}
_PLAYER_COUNT_BY_NAME = {str(players): players for players in PLAYER_COUNTS}


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


def kind_to_json(kind: PieceKind) -> str:
    """The JSON string for a canal `kind`: its lowercase ASCII name, e.g. `"t_branch"`.

    Raises `ValueError` for the floodgate, which is not a canal kind.
    """
    if not kind.is_canal:
        raise ValueError("the floodgate is not a canal kind")
    return kind.name.lower()


def kind_from_json(name: object) -> PieceKind:
    """The canal `PieceKind` for a JSON string; `ValueError` if it is not one."""
    return _lookup("kind", name, _KIND_BY_NAME)


def direction_to_json(direction: Direction) -> str:
    """The JSON string for `direction`: its name, e.g. `"NE"`."""
    return direction.name


def direction_from_json(name: object) -> Direction:
    """The `Direction` for a JSON string (case-sensitive); `ValueError` otherwise."""
    return _lookup("direction", name, _DIRECTION_BY_NAME)


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


class CanalJSON(BaseModel):
    """A canal piece on an empty hex: its shape, rotation, and owner."""

    model_config = ConfigDict(extra="forbid", strict=True)

    q: int = Field(description="Axial q coordinate of the hex the canal is on.")
    r: int = Field(description="Axial r coordinate of the hex the canal is on.")
    kind: KindName = Field(
        description="The canal shape (lowercase ASCII); a floodgate is not a canal."
    )
    rotation: int = Field(
        ge=0,
        le=ROTATIONS - 1,
        description="Rotation, 0 to 5; each step turns the shape 60 degrees counterclockwise.",
    )
    owner: str = Field(description="Id of the player who owns the canal.")


class FloodgateJSON(BaseModel):
    """A floodgate closing one opening of a canal."""

    model_config = ConfigDict(extra="forbid", strict=True)

    q: int = Field(description="Axial q coordinate of the canal the floodgate sits on.")
    r: int = Field(description="Axial r coordinate of the canal the floodgate sits on.")
    direction: DirectionName = Field(
        description="The canal opening the floodgate closes (case-sensitive)."
    )


class ClaimJSON(BaseModel):
    """A player's claim on a vineyard."""

    model_config = ConfigDict(extra="forbid", strict=True)

    q: int = Field(description="Axial q coordinate of the vineyard.")
    r: int = Field(description="Axial r coordinate of the vineyard.")
    player: str = Field(description="Id of the player who claimed it.")


class PlayerJSON(BaseModel):
    """A player and the bribe debt they carry."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, description="Player id, a non-empty string.")
    debt: int = Field(ge=0, description="Bribe debt, 0 or more.")


class WateredVineyardJSON(BaseModel):
    """One watered claimed vineyard and the water rights it causes."""

    model_config = ConfigDict(extra="forbid", strict=True)

    q: int = Field(description="Axial q coordinate of the vineyard.")
    r: int = Field(description="Axial r coordinate of the vineyard.")
    varietal: VarietalName = Field(description="The grape (lowercase ASCII).")
    path: list[CanalJSON] = Field(
        description="The canals the water runs through, from the river end to the vineyard."
    )
    pays: list[str] = Field(
        description="Rival ids the claimant pays 1 point each (owners on the path), in seat order."
    )


class ScoreJSON(BaseModel):
    """One player's final score, by term."""

    model_config = ConfigDict(extra="forbid", strict=True)

    player: str = Field(description="Player id.")
    seat: int = Field(description="Seat number, 1 to N in the order of the input players.")
    vineyards: int = Field(description="Points from the player's watered claimed vineyards.")
    bodega: int = Field(description="Bodega bonus for watering enough different varietals.")
    rights_paid: int = Field(description="Water rights paid to rivals, 1 point per rival per vineyard.")
    rights_collected: int = Field(description="Water rights collected from rivals.")
    debt: int = Field(description="Bribe debt.")
    total: int = Field(description="vineyards + bodega - rights_paid + rights_collected - debt.")
    watered: int = Field(description="Number of watered claimed vineyards (the tie-break).")
    watered_vineyards: list[WateredVineyardJSON] = Field(
        description="The player's watered claimed vineyards, by hex."
    )


_ROUNDS_DESCRIPTION = 'Rounds per player count, keyed "2" to "5".'
_BAG_MIX_DESCRIPTION = (
    'Percentage of the bag for each piece kind, keyed "straight", "gentle_curve", '
    '"sharp_curve", "symmetric_y", "t_branch", "claw", "floodgate".'
)
_DISTANCE_DESCRIPTION = "[low, high]: how far, in hexes, a vineyard lies from the river."


class PresetJSON(BaseModel):
    """Every value of a game preset (the numbers of one mode), after overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mode: ModeName = Field(description="The mode the preset belongs to.")
    rounds: dict[PlayerCountName, int] = Field(description=_ROUNDS_DESCRIPTION)
    hexes_per_player: int = Field(description="Board hexes per player.")
    vineyards_per_player: int = Field(description="Vineyards per player.")
    stone_share: int = Field(description="Percentage of non-river hexes that are stone.")
    vineyard_distance: list[int] = Field(
        min_length=2, max_length=2, description=_DISTANCE_DESCRIPTION
    )
    market_size: int = Field(description="Pieces face up in the market.")
    bag_mix: dict[PieceName, int] = Field(description=_BAG_MIX_DESCRIPTION)
    die_faces: int = Field(description="Faces of the bribe die.")
    bodega_points: int = Field(description="Points of the bodega bonus.")
    bodega_varietals: int = Field(description="Distinct watered varietals the bodega bonus needs.")


@with_config(ConfigDict(extra="forbid"))
class PresetOverridesJSON(TypedDict, total=False):
    """Preset values to replace, in the `PresetJSON` shape without `mode`.

    Every key is optional; omitted keys keep the mode's shipped value, and a
    key given replaces that value as a whole. Only keys and types are checked
    here (strict integers); the value rules come from `Preset`.
    """

    rounds: Annotated[
        dict[PlayerCountName, StrictInt],
        Field(description=_ROUNDS_DESCRIPTION + " Give every key, e.g. {\"2\": 10, ...}."),
    ]
    hexes_per_player: Annotated[StrictInt, Field(description="Board hexes per player.")]
    vineyards_per_player: Annotated[StrictInt, Field(description="Vineyards per player.")]
    stone_share: Annotated[
        StrictInt, Field(description="Percentage, 0 to 100, of non-river hexes that are stone.")
    ]
    vineyard_distance: Annotated[
        tuple[StrictInt, StrictInt],
        Field(description=_DISTANCE_DESCRIPTION + " low is 2 or more, high at least low."),
    ]
    market_size: Annotated[StrictInt, Field(description="Pieces face up in the market.")]
    bag_mix: Annotated[
        dict[PieceName, StrictInt],
        Field(description=_BAG_MIX_DESCRIPTION + " Give every key; the shares add up to 100."),
    ]
    die_faces: Annotated[StrictInt, Field(description="Faces of the bribe die, 2 or more.")]
    bodega_points: Annotated[StrictInt, Field(description="Points of the bodega bonus.")]
    bodega_varietals: Annotated[
        StrictInt, Field(description="Distinct watered varietals the bodega bonus needs, 1 to 3.")
    ]


def overrides_from_json(overrides: Mapping[str, Any]) -> dict[str, Any]:
    """The `with_overrides` keyword arguments for an overrides JSON object.

    `rounds` keys become `int`, `bag_mix` keys `PieceKind`, and
    `vineyard_distance` a tuple; every other value is passed on as is, for
    `Preset` to check. Raises `ValueError` on a `rounds` or `bag_mix` key
    that is not one.
    """
    if not isinstance(overrides, Mapping):
        raise TypeError(f"overrides must be an object, got {overrides!r}")
    changes = dict(overrides)
    if isinstance(changes.get("rounds"), Mapping):
        changes["rounds"] = {
            _lookup("rounds key", key, _PLAYER_COUNT_BY_NAME): value
            for key, value in changes["rounds"].items()
        }
    if isinstance(changes.get("bag_mix"), Mapping):
        changes["bag_mix"] = {
            _lookup("bag_mix key", key, _PIECE_BY_NAME): value
            for key, value in changes["bag_mix"].items()
        }
    if isinstance(changes.get("vineyard_distance"), (list, tuple)):
        changes["vineyard_distance"] = tuple(changes["vineyard_distance"])
    return changes


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


# --- Pieces, players, and scores <-> JSON -----------------------------------
#
# The `*_from_json` functions take a mapping or the matching Pydantic model.
# A mapping is checked against the model first (pydantic's `ValidationError`
# is a `ValueError`); where pieces may sit is left to `Board` and `GameState`.


def canal_to_json(canal: PlacedCanal) -> dict[str, Any]:
    """The canal JSON object for one `PlacedCanal`."""
    return {
        "q": canal.hex.q,
        "r": canal.hex.r,
        "kind": kind_to_json(canal.kind),
        "rotation": canal.rotation,
        "owner": canal.owner,
    }


def canal_from_json(item: Mapping[str, Any] | CanalJSON) -> PlacedCanal:
    """The `PlacedCanal` for one canal JSON object."""
    item = CanalJSON.model_validate(item)
    return PlacedCanal(
        hex=Hex(item.q, item.r),
        kind=kind_from_json(item.kind),
        rotation=item.rotation,
        owner=item.owner,
    )


def floodgate_from_json(item: Mapping[str, Any] | FloodgateJSON) -> Floodgate:
    """The `Floodgate` for one floodgate JSON object."""
    item = FloodgateJSON.model_validate(item)
    return Floodgate(hex=Hex(item.q, item.r), direction=direction_from_json(item.direction))


def claim_from_json(item: Mapping[str, Any] | ClaimJSON) -> tuple[Hex, str]:
    """The `(hex, player id)` claim pair for one claim JSON object."""
    item = ClaimJSON.model_validate(item)
    return (Hex(item.q, item.r), item.player)


def players_from_json(items: Iterable[Mapping[str, Any] | PlayerJSON]) -> tuple[Player, ...]:
    """The `Player`s for a players list, with seats 1 to N in list order."""
    if isinstance(items, (str, bytes, Mapping)) or not isinstance(items, Iterable):
        raise TypeError(f"players must be a list of player objects, got {items!r}")
    return tuple(
        Player(id=item.id, seat=seat, debt=item.debt)
        for seat, item in enumerate((PlayerJSON.model_validate(i) for i in items), start=1)
    )


def watered_vineyard_to_json(vineyard: WateredVineyard) -> dict[str, Any]:
    """The JSON object for one `WateredVineyard`: hex, varietal, path, and pays."""
    return {
        "q": vineyard.hex.q,
        "r": vineyard.hex.r,
        "varietal": varietal_to_json(vineyard.varietal),
        "path": [canal_to_json(canal) for canal in vineyard.path.canals],
        "pays": list(vineyard.pays),
    }


def score_to_json(score: Score) -> dict[str, Any]:
    """The score JSON object for one `Score`, every term copied as is."""
    return {
        "player": score.player,
        "seat": score.seat,
        "vineyards": score.vineyards,
        "bodega": score.bodega,
        "rights_paid": score.rights_paid,
        "rights_collected": score.rights_collected,
        "debt": score.debt,
        "total": score.total,
        "watered": score.watered,
        "watered_vineyards": [watered_vineyard_to_json(v) for v in score.watered_vineyards],
    }
