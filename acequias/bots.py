"""Simple-policy bots: pick one legal action for a player.

A bot is a plain function ``decide(state, player, rng)`` (the ``Bot`` type
of ``acequias.game``) that returns one element of
``acequias.turn.legal_actions(state, player)``. Bots keep no state between
calls, never change the state they are given, and draw random numbers only
from ``rng``.

Three policies for the MVP:

- ``random_bot``: ``rng.choice`` over every legal action, bribes and
  floodgates included.
- ``greedy_bot``: one move, no lookahead. It places the canal that claims
  the most vineyard points this turn (``Varietal.points``); with no claim
  possible, the canal nearest an unclaimed vineyard, preferring the most
  valuable one at that distance. With no canal to place it puts a
  floodgate on a rival's canal if it can, any floodgate otherwise. It never
  bribes. Ties go to ``rng.choice`` over the tied candidates in
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

Greedy and saboteur count only vineyard points: water rights, the bodega bonus, and
debt are left out on purpose for the MVP. Boards and claims come from
``acequias.turn`` (the private ``_board_after`` that ``apply`` uses too),
so no rule is reimplemented here.

``POLICIES`` maps policy names to bots, and ``policy(name)`` looks one up.
Standard library only; no global randomness.
"""

from __future__ import annotations

import random
from collections.abc import Iterable, Sequence
from fractions import Fraction
from types import MappingProxyType
from typing import TypeVar

from acequias.config import preset as shipped_preset
from acequias.flow import _watered
from acequias.game import Bot
from acequias.hex import Hex
from acequias.model import Board, GameState, Terrain
from acequias.turn import (
    Action,
    Bribe,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    _board_after,
    legal_actions,
)

__all__ = ["random_bot", "greedy_bot", "saboteur_bot", "POLICIES", "policy"]

T = TypeVar("T")


def random_bot(state: GameState, player: str, rng: random.Random) -> Action:
    """A uniformly random legal action: ``rng.choice(legal_actions(state, player))``."""
    return rng.choice(legal_actions(state, player))


def greedy_bot(state: GameState, player: str, rng: random.Random) -> Action:
    """The placement that claims the most vineyard points now; see the module docstring.

    Raises ``ValueError`` for a ``player`` that is not in the game.
    """
    actions = legal_actions(state, player)
    canals = [a for a in actions if isinstance(a, PlaceCanal)]
    if canals:
        return _pick(_best_canals(state, player, canals, rng), rng)
    gates = [a for a in actions if isinstance(a, PlaceFloodgate)]
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
    actions = legal_actions(state, player)
    if actions == (Pass(),):
        return Pass()
    die_faces = (state.preset or shipped_preset(state.mode)).die_faces
    bribe_cost = Fraction(die_faces + 1, 2)
    own_before, rivals_before = _balance(state.board, _watered(state.board), player)

    candidates: list[Action] = []
    values: list[Fraction] = []
    for action in actions:
        if isinstance(action, Pass):
            continue
        after, watered = _board_after(state, player, action)  # the board apply would give
        own_after, rivals_after = _balance(after, watered, player)
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


POLICIES = MappingProxyType(
    {"random": random_bot, "greedy": greedy_bot, "saboteur": saboteur_bot}
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

    gains = [_gain(state, player, canal, unclaimed) for canal in canals]
    best_gain = max(gains)
    if best_gain > 0:
        return [c for c, g in zip(canals, gains) if g == best_gain]

    def closeness(canal: PlaceCanal) -> tuple[int, int]:
        distances = [(canal.hex.distance(t.hex), t.varietal.points) for t in unclaimed]
        nearest = min(d for d, _ in distances)
        best_value = max(p for d, p in distances if d == nearest)
        return (-nearest, best_value)

    keys = [closeness(c) for c in canals]
    top = max(keys)
    return [c for c, k in zip(canals, keys) if k == top]


def _gain(state, player, canal, unclaimed) -> int:
    """Points of the unclaimed vineyards that ``canal`` claims for ``player``."""
    after, _ = _board_after(state, player, canal)  # the board apply would give; no draw
    return sum(t.varietal.points for t in unclaimed if after.claimant(t.hex) == player)


def _touches_rival_canal(state: GameState, player: str, gate: PlaceFloodgate) -> bool:
    """Whether a canal on either side of the floodgate's edge belongs to another player."""
    board = state.board
    for hex in (gate.hex, gate.hex.neighbor(gate.direction)):
        canal = board.canal_at(hex)
        if canal is not None and canal.owner != player:
            return True
    return False


# --- Saboteur ----------------------------------------------------------------


def _balance(board: Board, watered: Iterable[Hex], player: str) -> tuple[int, int]:
    """``(own, rivals)``: points of watered vineyards claimed by ``player``, and by anyone else.

    ``watered`` is the board's watered vineyards (the keys of ``water(board)``).
    Unclaimed vineyards count in neither.
    """
    own = rivals = 0
    for hex in watered:
        claimant = board.claimant(hex)
        if claimant is None:
            continue
        points = board.tile_at(hex).varietal.points
        if claimant == player:
            own += points
        else:
            rivals += points
    return own, rivals


def _pick(candidates: Sequence[T], rng: random.Random) -> T:
    """The only candidate with no draw, or ``rng.choice`` among several."""
    if len(candidates) == 1:
        return candidates[0]
    return rng.choice(candidates)

