"""The JSON shapes the MCP tools share, and their conversions to `acequias` types.

Every tool that sends or reads a board uses this module, so a board means the
same JSON everywhere (`generate_board` writes it, `calculate_score` reads it).

String mappings (`acequias` enum -> JSON string):

- `Terrain`: its value, `"river"`, `"vineyard"`, `"stone"`, or `"empty"`
- `Varietal`: its lowercase enum name, ASCII only: `"malbec"`,
  `"cabernet_sauvignon"`, `"cabernet_franc"`, `"syrah"`, `"merlot"`,
  `"bonarda"`, `"torrontes"`, `"chardonnay"` (not the display names
  `"Torrontés"` or `"Cabernet Sauvignon"`)
- `VarietalRules`: its value, `"fixed"` or `"roulette"`
- `BribeRules`: its value, `"d6"` or `"action_die"`
- `DieFace`: its value, `"floodgate"`, `"release"`, `"resow"`, `"move"`
  (Rules v3 only), `"good_season"`, or `"drought"`
- `Mode`: its value, `"normal"` or `"flash"`
- `PieceKind` (canal shapes only): its lowercase enum name, ASCII only:
  `"straight"`, `"gentle_curve"`, `"sharp_curve"`, `"symmetric_y"`,
  `"t_branch"`, `"claw"` (not the values `"gentle curve"` or `"T branch"`).
  The floodgate is not a canal kind and has no string here
- `Direction`: its name, case-sensitive: `"E"`, `"NE"`, `"NW"`, `"W"`,
  `"SW"`, `"SE"`

A hex is `{"q": int, "r": int, "terrain": str, "varietal": str | null}`, where
`varietal` is null on every terrain but a vineyard, and on a vineyard too
under roulette rules (a blank plot). `board_to_hexes` writes one per
`Board.tiles` entry, in the board's order; `hexes_to_board` reads them back.

The other shapes, read and written by `calculate_score`:

- canal: `{"q", "r", "kind", "rotation", "owner"}`, one `PlacedCanal`
- floodgate: `{"q", "r", "direction"}`, a `Floodgate` on the canal at `q`,
  `r`, closing its opening `direction`
- claim: `{"q", "r", "player", "varietal"}`, one vineyard claim; `varietal`
  (optional, default null) is what the roulette planted there, a
  `Board.plantings` entry
- player: `{"id", "debt", "season", "drought"}` (`season` and `drought` optional,
  default 0); the list order is the seat order (seats 1 to N)
- score: one `Score`, its `watered_vineyards` each with the canal path in the
  canal shape; a vertex vineyard (Rules v3) has `hexes` (its vertex) in place
  of `q` and `r`
- planted vineyard (Rules v3): `{"hexes", "player", "varietal"}`, one
  `PlantedVineyard`; a vertex is its 3 hexes `[[q, r], [q, r], [q, r]]` in
  hex order
- river strip (Rules v3 open board): `{"segments": [[[q, r], ...], ...]}`

The preset shape, written by `simulate_game` (the `preset` of
`SimResult.to_json()`) and read back as its `overrides`: `mode` by value,
`rounds` keyed by player count as a string (`"2"` to `"5"`), `bag_mix` keyed
by the lowercase `PieceKind` name (`"straight"` ... `"floodgate"`, the
floodgate included), `vineyard_distance` as `[low, high]`, `varietal_rules`
by value, `varietal_points` keyed by varietal name, `roulette` as a list of
varietal names, `grape_clusters_per_player` as an int or null (no cap),
`bribe_rules` by value, `action_die` as a list of face values,
`season_points`, `drought_points` and `season_roll_every` as an int or null,
`planting` by value (`"hexes"` or `"vertices"`; left out of `simulate_game`'s
JSON when `"hexes"`), `board_shape` by value (`"field"` or `"river_strip"`),
`river_hexes_per_segment` as an int, and `bag_size` keyed by player count as a
string (all three left out of `simulate_game`'s JSON at their defaults),
`multiple_bodegas` and `season_roll_personal_faces` as bools, `seat_bonus`
keyed by player count as a string with a list of ints each, the rest as ints. `overrides_from_json` turns those keys
back into `int`, `PieceKind`, and `Varietal`, the names into `VarietalRules`,
`BribeRules`, `DieFace`, and `Varietal`, and the lists into tuples; every value check is left to
`Preset`.

The piece shape, read by `generate_piece_stl` (and `build_plate`): `PieceJSON`,
one object per printable piece, told apart by `type` (`"terrain"`,
`"canal"`, `"floodgate"`, `"owner_token"`, `"grape_cluster"`,
`"debt_token"`, `"qr_plate"`), with the sizes of its `acequias.cad` generator in mm.
`piece_variant` and `piece_params` split one into the arguments of
`acequias.cad.pieces.build_piece`. `build_plate` reads a list of
`PlateEntryJSON`: `{"piece": PieceJSON, "count": int, "color": str}`.

Reading JSON back leaves the checks to the model: `Hex`, `Tile`, and `Board`
raise `ValueError` or `TypeError` on a bad hex, and the `*_from_json`
functions raise `ValueError` on an unknown string, so a tool wrapped with
`tool_errors` reports them as tool errors. No game logic lives here.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    model_validator,
    with_config,
)
from typing_extensions import TypedDict

from acequias.assembly import AssemblyStep
from acequias.config import (
    PLAYER_COUNTS,
    Blend,
    BlendRule,
    EndCondition,
    BodegaPlacement,
    BoardShape,
    BribeRules,
    PlantingRules,
    VarietalRules,
    players_text,
)
from acequias.config import preset as shipped_preset
from acequias.hex import Direction, Hex, Vertex
from acequias.model import (
    ROTATIONS,
    Board,
    BodegaBuilding,
    DieFace,
    Floodgate,
    Mode,
    PieceKind,
    PlacedCanal,
    PlantedVineyard,
    Player,
    RiverStrip,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import Score, WateredBodega, WateredVineyard

TerrainName = Literal["river", "vineyard", "stone", "empty"]
VarietalName = Literal[
    "malbec",
    "cabernet_sauvignon",
    "cabernet_franc",
    "syrah",
    "merlot",
    "bonarda",
    "torrontes",
    "chardonnay",
]
VarietalRulesName = Literal["fixed", "roulette"]
BribeRulesName = Literal["d6", "action_die"]
PlantingName = Literal["hexes", "vertices"]
BoardShapeName = Literal["field", "river_strip"]
BlendRuleName = Literal["each_once", "disjoint"]
EndConditionName = Literal[
    "rounds", "bag_empty", "vineyards_out", "score_target", "supply_empty", "dead_turns"
]
TriggerName = Literal["bag_empty", "vineyards_out", "score_target", "supply_empty", "dead_turns"]
BodegaPlacementName = Literal["new_spot", "replace"]
DieFaceName = Literal["floodgate", "release", "resow", "move", "good_season", "drought"]
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
_RULES_BY_NAME = {rules.value: rules for rules in VarietalRules}
_BRIBE_RULES_BY_NAME = {rules.value: rules for rules in BribeRules}
_PLANTING_BY_NAME = {rules.value: rules for rules in PlantingRules}
_BOARD_SHAPE_BY_NAME = {shape.value: shape for shape in BoardShape}
_BLEND_RULE_BY_NAME = {rule.value: rule for rule in BlendRule}
_END_CONDITION_BY_NAME = {end.value: end for end in EndCondition}
_BODEGA_PLACEMENT_BY_NAME = {placement.value: placement for placement in BodegaPlacement}
_FACE_BY_NAME = {face.value: face for face in DieFace}
_KIND_BY_NAME = {kind.name.lower(): kind for kind in PieceKind if kind.is_canal}
_DIRECTION_BY_NAME = {direction.name: direction for direction in Direction}
_PIECE_BY_NAME = {kind.name.lower(): kind for kind in PieceKind}
_PLAYER_COUNT_BY_NAME = {str(players): players for players in PLAYER_COUNTS}

MODE_PLAYERS = "; ".join(
    f"{mode.value} {players_text(shipped_preset(mode).player_counts)}" for mode in Mode
)
"""The player counts each mode is for, from the shipped presets: "normal 2 to 5; flash 2 to 3"."""


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
        description=(
            "The grape on a vineyard (lowercase ASCII); null on every other terrain, "
            "and on a blank vineyard under roulette rules."
        )
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
    varietal: VarietalName | None = Field(
        default=None,
        description=(
            "Under roulette rules, the grape the roulette planted on this blank vineyard "
            "(lowercase ASCII); null under fixed rules, where the hex has the varietal."
        ),
    )


class PlayerJSON(BaseModel):
    """A player and the bribe debt they carry."""

    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1, description="Player id, a non-empty string.")
    debt: int = Field(ge=0, description="Bribe debt, 0 or more.")
    season: int = Field(default=0, ge=0, description="Good season gains of the action die.")
    drought: int = Field(
        default=0,
        ge=0,
        description="Drought losses of the action die (scoring never takes a total below 0).",
    )


def _is_none(value: object) -> bool:
    return value is None


VertexJSON = Annotated[
    list[Annotated[list[int], Field(min_length=2, max_length=2)]],
    Field(
        min_length=3,
        max_length=3,
        description="A hex vertex (Rules v3) as its 3 hexes, [[q, r], [q, r], [q, r]], in hex order.",
    ),
]


class PlantedVineyardJSON(BaseModel):
    """A vineyard planted on a hex vertex (Rules v3): its spot, its owner, and its varietal."""

    model_config = ConfigDict(extra="forbid", strict=True)

    hexes: VertexJSON
    player: str = Field(description="Id of the player who planted it (its owner).")
    varietal: VarietalName = Field(description="The grape the roulette gave it (lowercase ASCII).")


class BodegaBuildingJSON(BaseModel):
    """A bodega built on a hex vertex (Rules v3 bodega_building, #166): its spot and builder."""

    model_config = ConfigDict(extra="forbid", strict=True)

    hexes: VertexJSON
    player: str = Field(description="Id of the player who built it.")


class WateredBodegaJSON(BaseModel):
    """A bodega building with at least one of the player's watered thirds (#166)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    hexes: VertexJSON
    builder: str = Field(description="Id of the player who built it.")
    thirds: int = Field(description="The player's watered thirds of it, 1 to 3.")
    points: int = Field(
        description="What the player scores from it: bodega_building_points x thirds / 3, rounded down."
    )


class RiverStripJSON(BaseModel):
    """The river strip of a Rules v3 open board (board_shape "river_strip")."""

    model_config = ConfigDict(extra="forbid", strict=True)

    segments: list[list[Annotated[list[int], Field(min_length=2, max_length=2)]]] = Field(
        description=(
            "The printed river pieces north to south, each its river hexes [q, r] north to "
            "south, one per row from r 0. East of each row's river hex the table is open."
        )
    )


class WateredVineyardJSON(BaseModel):
    """One watered vineyard and the water rights it causes.

    A hex vineyard has `q` and `r`; a vertex vineyard (Rules v3) has `hexes`
    instead, plus `planter`, `thirds` and `points` (split scoring).
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    q: int | None = Field(
        default=None, exclude_if=_is_none,
        description="Axial q coordinate of a hex vineyard; left out for a vertex vineyard.",
    )
    r: int | None = Field(
        default=None, exclude_if=_is_none,
        description="Axial r coordinate of a hex vineyard; left out for a vertex vineyard.",
    )
    hexes: VertexJSON | None = Field(
        default=None, exclude_if=_is_none,
        description=(
            "Rules v3: the vertex the vineyard is planted on, as its 3 hexes [[q, r], ...]; "
            "left out for a hex vineyard."
        ),
    )
    varietal: VarietalName = Field(description="The grape (lowercase ASCII).")
    path: list[CanalJSON] = Field(
        description=(
            "The canals the water runs through, from the river end to the vineyard. For a "
            "vertex vineyard: the player's watered canals on its vertex, one per third."
        )
    )
    pays: list[str] = Field(
        description=(
            "Rival ids the claimant pays 1 point each (owners on the path), in seat order. "
            "Always empty for a vertex vineyard (no water rights under Rules v3)."
        )
    )
    planter: str | None = Field(
        default=None, exclude_if=_is_none,
        description="Rules v3: who planted the vertex vineyard; left out for a hex vineyard.",
    )
    thirds: int | None = Field(
        default=None, exclude_if=_is_none,
        description=(
            "Rules v3: the player's watered thirds of the vertex vineyard, 1 to 3 (canals of "
            "theirs carrying water on its hexes); left out for a hex vineyard."
        ),
    )
    points: int | None = Field(
        default=None, exclude_if=_is_none,
        description=(
            "Rules v3: what the player scores from the vertex vineyard, value x thirds / 3 "
            "rounded down; left out for a hex vineyard."
        ),
    )

    @model_validator(mode="after")
    def _one_spot(self) -> WateredVineyardJSON:
        if self.hexes is None and (self.q is None or self.r is None):
            raise ValueError("a watered vineyard needs q and r (a hex) or hexes (a vertex)")
        if self.hexes is not None and (self.q is not None or self.r is not None):
            raise ValueError("a watered vineyard has q and r (a hex) or hexes (a vertex), not both")
        return self


_BODEGAS_DESCRIPTION = (
    "Bodega bonuses earned: 0 or 1, or with multiple_bodegas the largest number of disjoint "
    "groups of bodega_varietals watered vineyards, each of distinct varietals."
)


class ScoreJSON(BaseModel):
    """One player's final score, by term."""

    model_config = ConfigDict(extra="forbid", strict=True)

    player: str = Field(description="Player id.")
    seat: int = Field(description="Seat number, 1 to N in the order of the input players.")
    vineyards: int = Field(description="Points from the player's watered claimed vineyards.")
    bodega: int = Field(
        description="Bodega bonus for watering enough different varietals: bodegas x bodega_points."
    )
    rights_paid: int = Field(
        description=(
            "Water rights paid to rivals, in points: water_right_points per rival per vineyard."
        )
    )
    rights_collected: int = Field(description="Water rights collected from rivals, in points.")
    debt: int = Field(description="Bribe debt.")
    season: int = Field(description="Good season gains of the action die.")
    drought: int = Field(
        description=(
            "Drought losses of the action die actually taken: clamped so the total never goes "
            "below 0 because of them."
        )
    )
    total: int = Field(
        description=(
            "vineyards + bodega + blend + buildings - rights_paid + rights_collected - debt "
            "+ season + seat_bonus - drought."
        )
    )
    watered: int = Field(description="Number of watered claimed vineyards (the tie-break).")
    watered_vineyards: list[WateredVineyardJSON] = Field(
        description="The player's watered claimed vineyards, by hex."
    )
    bodegas: int = Field(description=_BODEGAS_DESCRIPTION)
    seat_bonus: int = Field(
        description="Seat bonus points for the player's position in round 1's turn order."
    )
    blend: int | None = Field(
        default=None, exclude_if=_is_none,
        description="Rules v3 blends (#166): the blend bonus points; left out when 0.",
    )
    blends: list[str] | None = Field(
        default=None, exclude_if=_is_none,
        description=(
            'Rules v3 blends: the blends scored, by name (e.g. "Malbec + Cabernet Franc"), in '
            "the preset's order; left out when none."
        ),
    )
    buildings: int | None = Field(
        default=None, exclude_if=_is_none,
        description="Rules v3 bodega buildings (#166): their split points; left out when 0.",
    )
    watered_bodegas: list[WateredBodegaJSON] | None = Field(
        default=None, exclude_if=_is_none,
        description=(
            "Rules v3 bodega buildings with one of the player's watered thirds, by vertex; "
            "left out when none."
        ),
    )


_ROUNDS_DESCRIPTION = (
    'Rounds per player count, keyed "2" to "5"; the keys are the player counts the mode is '
    f"for ({MODE_PLAYERS} in the shipped presets), and any other count is rejected."
)
_BAG_MIX_DESCRIPTION = (
    'Percentage of the bag for each piece kind, keyed "straight", "gentle_curve", '
    '"sharp_curve", "symmetric_y", "t_branch", "claw", "floodgate".'
)
_DISTANCE_DESCRIPTION = "[low, high]: how far, in hexes, a vineyard lies from the river."
_RULES_DESCRIPTION = (
    'How vineyards get their varietal: "fixed" (dealt on the board) or "roulette" '
    "(blank plots, planted by a roulette spin when claimed)."
)
_POINTS_DESCRIPTION = (
    "Points of a watered vineyard by varietal name; under fixed rules its keys are "
    "the varietals dealt on the board."
)
_ROULETTE_DESCRIPTION = "The roulette's sectors in order, one varietal name each."
_CLUSTERS_DESCRIPTION = (
    "Grape clusters (claims) each player can hold; null means no cap. A player at "
    "the cap claims nothing more, and the vineyards they water stay unclaimed."
)
_BRIBE_RULES_DESCRIPTION = (
    'What the bribe is: "d6" (roll the bribe die, add the roll to your debt, remove or '
    'move a floodgate) or "action_die" (pay action_die_cost in debt, roll the action die, '
    "use its face; floodgates come only from the die, so bag_mix gives them 0)."
)
_WATER_RIGHT_DESCRIPTION = "Points a vineyard pays each distinct rival on its water path."
_DIE_COST_DESCRIPTION = "Debt one roll of the action die costs (action_die rules)."
_ACTION_DIE_DESCRIPTION = (
    'The faces of the action die in order, each "floodgate", "release", "resow", "move" '
    '(planting "vertices" only), "good_season", or "drought" (action_die rules). A season '
    "face (good_season, drought) applies to every player when rolled."
)
_SEASON_POINTS_DESCRIPTION = (
    "Points every player gains on a good_season face; null: one common vineyard plot's value."
)
_DROUGHT_POINTS_DESCRIPTION = (
    "Points every player loses on a drought face; null: half the good season gain, "
    "rounded down, at least 1."
)
_MULTIPLE_BODEGAS_DESCRIPTION = (
    "Whether a player can earn the bodega bonus more than once: once per disjoint group of "
    "bodega_varietals watered vineyards of distinct varietals. false: at most once."
)
_SEASON_ROLL_PERSONAL_FACES_DESCRIPTION = (
    "Whether a season roll's personal face (floodgate, release, resow) is the holder's to use. "
    "false: the season roll applies only a good season or a drought, and a personal face does "
    "nothing. Voluntary rolls keep every face."
)
_SEAT_BONUS_DESCRIPTION = (
    'Seat bonus points per player count, keyed "2" to "5": one value per seat, the first for '
    "round 1's start player, then in turn order. A player count not given has no bonus; {} is off."
)
_SEASON_ROLL_DESCRIPTION = (
    "Every this many rounds the season die's holder rolls the action die for free before "
    "the start player's turn, without spending their own (action_die rules); the season die "
    "starts with the first start player and passes left after each season roll. null: off."
)


_PLANTING_DESCRIPTION = (
    'Where vineyards grow: "hexes" (vineyard tiles, Rules v1 and v2) or "vertices" '
    "(Rules v3, the shipped game: no vineyard tiles; vineyards are planted on hex vertices next "
    "to the planter's own watered canal). \"vertices\" needs varietal_rules \"roulette\"."
)
_BOARD_SHAPE_DESCRIPTION = (
    'What the board is: "field" (the generated hex board, Rules v1 and v2) or "river_strip" '
    "(Rules v3, the shipped game: only a river strip, a base segment for 2 players plus one per extra "
    'player, with an open table east of it; no stones). "river_strip" needs planting '
    '"vertices" and a bag_size for every player count.'
)
_RIVER_HEXES_DESCRIPTION = "River hexes in each segment of the river strip board (default 5)."
_BAG_SIZE_DESCRIPTION = (
    'Pieces in the bag (market included) per player count, keyed "2" to "5". A player count '
    "not given gets one piece per empty hex of the board; {} is off."
)
_THREE_CANALS_DESCRIPTION = (
    'Rules v3 only (planting "vertices"): whether a vineyard may be planted only on a vertex '
    "whose 3 hexes all hold a canal. false: a vertex with a river or empty hex may be planted, "
    "and that third scores for nobody. false by default; left out of simulate_game's JSON "
    "when false."
)


def _is_one(value: object) -> bool:
    return value == 1


_VARIETAL_BODEGA_DESCRIPTION = (
    "Rules v3 (#166): whether the bodega bonus for bodega_varietals distinct varietals is "
    "scored; false turns it off (blends replace it). true by default; left out when true."
)
_BLENDS_DESCRIPTION = (
    "Rules v3 (#166): the blend (corte) table, each {\"varietals\": [2 or more distinct "
    "varietals, red, white or mixed], \"points\": bonus}. A player holds a varietal when they "
    "own a watered third of a vineyard of it. Needs planting \"vertices\"."
)
_BLEND_RULE_DESCRIPTION = (
    'Rules v3 (#166): "each_once" (each held blend scores once; a vineyard may count for '
    'several) or "disjoint" (the best set of distinct blends with no vineyard used twice).'
)
_BODEGA_BUILDING_DESCRIPTION = (
    'Rules v3 (#166): adds the "build a bodega" action, a bodega worth bodega_building_points '
    "split in thirds like a vineyard. false by default; left out when false. Needs planting "
    '"vertices".'
)
_BODEGA_PLACEMENT_DESCRIPTION = (
    'Rules v3 (#166): where a bodega goes: "new_spot" (a free vertex the player may plant on) '
    'or "replace" (in place of one of their planted vineyards).'
)
_BODEGA_MIN_DESCRIPTION = (
    "Rules v3 (#166): the planted vineyards of their own a player needs to build a bodega, 0 or more."
)
_BODEGA_REDS_DESCRIPTION = (
    "Rules v3 (#166): the distinct red varietals among a player's own planted vineyards a "
    "bodega needs, 0 or more."
)
_BODEGA_WHITES_DESCRIPTION = (
    "Rules v3 (#166): the distinct white varietals (torrontes, chardonnay) among a player's own "
    "planted vineyards a bodega needs, 0 or more."
)
_BODEGA_POINTS_DESCRIPTION = "Rules v3 (#166): a bodega building's points, split in thirds."
_BODEGAS_PER_PLAYER_DESCRIPTION = "Rules v3 (#166): the most bodegas a player may build (null: no cap)."
_BRIBE_OPTIONAL_DESCRIPTION = (
    "Rules v3 (#168): whether the floodgate and release faces are optional, with the bribe "
    "(action_die_cost) paid only when the player places or removes a floodgate; declining costs "
    "nothing. false (the default): those faces are mandatory and the bribe is paid on the roll. "
    'Needs planting "vertices".'
)

_END_CONDITION_DESCRIPTION = (
    'Rules v3 (#163): what ends the game: "rounds" (the round count, the default), "bag_empty" '
    '(the bag and the market are empty), "vineyards_out" (a player has planted all their '
    'vineyard_markers) or "score_target" (a player reaches score_target). A trigger that never '
    'fires ends the game after twice the round count. Any but "rounds" needs planting "vertices".'
)
_FINISH_ROUND_DESCRIPTION = (
    "Rules v3 (#163): true (the default) plays out the round in which the end condition fired, "
    "so everyone has the same number of turns; false ends the game right after that turn."
)
_MARKERS_DESCRIPTION = (
    'Rules v3 (#163): vineyard markers per player for "vineyards_out", keyed "2" to "5"; a '
    "player count not given uses the default (Normal 6 / 9 / 7 / 6, Flash 3)."
)
_SCORE_TARGET_DESCRIPTION = (
    'Rules v3 (#163): the target score for "score_target", keyed "2" to "5"; a player count not '
    "given uses the default (Normal 30 / 51 / 43 / 37, Flash 14)."
)
_UNLIMITED_BAG_DESCRIPTION = (
    "Rules v3 (#163): whether the bag never runs out (each piece drawn goes back to its bottom)."
)
_SUPPLY_DESCRIPTION = (
    'Rules v3 (#181): the shared vineyard supply, keyed "2" to "5": a multiplier m, so the supply '
    "holds m pieces per roulette sector of each varietal and every planted vineyard takes one. "
    "A player count not given has no supply. Needs planting \"vertices\"."
)
_MAX_SPINS_DESCRIPTION = (
    "Rules v3 (#181): spins a plant or a resow may make: a spin on a varietal with no piece left "
    "in the supply is spun again, up to this many spins; when all fail the turn is lost."
)
_END_CONDITIONS_DESCRIPTION = (
    'Rules v3 (#181): several end triggers at once (no "rounds", no repeats); the first to fire '
    'ends the game. "supply_empty": the vineyard supply is empty; "dead_turns": every player '
    'has lost 2 turns in a row (ends the game at once). Needs end_condition "rounds".'
)


class BlendJSON(BaseModel):
    """One blend (corte) of the Rules v3 blend table (#166)."""

    model_config = ConfigDict(extra="forbid", strict=True)

    varietals: list[VarietalName] = Field(description="The blend's varietals, 2 or more, distinct.")
    points: int = Field(description="The blend's bonus points, 1 or more.")


@with_config(ConfigDict(extra="forbid"))
class BlendOverrideJSON(TypedDict):
    """One blend (corte) in an overrides object."""

    varietals: Annotated[list[VarietalName], Field(description="2 or more distinct varietals.")]
    points: Annotated[StrictInt, Field(description="Bonus points, 1 or more.")]


class PresetJSON(BaseModel):
    """Every value of a game preset (the numbers of one mode), after overrides."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mode: ModeName = Field(description="The mode the preset belongs to.")
    rounds: dict[PlayerCountName, int] = Field(description=_ROUNDS_DESCRIPTION)
    hexes_per_player: int = Field(description="Board hexes per player.")
    vineyards_per_player: int = Field(description="Vineyard plots per player.")
    stone_share: int = Field(description="Percentage of non-river hexes that are stone.")
    vineyard_distance: list[int] = Field(
        min_length=2, max_length=2, description=_DISTANCE_DESCRIPTION
    )
    market_size: int = Field(description="Pieces face up in the market.")
    bag_mix: dict[PieceName, int] = Field(description=_BAG_MIX_DESCRIPTION)
    die_faces: int = Field(description="Faces of the bribe d6 (d6 rules).")
    bodega_points: int = Field(description="Points of the bodega bonus.")
    bodega_varietals: int = Field(description="Distinct watered varietals the bodega bonus needs.")
    water_right_points: int = Field(description=_WATER_RIGHT_DESCRIPTION)
    varietal_rules: VarietalRulesName = Field(description=_RULES_DESCRIPTION)
    varietal_points: dict[VarietalName, int] = Field(description=_POINTS_DESCRIPTION)
    roulette: list[VarietalName] = Field(description=_ROULETTE_DESCRIPTION)
    grape_clusters_per_player: int | None = Field(description=_CLUSTERS_DESCRIPTION)
    bribe_rules: BribeRulesName = Field(description=_BRIBE_RULES_DESCRIPTION)
    action_die_cost: int = Field(description=_DIE_COST_DESCRIPTION)
    action_die: list[DieFaceName] = Field(description=_ACTION_DIE_DESCRIPTION)
    season_points: int | None = Field(description=_SEASON_POINTS_DESCRIPTION)
    drought_points: int | None = Field(description=_DROUGHT_POINTS_DESCRIPTION)
    season_roll_every: int | None = Field(description=_SEASON_ROLL_DESCRIPTION)
    multiple_bodegas: bool = Field(description=_MULTIPLE_BODEGAS_DESCRIPTION)
    season_roll_personal_faces: bool = Field(description=_SEASON_ROLL_PERSONAL_FACES_DESCRIPTION)
    seat_bonus: dict[PlayerCountName, list[int]] = Field(description=_SEAT_BONUS_DESCRIPTION)
    # Rules v3 options (#149), left out of simulate_game's JSON at their defaults.
    planting: PlantingName | None = Field(
        default=None, exclude_if=_is_none,
        description=_PLANTING_DESCRIPTION + ' Left out when "hexes".',
    )
    vertex_needs_three_canals: bool | None = Field(
        default=None, exclude_if=_is_none, description=_THREE_CANALS_DESCRIPTION
    )
    board_shape: BoardShapeName | None = Field(
        default=None, exclude_if=_is_none,
        description=_BOARD_SHAPE_DESCRIPTION + ' Left out when "field".',
    )
    river_hexes_per_segment: int | None = Field(
        default=None, exclude_if=_is_none,
        description=_RIVER_HEXES_DESCRIPTION + " Left out at the default.",
    )
    bag_size: dict[PlayerCountName, int] | None = Field(
        default=None, exclude_if=_is_none, description=_BAG_SIZE_DESCRIPTION + " Left out when {}."
    )
    # Rules v3 scoring options (#166), left out of simulate_game's JSON at their defaults.
    varietal_bodega: bool | None = Field(
        default=None, exclude_if=_is_none, description=_VARIETAL_BODEGA_DESCRIPTION
    )
    blends: list[BlendJSON] | None = Field(
        default=None, exclude_if=_is_none, description=_BLENDS_DESCRIPTION + " Left out when []."
    )
    blend_rule: BlendRuleName | None = Field(
        default=None, exclude_if=_is_none,
        description=_BLEND_RULE_DESCRIPTION + ' Left out when "each_once".',
    )
    bodega_building: bool | None = Field(
        default=None, exclude_if=_is_none, description=_BODEGA_BUILDING_DESCRIPTION
    )
    bodega_placement: BodegaPlacementName | None = Field(
        default=None, exclude_if=_is_none,
        description=_BODEGA_PLACEMENT_DESCRIPTION + ' Left out when "new_spot".',
    )
    bodega_min_vineyards: int | None = Field(
        default=None, exclude_if=_is_none, description=_BODEGA_MIN_DESCRIPTION + " Left out at 0."
    )
    bodega_min_reds: int | None = Field(
        default=None, exclude_if=_is_none, description=_BODEGA_REDS_DESCRIPTION + " Left out at 2."
    )
    bodega_min_whites: int | None = Field(
        default=None, exclude_if=_is_none,
        description=_BODEGA_WHITES_DESCRIPTION + " Left out at 2.",
    )
    bodega_building_points: int | None = Field(
        default=None, exclude_if=_is_none,
        description=_BODEGA_POINTS_DESCRIPTION + " Left out at 12.",
    )
    bodegas_per_player: int | None = Field(
        default=1, exclude_if=_is_one,
        description=_BODEGAS_PER_PLAYER_DESCRIPTION + " Left out at 1.",
    )
    bribe_optional: bool | None = Field(
        default=None, exclude_if=_is_none,
        description=_BRIBE_OPTIONAL_DESCRIPTION + " Left out when false.",
    )
    # End of game options (#163), left out of simulate_game's JSON at their defaults.
    end_condition: EndConditionName | None = Field(
        default=None, exclude_if=_is_none,
        description=_END_CONDITION_DESCRIPTION + ' Left out when "rounds".',
    )
    finish_round: bool | None = Field(
        default=None, exclude_if=_is_none, description=_FINISH_ROUND_DESCRIPTION + " Left out when true."
    )
    vineyard_markers: dict[PlayerCountName, int] | None = Field(
        default=None, exclude_if=_is_none, description=_MARKERS_DESCRIPTION + " Left out when {}."
    )
    score_target: dict[PlayerCountName, int] | None = Field(
        default=None, exclude_if=_is_none, description=_SCORE_TARGET_DESCRIPTION + " Left out when {}."
    )
    unlimited_bag: bool | None = Field(
        default=None, exclude_if=_is_none, description=_UNLIMITED_BAG_DESCRIPTION + " Left out when false."
    )
    vineyard_supply: dict[PlayerCountName, int | float] | None = Field(
        default=None, exclude_if=_is_none, description=_SUPPLY_DESCRIPTION + " Left out when {}."
    )
    max_spins: int | None = Field(
        default=None, exclude_if=_is_none, description=_MAX_SPINS_DESCRIPTION + " Left out at 1."
    )
    end_conditions: list[TriggerName] | None = Field(
        default=None, exclude_if=_is_none, description=_END_CONDITIONS_DESCRIPTION + " Left out when []."
    )


@with_config(ConfigDict(extra="forbid"))
class PresetOverridesJSON(TypedDict, total=False):
    """Preset values to replace, in the `PresetJSON` shape without `mode`.

    Every key is optional; omitted keys keep the mode's shipped value, and a
    key given replaces that value as a whole. Only keys and types are checked
    here (strict integers); the value rules come from `Preset`.
    """

    rounds: Annotated[
        dict[PlayerCountName, StrictInt],
        Field(
            description=_ROUNDS_DESCRIPTION
            + " Give every player count to play, e.g. {\"2\": 10, ...}; it replaces the mode's."
        ),
    ]
    hexes_per_player: Annotated[StrictInt, Field(description="Board hexes per player.")]
    vineyards_per_player: Annotated[StrictInt, Field(description="Vineyard plots per player.")]
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
    die_faces: Annotated[
        StrictInt, Field(description="Faces of the bribe d6 (d6 rules), 2 or more.")
    ]
    bodega_points: Annotated[StrictInt, Field(description="Points of the bodega bonus.")]
    bodega_varietals: Annotated[
        StrictInt,
        Field(
            description=(
                "Distinct watered varietals the bodega bonus needs, 1 to the number of "
                "varietals in play (varietal_points under fixed rules, the roulette's "
                "under roulette rules)."
            )
        ),
    ]
    water_right_points: Annotated[
        StrictInt, Field(description=_WATER_RIGHT_DESCRIPTION + " 1 or more.")
    ]
    varietal_rules: Annotated[VarietalRulesName, Field(description=_RULES_DESCRIPTION)]
    varietal_points: Annotated[
        dict[VarietalName, StrictInt],
        Field(description=_POINTS_DESCRIPTION + " Each value is 1 or more."),
    ]
    roulette: Annotated[
        list[VarietalName],
        Field(
            description=_ROULETTE_DESCRIPTION
            + " Not empty; under roulette rules every sector needs a varietal_points entry."
        ),
    ]
    grape_clusters_per_player: Annotated[
        StrictInt | None,
        Field(description=_CLUSTERS_DESCRIPTION + " An int is 1 or more."),
    ]
    bribe_rules: Annotated[
        BribeRulesName,
        Field(
            description=_BRIBE_RULES_DESCRIPTION
            + ' "action_die" with a resow face needs varietal_rules "roulette".'
        ),
    ]
    action_die_cost: Annotated[
        StrictInt, Field(description=_DIE_COST_DESCRIPTION + " 0 or more.")
    ]
    action_die: Annotated[
        list[DieFaceName], Field(description=_ACTION_DIE_DESCRIPTION + " Not empty.")
    ]
    season_points: Annotated[
        StrictInt | None, Field(description=_SEASON_POINTS_DESCRIPTION + " An int is 1 or more.")
    ]
    drought_points: Annotated[
        StrictInt | None, Field(description=_DROUGHT_POINTS_DESCRIPTION + " An int is 1 or more.")
    ]
    season_roll_every: Annotated[
        StrictInt | None, Field(description=_SEASON_ROLL_DESCRIPTION + " An int is 1 or more.")
    ]
    multiple_bodegas: Annotated[StrictBool, Field(description=_MULTIPLE_BODEGAS_DESCRIPTION)]
    season_roll_personal_faces: Annotated[
        StrictBool, Field(description=_SEASON_ROLL_PERSONAL_FACES_DESCRIPTION)
    ]
    seat_bonus: Annotated[
        dict[PlayerCountName, list[StrictInt]],
        Field(description=_SEAT_BONUS_DESCRIPTION + " Each list has one int >= 0 per player."),
    ]
    planting: Annotated[PlantingName, Field(description=_PLANTING_DESCRIPTION)]
    vertex_needs_three_canals: Annotated[StrictBool, Field(description=_THREE_CANALS_DESCRIPTION)]
    board_shape: Annotated[BoardShapeName, Field(description=_BOARD_SHAPE_DESCRIPTION)]
    river_hexes_per_segment: Annotated[
        StrictInt, Field(description=_RIVER_HEXES_DESCRIPTION + " 1 or more.")
    ]
    bag_size: Annotated[
        dict[PlayerCountName, StrictInt],
        Field(description=_BAG_SIZE_DESCRIPTION + " Each value is 1 or more."),
    ]
    varietal_bodega: Annotated[StrictBool, Field(description=_VARIETAL_BODEGA_DESCRIPTION)]
    blends: Annotated[list[BlendOverrideJSON], Field(description=_BLENDS_DESCRIPTION)]
    blend_rule: Annotated[BlendRuleName, Field(description=_BLEND_RULE_DESCRIPTION)]
    bodega_building: Annotated[StrictBool, Field(description=_BODEGA_BUILDING_DESCRIPTION)]
    bodega_placement: Annotated[
        BodegaPlacementName, Field(description=_BODEGA_PLACEMENT_DESCRIPTION)
    ]
    bodega_min_vineyards: Annotated[StrictInt, Field(description=_BODEGA_MIN_DESCRIPTION)]
    bodega_min_reds: Annotated[StrictInt, Field(description=_BODEGA_REDS_DESCRIPTION)]
    bodega_min_whites: Annotated[StrictInt, Field(description=_BODEGA_WHITES_DESCRIPTION)]
    bodega_building_points: Annotated[
        StrictInt, Field(description=_BODEGA_POINTS_DESCRIPTION + " 1 or more.")
    ]
    bodegas_per_player: Annotated[
        StrictInt | None,
        Field(description=_BODEGAS_PER_PLAYER_DESCRIPTION + " An int is 1 or more."),
    ]
    bribe_optional: Annotated[StrictBool, Field(description=_BRIBE_OPTIONAL_DESCRIPTION)]
    end_condition: Annotated[EndConditionName, Field(description=_END_CONDITION_DESCRIPTION)]
    finish_round: Annotated[StrictBool, Field(description=_FINISH_ROUND_DESCRIPTION)]
    vineyard_markers: Annotated[
        dict[PlayerCountName, StrictInt],
        Field(description=_MARKERS_DESCRIPTION + " Each value is 1 or more."),
    ]
    score_target: Annotated[
        dict[PlayerCountName, StrictInt],
        Field(description=_SCORE_TARGET_DESCRIPTION + " Each value is 1 or more."),
    ]
    unlimited_bag: Annotated[StrictBool, Field(description=_UNLIMITED_BAG_DESCRIPTION)]
    vineyard_supply: Annotated[
        dict[PlayerCountName, StrictInt | StrictFloat],
        Field(description=_SUPPLY_DESCRIPTION + " Each value is above 0, an integer or not (e.g. 1.25)."),
    ]
    max_spins: Annotated[StrictInt, Field(description=_MAX_SPINS_DESCRIPTION + " 1 or more.")]
    end_conditions: Annotated[list[TriggerName], Field(description=_END_CONDITIONS_DESCRIPTION)]


def _blend_from_json(item: object) -> Blend:
    """The `Blend` for one `{"varietals", "points"}` object; `Blend` checks the values."""
    if not isinstance(item, Mapping) or set(item) != {"varietals", "points"}:
        raise ValueError(f"a blend needs exactly the keys varietals, points; got {item!r}")
    names = item["varietals"]
    if isinstance(names, (str, bytes, Mapping)) or not isinstance(names, Iterable):
        raise TypeError(f"a blend's varietals must be a list of varietal names, got {names!r}")
    varietals = [_lookup("blend varietal", name, _VARIETAL_BY_NAME) for name in names]
    if len(set(varietals)) != len(varietals):
        raise ValueError(f"a blend lists a varietal twice: {list(names)!r}")
    return Blend(frozenset(varietals), item["points"])


def blend_to_json(blend: Blend) -> dict[str, Any]:
    """A `Blend` as `{"varietals", "points"}`, the varietals in `Varietal` order."""
    return {
        "varietals": [varietal_to_json(v) for v in Varietal if v in blend.varietals],
        "points": blend.points,
    }


def overrides_from_json(overrides: Mapping[str, Any]) -> dict[str, Any]:
    """The `with_overrides` keyword arguments for an overrides JSON object.

    `rounds` and `seat_bonus` keys become `int` (`seat_bonus` lists tuples), `bag_mix` keys `PieceKind`, `varietal_points`
    keys `Varietal`, `varietal_rules` a `VarietalRules`, `roulette` a tuple
    of `Varietal`, `bribe_rules` a `BribeRules`, `action_die` a tuple of
    `DieFace`, and `vineyard_distance` a tuple; every other value is
    passed on as is, for `Preset` to check. Raises `ValueError` on a key or
    name that is not one.
    """
    if not isinstance(overrides, Mapping):
        raise TypeError(f"overrides must be an object, got {overrides!r}")
    changes = dict(overrides)
    if isinstance(changes.get("rounds"), Mapping):
        changes["rounds"] = {
            _lookup("rounds key", key, _PLAYER_COUNT_BY_NAME): value
            for key, value in changes["rounds"].items()
        }
    if isinstance(changes.get("seat_bonus"), Mapping):
        changes["seat_bonus"] = {
            _lookup("seat_bonus key", key, _PLAYER_COUNT_BY_NAME): (
                tuple(value) if isinstance(value, (list, tuple)) else value
            )
            for key, value in changes["seat_bonus"].items()
        }
    if isinstance(changes.get("bag_size"), Mapping):
        changes["bag_size"] = {
            _lookup("bag_size key", key, _PLAYER_COUNT_BY_NAME): value
            for key, value in changes["bag_size"].items()
        }
    for name in ("vineyard_markers", "score_target", "vineyard_supply"):
        if isinstance(changes.get(name), Mapping):
            changes[name] = {
                _lookup(f"{name} key", key, _PLAYER_COUNT_BY_NAME): value
                for key, value in changes[name].items()
            }
    if "end_condition" in changes:
        changes["end_condition"] = _lookup(
            "end_condition", changes["end_condition"], _END_CONDITION_BY_NAME
        )
    if isinstance(changes.get("end_conditions"), (list, tuple)):
        changes["end_conditions"] = tuple(
            _lookup("end_conditions item", name, _END_CONDITION_BY_NAME)
            for name in changes["end_conditions"]
        )
    if "board_shape" in changes:
        changes["board_shape"] = _lookup(
            "board_shape", changes["board_shape"], _BOARD_SHAPE_BY_NAME
        )
    if isinstance(changes.get("bag_mix"), Mapping):
        changes["bag_mix"] = {
            _lookup("bag_mix key", key, _PIECE_BY_NAME): value
            for key, value in changes["bag_mix"].items()
        }
    if isinstance(changes.get("vineyard_distance"), (list, tuple)):
        changes["vineyard_distance"] = tuple(changes["vineyard_distance"])
    if "varietal_rules" in changes:
        changes["varietal_rules"] = _lookup(
            "varietal_rules", changes["varietal_rules"], _RULES_BY_NAME
        )
    if isinstance(changes.get("varietal_points"), Mapping):
        changes["varietal_points"] = {
            _lookup("varietal_points key", key, _VARIETAL_BY_NAME): value
            for key, value in changes["varietal_points"].items()
        }
    if isinstance(changes.get("roulette"), (list, tuple)):
        changes["roulette"] = tuple(
            _lookup("roulette sector", name, _VARIETAL_BY_NAME) for name in changes["roulette"]
        )
    if "bribe_rules" in changes:
        changes["bribe_rules"] = _lookup(
            "bribe_rules", changes["bribe_rules"], _BRIBE_RULES_BY_NAME
        )
    if "planting" in changes:
        changes["planting"] = _lookup("planting", changes["planting"], _PLANTING_BY_NAME)
    if isinstance(changes.get("blends"), (list, tuple)):
        changes["blends"] = tuple(_blend_from_json(item) for item in changes["blends"])
    if "blend_rule" in changes:
        changes["blend_rule"] = _lookup("blend_rule", changes["blend_rule"], _BLEND_RULE_BY_NAME)
    if "bodega_placement" in changes:
        changes["bodega_placement"] = _lookup(
            "bodega_placement", changes["bodega_placement"], _BODEGA_PLACEMENT_BY_NAME
        )
    if isinstance(changes.get("action_die"), (list, tuple)):
        changes["action_die"] = tuple(
            _lookup("action_die face", name, _FACE_BY_NAME) for name in changes["action_die"]
        )
    return changes


# --- Printable pieces -------------------------------------------------------
#
# One shape per piece type, told apart by `type`; `PieceJSON` is their union.
# `generate_piece_stl` and `build_plate` read the same objects. Every
# default is the default of the `acequias.cad` generator the type maps to
# (`acequias.cad.pieces`); the CAD modules are not imported here, so the
# numbers are repeated, and a test checks they match. Only the plain limits
# are checked here; the CAD functions check the combinations.

MAX_LENGTH_MM = 100.0
"""The largest length a piece parameter takes, in mm."""

MAX_FIT_MM = 2.0
"""The largest clearance or tolerance a piece parameter takes, in mm."""

DebtValue = Literal[1, 5]

QrLanguage = Literal["reglas", "rules"]

_LENGTH_LIMITS = f"above 0 and at most {MAX_LENGTH_MM:g}"
_FIT_LIMITS = f"0 to {MAX_FIT_MM:g}"


def _length(default: float, description: str) -> Any:
    return Field(default, gt=0, le=MAX_LENGTH_MM, description=f"{description}, in mm, {_LENGTH_LIMITS}.")


def _fit(default: float, description: str) -> Any:
    return Field(default, ge=0, le=MAX_FIT_MM, description=f"{description}, in mm, {_FIT_LIMITS}.")


def _side() -> Any:
    return _length(16.0, "Nominal hex side (corner to corner is twice this)")


def _tile_height() -> Any:
    return _length(4.0, "Height of the tile")


def _clearance() -> Any:
    return _fit(0.0, "Gap each edge moves in, between neighboring printed tiles")


def _groove_width(fits: str = "") -> Any:
    return _length(6.0, "Width of the canal groove" + fits)


def _groove_depth(fits: str = "") -> Any:
    return _length(1.5, "Depth of the canal groove" + fits)


_MATCH_CANALS = "; must match the canal pieces the floodgate goes in"


def _reject_bool(value: Any) -> Any:
    if type(value) is not int:
        raise ValueError(f"must be the integer 1 or 5, got {value!r}")
    return value


class TerrainPieceJSON(BaseModel):
    """A terrain hex: for the MVP the plain hexagonal tile, the same for every terrain."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["terrain"] = Field(description='Piece type: "terrain".')
    terrain: TerrainName = Field(description="The hex terrain; it names the file only.")
    side: float = _side()
    height: float = _tile_height()
    clearance: float = _clearance()


class CanalPieceJSON(BaseModel):
    """A canal piece: a hex tile with a groove, and a hole for the owner token."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["canal"] = Field(description='Piece type: "canal".')
    kind: KindName = Field(description="The canal shape (lowercase ASCII); a floodgate is not a canal.")
    side: float = _side()
    height: float = _tile_height()
    clearance: float = _clearance()
    groove_width: float = _groove_width()
    groove_depth: float = _groove_depth()


class FloodgatePieceJSON(BaseModel):
    """A floodgate: a gate that slots into a canal groove and closes one opening."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["floodgate"] = Field(description='Piece type: "floodgate".')
    tolerance: float = _fit(0.15, "Fit gap against the groove on each side")
    groove_width: float = _groove_width(_MATCH_CANALS)
    groove_depth: float = _groove_depth(_MATCH_CANALS)
    thickness: float = _length(3.0, "Thickness of the gate's base along the groove")
    fin_thickness: float = _length(1.6, "Thickness of the grip fin along the groove")
    height: float = _length(7.0, "Total height of the gate, base and grip fin")


class OwnerTokenPieceJSON(BaseModel):
    """An owner token: a cap on a peg that fits the hole of a canal piece."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["owner_token"] = Field(description='Piece type: "owner_token".')
    tolerance: float = _fit(0.20, "Fit gap between the peg and the canal hole")
    cap_diameter: float = _length(7.0, "Diameter of the cap")
    cap_height: float = _length(1.2, "Height of the cap")


class GrapeClusterPieceJSON(BaseModel):
    """A grape cluster: the marker a player puts on a claimed vineyard."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["grape_cluster"] = Field(description='Piece type: "grape_cluster".')
    base_diameter: float = _length(14.0, "Diameter of the round base")
    height: float = _length(15.0, "Total height, stem included (at most 1.5 x base_diameter)")


class DebtTokenPieceJSON(BaseModel):
    """A debt token: a round coin worth 1 or 5 points of bribe debt."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["debt_token"] = Field(description='Piece type: "debt_token".')
    value: Annotated[DebtValue, BeforeValidator(_reject_bool)] = Field(
        description="The debt the token is worth: 1 or 5."
    )
    diameter: float = _length(12.0, "Diameter of the coin")
    thickness: float = _length(2.0, "Thickness of the coin")


class QrPlatePieceJSON(BaseModel):
    """A QR plate: a QR code to the online rulebook, to glue inside the box."""

    model_config = ConfigDict(extra="forbid", strict=True)

    type: Literal["qr_plate"] = Field(description='Piece type: "qr_plate".')
    language: QrLanguage = Field(
        description='The rulebook the code opens: "reglas" (Spanish) or "rules" (English).'
    )
    size: float = _length(
        45.0, "Width of the plate, the side of the code with its quiet zone (modules at least 1 mm)"
    )
    base_height: float = _length(1.0, "Thickness of the plate under the modules (at least 0.8)")
    module_height: float = _length(
        0.6, "How far the dark modules and the label rise; change filament there (at least 0.4)"
    )
    label_band: float = _length(6.0, "Depth of the label band under the code (at least 6)")


PieceJSON = Annotated[
    TerrainPieceJSON
    | CanalPieceJSON
    | FloodgatePieceJSON
    | OwnerTokenPieceJSON
    | GrapeClusterPieceJSON
    | DebtTokenPieceJSON
    | QrPlatePieceJSON,
    Field(discriminator="type"),
]
"""One printable piece, by `type`."""

PIECE_MODELS: dict[str, type[BaseModel]] = {
    "terrain": TerrainPieceJSON,
    "canal": CanalPieceJSON,
    "floodgate": FloodgatePieceJSON,
    "owner_token": OwnerTokenPieceJSON,
    "grape_cluster": GrapeClusterPieceJSON,
    "debt_token": DebtTokenPieceJSON,
    "qr_plate": QrPlatePieceJSON,
}
"""Each piece type and its shape, in the order of `acequias.cad.pieces.PIECE_TYPES`."""

PIECE_VARIANT_FIELDS: dict[str, str] = {
    "terrain": "terrain",
    "canal": "kind",
    "debt_token": "value",
    "qr_plate": "language",
}
"""The field that holds the variant, for the piece types that have one."""


MAX_PLATE_COUNT = 500
"""The most copies of one entry, and of all entries together, `build_plate` takes."""

COLOR_PATTERN = r"^[a-z0-9][a-z0-9_-]{0,31}$"
"""A color group: 1 to 32 of `a-z`, `0-9`, `_`, `-`, starting with a letter or digit."""


class PlateEntryJSON(BaseModel):
    """One line of a `build_plate` request: a piece, how many, and its color."""

    model_config = ConfigDict(extra="forbid", strict=True)

    piece: PieceJSON = Field(
        description=(
            'The piece to print, chosen by its "type": "terrain", "canal", "floodgate", '
            '"owner_token", "grape_cluster", "debt_token", or "qr_plate". Sizes are in mm; any left '
            "out take their default."
        )
    )
    count: int = Field(
        ge=1,
        le=MAX_PLATE_COUNT,
        description=f"How many of this piece to print, 1 to {MAX_PLATE_COUNT}.",
    )
    color: str = Field(
        min_length=1,
        max_length=32,
        pattern=COLOR_PATTERN,
        description=(
            "The color group and the filament the piece prints in: 1 to 32 characters "
            'from a-z, 0-9, "_", "-", starting with a letter or digit (for example '
            '"red", "neutral", "dark_green"). Each plate holds one color.'
        ),
    )


def piece_variant(piece: BaseModel) -> Terrain | PieceKind | int | str | None:
    """The variant of a piece as `acequias.cad.pieces.build_piece` takes it.

    A `Terrain` for a terrain, a canal `PieceKind` for a canal, the value for
    a debt token, the language for a QR plate, and None for the other types.
    """
    field = PIECE_VARIANT_FIELDS.get(piece.type)  # type: ignore[attr-defined]
    if field is None:
        return None
    raw = getattr(piece, field)
    if field == "terrain":
        return terrain_from_json(raw)
    if field == "kind":
        return kind_from_json(raw)
    return raw


def piece_params(piece: BaseModel) -> dict[str, float]:
    """The size parameters of a piece, in field order: every field but `type` and the variant."""
    skip = {"type", PIECE_VARIANT_FIELDS.get(piece.type)}  # type: ignore[attr-defined]
    return {name: value for name, value in piece.model_dump().items() if name not in skip}


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


def planting_from_json(item: Mapping[str, Any] | ClaimJSON) -> tuple[Hex, Varietal] | None:
    """The `(hex, varietal)` planting of one claim JSON object, or None if it has no varietal."""
    item = ClaimJSON.model_validate(item)
    varietal = varietal_from_json(item.varietal)
    return None if varietal is None else (Hex(item.q, item.r), varietal)


def claims_to_json(board: Board) -> list[dict[str, Any]]:
    """The claims list for `board`, in its order, each with what was planted there (or null)."""
    planted = dict(board.plantings)
    return [
        {
            "q": hex.q,
            "r": hex.r,
            "player": player,
            "varietal": varietal_to_json(planted.get(hex)),
        }
        for hex, player in board.claims
    ]


def players_from_json(items: Iterable[Mapping[str, Any] | PlayerJSON]) -> tuple[Player, ...]:
    """The `Player`s for a players list, with seats 1 to N in list order."""
    if isinstance(items, (str, bytes, Mapping)) or not isinstance(items, Iterable):
        raise TypeError(f"players must be a list of player objects, got {items!r}")
    return tuple(
        Player(id=item.id, seat=seat, debt=item.debt, season=item.season, drought=item.drought)
        for seat, item in enumerate((PlayerJSON.model_validate(i) for i in items), start=1)
    )


def watered_vineyard_to_json(vineyard: WateredVineyard) -> dict[str, Any]:
    """The JSON object for one `WateredVineyard`: hex, varietal, path, and pays.

    A vertex vineyard (Rules v3) has `hexes` (its vertex) instead of `q`, `r`.
    """
    where: dict[str, Any]
    split: dict[str, Any] = {}
    if vineyard.vertex is not None:
        where = {"hexes": vertex_to_json(vineyard.vertex)}
        split = {"planter": vineyard.planter, "thirds": vineyard.thirds, "points": vineyard.points}
    else:
        where = {"q": vineyard.hex.q, "r": vineyard.hex.r}
    return {
        **where,
        "varietal": varietal_to_json(vineyard.varietal),
        "path": [canal_to_json(canal) for canal in vineyard.path.canals],
        "pays": list(vineyard.pays),
        **split,
    }


# --- Vertices (Rules v3) ------------------------------------------------------


def vertex_to_json(vertex: Vertex) -> list[list[int]]:
    """A vertex as its 3 hexes, `[[q, r], [q, r], [q, r]]`, in hex order."""
    return [[h.q, h.r] for h in vertex.hexes]


def vertex_from_json(item: object) -> Vertex:
    """The `Vertex` for a list of 3 `[q, r]` pairs; `Vertex` checks they meet at a point."""
    if isinstance(item, (str, bytes, Mapping)) or not isinstance(item, Iterable):
        raise TypeError(f"a vertex must be a list of 3 [q, r] pairs, got {item!r}")
    pairs = [tuple(pair) for pair in item]
    if any(len(pair) != 2 for pair in pairs):
        raise ValueError(f"a vertex must be a list of 3 [q, r] pairs, got {item!r}")
    return Vertex(tuple(Hex(q, r) for q, r in pairs))


def spots_to_json(board: Board) -> list[list[list[int]]]:
    """The planting spots of `board` (Rules v3), in its order, each a vertex."""
    return [vertex_to_json(spot) for spot in board.spots]


def strip_to_json(board: Board) -> dict[str, Any] | None:
    """The river strip of `board` (Rules v3 open board), or null on a fixed board.

    `{"segments": [[[q, r], ...], ...]}`: the printed river pieces north to
    south, each its river hexes north to south, one per row from `r` 0.
    East of each row's river hex the table is open; there are no other hexes.
    """
    if board.strip is None:
        return None
    return {"segments": [[[h.q, h.r] for h in segment] for segment in board.strip.segments]}


def strip_from_json(item: Mapping[str, Any] | RiverStripJSON) -> Board:
    """The river strip `Board` for one object of `strip_to_json`; `RiverStrip` checks it."""
    if isinstance(item, RiverStripJSON):
        item = item.model_dump()
    if not isinstance(item, Mapping) or set(item) != {"segments"}:
        raise ValueError(f"a river strip must be an object with exactly the key segments, got {item!r}")
    segments = item["segments"]
    if isinstance(segments, (str, bytes, Mapping)) or not isinstance(segments, Iterable):
        raise TypeError(f"segments must be a list of lists of [q, r] pairs, got {segments!r}")
    strip = RiverStrip(tuple(tuple(Hex(*pair) for pair in segment) for segment in segments))
    return Board(tiles=tuple(Tile(h, Terrain.RIVER) for h in strip.river), strip=strip)


def planted_to_json(board: Board) -> list[dict[str, Any]]:
    """The vertex vineyards of `board`: `{"hexes", "player", "varietal"}` each, in its order."""
    return [
        {
            "hexes": vertex_to_json(v.vertex),
            "player": v.owner,
            "varietal": varietal_to_json(v.varietal),
        }
        for v in board.planted
    ]


def planted_from_json(item: Mapping[str, Any] | PlantedVineyardJSON) -> PlantedVineyard:
    """The `PlantedVineyard` for one object of `planted_to_json`."""
    if isinstance(item, PlantedVineyardJSON):
        item = item.model_dump()
    if not isinstance(item, Mapping):
        raise TypeError(f"a planted vineyard must be an object, got {item!r}")
    if set(item) != {"hexes", "player", "varietal"}:
        raise ValueError(
            f"a planted vineyard needs exactly the keys hexes, player, varietal; got {sorted(item)}"
        )
    varietal = varietal_from_json(item["varietal"])
    if varietal is None:
        raise ValueError("a planted vineyard needs a varietal")
    return PlantedVineyard(vertex_from_json(item["hexes"]), item["player"], varietal)


def bodega_from_json(item: Mapping[str, Any] | BodegaBuildingJSON) -> BodegaBuilding:
    """The `BodegaBuilding` for one `{"hexes", "player"}` object (#166)."""
    if isinstance(item, BodegaBuildingJSON):
        item = item.model_dump()
    if not isinstance(item, Mapping):
        raise TypeError(f"a bodega must be an object, got {item!r}")
    if set(item) != {"hexes", "player"}:
        raise ValueError(f"a bodega needs exactly the keys hexes, player; got {sorted(item)}")
    return BodegaBuilding(vertex_from_json(item["hexes"]), item["player"])


def watered_bodega_to_json(bodega: WateredBodega) -> dict[str, Any]:
    """The JSON object for one `WateredBodega`."""
    return {
        "hexes": vertex_to_json(bodega.vertex),
        "builder": bodega.builder,
        "thirds": bodega.thirds,
        "points": bodega.points,
    }


def score_to_json(score: Score) -> dict[str, Any]:
    """The score JSON object for one `Score`, every term copied as is.

    The Rules v3 #166 terms (`blend`, `blends`, `buildings`,
    `watered_bodegas`) are given only when not 0 or empty, so other results
    keep their keys.
    """
    extra: dict[str, Any] = {}
    if score.blend:
        extra["blend"] = score.blend
    if score.blends:
        extra["blends"] = list(score.blends)
    if score.buildings:
        extra["buildings"] = score.buildings
    if score.watered_bodegas:
        extra["watered_bodegas"] = [watered_bodega_to_json(b) for b in score.watered_bodegas]
    return {
        "player": score.player,
        "seat": score.seat,
        "vineyards": score.vineyards,
        "bodega": score.bodega,
        "rights_paid": score.rights_paid,
        "rights_collected": score.rights_collected,
        "debt": score.debt,
        "season": score.season,
        "drought": score.drought,
        "total": score.total,
        "watered": score.watered,
        "watered_vineyards": [watered_vineyard_to_json(v) for v in score.watered_vineyards],
        "bodegas": score.bodegas,
        "seat_bonus": score.seat_bonus,
        **extra,
    }
