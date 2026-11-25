"""The turn engine: check and apply one player's action, and list the legal ones.

Rules come from ``README.md`` (Turn, Claims and watering, Floodgate, Bribe).
An action is one of eight frozen, hashable dataclasses: ``PlaceCanal``,
``PlaceFloodgate``, ``Bribe``, ``Pass``, and, under ``action_die`` bribe
rules (``Preset.bribe_rules``), ``RollActionDie``, ``Release``, ``Resow``,
and ``DeclineFace``.

``apply(state, player, action, rng)`` returns a new ``GameState`` and never
changes its input. It does not check or change whose turn it is (that is
the round loop's job), so ``current_player``, ``start_player``, and
``round`` are copied unchanged. ``rng`` is drawn from only after every
check has passed, so a rejected action leaves it untouched. A bribe first
rolls the die, one ``rng.randint(1, die_faces)`` call. Then, under roulette
varietal rules only, each vineyard the action newly claims is planted with
one ``rng.choice(preset.roulette)`` spin, in ascending hex order, and
recorded in ``Board.plantings``. Under fixed rules nothing else is drawn.

Action die rules replace the bribe (``Bribe`` is illegal there, and
``RollActionDie`` is illegal under ``d6`` rules). ``RollActionDie`` adds
``Preset.action_die_cost`` to the roller's debt and sets
``GameState.pending_face`` to the face rolled; it is legal whenever the
player could take a turn, and it is not a placement (``Pass`` keeps its
rule). While a face is pending only ``current_player`` may act, and only
with that face's uses or ``DeclineFace()``; either clears the face. The
floodgate face is a ``PlaceFloodgate`` that takes nothing from the market
(the market and bag are unchanged); ``Release`` removes a floodgate from
the board; ``Resow`` replants a claimed vineyard (the claim stays). A
declined or unusable face keeps the cost paid. A season face
(``GOOD_SEASON``, ``DROUGHT``) is never pending: the roll applies it at
once, adding ``Preset.season_gain`` to every player's ``Player.season``,
or ``Preset.drought_loss`` to every ``Player.drought`` (scoring clamps
the drought so no total goes below 0).

With ``Preset.season_roll_every``, a ``GameState.season_roll`` of ``DUE``
allows only ``RollActionDie()`` by ``current_player`` (the season die's
holder, ``acequias.game.season_holder``, who may not be the round's start
player): a free roll, with no cost. A season face applies and clears it;
a personal face is pending with ``season_roll`` ``ROLLED`` until it is
used or declined, which clears both. With
``Preset.season_roll_personal_faces`` off, a personal face from the
season roll does nothing: it is never pending, and the roll just clears
``season_roll``. The round loop then gives the round's start player
their turn. The rng order of the die:

- ``RollActionDie`` (voluntary or season roll): one
  ``rng.choice(preset.action_die)``, nothing else.
- ``Resow``: one ``rng.choice(preset.roulette)``, the vineyard's new
  planting, then the claim spins below.
- ``Release`` and the die's ``PlaceFloodgate``: no draw of their own, then
  the claim spins below.
- ``DeclineFace``: nothing.

After a placement, a bribe, or a used die face (not a ``Pass``, a roll,
or a declined face) the acting player claims the
unclaimed watered vineyards in ascending hex order. With a
``Preset.grape_clusters_per_player`` cap they stop once they hold that many
claims; the rest stay unclaimed for the next player who places or bribes.
A vineyard left unclaimed gets no roulette spin.

``legal_actions(state, player)`` lists every legal action once, in a fixed
order: canal placements, floodgate placements, bribes (``d6`` rules),
``RollActionDie()`` (``action_die`` rules), then pass; with a pending face,
that face's uses then ``DeclineFace()``. Actions
that mean the same move are listed once in a canonical spelling (the
smallest rotation that opens the same edges; a floodgate edge named from
the canal side with the smaller hex), and ``apply`` accepts any spelling
of them and gives the same state.

Rules v3 (``Preset.planting`` ``VERTICES``, #149) has its own turn, kept
apart from the above. Only ``current_player`` acts, and the turn is:

1. ``RollActionDie()``, mandatory (the only legal action while
   ``GameState.actions_left`` is None): one ``rng.choice(preset.action_die)``.
   Floodgate and release add ``Preset.action_die_cost`` (the bribe) to the
   roller's debt, even when the face has no use; resow, good season, and
   drought are free. The roll sets ``actions_left``: 2 actions with at most
   1 canal after a good season, none after a drought, 1 otherwise. A
   floodgate, release, or resow face with a use is left pending: floodgate
   (``PlaceFloodgate`` from the die) and release (``Release``) are
   mandatory, so ``DeclineFace`` is illegal for them; resow is optional:
   ``ResowVineyard`` (one ``rng.choice(preset.roulette)``) on any planted
   vineyard, ``MoveVineyard`` of one's own vineyard to a spot they may
   plant on (with ``Preset.resow_can_move``; no draw), or ``DeclineFace``.
2. The actions: ``PlaceCanal`` (as above, from the market, no claims),
   ``Plant`` on a spot of ``acequias.flow.plantable_spots`` (one
   ``rng.choice(preset.roulette)``; under a ``grape_clusters_per_player``
   cap only while the player holds fewer vineyards), or ``Pass``, always
   legal, which ends the turn. A canal is illegal once ``canals`` is 0.

There are no claims, bribes, season rolls, or season points under Rules v3;
the d6 ``Bribe``, the market ``PlaceFloodgate``, and the hex ``Resow`` are
illegal, and ``Plant``, ``ResowVineyard``, and ``MoveVineyard`` are illegal
under hex planting. ``legal_actions`` lists, for ``current_player`` only:
``RollActionDie()`` before the roll; a pending face's uses (floodgates and
releases in edge order, then resows by vertex, then moves by vertex and
target), then ``DeclineFace()`` for resow; otherwise canal placements,
plants by vertex, then ``Pass()``. ``acequias.game`` ends the turn once no
face is pending and no action is left. Nothing here depends on the board's
bounds or ``Board.spots``, so the turn also fits an open board.

Watering comes from ``acequias.flow.water``; the die size from the game's
preset. Standard library only; no global randomness.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from acequias.config import BribeRules, PlantingRules, Preset, VarietalRules
from acequias.config import preset as shipped_preset
from acequias.flow import _watered, can_plant, plantable_spots
from acequias.hex import Direction, Hex, Vertex
from acequias.model import (
    ROTATIONS,
    ActionsLeft,
    Board,
    DieFace,
    Floodgate,
    GameState,
    PieceKind,
    PlacedCanal,
    PlantedVineyard,
    SeasonRoll,
    Terrain,
)

__all__ = [
    "PlaceCanal",
    "PlaceFloodgate",
    "Bribe",
    "Pass",
    "RollActionDie",
    "Release",
    "Resow",
    "DeclineFace",
    "Plant",
    "ResowVineyard",
    "MoveVineyard",
    "Action",
    "IllegalAction",
    "apply",
    "legal_actions",
    "season_applied",
    "roll_face",
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
    """Place a floodgate on the edge of ``hex`` facing ``direction``.

    It comes from the market or, while the action die's floodgate face is
    pending, from the die (the market and bag are left alone).
    """

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


@dataclass(frozen=True)
class RollActionDie:
    """Pay the action die's cost in debt and roll it (``action_die`` rules only)."""


@dataclass(frozen=True)
class Release:
    """Die face Release: remove the floodgate on the edge of ``hex`` facing ``direction``."""

    hex: Hex
    direction: Direction

    def __post_init__(self) -> None:
        _check_type("Release.hex", self.hex, Hex)
        _check_type("Release.direction", self.direction, Direction)


@dataclass(frozen=True)
class Resow:
    """Die face Resow: spin the roulette again for the claimed vineyard on ``hex``."""

    hex: Hex

    def __post_init__(self) -> None:
        _check_type("Resow.hex", self.hex, Hex)


@dataclass(frozen=True)
class DeclineFace:
    """Leave the rolled die face unused; its cost stays paid."""


@dataclass(frozen=True)
class Plant:
    """Rules v3: plant a vineyard on ``vertex``; the roulette picks its varietal."""

    vertex: Vertex

    def __post_init__(self) -> None:
        _check_type("Plant.vertex", self.vertex, Vertex)


@dataclass(frozen=True)
class ResowVineyard:
    """Rules v3 resow face: spin the roulette again for the vineyard planted on ``vertex``."""

    vertex: Vertex

    def __post_init__(self) -> None:
        _check_type("ResowVineyard.vertex", self.vertex, Vertex)


@dataclass(frozen=True)
class MoveVineyard:
    """Rules v3 resow face with ``resow_can_move``: move your vineyard on ``vertex`` to ``to``.

    The vineyard keeps its varietal; ``to`` must be a spot you may plant on.
    """

    vertex: Vertex
    to: Vertex

    def __post_init__(self) -> None:
        _check_type("MoveVineyard.vertex", self.vertex, Vertex)
        _check_type("MoveVineyard.to", self.to, Vertex)


Action = (
    PlaceCanal
    | PlaceFloodgate
    | Bribe
    | Pass
    | RollActionDie
    | Release
    | Resow
    | DeclineFace
    | Plant
    | ResowVineyard
    | MoveVineyard
)
_ACTION_TYPES = (
    PlaceCanal, PlaceFloodgate, Bribe, Pass, RollActionDie, Release, Resow, DeclineFace,
    Plant, ResowVineyard, MoveVineyard,
)
_V3_ACTIONS = (Plant, ResowVineyard, MoveVineyard)
_FACE_ACTIONS = {
    DieFace.FLOODGATE: PlaceFloodgate,
    DieFace.RELEASE: Release,
    DieFace.RESOW: Resow,
}


class IllegalAction(ValueError):
    """An action the rules do not allow in this state; the message names the rule."""


# --- Public API --------------------------------------------------------------


def apply(state: GameState, player: str, action: Action, rng: random.Random) -> GameState:
    """The state after ``player`` takes ``action``; ``state`` is never changed.

    Raises ``TypeError`` for an object that is not an action, ``ValueError``
    for a player id that is not in the game, and ``IllegalAction`` (a
    ``ValueError``) naming the broken rule for an illegal action. Every
    check runs before any die or roulette draw, so a rejected action leaves
    ``rng`` untouched.
    """
    _check_type("state", state, GameState)
    if not isinstance(action, _ACTION_TYPES):
        raise TypeError(
            "action must be PlaceCanal, PlaceFloodgate, Bribe, Pass, RollActionDie, "
            f"Release, Resow, DeclineFace, Plant, ResowVineyard, or MoveVineyard, got {action!r}"
        )
    _check_player(state, player)
    preset = _preset(state)
    if preset.planting is PlantingRules.VERTICES:
        return _apply_v3(state, player, action, rng, preset)
    if isinstance(action, _V3_ACTIONS):
        raise IllegalAction(
            f"{type(action).__name__} is only legal under vertex planting (Rules v3)"
        )

    if state.pending_face is not None:
        return _resolve_face(state, player, action, rng)
    if state.season_roll is SeasonRoll.DUE:
        if player != state.current_player:
            raise IllegalAction(
                f"{state.current_player} has the season roll to make; {player} cannot act"
            )
        if not isinstance(action, RollActionDie):
            raise IllegalAction(
                f"the season roll comes first: {player} must roll the action die, "
                f"not {type(action).__name__}"
            )
        return _roll(state, player, 0, SeasonRoll.ROLLED, rng)
    if isinstance(action, (Release, Resow, DeclineFace)):
        raise IllegalAction(f"{type(action).__name__} needs a rolled action die face")
    if isinstance(action, RollActionDie):
        if preset.bribe_rules is not BribeRules.ACTION_DIE:
            raise IllegalAction("the action die is only rolled under action_die bribe rules")
        return _roll(state, player, preset.action_die_cost, None, rng)
    if isinstance(action, Bribe) and preset.bribe_rules is not BribeRules.D6:
        raise IllegalAction("there is no bribe under action_die rules; roll the action die")

    if isinstance(action, PlaceCanal):
        board, _ = _board_after(state, player, action)
        return _take_from_market(state, _plant(state, board, rng), action.kind)
    if isinstance(action, PlaceFloodgate):
        board, _ = _board_after(state, player, action)
        return _take_from_market(state, _plant(state, board, rng), PieceKind.FLOODGATE)
    if isinstance(action, Bribe):
        board, _ = _board_after(state, player, action)
        roll = rng.randint(1, preset.die_faces)
        players = tuple(
            replace(p, debt=p.debt + roll) if p.id == player else p for p in state.players
        )
        return replace(state, players=players, board=_plant(state, board, rng))
    if _has_placement(state):
        raise IllegalAction("pass is only legal when the player has nothing they can place")
    return replace(state)


def legal_actions(state: GameState, player: str) -> tuple[Action, ...]:
    """Every legal action for ``player``, each once, in a fixed order.

    Canal placements come first (by kind in ``PieceKind`` order, then hex,
    then rotation), then floodgate placements (by hex, then direction in
    ``Direction`` order), then bribes (by the floodgate's hex and
    direction; removal before moves, moves by target hex and direction),
    then ``RollActionDie()`` under action die rules (bribes are listed only
    under d6 rules), and last ``Pass()``, listed only when there is no
    placement. With a pending die face the list is that face's uses, then
    ``DeclineFace()``: floodgate edges or releases in the bribe edge order,
    or resows by hex. It is empty for any player but ``current_player``.
    With a season roll ``DUE`` it is ``(RollActionDie(),)`` for
    ``current_player`` and empty for everyone else. Under Rules v3 the
    order is the one in the module docstring.
    """
    _check_type("state", state, GameState)
    _check_player(state, player)
    preset = _preset(state)
    if preset.planting is PlantingRules.VERTICES:
        return _legal_v3(state, player, preset)
    face = state.pending_face
    if face is not None:
        if player != state.current_player:
            return ()
        return (*_face_uses(state.board, face), DeclineFace())
    if state.season_roll is SeasonRoll.DUE:
        return (RollActionDie(),) if player == state.current_player else ()
    action_die = preset.bribe_rules is BribeRules.ACTION_DIE
    canals = _canal_placements(state)
    gates = _floodgate_placements(state)
    bribes: list[Bribe] = [] if action_die else _bribes(state.board)
    rolls: tuple[Action, ...] = (RollActionDie(),) if action_die else ()
    passes: tuple[Action, ...] = () if canals or gates else (Pass(),)
    return (*canals, *gates, *bribes, *rolls, *passes)


def _board_after(
    state: GameState,
    player: str,
    action: PlaceCanal | PlaceFloodgate | Bribe | Release | Resow,
) -> tuple[Board, list[Hex]]:
    """The board after ``player`` places a piece, bribes, or uses a die face, and its watered vineyards.

    The board is the one ``apply`` puts in its new state, claims included;
    the market, debt, die roll, and roulette spins are left out, so nothing
    is drawn (under roulette rules the new claims have no planting, and a
    ``Resow`` keeps the old planting). Raises
    ``IllegalAction`` exactly as ``apply`` does. ``state`` and ``player``
    must already be checked. The bots use this to weigh a move without
    building a whole state.
    """
    if isinstance(action, PlaceCanal):
        board = _canal_board(state, player, action)
    elif isinstance(action, PlaceFloodgate):
        board = _floodgate_board(state, action)
    elif isinstance(action, Release):
        board = _release_board(state, action)
    elif isinstance(action, Resow):
        board = _resow_check(state, action)
    else:
        board = _bribe_board(state, action)
    cap = _preset(state).grape_clusters_per_player
    return _claim(board, player, cap)


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
    """The board with the floodgate; from the die while its floodgate face is pending."""
    if state.pending_face is not DieFace.FLOODGATE and PieceKind.FLOODGATE not in state.market:
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


# --- Action die --------------------------------------------------------------


def _resolve_face(
    state: GameState, player: str, action: Action, rng: random.Random
) -> GameState:
    """The state after ``player`` uses or declines the pending die face."""
    face = state.pending_face
    if player != state.current_player:
        raise IllegalAction(
            f"{state.current_player} has a {face.value} face to resolve; {player} cannot act"
        )
    if isinstance(action, DeclineFace):
        return replace(state, pending_face=None, season_roll=None)
    use = _FACE_ACTIONS[face]
    if not isinstance(action, use):
        raise IllegalAction(
            f"the pending {face.value} face allows only {use.__name__} or DeclineFace, "
            f"not {type(action).__name__}"
        )
    board, _ = _board_after(state, player, action)
    if isinstance(action, Resow):
        board = _resow(state, board, action.hex, rng)
    return replace(state, board=_plant(state, board, rng), pending_face=None, season_roll=None)


def _roll(
    state: GameState,
    player: str,
    cost: int,
    rolled: SeasonRoll | None,
    rng: random.Random,
) -> GameState:
    """The state after ``player`` pays ``cost`` in debt and rolls the action die.

    A personal face is left pending, with ``season_roll`` set to
    ``rolled``; a season face applies at once and clears ``season_roll``.
    A personal face from the season roll (``rolled`` set) does nothing
    when ``Preset.season_roll_personal_faces`` is off: ``season_roll`` is
    cleared and no face is pending.
    """
    preset = _preset(state)
    face = roll_face(preset, rng)
    players = tuple(
        replace(p, debt=p.debt + cost) if p.id == player else p for p in state.players
    )
    state = replace(state, players=players)
    if face.is_season:
        return season_applied(state, face)
    if rolled is not None and not preset.season_roll_personal_faces:
        return replace(state, season_roll=None)
    return replace(state, pending_face=face, season_roll=rolled)


def roll_face(preset: Preset, rng: random.Random) -> DieFace:
    """One roll of ``preset``'s action die: ``rng.choice(preset.action_die)``."""
    return rng.choice(preset.action_die)


def season_applied(state: GameState, face: DieFace) -> GameState:
    """``state`` after the season face ``face`` applies to every player; no draw.

    A good season adds ``Preset.season_gain`` to every ``Player.season``,
    a drought ``Preset.drought_loss`` to every ``Player.drought`` (taken
    off at scoring, never below a total of 0). ``season_roll`` is cleared.
    """
    preset = _preset(state)
    if face is DieFace.GOOD_SEASON:
        gain = preset.season_gain
        players = tuple(replace(p, season=p.season + gain) for p in state.players)
    elif face is DieFace.DROUGHT:
        loss = preset.drought_loss
        players = tuple(replace(p, drought=p.drought + loss) for p in state.players)
    else:
        raise ValueError(f"{face.value} is not a season face")
    return replace(state, players=players, pending_face=None, season_roll=None)


def _release_board(state: GameState, action: Release) -> Board:
    """The board with the floodgate on the action's edge removed."""
    board = state.board
    gate = board.floodgate_at(action.hex, action.direction)
    if gate is None:
        raise IllegalAction(
            f"the edge of {action.hex} facing {action.direction.name} has no floodgate to release"
        )
    return board._derive(floodgates=tuple(g for g in board.floodgates if g != gate))


def _resow_check(state: GameState, action: Resow) -> Board:
    """Check the resow target is a claimed vineyard; the board itself is unchanged."""
    if state.board.claimant(action.hex) is None:
        raise IllegalAction(f"{action.hex} is not a claimed vineyard; only those can be resown")
    return state.board


def _resow(state: GameState, board: Board, hex: Hex, rng: random.Random) -> Board:
    """``board`` with one roulette spin replacing the planting on ``hex``."""
    varietal = rng.choice(_preset(state).roulette)
    plantings = tuple(p for p in board.plantings if p[0] != hex) + ((hex, varietal),)
    return board._derive(plantings=plantings)  # hex is a claimed blank vineyard


def _face_uses(board: Board, face: DieFace) -> list[Action]:
    """Every use of ``face`` on ``board``, in ``legal_actions`` order."""
    if face is DieFace.FLOODGATE:
        return [PlaceFloodgate(h, d) for h, d in _open_gate_edges(board)]
    if face is DieFace.RELEASE:
        gates = sorted(
            (_gate_side(board, g.hex, g.direction) for g in board.floodgates), key=_side_key
        )
        return [Release(h, d) for h, d in gates]
    return [Resow(hex) for hex, _ in board.claims]  # claims are stored by hex


# --- Rules v3 turn -------------------------------------------------------------

_BRIBE_FACES = (DieFace.FLOODGATE, DieFace.RELEASE)  # cost the bribe; also mandatory


def _apply_v3(
    state: GameState, player: str, action: Action, rng: random.Random, preset: Preset
) -> GameState:
    """``apply`` under Rules v3 (vertex planting); see the module docstring."""
    name = type(action).__name__
    if player != state.current_player:
        raise IllegalAction(f"it is {state.current_player}'s turn; {player} cannot act")
    if state.pending_face is not None:
        return _resolve_v3_face(state, player, action, rng, preset)
    left = state.actions_left
    if left is None:
        if not isinstance(action, RollActionDie):
            raise IllegalAction(f"{player} must roll the action die first, not {name}")
        return _roll_v3(state, player, rng, preset)
    if left.actions == 0:
        raise IllegalAction(f"{player} has no action left this turn")
    if isinstance(action, Pass):
        return replace(state, actions_left=ActionsLeft(0, 0))
    if isinstance(action, PlaceCanal):
        if left.canals == 0:
            raise IllegalAction("only one canal per turn; plant or pass")
        board = _canal_board(state, player, action)
        state = _take_from_market(state, board, action.kind)
        return replace(state, actions_left=ActionsLeft(left.actions - 1, left.canals - 1))
    if isinstance(action, Plant):
        _check_plant(state, player, action.vertex, preset)
        varietal = rng.choice(preset.roulette)
        planted = state.board.planted + (PlantedVineyard(action.vertex, player, varietal),)
        actions = left.actions - 1
        return replace(
            state,
            board=state.board._derive(planted=planted),  # checked by _check_plant
            actions_left=ActionsLeft(actions, min(left.canals, actions)),
        )
    raise IllegalAction(f"{name} is not a Rules v3 action here; place a canal, plant, or pass")


def _roll_v3(state: GameState, player: str, rng: random.Random, preset: Preset) -> GameState:
    """The state after ``player``'s mandatory roll: the bribe paid, the face pending or applied."""
    face = roll_face(preset, rng)
    cost = preset.action_die_cost if face in _BRIBE_FACES else 0
    players = tuple(
        replace(p, debt=p.debt + cost) if p.id == player else p for p in state.players
    )
    if face is DieFace.GOOD_SEASON:
        left = ActionsLeft(2, 1)
    elif face is DieFace.DROUGHT:
        left = ActionsLeft(0, 0)
    else:
        left = ActionsLeft(1, 1)
    state = replace(state, players=players, actions_left=left)
    if face.is_season or not _v3_face_uses(state.board, player, face, preset):
        return state
    return replace(state, pending_face=face)


def _resolve_v3_face(
    state: GameState, player: str, action: Action, rng: random.Random, preset: Preset
) -> GameState:
    """The state after ``player`` uses (or, for resow, declines) the pending face."""
    face = state.pending_face
    if isinstance(action, DeclineFace):
        if face in _BRIBE_FACES:
            raise IllegalAction(f"the {face.value} face is mandatory; it cannot be declined")
        return replace(state, pending_face=None)
    board = state.board
    if face is DieFace.FLOODGATE and isinstance(action, PlaceFloodgate):
        board = _floodgate_board(state, action)
    elif face is DieFace.RELEASE and isinstance(action, Release):
        board = _release_board(state, action)
    elif face is DieFace.RESOW and isinstance(action, ResowVineyard):
        vineyard = board.planted_at(action.vertex)
        if vineyard is None:
            raise IllegalAction(f"no vineyard is planted on {action.vertex}")
        varietal = rng.choice(preset.roulette)
        rest = tuple(v for v in board.planted if v != vineyard)
        board = board._derive(planted=rest + (replace(vineyard, varietal=varietal),))
    elif face is DieFace.RESOW and isinstance(action, MoveVineyard) and preset.resow_can_move:
        vineyard = board.planted_at(action.vertex)
        if vineyard is None or vineyard.owner != player:
            raise IllegalAction(f"{player} has no vineyard on {action.vertex} to move")
        if not can_plant(board, player, action.to):
            raise IllegalAction(f"{player} may not plant on {action.to}")
        rest = tuple(v for v in board.planted if v != vineyard)
        board = board._derive(planted=rest + (replace(vineyard, vertex=action.to),))
    else:
        raise IllegalAction(
            f"the pending {face.value} face does not allow {type(action).__name__}"
        )
    return replace(state, board=board, pending_face=None)


def _v3_face_uses(board: Board, player: str, face: DieFace, preset: Preset) -> list[Action]:
    """Every use of a personal ``face`` for ``player`` under Rules v3, in ``legal_actions`` order."""
    if face is DieFace.RESOW:
        uses: list[Action] = [ResowVineyard(v.vertex) for v in board.planted]
        if preset.resow_can_move:
            mine = [v.vertex for v in board.planted if v.owner == player]
            spots = plantable_spots(board, player) if mine else ()
            uses += [MoveVineyard(v, to) for v in mine for to in spots]
        return uses
    return _face_uses(board, face)


def _check_plant(state: GameState, player: str, vertex: Vertex, preset: Preset) -> None:
    if not can_plant(state.board, player, vertex):
        raise IllegalAction(
            f"{player} may not plant on {vertex}: it must be free and touch one of "
            "their own canals that carries water"
        )
    if not _below_cap(state, player, preset):
        raise IllegalAction(
            f"{player} already holds grape_clusters_per_player "
            f"({preset.grape_clusters_per_player}) vineyards"
        )


def _below_cap(state: GameState, player: str, preset: Preset) -> bool:
    cap = preset.grape_clusters_per_player
    return cap is None or sum(1 for v in state.board.planted if v.owner == player) < cap


def _legal_v3(state: GameState, player: str, preset: Preset) -> tuple[Action, ...]:
    """``legal_actions`` under Rules v3; see the module docstring."""
    if player != state.current_player:
        return ()
    face = state.pending_face
    if face is not None:
        uses = _v3_face_uses(state.board, player, face, preset)
        return tuple(uses) if face in _BRIBE_FACES else (*uses, DeclineFace())
    left = state.actions_left
    if left is None:
        return (RollActionDie(),)
    if left.actions == 0:
        return ()
    canals = _canal_placements(state) if left.canals else []
    plants = (
        [Plant(v) for v in plantable_spots(state.board, player)]
        if _below_cap(state, player, preset)
        else []
    )
    return (*canals, *plants, Pass())


# --- Shared ------------------------------------------------------------------


def _preset(state: GameState) -> Preset:
    return state.preset or shipped_preset(state.mode)



def _claim(board: Board, player: str, cap: int | None) -> tuple[Board, list[Hex]]:
    """``player`` claims the unclaimed watered vineyards; also returns the watered vineyards.

    Claims go in ascending hex order and stop once ``player`` holds ``cap``
    claims (``None``: no cap). The rest stay unclaimed.
    """
    watered = _watered(board)
    claims = list(board.claims)
    held = sum(1 for _, p in claims if p == player) if cap is not None else 0
    for vineyard in watered:
        if cap is not None and held >= cap:
            break
        if board.claimant(vineyard) is None:
            claims.append((vineyard, player))
            held += 1
    return board._derive(claims=tuple(claims)), watered


def _plant(state: GameState, board: Board, rng: random.Random) -> Board:
    """``board`` with one roulette spin planted on each vineyard newly claimed since ``state``.

    Only under roulette rules; the spins go in ascending hex order. Under
    fixed rules ``board`` is returned as is and nothing is drawn.
    """
    preset = _preset(state)
    if preset.varietal_rules is not VarietalRules.ROULETTE:
        return board
    before = state.board._claim_index
    new = sorted(hex for hex, _ in board.claims if hex not in before)
    if not new:
        return board
    plantings = board.plantings + tuple((hex, rng.choice(preset.roulette)) for hex in new)
    return board._derive(plantings=plantings)  # each hex is a newly claimed blank vineyard


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
