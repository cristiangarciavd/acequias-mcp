"""The turn engine: check and apply one player's action, and list the legal ones.

Rules come from ``README.md`` (Turn, Claims and watering, Floodgate, Bribe).
An action is one of four frozen, hashable dataclasses: ``PlaceCanal``,
``PlaceFloodgate``, ``Bribe``, or ``Pass``.

``apply(state, player, action, rng)`` returns a new ``GameState`` and never
changes its input. It does not check or change whose turn it is (that is
the round loop's job), so ``current_player``, ``start_player``, and
``round`` are copied unchanged. Only a bribe draws from ``rng``, with one
``rng.randint(1, die_faces)`` call made after every check has passed.

``legal_actions(state, player)`` lists every legal action once, in a fixed
order: canal placements, floodgate placements, bribes, then pass. Actions
that mean the same move are listed once in a canonical spelling (the
smallest rotation that opens the same edges; a floodgate edge named from
the canal side with the smaller hex), and ``apply`` accepts any spelling
of them and gives the same state.

Watering comes from ``acequias.flow.water``; the die size from the game's
preset. Standard library only; no global randomness.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from acequias.config import preset as shipped_preset
from acequias.flow import _watered
from acequias.hex import Direction, Hex
from acequias.model import (
    ROTATIONS,
    Board,
    Floodgate,
    GameState,
    PieceKind,
    PlacedCanal,
    Terrain,
)

__all__ = [
    "PlaceCanal",
    "PlaceFloodgate",
    "Bribe",
    "Pass",
    "Action",
    "IllegalAction",
    "apply",
    "legal_actions",
]


# --- Actions -----------------------------------------------------------------


@dataclass(frozen=True)
class PlaceCanal:
    """Take a canal shape from the market and place it on ``hex`` at ``rotation``."""

    kind: PieceKind
    hex: Hex
    rotation: int

    def __post_init__(self) -> None:
        _check_type("PlaceCanal.kind", self.kind, PieceKind)
        _check_type("PlaceCanal.hex", self.hex, Hex)
        _check_int("PlaceCanal.rotation", self.rotation)


@dataclass(frozen=True)
class PlaceFloodgate:
    """Take a floodgate from the market and place it on the edge of ``hex`` facing ``direction``."""

    hex: Hex
    direction: Direction

    def __post_init__(self) -> None:
        _check_type("PlaceFloodgate.hex", self.hex, Hex)
        _check_type("PlaceFloodgate.direction", self.direction, Direction)


@dataclass(frozen=True)
class Bribe:
    """Bribe to remove the floodgate on an edge, or move it to the edge ``to``.

    ``hex`` and ``direction`` name the edge holding the floodgate. With
    ``to=None`` the floodgate leaves the game; with ``to=(hex, direction)``
    it moves to that edge.
    """

    hex: Hex
    direction: Direction
    to: tuple[Hex, Direction] | None = None

    def __post_init__(self) -> None:
        _check_type("Bribe.hex", self.hex, Hex)
        _check_type("Bribe.direction", self.direction, Direction)
        if self.to is not None:
            if (
                not isinstance(self.to, tuple)
                or len(self.to) != 2
                or not isinstance(self.to[0], Hex)
                or not isinstance(self.to[1], Direction)
            ):
                raise TypeError(f"Bribe.to must be None or a (Hex, Direction) pair, got {self.to!r}")


@dataclass(frozen=True)
class Pass:
    """Do nothing; legal only when the player has nothing they can place."""


Action = PlaceCanal | PlaceFloodgate | Bribe | Pass


class IllegalAction(ValueError):
    """An action the rules do not allow in this state; the message names the rule."""


# --- Public API --------------------------------------------------------------


def apply(state: GameState, player: str, action: Action, rng: random.Random) -> GameState:
    """The state after ``player`` takes ``action``; ``state`` is never changed.

    Raises ``TypeError`` for an object that is not an action, ``ValueError``
    for a player id that is not in the game, and ``IllegalAction`` (a
    ``ValueError``) naming the broken rule for an illegal action. Every
    check runs before the bribe die is rolled, so a rejected action leaves
    ``rng`` untouched.
    """
    _check_type("state", state, GameState)
    if not isinstance(action, (PlaceCanal, PlaceFloodgate, Bribe, Pass)):
        raise TypeError(f"action must be PlaceCanal, PlaceFloodgate, Bribe, or Pass, got {action!r}")
    _check_player(state, player)

    if isinstance(action, PlaceCanal):
        board, _ = _board_after(state, player, action)
        return _take_from_market(state, board, action.kind)
    if isinstance(action, PlaceFloodgate):
        board, _ = _board_after(state, player, action)
        return _take_from_market(state, board, PieceKind.FLOODGATE)
    if isinstance(action, Bribe):
        board, _ = _board_after(state, player, action)
        die_faces = (state.preset or shipped_preset(state.mode)).die_faces
        roll = rng.randint(1, die_faces)
        players = tuple(
            replace(p, debt=p.debt + roll) if p.id == player else p for p in state.players
        )
        return replace(state, players=players, board=board)
    if _has_placement(state):
        raise IllegalAction("pass is only legal when the player has nothing they can place")
    return replace(state)


def legal_actions(state: GameState, player: str) -> tuple[Action, ...]:
    """Every legal action for ``player``, each once, in a fixed order.

    Canal placements come first (by kind in ``PieceKind`` order, then hex,
    then rotation), then floodgate placements (by hex, then direction in
    ``Direction`` order), then bribes (by the floodgate's hex and
    direction; removal before moves, moves by target hex and direction),
    and last ``Pass()``, listed only when there is no placement.
    """
    _check_type("state", state, GameState)
    _check_player(state, player)
    canals = _canal_placements(state)
    gates = _floodgate_placements(state)
    bribes = _bribes(state.board)
    passes: tuple[Action, ...] = () if canals or gates else (Pass(),)
    return (*canals, *gates, *bribes, *passes)


def _board_after(
    state: GameState, player: str, action: PlaceCanal | PlaceFloodgate | Bribe
) -> tuple[Board, list[Hex]]:
    """The board after ``player`` places a piece or bribes, and its watered vineyards.

    The board is the one ``apply`` puts in its new state, claims included;
    the market, debt, and die roll are left out, so nothing is drawn. Raises
    ``IllegalAction`` exactly as ``apply`` does. ``state`` and ``player``
    must already be checked. The bots use this to weigh a move without
    building a whole state.
    """
    if isinstance(action, PlaceCanal):
        board = _canal_board(state, player, action)
    elif isinstance(action, PlaceFloodgate):
        board = _floodgate_board(state, action)
    else:
        board = _bribe_board(state, action)
    return _claim(board, player)


# --- Place a canal -----------------------------------------------------------


def _canal_board(state: GameState, player: str, action: PlaceCanal) -> Board:
    board = state.board
    kind, hex, rotation = action.kind, action.hex, action.rotation
    if not kind.is_canal:
        raise IllegalAction(f"{kind.value} is not a canal shape; place it with PlaceFloodgate")
    if not 0 <= rotation < ROTATIONS:
        raise IllegalAction(f"rotation must be 0 to {ROTATIONS - 1}, got {rotation}")
    if kind not in state.market:
        raise IllegalAction(f"the market has no {kind.value}")
    reason = _canal_hex_problem(board, hex)
    if reason:
        raise IllegalAction(reason)
    edges = kind.edges(rotation)
    if not _connects(board, hex, edges):
        raise IllegalAction(
            f"a {kind.value} on {hex} at rotation {rotation} has no opening facing the river "
            "or an opening of a canal on the board"
        )
    canal = PlacedCanal(hex, kind, _canonical_rotation(kind, rotation), player)
    return board._derive(canals=board.canals + (canal,))  # every piece checked above


def _canal_hex_problem(board: Board, hex: Hex) -> str | None:
    tile = board.tile_at(hex)
    if tile is None:
        return f"{hex} is off the board"
    if tile.terrain is not Terrain.EMPTY:
        return f"{hex} is a {tile.terrain.value} tile; canals go on empty tiles"
    if board.canal_at(hex) is not None:
        return f"{hex} already has a canal"
    return None


def _connects(board: Board, hex: Hex, edges: frozenset[Direction]) -> bool:
    """Whether an opening faces the river or an opening of any canal, gated or dry.

    ``hex`` is an empty tile of ``board``.
    """
    return not edges.isdisjoint(_connecting_dirs(board, hex))


def _connecting_dirs(board: Board, hex: Hex) -> frozenset[Direction]:
    """The directions from tile ``hex`` that face the river or an opening of a canal."""
    statics = board._static()
    dirs = statics.river_dirs[hex]
    canal_at = board._canal_index.get
    extra = [
        d
        for d, target in statics.neighbors[hex].items()
        if (other := canal_at(target)) is not None and _OPPOSITE[d] in other.edges
    ]
    return dirs.union(extra) if extra else dirs


def _canonical_rotation(kind: PieceKind, rotation: int) -> int:
    return _CANONICAL[kind, rotation]


def _first_rotation(kind: PieceKind, rotation: int) -> int:
    """The smallest rotation that gives ``kind`` the same edges as ``rotation``."""
    edges = kind.edges(rotation)
    return next(r for r in range(ROTATIONS) if kind.edges(r) == edges)


_OPPOSITE = {d: d.opposite() for d in Direction}
_CANONICAL: dict[tuple[PieceKind, int], int] = {
    (kind, r): _first_rotation(kind, r)
    for kind in PieceKind
    if kind.is_canal
    for r in range(ROTATIONS)
}
_CANONICAL_ROTATIONS: dict[PieceKind, tuple[int, ...]] = {
    kind: tuple(r for r in range(ROTATIONS) if _CANONICAL[kind, r] == r)
    for kind in PieceKind
    if kind.is_canal
}


# --- Place a floodgate -------------------------------------------------------


def _floodgate_board(state: GameState, action: PlaceFloodgate) -> Board:
    if PieceKind.FLOODGATE not in state.market:
        raise IllegalAction("the market has no floodgate")
    board = state.board
    side = _gate_side_or_raise(board, action.hex, action.direction)
    return board._derive(floodgates=board.floodgates + (Floodgate(*side),))


def _gate_side(board: Board, hex: Hex, direction: Direction) -> tuple[Hex, Direction] | None:
    """The canonical side of an edge that a canal opens: the smaller hex; None if no canal opens it."""
    sides = []
    for h, d in ((hex, direction), (hex.neighbor(direction), direction.opposite())):
        canal = board.canal_at(h)
        if canal is not None and d in canal.edges:
            sides.append((h, d))
    return min(sides, key=lambda side: side[0]) if sides else None


def _gate_side_or_raise(board: Board, hex: Hex, direction: Direction) -> tuple[Hex, Direction]:
    """Check a floodgate may go on this edge, and return its canonical side."""
    side = _gate_side(board, hex, direction)
    if side is None:
        raise IllegalAction(
            f"the edge of {hex} facing {direction.name} is not an open edge of a canal"
        )
    if board.has_floodgate(hex, direction):
        raise IllegalAction(f"the edge of {hex} facing {direction.name} already has a floodgate")
    return side


# --- Bribe -------------------------------------------------------------------


def _bribe_board(state: GameState, action: Bribe) -> Board:
    """The board after the bribe; the die is rolled by ``apply``, after this passes."""
    board = state.board
    if not board.floodgates:
        raise IllegalAction("a bribe needs a floodgate on the board")
    gate = board.floodgate_at(action.hex, action.direction)
    if gate is None:
        raise IllegalAction(
            f"the edge of {action.hex} facing {action.direction.name} has no floodgate to bribe"
        )
    floodgates = tuple(g for g in board.floodgates if g != gate)
    if action.to is not None:
        to_hex, to_direction = action.to
        if Floodgate(to_hex, to_direction) == gate:
            raise IllegalAction("a moved floodgate must go to another edge, not the one it is on")
        side = _gate_side_or_raise(board, to_hex, to_direction)
        floodgates += (Floodgate(*side),)
    return board._derive(floodgates=floodgates)


# --- Shared ------------------------------------------------------------------


def _claim(board: Board, player: str) -> tuple[Board, list[Hex]]:
    """``player`` claims every newly watered vineyard; also returns the watered vineyards."""
    watered = _watered(board)
    claims = list(board.claims)
    for vineyard in watered:
        if board.claimant(vineyard) is None:
            claims.append((vineyard, player))
    return board._derive(claims=tuple(claims)), watered


def _take_from_market(state: GameState, board: Board, market_take: PieceKind) -> GameState:
    """The state with ``board``, after the placed piece left the market and it was refilled."""
    market = list(state.market)
    market.remove(market_take)  # the first copy of that kind
    bag = state.bag
    if bag:
        market.append(bag[0])
        bag = bag[1:]
    return replace(state, board=board, market=tuple(market), bag=bag)


def _has_placement(state: GameState) -> bool:
    return bool(_canal_placements(state)) or bool(_floodgate_placements(state))


def _canal_placements(state: GameState) -> list[PlaceCanal]:
    board = state.board
    kinds = [k for k in PieceKind if k.is_canal and k in state.market]
    if not kinds:
        return []
    # The empty tiles with no canal, in hex order, each with the directions
    # an opening must face to connect.
    has_canal = board._canal_index
    hexes = [
        (hex, _connecting_dirs(board, hex))
        for hex in board._static().empty
        if hex not in has_canal
    ]
    actions = []
    for kind in kinds:
        rotations = [(r, kind.edges(r)) for r in _CANONICAL_ROTATIONS[kind]]
        for hex, connecting in hexes:
            for rotation, edges in rotations:
                if not edges.isdisjoint(connecting):
                    actions.append(PlaceCanal(kind, hex, rotation))
    return actions


def _open_gate_edges(board: Board) -> list[tuple[Hex, Direction]]:
    """Every edge a floodgate may go on, by its canonical side, in hex then direction order."""
    edges = []
    canal_at = board._canal_index.get
    gated = board._floodgate_index
    neighbors = board._static().neighbors
    for canal in board.canals:
        hex = canal.hex
        for d in canal.edges:
            if gated and board.has_floodgate(hex, d):
                continue
            # The canonical side is the smaller hex among the canals opening the edge.
            target = neighbors[hex][d]
            other = canal_at(target)
            if other is not None and _OPPOSITE[d] in other.edges and target < hex:
                continue
            edges.append((hex, d))
    return sorted(edges, key=_side_key)


def _floodgate_placements(state: GameState) -> list[PlaceFloodgate]:
    if PieceKind.FLOODGATE not in state.market:
        return []
    return [PlaceFloodgate(h, d) for h, d in _open_gate_edges(state.board)]


def _bribes(board: Board) -> list[Bribe]:
    gates = sorted(
        (_gate_side(board, g.hex, g.direction) for g in board.floodgates), key=_side_key
    )
    targets = _open_gate_edges(board)
    actions = []
    for h, d in gates:
        actions.append(Bribe(h, d))
        actions.extend(Bribe(h, d, to) for to in targets)
    return actions


_DIRECTION_INDEX = {d: i for i, d in enumerate(Direction)}


def _side_key(side: tuple[Hex, Direction]) -> tuple[Hex, int]:
    return (side[0], _DIRECTION_INDEX[side[1]])


def _check_player(state: GameState, player: object) -> None:
    if not isinstance(player, str) or state.player(player) is None:
        raise ValueError(f"{player!r} is not one of the game's players")


def _check_type(name: str, value: object, cls: type) -> None:
    if not isinstance(value, cls):
        raise TypeError(f"{name} must be a {cls.__name__}, got {value!r}")


def _check_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {value!r}")
