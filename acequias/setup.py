"""Game setup: the starting ``GameState`` for a new game.

Rules come from ``README.md`` (Setup): a generated board, the players with
no debt, a bag of pieces with the face-up market dealt from it, and a start
player. Every number comes from the preset (``acequias.config``): the board
size, the bag mix, and the market size.

The bag holds one piece per ``EMPTY`` hex on the board (its canalizable
capacity), split by ``preset.bag_mix`` with the largest remainder method.
The board comes from ``generate_board``, which keeps its own RNG; the bag
shuffle and the start player come from one ``random.Random(seed)``, drawn
in that order, so the same arguments always give an equal state.
"""

from __future__ import annotations

import random

from acequias.board import generate_board
from acequias.config import Preset
from acequias.config import preset as shipped_preset
from acequias.model import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    GameState,
    Mode,
    PieceKind,
    Player,
    Terrain,
)


def new_game(
    players: int, seed: int, mode: Mode, *, preset: Preset | None = None
) -> GameState:
    """The starting state of a game of ``players`` players in ``mode``.

    ``preset`` replaces the shipped preset for ``mode`` (for the
    simulation); its mode must be ``mode``. The state records the preset
    actually used in ``GameState.preset``. The same arguments always give
    an equal state.
    """
    _check_int("players", players)
    _check_int("seed", seed)
    if not isinstance(mode, Mode):
        raise TypeError(f"mode must be a Mode, got {mode!r}")
    if preset is None:
        preset = shipped_preset(mode)
    elif not isinstance(preset, Preset):
        raise TypeError(f"preset must be a Preset, got {preset!r}")
    if not MIN_PLAYERS <= players <= MAX_PLAYERS:
        raise ValueError(f"players must be {MIN_PLAYERS} to {MAX_PLAYERS}, got {players}")
    if preset.mode is not mode:
        raise ValueError(f"preset is for mode {preset.mode.name}, but mode is {mode.name}")

    board = generate_board(players, seed, mode, preset=preset)
    capacity = sum(1 for tile in board.tiles if tile.terrain is Terrain.EMPTY)

    rng = random.Random(seed)
    pieces = [
        kind for kind, count in bag_counts(capacity, preset).items() for _ in range(count)
    ]
    rng.shuffle(pieces)
    start = rng.randrange(players)

    seats = tuple(Player(f"p{seat}", seat) for seat in range(1, players + 1))
    start_player = seats[start].id
    return GameState(
        board=board,
        players=seats,
        mode=mode,
        round=1,
        start_player=start_player,
        current_player=start_player,
        market=tuple(pieces[: preset.market_size]),
        bag=tuple(pieces[preset.market_size :]),
        preset=preset,
    )


def bag_counts(total: int, preset: Preset) -> dict[PieceKind, int]:
    """How many pieces of each kind a bag of ``total`` pieces holds.

    Each kind gets the floor of its ``preset.bag_mix`` share of ``total``;
    the pieces left over go one each to the kinds with the largest
    fractional remainder, ties broken by ``PieceKind`` declaration order.
    The counts add up to ``total`` exactly; keys are in declaration order.
    """
    _check_int("total", total)
    if total < 0:
        raise ValueError(f"total cannot be negative, got {total}")
    if not isinstance(preset, Preset):
        raise TypeError(f"preset must be a Preset, got {preset!r}")
    kinds = list(PieceKind)
    counts = {kind: preset.bag_mix[kind] * total // 100 for kind in kinds}
    left = total - sum(counts.values())
    by_remainder = sorted(
        kinds, key=lambda kind: (-(preset.bag_mix[kind] * total % 100), kinds.index(kind))
    )
    for kind in by_remainder[:left]:
        counts[kind] += 1
    return counts


def _check_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {value!r}")
