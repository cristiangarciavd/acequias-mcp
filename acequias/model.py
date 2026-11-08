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

from acequias.hex import Direction, Hex

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
    """A vineyard's grape, which sets its value in points."""

    MALBEC = "Malbec"
    BONARDA = "Bonarda"
    TORRONTES = "Torrontés"

    @property
    def display_name(self) -> str:
        """The name as written in the rules, accents included."""
        return self.value

    @property
    def points(self) -> int:
        """Points the vineyard scores when watered at the end of the game."""
        return _VARIETAL_POINTS[self]


_VARIETAL_POINTS = {Varietal.MALBEC: 3, Varietal.BONARDA: 2, Varietal.TORRONTES: 1}


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


# --- Pieces on the board ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class Tile:
    """A board hex and its terrain; a vineyard tile also has a varietal."""

    hex: Hex
    terrain: Terrain
    varietal: Varietal | None = None

    def __post_init__(self) -> None:
        _check_type("Tile.hex", self.hex, Hex)
        _check_type("Tile.terrain", self.terrain, Terrain)
        if self.terrain is Terrain.VINEYARD:
            if not isinstance(self.varietal, Varietal):
                raise ValueError(f"a vineyard tile needs a varietal, got {self.varietal!r}")
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


# --- Board -----------------------------------------------------------------


@dataclass(frozen=True)
class Board:
    """Tiles, placed canals, floodgates, and vineyard claims.

    ``claims`` pairs a vineyard hex with the id of the player who claimed
    it; a vineyard with no claim is unclaimed. The board checks where pieces
    may sit, not who owns them: ``GameState`` checks owners against its
    players.
    """

    tiles: tuple[Tile, ...] = ()
    canals: tuple[PlacedCanal, ...] = ()
    floodgates: tuple[Floodgate, ...] = ()
    claims: tuple[tuple[Hex, str], ...] = ()

    _tile_index: Mapping[Hex, Tile] = field(init=False, repr=False, compare=False)
    _canal_index: Mapping[Hex, PlacedCanal] = field(init=False, repr=False, compare=False)
    _claim_index: Mapping[Hex, str] = field(init=False, repr=False, compare=False)
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

        _set(self, "tiles", tuple(sorted(tiles, key=lambda t: t.hex)))
        _set(self, "canals", tuple(sorted(canals, key=lambda c: c.hex)))
        _set(self, "floodgates", tuple(sorted(floodgates, key=_floodgate_key)))
        _set(self, "claims", tuple(sorted(claims)))
        _set(self, "_tile_index", MappingProxyType(tile_index))
        _set(self, "_canal_index", MappingProxyType(canal_index))
        _set(self, "_claim_index", MappingProxyType(claim_index))
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
        return new


class _BoardStatics:
    """Lookups that depend only on a board's tiles.

    For each tile hex: its neighbours by direction, the directions that face
    a river tile, and the directions that face a vineyard tile (with the
    vineyard hex). ``empty`` lists the ``EMPTY`` tile hexes in hex order.
    """

    __slots__ = ("neighbors", "river_dirs", "vineyard_dirs", "empty")

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


_DIRECTION_INDEX = {d: i for i, d in enumerate(Direction)}


def _canal_order(canal: PlacedCanal) -> Hex:
    return canal.hex


def _floodgate_key(gate: Floodgate) -> tuple[Hex, Hex, int, int]:
    """A canonical order for floodgates, the same from either side of the edge."""
    a, b = sorted(gate.edge, key=lambda side: (side[0], _DIRECTION_INDEX[side[1]]))
    return (a[0], b[0], _DIRECTION_INDEX[a[1]], _DIRECTION_INDEX[b[1]])


# --- Players and game state ------------------------------------------------


@dataclass(frozen=True, slots=True)
class Player:
    """A player: an id, a seat number, and the bribe debt accumulated so far."""

    id: str
    seat: int
    debt: int = 0

    def __post_init__(self) -> None:
        _check_type("Player.id", self.id, str)
        _check_int("Player.seat", self.seat)
        _check_int("Player.debt", self.debt)
        if self.debt < 0:
            raise ValueError(f"debt cannot be negative, got {self.debt}")


@dataclass(frozen=True, slots=True)
class GameState:
    """Everything that describes a game at one moment.

    ``start_player`` and ``current_player`` are player ids. ``market`` and
    ``bag`` hold piece kinds, floodgates included; ``bag[0]`` is the next
    piece drawn. ``preset`` is the preset the game was built with (its mode
    must be ``mode``); ``None`` means the shipped preset for ``mode``. It
    takes part in equality but not in the hash, since a ``Preset`` holds
    read-only mappings and is not hashable.
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
