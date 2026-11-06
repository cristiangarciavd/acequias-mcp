"""Simple-policy bots: pick one legal action for a player.

A bot is a plain function ``decide(state, player, rng)`` (the ``Bot`` type
of ``acequias.game``) that returns one element of
``acequias.turn.legal_actions(state, player)``. Bots keep no state between
calls, never change the state they are given, and draw random numbers only
from ``rng``.

Two policies for the MVP:

- ``random_bot``: ``rng.choice`` over every legal action, bribes and
  floodgates included.
- ``greedy_bot``: one move, no lookahead. It places the canal that claims
  the most vineyard points this turn (``Varietal.points``); with no claim
  possible, the canal nearest an unclaimed vineyard, preferring the most
  valuable one at that distance. With no canal to place it puts a
  floodgate on a rival's canal if it can, any floodgate otherwise. It never
  bribes. Ties go to ``rng.choice`` over the tied candidates in
  ``legal_actions`` order, with no draw when only one is left.

Greedy counts only vineyard points: water rights, the bodega bonus, and
debt are left out on purpose for the MVP. Claims come from
``acequias.turn.apply``, so no rule is reimplemented here.

``POLICIES`` maps policy names to bots, and ``policy(name)`` looks one up.
Standard library only; no global randomness.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from types import MappingProxyType
from typing import TypeVar

from acequias.game import Bot
from acequias.model import GameState, Terrain
from acequias.turn import Action, Pass, PlaceCanal, PlaceFloodgate, apply, legal_actions

__all__ = ["random_bot", "greedy_bot", "POLICIES", "policy"]

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


POLICIES = MappingProxyType({"random": random_bot, "greedy": greedy_bot})
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

    gains = [_gain(state, player, canal, rng, unclaimed) for canal in canals]
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


def _gain(state, player, canal, rng, unclaimed) -> int:
    """Points of the unclaimed vineyards that ``canal`` claims for ``player``."""
    after = apply(state, player, canal, rng).board  # placements never draw from rng
    return sum(t.varietal.points for t in unclaimed if after.claimant(t.hex) == player)


def _touches_rival_canal(state: GameState, player: str, gate: PlaceFloodgate) -> bool:
    """Whether a canal on either side of the floodgate's edge belongs to another player."""
    board = state.board
    for hex in (gate.hex, gate.hex.neighbor(gate.direction)):
        canal = board.canal_at(hex)
        if canal is not None and canal.owner != player:
            return True
    return False


def _pick(candidates: Sequence[T], rng: random.Random) -> T:
    """The only candidate with no draw, or ``rng.choice`` among several."""
    if len(candidates) == 1:
        return candidates[0]
    return rng.choice(candidates)

