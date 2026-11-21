"""Simple-policy bots: pick one legal action for a player.

A bot is a plain function ``decide(state, player, rng)`` (the ``Bot`` type
of ``acequias.game``) that returns one element of
``acequias.turn.legal_actions(state, player)``. Bots keep no state between
calls, never change the state they are given, and draw random numbers only
from ``rng``.

Three policies for the MVP, and a fourth after it:

- ``random_bot``: ``rng.choice`` over every legal action, bribes and
  floodgates included.
- ``greedy_bot``: one move, no lookahead. It places the canal that claims
  the most vineyard points this turn (``Preset.varietal_points``); with no claim
  possible, the canal nearest an unclaimed vineyard, preferring the most
  valuable one at that distance. With no canal to place it puts a
  floodgate on a rival's canal if it can, any floodgate otherwise. It never
  bribes. A player with no grape clusters left (``Preset.grape_clusters_per_player``)
  values every unclaimed vineyard at 0, so it skips the canal step and
  places a floodgate as above; with no floodgate to place it picks any
  canal. Ties go to ``rng.choice`` over the tied candidates in
  ``legal_actions`` order, with no draw when only one is left.
- ``saboteur_bot``: places floodgates and bribes on purpose. Every legal
  action but ``Pass`` gets a swing: the change in watered vineyard points
  claimed by the player minus the change in those claimed by rivals,
  measured on the watered vineyards of ``flow.water`` before and after
  the board ``apply`` would give. A bribe's value
  is its swing minus the die's expected roll, ``(die_faces + 1) / 2``;
  values are exact ``Fraction``s. It plays the highest value above 0 (ties
  by one ``rng.choice``) and falls back to ``greedy_bot`` when nothing is
  worth more than 0.

Under action die rules (``Preset.bribe_rules``) greedy and saboteur never
roll the die (weighing the roll is #67 and #42). Handed a pending face,
both play its use with the best swing above 0 (ties by one ``rng.choice``),
else ``DeclineFace()``. A ``Resow`` is weighed on the board with that
vineyard blank, so its swing is the roulette's mean points minus the
vineyard's points (for the player, or against a rival). ``random_bot``
rolls and resolves like any other legal action.

Claims come from ``_board_after``, which follows the cluster cap, so the
saboteur's swing counts only vineyards the player can claim: one a move
waters but leaves unclaimed counts for nobody.

Greedy and saboteur count only vineyard points: water rights, the bodega bonus, and
debt are left out on purpose for the MVP. A vineyard is worth the points of
``Board.varietal_at``; under roulette rules one with no varietal yet
(unclaimed, or newly claimed on the board ``_board_after`` gives, before
its spin) is worth the roulette's mean points, an exact ``Fraction``.
Boards and claims come from
``acequias.turn`` (the private ``_board_after`` that ``apply`` uses too),
so no rule is reimplemented here.

``score_aware_bot`` (#67) values every action by its effect on the full
score of ``acequias.scoring.calculate_score`` (vineyards, bodega, water
rights, debt), as if the game ended on the board the action gives
(``_board_after``, no draw): the change in its own total minus the change
in the best rival's total (the highest rival total after, against the
highest before). Values are exact ``Fraction``s. Chance counts by
expectation, never by sampling: a claimed vineyard with no varietal yet
counts at the roulette's mean points (the bodega handling is in
``_Evaluator._totals``), a d6 bribe adds ``(die_faces + 1) / 2`` debt, a
``Resow`` counts the vineyard at the roulette's mean, and
``RollActionDie`` is worth ``-action_die_cost`` plus the mean, over the
faces of ``Preset.action_die``, of ``max(0, best use of that face)`` (a
face can be declined; one with no use counts 0). It plays the highest
value even when none is above 0, and never falls back to greedy; ``Pass``
is legal only with nothing to place, and is then weighed at 0 against the
bribes or the roll. Handed a pending face, it plays the use with the
highest value, or ``DeclineFace()`` when none is above 0. Ties go to one
``rng.choice`` over the tied actions in ``legal_actions`` order, with no
draw when one is left; that is its only use of ``rng``. Claims come from
``_board_after``, so the cluster cap applies: a vineyard it waters but
cannot claim is worth nothing to it.

``POLICIES`` maps policy names to bots, and ``policy(name)`` looks one up.
Standard library only; no global randomness.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from fractions import Fraction
from types import MappingProxyType
from typing import TypeVar

from acequias.config import Preset, VarietalRules
from acequias.config import preset as shipped_preset
from acequias.flow import _watered
from acequias.game import Bot
from acequias.hex import Hex
from acequias.model import Board, GameState, Terrain
from acequias.scoring import Score, calculate_score
from acequias.turn import (
    Action,
    Bribe,
    DeclineFace,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    Resow,
    RollActionDie,
    _board_after,
    legal_actions,
)

__all__ = ["random_bot", "greedy_bot", "saboteur_bot", "score_aware_bot", "POLICIES", "policy"]

T = TypeVar("T")


def random_bot(state: GameState, player: str, rng: random.Random) -> Action:
    """A uniformly random legal action: ``rng.choice(legal_actions(state, player))``."""
    return rng.choice(legal_actions(state, player))


def greedy_bot(state: GameState, player: str, rng: random.Random) -> Action:
    """The placement that claims the most vineyard points now; see the module docstring.

    Raises ``ValueError`` for a ``player`` that is not in the game.
    """
    if state.pending_face is not None:
        return _resolve_face(state, player, rng)
    actions = legal_actions(state, player)
    canals = [a for a in actions if isinstance(a, PlaceCanal)]
    gates = [a for a in actions if isinstance(a, PlaceFloodgate)]
    out_of_clusters = _out_of_clusters(state, player)
    if canals and not (out_of_clusters and gates):
        if out_of_clusters:
            return _pick(canals, rng)
        return _pick(_best_canals(state, player, canals, rng), rng)
    if gates:
        on_rival = [g for g in gates if _touches_rival_canal(state, player, g)]
        return _pick(on_rival or gates, rng)
    return Pass()


def saboteur_bot(state: GameState, player: str, rng: random.Random) -> Action:
    """The action with the best vineyard swing, floodgates and bribes included.

    See the module docstring. Raises ``ValueError`` for a ``player`` that is
    not in the game. Each action is evaluated on the board ``apply`` would
    give, without the die roll (it changes debt, not the board), so
    evaluation never draws from ``rng``.
    """
    if state.pending_face is not None:
        return _resolve_face(state, player, rng)
    actions = legal_actions(state, player)
    if all(isinstance(a, (Pass, RollActionDie)) for a in actions):
        return Pass()
    die_faces = (state.preset or shipped_preset(state.mode)).die_faces
    bribe_cost = Fraction(die_faces + 1, 2)
    worth = _worth(state)
    own_before, rivals_before = _balance(state.board, _watered(state.board), player, worth)

    candidates: list[Action] = []
    values: list[Fraction] = []
    for action in actions:
        if isinstance(action, (Pass, RollActionDie)):
            continue
        after, watered = _board_after(state, player, action)  # the board apply would give
        own_after, rivals_after = _balance(after, watered, player, worth)
        value = Fraction((own_after - own_before) - (rivals_after - rivals_before))
        if isinstance(action, Bribe):
            value -= bribe_cost
        if value > 0:
            candidates.append(action)
            values.append(value)
    if not candidates:
        return greedy_bot(state, player, rng)
    best = max(values)
    return _pick([a for a, v in zip(candidates, values) if v == best], rng)


def score_aware_bot(state: GameState, player: str, rng: random.Random) -> Action:
    """The action that most raises its total over the best rival's; see the module docstring.

    Raises ``ValueError`` for a ``player`` that is not in the game, or one
    with no action (a pending face that is someone else's). Evaluation
    never draws from ``rng``; only a tie does, once.
    """
    actions = legal_actions(state, player)
    if not actions:
        raise ValueError(f"{player!r} has no die face to resolve; it is {state.current_player}'s")
    if len(actions) == 1 and state.pending_face is None:
        return actions[0]  # Pass alone
    evaluator = _Evaluator(state, player)
    if state.pending_face is not None:
        uses = [a for a in actions if not isinstance(a, DeclineFace)]
        values = [evaluator.value(state, a) for a in uses]
        best = max(values, default=Fraction(0))
        if best <= 0:
            return DeclineFace()
        return _pick([a for a, v in zip(uses, values) if v == best], rng)
    values = [
        evaluator.roll_value() if isinstance(a, RollActionDie)
        else Fraction(0) if isinstance(a, Pass)
        else evaluator.value(state, a)
        for a in actions
    ]
    best = max(values)
    return _pick([a for a, v in zip(actions, values) if v == best], rng)


POLICIES = MappingProxyType(
    {
        "random": random_bot,
        "greedy": greedy_bot,
        "saboteur": saboteur_bot,
        "score_aware": score_aware_bot,
    }
)
"""Every bot policy by name, read-only."""


def policy(name: str) -> Bot:
    """The bot for policy ``name``; ``ValueError`` listing the valid names if unknown."""
    if not isinstance(name, str):
        raise TypeError(f"policy name must be a str, got {name!r}")
    try:
        return POLICIES[name]
    except KeyError:
        valid = ", ".join(repr(n) for n in POLICIES)
        raise ValueError(f"unknown policy {name!r}; valid policies are {valid}") from None


# --- Greedy ------------------------------------------------------------------


def _best_canals(
    state: GameState, player: str, canals: list[PlaceCanal], rng: random.Random
) -> list[PlaceCanal]:
    """The canal placements greedy ties between, in ``legal_actions`` order."""
    board = state.board
    unclaimed = [
        t for t in board.tiles
        if t.terrain is Terrain.VINEYARD and board.claimant(t.hex) is None
    ]
    if not unclaimed:
        return canals

    worth = _worth(state)
    gains = [_gain(state, player, canal, unclaimed, worth) for canal in canals]
    best_gain = max(gains)
    if best_gain > 0:
        return [c for c, g in zip(canals, gains) if g == best_gain]

    def closeness(canal: PlaceCanal) -> tuple[int, Fraction | int]:
        distances = [(canal.hex.distance(t.hex), worth(board, t.hex)) for t in unclaimed]
        nearest = min(d for d, _ in distances)
        best_value = max(p for d, p in distances if d == nearest)
        return (-nearest, best_value)

    keys = [closeness(c) for c in canals]
    top = max(keys)
    return [c for c, k in zip(canals, keys) if k == top]


def _gain(state, player, canal, unclaimed, worth) -> Fraction | int:
    """Points of the unclaimed vineyards that ``canal`` claims for ``player``."""
    after, _ = _board_after(state, player, canal)  # the board apply would give; no draw
    return sum(worth(after, t.hex) for t in unclaimed if after.claimant(t.hex) == player)


def _out_of_clusters(state: GameState, player: str) -> bool:
    """Whether ``player`` already holds as many claims as the preset's cluster cap."""
    cap = (state.preset or shipped_preset(state.mode)).grape_clusters_per_player
    if cap is None:
        return False
    return sum(1 for _, p in state.board.claims if p == player) >= cap


Worth = Callable[[Board, Hex], "Fraction | int"]


def _worth(state: GameState) -> Worth:
    """The bots' value of the vineyard at a hex of a board, under the game's preset.

    The points of ``board.varietal_at(hex)``; under roulette rules a
    vineyard with no varietal yet is worth the roulette's mean points.
    """
    preset = state.preset or shipped_preset(state.mode)
    points = preset.varietal_points
    if preset.varietal_rules is not VarietalRules.ROULETTE:
        return lambda board, hex: points[board.varietal_at(hex)]
    sectors = preset.roulette
    mean = Fraction(sum(points[v] for v in sectors), len(sectors))

    def worth(board: Board, hex: Hex) -> Fraction | int:
        varietal = board.varietal_at(hex)
        return mean if varietal is None else points[varietal]

    return worth


def _touches_rival_canal(state: GameState, player: str, gate: PlaceFloodgate) -> bool:
    """Whether a canal on either side of the floodgate's edge belongs to another player."""
    board = state.board
    for hex in (gate.hex, gate.hex.neighbor(gate.direction)):
        canal = board.canal_at(hex)
        if canal is not None and canal.owner != player:
            return True
    return False


# --- Saboteur ----------------------------------------------------------------


def _balance(
    board: Board, watered: Iterable[Hex], player: str, worth: Worth
) -> tuple[Fraction | int, Fraction | int]:
    """``(own, rivals)``: points of watered vineyards claimed by ``player``, and by anyone else.

    ``watered`` is the board's watered vineyards (the keys of ``water(board)``).
    Unclaimed vineyards count in neither.
    """
    own: Fraction | int = 0
    rivals: Fraction | int = 0
    for hex in watered:
        claimant = board.claimant(hex)
        if claimant is None:
            continue
        points = worth(board, hex)
        if claimant == player:
            own += points
        else:
            rivals += points
    return own, rivals


# --- Action die --------------------------------------------------------------


def _resolve_face(state: GameState, player: str, rng: random.Random) -> Action:
    """The pending face's use with the best vineyard swing above 0, else ``DeclineFace()``."""
    actions = legal_actions(state, player)
    if not actions:
        raise ValueError(f"{player!r} has no die face to resolve; it is {state.current_player}'s")
    worth = _worth(state)
    own_before, rivals_before = _balance(state.board, _watered(state.board), player, worth)
    candidates: list[Action] = []
    values: list[Fraction] = []
    for action in actions:
        if isinstance(action, DeclineFace):
            continue
        after, watered = _board_after(state, player, action)
        if isinstance(action, Resow):  # weighed blank: the respin's mean points
            after = after._derive(plantings=tuple(p for p in after.plantings if p[0] != action.hex))
        own_after, rivals_after = _balance(after, watered, player, worth)
        value = Fraction((own_after - own_before) - (rivals_after - rivals_before))
        if value > 0:
            candidates.append(action)
            values.append(value)
    if not candidates:
        return DeclineFace()
    best = max(values)
    return _pick([a for a, v in zip(candidates, values) if v == best], rng)


# --- Score-aware -------------------------------------------------------------


class _Evaluator:
    """The score-aware values of actions for one player on one state.

    ``value`` is (own expected total after - own total now) - (best rival's
    expected total after - best rival's total now), on the board
    ``_board_after`` gives, scored by ``calculate_score`` as if the game
    ended there. Values are cached by action, so a use weighed for the die
    is scored once.
    """

    def __init__(self, state: GameState, player: str) -> None:
        preset = state.preset or shipped_preset(state.mode)
        self.state = state
        self.player = player
        self.preset: Preset = preset
        self.rivals = [p.id for p in state.players if p.id != player]
        if preset.varietal_rules is VarietalRules.ROULETTE:
            points = preset.varietal_points
            self.mean = Fraction(sum(points[v] for v in preset.roulette), len(preset.roulette))
        else:
            self.mean = Fraction(0)  # under fixed rules no vineyard is blank
        self.bribe_debt = Fraction(preset.die_faces + 1, 2)
        totals = self._totals(state.board, _watered(state.board))
        self.own_now = totals[player]
        self.rival_now = max(totals[r] for r in self.rivals)
        self._cache: dict[Action, Fraction] = {}

    def value(self, state: GameState, action: Action) -> Fraction:
        """The value of a placement, bribe, or face use; ``state`` carries any pending face."""
        cached = self._cache.get(action)
        if cached is not None:
            return cached
        after, watered = _board_after(state, self.player, action)  # no draw
        if isinstance(action, Resow):  # weighed blank: the respin's mean points
            after = after._derive(plantings=tuple(p for p in after.plantings if p[0] != action.hex))
        totals = self._totals(after, watered)
        value = (totals[self.player] - self.own_now) - (
            max(totals[r] for r in self.rivals) - self.rival_now
        )
        if isinstance(action, Bribe):
            value -= self.bribe_debt
        self._cache[action] = value
        return value

    def roll_value(self) -> Fraction:
        """``-action_die_cost`` plus the mean, over the die's faces, of max(0, the face's best use)."""
        faces = self.preset.action_die
        best = {}
        for face in set(faces):
            rolled = replace(self.state, pending_face=face)
            uses = legal_actions(rolled, self.player)
            best[face] = max(
                (self.value(rolled, a) for a in uses if not isinstance(a, DeclineFace)),
                default=Fraction(0),
            )
        mean = Fraction(sum(max(Fraction(0), best[f]) for f in faces), len(faces))
        return mean - self.preset.action_die_cost

    def _totals(self, board: Board, watered: Iterable[Hex]) -> dict[str, Fraction]:
        """Every player's expected total on ``board``; ``watered`` is its watered vineyards.

        A watered claimed vineyard with no varietal yet (a claim before its
        spin, or a vineyard weighed for a resow) counts at the roulette's
        mean points, and never towards the bodega: the bodega bonus is the
        one the varietals already planted earn. This approximation
        undervalues a claim whose spin could complete the bodega (and
        cannot lose one, which only the varietals already counted earn).
        Rights and debt do not depend on varietals, so they come from a
        scoring with every blank planted with a placeholder; vineyards and
        bodega come from a scoring with the blank claims dropped.
        """
        blanks = [
            h for h in watered if board.claimant(h) is not None and board.varietal_at(h) is None
        ]
        if not blanks:
            return {pid: Fraction(s.total) for pid, s in self._score(board).items()}
        placeholder = self.preset.roulette[0]
        blank_set = set(blanks)
        planted = board._derive(plantings=board.plantings + tuple((h, placeholder) for h in blanks))
        dropped = board._derive(claims=tuple(c for c in board.claims if c[0] not in blank_set))
        full, known = self._score(planted), self._score(dropped)
        totals = {}
        for pid, s in full.items():
            count = sum(1 for h in blanks if board.claimant(h) == pid)
            totals[pid] = (
                s.total - s.vineyards - s.bodega
                + known[pid].vineyards + known[pid].bodega + self.mean * count
            )
        return totals

    def _score(self, board: Board) -> Mapping[str, Score]:
        return calculate_score(replace(self.state, board=board, pending_face=None), self.preset)


def _pick(candidates: Sequence[T], rng: random.Random) -> T:
    """The only candidate with no draw, or ``rng.choice`` among several."""
    if len(candidates) == 1:
        return candidates[0]
    return rng.choice(candidates)

