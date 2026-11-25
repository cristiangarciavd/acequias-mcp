"""The Acequias data model: types and their invariants, no game logic.

Rules come from ``README.md`` (Components, Water flow, Floodgate, Claims and
watering, Bribe). Coordinates and directions come from ``acequias.hex``.

Every type is a frozen dataclass and every collection field is a tuple, so
an update always produces a new value. Collections are stored in a
canonical order (by hex), so two values with the same contents are equal
whatever order they were given in.

This module depends on nothing in ``acequias`` except ``acequias.hex`` at
import time. ``GameState.preset`` is a ``acequias.config.Preset``, but
``config`` imports this module, so ``Preset`` is imported only for type
checking and, lazily, inside ``GameState.__post_init__``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from acequias.hex import Direction, Hex, Vertex

if TYPE_CHECKING:
    from acequias.config import Preset

MIN_PLAYERS = 2
MAX_PLAYERS = 5
ROTATIONS = 6


# --- Enums -----------------------------------------------------------------


class Terrain(Enum):
    """The terrain of a board hex."""

    RIVER = "river"
    VINEYARD = "vineyard"
    STONE = "stone"
    EMPTY = "empty"


class Varietal(Enum):
    """A vineyard's grape. Its value in points comes from the preset
    (``Preset.varietal_points``)."""

    MALBEC = "Malbec"
    CABERNET_SAUVIGNON = "Cabernet Sauvignon"
    CABERNET_FRANC = "Cabernet Franc"
    SYRAH = "Syrah"
    MERLOT = "Merlot"
    BONARDA = "Bonarda"
    TORRONTES = "Torrontés"
    CHARDONNAY = "Chardonnay"

    @property
    def display_name(self) -> str:
        """The name as written in the rules, accents included."""
        return self.value


class PieceKind(Enum):
    """A piece in the bag or market: one of six canal shapes, or a floodgate."""

    STRAIGHT = "straight"
    GENTLE_CURVE = "gentle curve"
    SHARP_CURVE = "sharp curve"
    SYMMETRIC_Y = "symmetric Y"
    T_BRANCH = "T branch"
    CLAW = "claw"
    FLOODGATE = "floodgate"

    @property
    def is_canal(self) -> bool:
        """Whether this kind is a canal shape (every kind but the floodgate)."""
        return self is not PieceKind.FLOODGATE

    def edges(self, rotation: int) -> frozenset[Direction]:
        """The hex edges this canal shape opens at ``rotation``.

        Each rotation step turns the shape 60 degrees counterclockwise.
        ``rotation`` must be an int from 0 to 5. The floodgate is not a
        canal shape and has no edges.
        """
        if type(rotation) is int:
            edges = _EDGES.get((self, rotation))
            if edges is not None:
                return edges
        _check_rotation(rotation)
        if not self.is_canal:
            raise ValueError("the floodgate is not a canal shape and has no edges")
        return frozenset(d.rotated(rotation) for d in _BASE_EDGES[self])


# Openings at rotation 0, as in README.md (Water flow).
_BASE_EDGES: dict[PieceKind, tuple[Direction, ...]] = {
    PieceKind.STRAIGHT: (Direction.E, Direction.W),
    PieceKind.GENTLE_CURVE: (Direction.E, Direction.NW),
    PieceKind.SHARP_CURVE: (Direction.E, Direction.NE),
    PieceKind.SYMMETRIC_Y: (Direction.E, Direction.NW, Direction.SW),
    PieceKind.T_BRANCH: (Direction.E, Direction.W, Direction.NE),
    PieceKind.CLAW: (Direction.E, Direction.NE, Direction.NW),
}

# Every canal shape's edges at every rotation, worked out once.
_EDGES: dict[tuple[PieceKind, int], frozenset[Direction]] = {
    (kind, rotation): frozenset(d.rotated(rotation) for d in base)
    for kind, base in _BASE_EDGES.items()
    for rotation in range(ROTATIONS)
}


class Mode(Enum):
    """The game length mode."""

    NORMAL = "normal"
    FLASH = "flash"


class DieFace(Enum):
    """A face of the action die (``action_die`` bribe rules): what the roll lets you do.

    ``FLOODGATE``, ``RELEASE`` and ``RESOW`` are personal: the roller uses
    or declines them. ``GOOD_SEASON`` and ``DROUGHT`` are season faces:
    they always apply, to every player, as soon as they are rolled.
    """

    FLOODGATE = "floodgate"
    RELEASE = "release"
    RESOW = "resow"
    GOOD_SEASON = "good_season"
    DROUGHT = "drought"

    @property
    def is_season(self) -> bool:
        """Whether the face applies to every player (good season, drought), not only the roller."""
        return self in (DieFace.GOOD_SEASON, DieFace.DROUGHT)


class SeasonRoll(Enum):
    """Where the round's free season roll is (``Preset.season_roll_every``).

    ``DUE``: the season die's holder (``current_player``, see
    ``acequias.game.season_holder``) must roll the action die for free
    before the start player's turn. ``ROLLED``: they rolled a personal face
    and must use or decline it; then the start player takes their turn.
    """

    DUE = "due"
    ROLLED = "rolled"


# --- Pieces on the board ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tile:
    """A board hex and its terrain.

    A vineyard tile has a varietal under fixed rules, and none under
    roulette rules, where the varietal is planted when the vineyard is
    claimed (``Board.plantings``). Other terrains never have one.
    """

    hex: Hex
    terrain: Terrain
    varietal: Varietal | None = None

    def __post_init__(self) -> None:
        _check_type("Tile.hex", self.hex, Hex)
        _check_type("Tile.terrain", self.terrain, Terrain)
        if self.terrain is Terrain.VINEYARD:
            if self.varietal is not None and not isinstance(self.varietal, Varietal):
                raise ValueError(
                    f"a vineyard tile's varietal must be a Varietal or None, got {self.varietal!r}"
                )
        elif self.varietal is not None:
            raise ValueError(f"a {self.terrain.value} tile cannot have a varietal")


@dataclass(frozen=True, slots=True)
class PlacedCanal:
    """A canal piece on a hex, with its rotation and the id of its owner."""

    hex: Hex
    kind: PieceKind
    rotation: int
    owner: str

    def __post_init__(self) -> None:
        _check_type("PlacedCanal.hex", self.hex, Hex)
        _check_type("PlacedCanal.kind", self.kind, PieceKind)
        _check_rotation(self.rotation)
        _check_type("PlacedCanal.owner", self.owner, str)
        if not self.kind.is_canal:
            raise ValueError("a floodgate is an edge piece, not a canal on a hex")

    @property
    def edges(self) -> frozenset[Direction]:
        """The hex edges this canal opens."""
        return self.kind.edges(self.rotation)


@dataclass(frozen=True, slots=True, eq=False)
class Floodgate:
    """A floodgate closing one opening of a canal.

    It sits on an edge, not a hex: ``hex`` is the canal it was placed on and
    ``direction`` the opening it closes. The same edge seen from the
    neighbouring hex is the same floodgate, so ``Floodgate(a, E)`` equals
    ``Floodgate(a.neighbor(E), W)`` and hashes the same.
    """

    hex: Hex
    direction: Direction

    def __post_init__(self) -> None:
        _check_type("Floodgate.hex", self.hex, Hex)
        _check_type("Floodgate.direction", self.direction, Direction)

    @property
    def edge(self) -> frozenset[tuple[Hex, Direction]]:
        """The edge as both of its sides, ``(hex, direction)`` from each hex."""
        return _edge(self.hex, self.direction)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Floodgate):
            return NotImplemented
        return self.edge == other.edge

    def __hash__(self) -> int:
        return hash(self.edge)


def _edge(hex: Hex, direction: Direction) -> frozenset[tuple[Hex, Direction]]:
    return frozenset({(hex, direction), (hex.neighbor(direction), direction.opposite())})


@dataclass(frozen=True, slots=True)
class PlantedVineyard:
    """A vineyard planted on a vertex (Rules v3): its spot, its owner, and its varietal.

    Planting makes the vineyard its planter's at once, with the varietal
    the roulette gave it; there is no separate claim.
    """

    vertex: Vertex
    owner: str
    varietal: Varietal

    def __post_init__(self) -> None:
        _check_type("PlantedVineyard.vertex", self.vertex, Vertex)
        _check_type("PlantedVineyard.owner", self.owner, str)
        _check_type("PlantedVineyard.varietal", self.varietal, Varietal)


@dataclass(frozen=True, slots=True)
class ActionsLeft:
    """What the current player may still do this turn under Rules v3, after the die roll.

    ``actions`` is the actions left (canal or plant), ``canals`` how many of
    them may still be canals: 1 and 1 on a normal turn, 2 and 1 after a
    good season (never 2 canals), 0 and 0 after a drought or a pass.
    """

    actions: int
    canals: int

    def __post_init__(self) -> None:
        _check_int("ActionsLeft.actions", self.actions)
        _check_int("ActionsLeft.canals", self.canals)
        if not 0 <= self.canals <= self.actions:
            raise ValueError(
                f"ActionsLeft needs 0 <= canals <= actions, got {self.canals} and {self.actions}"
            )


# --- Board -----------------------------------------------------------------


@dataclass(frozen=True)
class Board:
    """Tiles, placed canals, floodgates, vineyard claims, and plantings.

    ``claims`` pairs a vineyard hex with the id of the player who claimed
    it; a vineyard with no claim is unclaimed. ``plantings`` pairs a claimed
    vineyard whose tile has no varietal with the varietal the roulette
    planted there. The board checks where pieces may sit, not who owns
    them: ``GameState`` checks owners against its players.

    Rules v3 (``PlantingRules.VERTICES``) plants vineyards on vertices
    instead. ``planted`` holds those vineyards, at most one per vertex, each
    on a vertex that touches a non-river tile. ``spots`` lists the planting
    spots the generator dealt (every vertex touching a non-river tile); it
    describes the printed board only: where a player may plant is worked out
    from the placed canals (``acequias.flow.can_plant``), never from
    ``spots``, so the same rules work on a board without fixed bounds. Both
    are empty on a board of hex vineyards.
    """

    tiles: tuple[Tile, ...] = ()
    canals: tuple[PlacedCanal, ...] = ()
    floodgates: tuple[Floodgate, ...] = ()
    claims: tuple[tuple[Hex, str], ...] = ()
    plantings: tuple[tuple[Hex, Varietal], ...] = ()
    spots: tuple[Vertex, ...] = ()
    planted: tuple[PlantedVineyard, ...] = ()

    _tile_index: Mapping[Hex, Tile] = field(init=False, repr=False, compare=False)
    _canal_index: Mapping[Hex, PlacedCanal] = field(init=False, repr=False, compare=False)
    _claim_index: Mapping[Hex, str] = field(init=False, repr=False, compare=False)
    _planting_index: Mapping[Hex, Varietal] = field(init=False, repr=False, compare=False)
    _spot_set: frozenset[Vertex] = field(init=False, repr=False, compare=False)
    _planted_index: Mapping[Vertex, PlantedVineyard] = field(
        init=False, repr=False, compare=False
    )
    _floodgate_index: Mapping[frozenset, Floodgate] = field(
        init=False, repr=False, compare=False
    )
    # Lookups that depend on the tiles only, built on first use (``_static``)
    # and shared by every board ``_derive`` makes from this one.
    _statics: _BoardStatics | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        tiles = _items("Board.tiles", self.tiles, Tile)
        canals = _items("Board.canals", self.canals, PlacedCanal)
        floodgates = _items("Board.floodgates", self.floodgates, Floodgate)
        claims = _claim_items(self.claims)
        plantings = _planting_items(self.plantings)
        spots = _items("Board.spots", self.spots, Vertex)
        planted = _items("Board.planted", self.planted, PlantedVineyard)

        tile_index: dict[Hex, Tile] = {}
        for tile in tiles:
            if tile.hex in tile_index:
                raise ValueError(f"two tiles on {tile.hex}")
            tile_index[tile.hex] = tile

        canal_index: dict[Hex, PlacedCanal] = {}
        for canal in canals:
            if canal.hex in canal_index:
                raise ValueError(f"two canals on {canal.hex}")
            tile = tile_index.get(canal.hex)
            if tile is None:
                raise ValueError(f"canal on {canal.hex}, which has no tile")
            if tile.terrain is not Terrain.EMPTY:
                raise ValueError(
                    f"canal on {canal.hex}, a {tile.terrain.value} tile; canals go on empty tiles"
                )
            canal_index[canal.hex] = canal

        floodgate_index: dict[frozenset, Floodgate] = {}
        for gate in floodgates:
            canal = canal_index.get(gate.hex)
            if canal is None:
                raise ValueError(f"floodgate on {gate.hex}, which has no canal")
            if gate.direction not in canal.edges:
                raise ValueError(
                    f"floodgate on {gate.hex} facing {gate.direction.name}, "
                    "an edge the canal does not open"
                )
            if gate.edge in floodgate_index:
                raise ValueError(f"two floodgates on the edge {gate.hex} {gate.direction.name}")
            floodgate_index[gate.edge] = gate

        claim_index: dict[Hex, str] = {}
        for hex, player_id in claims:
            if hex in claim_index:
                raise ValueError(f"two claims on {hex}")
            tile = tile_index.get(hex)
            if tile is None or tile.terrain is not Terrain.VINEYARD:
                raise ValueError(f"claim on {hex}, which is not a vineyard")
            claim_index[hex] = player_id

        planting_index: dict[Hex, Varietal] = {}
        for hex, varietal in plantings:
            if hex in planting_index:
                raise ValueError(f"two plantings on {hex}")
            tile = tile_index.get(hex)
            if tile is None or tile.terrain is not Terrain.VINEYARD:
                raise ValueError(f"planting on {hex}, which is not a vineyard")
            if tile.varietal is not None:
                raise ValueError(
                    f"planting on {hex}, whose tile already has {tile.varietal.display_name}"
                )
            if hex not in claim_index:
                raise ValueError(f"planting on {hex}, an unclaimed vineyard")
            planting_index[hex] = varietal

        spot_set: set[Vertex] = set()
        for spot in spots:
            if spot in spot_set:
                raise ValueError(f"two planting spots on {spot}")
            if not _touches_land(spot, tile_index):
                raise ValueError(f"planting spot {spot} touches no non-river tile")
            spot_set.add(spot)

        planted_index: dict[Vertex, PlantedVineyard] = {}
        for vineyard in planted:
            if not _touches_land(vineyard.vertex, tile_index):
                raise ValueError(
                    f"vineyard planted on {vineyard.vertex}, which touches no non-river tile"
                )
            if vineyard.vertex in planted_index:
                raise ValueError(f"two vineyards planted on {vineyard.vertex}")
            planted_index[vineyard.vertex] = vineyard

        _set(self, "tiles", tuple(sorted(tiles, key=lambda t: t.hex)))
        _set(self, "canals", tuple(sorted(canals, key=lambda c: c.hex)))
        _set(self, "floodgates", tuple(sorted(floodgates, key=_floodgate_key)))
        _set(self, "claims", tuple(sorted(claims)))
        _set(self, "plantings", tuple(sorted(plantings, key=_planting_order)))
        _set(self, "spots", tuple(sorted(spot_set)))
        _set(self, "planted", tuple(sorted(planted, key=_planted_order)))
        _set(self, "_spot_set", frozenset(spot_set))
        _set(self, "_planted_index", MappingProxyType(planted_index))
        _set(self, "_tile_index", MappingProxyType(tile_index))
        _set(self, "_canal_index", MappingProxyType(canal_index))
        _set(self, "_claim_index", MappingProxyType(claim_index))
        _set(self, "_planting_index", MappingProxyType(planting_index))
        _set(self, "_floodgate_index", MappingProxyType(floodgate_index))

    def tile_at(self, hex: Hex) -> Tile | None:
        """The tile at ``hex``, or None if the hex is off the board."""
        return self._tile_index.get(hex)

    def canal_at(self, hex: Hex) -> PlacedCanal | None:
        """The canal at ``hex``, or None if there is none."""
        return self._canal_index.get(hex)

    def claimant(self, hex: Hex) -> str | None:
        """The id of the player who claimed the vineyard at ``hex``, or None."""
        return self._claim_index.get(hex)

    def varietal_at(self, hex: Hex) -> Varietal | None:
        """The varietal at ``hex``: the tile's, else the one planted there, else None."""
        tile = self._tile_index.get(hex)
        if tile is not None and tile.varietal is not None:
            return tile.varietal
        return self._planting_index.get(hex)

    def is_spot(self, vertex: Vertex) -> bool:
        """Whether ``vertex`` is a planting spot (Rules v3)."""
        return vertex in self._spot_set

    def planted_at(self, vertex: Vertex) -> PlantedVineyard | None:
        """The vineyard planted on ``vertex``, or None."""
        return self._planted_index.get(vertex)

    def vertex_tiles(self, vertex: Vertex) -> tuple[Tile, ...]:
        """The tiles ``vertex`` touches, in hex order: 3, or fewer on the edge of the board."""
        index = self._tile_index
        return tuple(index[h] for h in vertex.hexes if h in index)

    def floodgate_at(self, hex: Hex, direction: Direction) -> Floodgate | None:
        """The floodgate on the edge of ``hex`` facing ``direction``, from either side, or None."""
        return self._floodgate_index.get(_edge(hex, direction))

    def has_floodgate(self, hex: Hex, direction: Direction) -> bool:
        """Whether the edge of ``hex`` facing ``direction`` has a floodgate."""
        return self.floodgate_at(hex, direction) is not None

    # --- Internal fast paths (for ``acequias.turn`` and ``acequias.flow``) ----

    def _static(self) -> _BoardStatics:
        """The lookups that depend only on the tiles, built once per tile set."""
        statics = self._statics
        if statics is None:
            statics = _BoardStatics(self.tiles)
            _set(self, "_statics", statics)
        return statics

    def _derive(
        self,
        *,
        canals: tuple[PlacedCanal, ...] | None = None,
        floodgates: tuple[Floodgate, ...] | None = None,
        claims: tuple[tuple[Hex, str], ...] | None = None,
        plantings: tuple[tuple[Hex, Varietal], ...] | None = None,
        planted: tuple[PlantedVineyard, ...] | None = None,
    ) -> Board:
        """This board with some collections replaced, for callers that checked every piece.

        Equal to ``replace(self, ...)`` with the same arguments, but runs no
        check: the caller (``acequias.turn``) guarantees the new pieces are
        valid. The tiles, their index, and their statics are shared.
        """
        new = object.__new__(Board)
        _set(new, "tiles", self.tiles)
        _set(new, "_tile_index", self._tile_index)
        _set(new, "_statics", self._static())
        if canals is None:
            _set(new, "canals", self.canals)
            _set(new, "_canal_index", self._canal_index)
        else:
            canals = tuple(sorted(canals, key=_canal_order))
            _set(new, "canals", canals)
            _set(new, "_canal_index", MappingProxyType({c.hex: c for c in canals}))
        if floodgates is None:
            _set(new, "floodgates", self.floodgates)
            _set(new, "_floodgate_index", self._floodgate_index)
        else:
            floodgates = tuple(sorted(floodgates, key=_floodgate_key))
            _set(new, "floodgates", floodgates)
            _set(new, "_floodgate_index", MappingProxyType({g.edge: g for g in floodgates}))
        if claims is None:
            _set(new, "claims", self.claims)
            _set(new, "_claim_index", self._claim_index)
        else:
            claims = tuple(sorted(claims))
            _set(new, "claims", claims)
            _set(new, "_claim_index", MappingProxyType(dict(claims)))
        if plantings is None:
            _set(new, "plantings", self.plantings)
            _set(new, "_planting_index", self._planting_index)
        else:
            plantings = tuple(sorted(plantings, key=_planting_order))
            _set(new, "plantings", plantings)
            _set(new, "_planting_index", MappingProxyType(dict(plantings)))
        _set(new, "spots", self.spots)
        _set(new, "_spot_set", self._spot_set)
        if planted is None:
            _set(new, "planted", self.planted)
            _set(new, "_planted_index", self._planted_index)
        else:
            planted = tuple(sorted(planted, key=_planted_order))
            _set(new, "planted", planted)
            _set(new, "_planted_index", MappingProxyType({v.vertex: v for v in planted}))
        return new


class _BoardStatics:
    """Lookups that depend only on a board's tiles.

    For each tile hex: its neighbours by direction, the directions that face
    a river tile, and the directions that face a vineyard tile (with the
    vineyard hex). ``empty`` lists the ``EMPTY`` tile hexes in hex order.
    ``tile_varietals`` is the set of varietals on vineyard tiles, and
    ``blank_vineyards`` says whether any vineyard tile has none.
    """

    __slots__ = (
        "neighbors", "river_dirs", "vineyard_dirs", "empty", "tile_varietals", "blank_vineyards"
    )

    def __init__(self, tiles: tuple[Tile, ...]) -> None:
        terrain = {t.hex: t.terrain for t in tiles}
        self.neighbors: dict[Hex, dict[Direction, Hex]] = {}
        self.river_dirs: dict[Hex, frozenset[Direction]] = {}
        self.vineyard_dirs: dict[Hex, dict[Direction, Hex]] = {}
        for hex in terrain:
            around = {d: hex.neighbor(d) for d in Direction}
            self.neighbors[hex] = around
            self.river_dirs[hex] = frozenset(
                d for d, n in around.items() if terrain.get(n) is Terrain.RIVER
            )
            self.vineyard_dirs[hex] = {
                d: n for d, n in around.items() if terrain.get(n) is Terrain.VINEYARD
            }
        self.empty: tuple[Hex, ...] = tuple(
            sorted(h for h, t in terrain.items() if t is Terrain.EMPTY)
        )
        vineyards = [t for t in tiles if t.terrain is Terrain.VINEYARD]
        self.tile_varietals: frozenset[Varietal] = frozenset(
            t.varietal for t in vineyards if t.varietal is not None
        )
        self.blank_vineyards: bool = any(t.varietal is None for t in vineyards)


_DIRECTION_INDEX = {d: i for i, d in enumerate(Direction)}


def _canal_order(canal: PlacedCanal) -> Hex:
    return canal.hex


def _planting_order(planting: tuple[Hex, Varietal]) -> Hex:
    return planting[0]


def _touches_land(vertex: Vertex, tile_index: Mapping[Hex, Tile]) -> bool:
    """Whether ``vertex`` touches at least one non-river tile."""
    for h in vertex.hexes:
        tile = tile_index.get(h)
        if tile is not None and tile.terrain is not Terrain.RIVER:
            return True
    return False


def _planted_order(vineyard: PlantedVineyard) -> Vertex:
    return vineyard.vertex


def _floodgate_key(gate: Floodgate) -> tuple[Hex, Hex, int, int]:
    """A canonical order for floodgates, the same from either side of the edge."""
    a, b = sorted(gate.edge, key=lambda side: (side[0], _DIRECTION_INDEX[side[1]]))
    return (a[0], b[0], _DIRECTION_INDEX[a[1]], _DIRECTION_INDEX[b[1]])


# --- Players and game state ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Player:
    """A player: an id, a seat number, the bribe debt accumulated so far, and season points.

    ``season`` is the sum of the good season gains of the action die so
    far, and ``drought`` the sum of its drought losses; both are 0 or
    more. Scoring takes the drought off, but never below a total of 0.
    """

    id: str
    seat: int
    debt: int = 0
    season: int = 0
    drought: int = 0

    def __post_init__(self) -> None:
        _check_type("Player.id", self.id, str)
        _check_int("Player.seat", self.seat)
        _check_int("Player.debt", self.debt)
        _check_int("Player.season", self.season)
        _check_int("Player.drought", self.drought)
        for name in ("debt", "season", "drought"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} cannot be negative, got {getattr(self, name)}")


@dataclass(frozen=True, slots=True)
class GameState:
    """Everything that describes a game at one moment.

    ``start_player`` and ``current_player`` are player ids. ``market`` and
    ``bag`` hold piece kinds, floodgates included; ``bag[0]`` is the next
    piece drawn. ``preset`` is the preset the game was built with (its mode
    must be ``mode``); ``None`` means the shipped preset for ``mode``. It
    takes part in equality but not in the hash, since a ``Preset`` holds
    read-only mappings and is not hashable. With a
    ``grape_clusters_per_player`` cap in the preset, no player holds more
    claims than the cap.

    ``pending_face`` is the action die face ``current_player`` rolled and
    has not resolved yet; it is set only under ``action_die`` bribe rules,
    and only to a personal face on the preset's ``action_die`` (a season
    face applies at once and is never pending).

    ``season_roll`` is the round's free season roll: ``DUE`` before the
    season die's holder (``current_player`` meanwhile) rolls it (no face pending), ``ROLLED`` while its personal
    face is pending, ``None`` otherwise. It is set only when the preset
    has a ``season_roll_every``.

    ``actions_left`` is set only under vertex planting (Rules v3): ``None``
    while ``current_player`` has not rolled the action die this turn,
    otherwise what they may still do (``ActionsLeft``).
    """

    board: Board
    players: tuple[Player, ...]
    mode: Mode
    round: int
    start_player: str
    current_player: str
    market: tuple[PieceKind, ...] = ()
    bag: tuple[PieceKind, ...] = ()
    preset: Preset | None = field(default=None, hash=False)
    pending_face: DieFace | None = None
    season_roll: SeasonRoll | None = None
    actions_left: ActionsLeft | None = None

    def __post_init__(self) -> None:
        _check_type("GameState.board", self.board, Board)
        players = _items("GameState.players", self.players, Player)
        _check_type("GameState.mode", self.mode, Mode)
        _check_int("GameState.round", self.round)
        market = _items("GameState.market", self.market, PieceKind)
        bag = _items("GameState.bag", self.bag, PieceKind)
        _set(self, "players", players)
        _set(self, "market", market)
        _set(self, "bag", bag)
        if self.preset is not None:
            from acequias.config import Preset  # local: config imports this module

            _check_type("GameState.preset", self.preset, Preset)
            if self.preset.mode is not self.mode:
                raise ValueError(
                    f"GameState.preset is for mode {self.preset.mode.name}, "
                    f"but the game mode is {self.mode.name}"
                )

        if not MIN_PLAYERS <= len(players) <= MAX_PLAYERS:
            raise ValueError(
                f"a game has {MIN_PLAYERS} to {MAX_PLAYERS} players, got {len(players)}"
            )
        ids = [p.id for p in players]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate player ids: {ids}")
        seats = [p.seat for p in players]
        if len(set(seats)) != len(seats):
            raise ValueError(f"duplicate seat numbers: {seats}")
        if self.round < 1:
            raise ValueError(f"round must be at least 1, got {self.round}")

        known = set(ids)
        for name in ("start_player", "current_player"):
            value = getattr(self, name)
            if value not in known:
                raise ValueError(f"{name} {value!r} is not one of the players")
        for canal in self.board.canals:
            if canal.owner not in known:
                raise ValueError(f"canal on {canal.hex} owned by unknown player {canal.owner!r}")
        for hex, player_id in self.board.claims:
            if player_id not in known:
                raise ValueError(f"claim on {hex} by unknown player {player_id!r}")
        for vineyard in self.board.planted:
            if vineyard.owner not in known:
                raise ValueError(
                    f"vineyard on {vineyard.vertex} planted by unknown player {vineyard.owner!r}"
                )
        self._check_planting()
        self._check_varietals()
        self._check_clusters()
        self._check_pending_face()
        self._check_season_roll()

    def _check_pending_face(self) -> None:
        """A pending face only under action die rules, and only a personal face of the die."""
        if self.pending_face is None:
            return
        _check_type("GameState.pending_face", self.pending_face, DieFace)
        from acequias.config import BribeRules  # local: config imports this module
        from acequias.config import preset as shipped_preset

        preset = self.preset if self.preset is not None else shipped_preset(self.mode)
        if preset.bribe_rules is not BribeRules.ACTION_DIE:
            raise ValueError("a pending die face needs action_die bribe rules")
        if self.pending_face not in preset.action_die:
            raise ValueError(
                f"pending face {self.pending_face.value} is not on the preset's action die"
            )
        if self.pending_face.is_season:
            raise ValueError(
                f"a {self.pending_face.value} face applies when rolled; it is never pending"
            )

    def _check_season_roll(self) -> None:
        """A season roll only with ``season_roll_every``; ``ROLLED`` exactly while a face is pending."""
        if self.season_roll is None:
            return
        _check_type("GameState.season_roll", self.season_roll, SeasonRoll)
        from acequias.config import preset as shipped_preset  # local: config imports this module

        preset = self.preset if self.preset is not None else shipped_preset(self.mode)
        if preset.season_roll_every is None:
            raise ValueError("a season roll needs a preset with season_roll_every")
        if (self.season_roll is SeasonRoll.ROLLED) != (self.pending_face is not None):
            raise ValueError(
                "season_roll is ROLLED exactly while the season roll's face is pending"
            )

    def _check_planting(self) -> None:
        """The board's vineyards fit the preset's planting rules.

        Hex planting: no planting spots, nothing planted on a vertex, and no
        ``actions_left``. Vertex planting (Rules v3): no vineyard tiles, so
        no claims either, and a pending face only after a roll.
        """
        from acequias.config import PlantingRules  # local: config imports this module
        from acequias.config import preset as shipped_preset

        preset = self.preset if self.preset is not None else shipped_preset(self.mode)
        board = self.board
        if self.actions_left is not None:
            _check_type("GameState.actions_left", self.actions_left, ActionsLeft)
        if preset.planting is PlantingRules.VERTICES:
            if any(t.terrain is Terrain.VINEYARD for t in board.tiles):
                raise ValueError("under vertex planting the board has no vineyard tiles")
            if self.pending_face is not None and self.actions_left is None:
                raise ValueError("under vertex planting a pending face follows a roll")
        else:
            if board.spots or board.planted:
                raise ValueError(
                    "under hex planting the board has no planting spots or vertex vineyards"
                )
            if self.actions_left is not None:
                raise ValueError("actions_left is set only under vertex planting (Rules v3)")

    def _check_clusters(self) -> None:
        """With a grape-cluster cap, no player holds more claims than the cap."""
        from acequias.config import preset as shipped_preset  # local: config imports this module

        preset = self.preset if self.preset is not None else shipped_preset(self.mode)
        cap = preset.grape_clusters_per_player
        if cap is None:
            return
        held: dict[str, int] = {}
        for _, player_id in self.board.claims:
            held[player_id] = held.get(player_id, 0) + 1
        for vineyard in self.board.planted:
            held[vineyard.owner] = held.get(vineyard.owner, 0) + 1
        over = sorted(p for p, n in held.items() if n > cap)
        if over:
            raise ValueError(
                f"players {over} hold more claims than grape_clusters_per_player ({cap})"
            )

    def _check_varietals(self) -> None:
        """The board's varietals must fit the preset's varietal rules.

        Fixed rules: every vineyard tile has a varietal with points, and
        nothing is planted. Roulette rules: no vineyard tile has a varietal.
        """
        from acequias.config import VarietalRules  # local: config imports this module
        from acequias.config import preset as shipped_preset

        preset = self.preset if self.preset is not None else shipped_preset(self.mode)
        statics = self.board._static()
        if preset.varietal_rules is VarietalRules.FIXED:
            if statics.blank_vineyards:
                raise ValueError("under fixed varietal rules every vineyard tile needs a varietal")
            unscored = sorted(
                v.name for v in statics.tile_varietals if v not in preset.varietal_points
            )
            if unscored:
                raise ValueError(f"varietals {unscored} have no points under fixed varietal rules")
            if self.board.plantings:
                raise ValueError("under fixed varietal rules nothing is planted on claim")
        elif statics.tile_varietals:
            raise ValueError("under roulette varietal rules no vineyard tile has a varietal")

    def player(self, player_id: str) -> Player | None:
        """The player with ``player_id``, or None."""
        for p in self.players:
            if p.id == player_id:
                return p
        return None


# --- Helpers ---------------------------------------------------------------


def _set(obj: object, name: str, value: object) -> None:
    object.__setattr__(obj, name, value)


def _check_type(name: str, value: object, cls: type) -> None:
    if not isinstance(value, cls):
        raise TypeError(f"{name} must be a {cls.__name__}, got {value!r}")


def _check_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {value!r}")


def _check_rotation(rotation: object) -> None:
    if not isinstance(rotation, int) or isinstance(rotation, bool):
        raise TypeError(f"rotation must be an int, got {rotation!r}")
    if not 0 <= rotation < ROTATIONS:
        raise ValueError(f"rotation must be 0 to {ROTATIONS - 1}, got {rotation}")


def _items(name: str, values: Iterable[object], cls: type) -> tuple:
    if isinstance(values, (str, bytes, Mapping)):
        raise TypeError(f"{name} must be a sequence of {cls.__name__}, got {values!r}")
    items = tuple(values)
    for item in items:
        _check_type(f"{name} item", item, cls)
    return items


def _planting_items(values: Iterable[object]) -> tuple[tuple[Hex, Varietal], ...]:
    if isinstance(values, Mapping):
        values = values.items()
    items = tuple(tuple(pair) for pair in values)
    for pair in items:
        if len(pair) != 2:
            raise TypeError(f"a planting is a (hex, varietal) pair, got {pair!r}")
        _check_type("planting hex", pair[0], Hex)
        _check_type("planting varietal", pair[1], Varietal)
    return items


def _claim_items(values: Iterable[object]) -> tuple[tuple[Hex, str], ...]:
    if isinstance(values, Mapping):
        values = values.items()
    items = tuple(tuple(pair) for pair in values)
    for pair in items:
        if len(pair) != 2:
            raise TypeError(f"a claim is a (hex, player id) pair, got {pair!r}")
        _check_type("claim hex", pair[0], Hex)
        _check_type("claim player id", pair[1], str)
    return items
