"""The private fast paths behind the simulation speed-up (issue #84).

Each one must give exactly what the slow, public path gives: the tables
match the formulas, ``Board._derive`` matches ``replace``, ``_watered``
matches ``water``, and ``turn._board_after`` matches ``apply``.
"""

import random
from dataclasses import replace

import pytest

from acequias.flow import _watered, water
from acequias.game import act, game_over
from acequias.hex import Direction, Hex
from acequias.model import ROTATIONS, Mode, PieceKind
from acequias.setup import new_game
from acequias.turn import (
    _CANONICAL,
    Bribe,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    _board_after,
    apply,
    legal_actions,
)

MEMBERS = list(Direction)


def test_direction_tables_match_the_formulas():
    for i, d in enumerate(MEMBERS):
        assert d.opposite() is MEMBERS[(i + 3) % 6]
        assert d.offset == Hex(*d.value)
        for steps in range(-13, 14):
            assert d.rotated(steps) is MEMBERS[(i + steps) % 6]


def test_edges_table_matches_the_formula():
    base = {k: k.edges(0) for k in PieceKind if k.is_canal}
    for kind, edges in base.items():
        for r in range(ROTATIONS):
            assert kind.edges(r) == frozenset(d.rotated(r) for d in edges)


@pytest.mark.parametrize("bad", [True, 1.0, "1"])
def test_fast_paths_keep_the_type_errors(bad):
    with pytest.raises(TypeError):
        PieceKind.STRAIGHT.edges(bad)
    with pytest.raises(TypeError):
        Direction.E.rotated(bad)
    with pytest.raises(TypeError):
        Hex(bad, 0)


def test_fast_paths_keep_the_value_errors():
    with pytest.raises(ValueError):
        PieceKind.STRAIGHT.edges(6)
    with pytest.raises(ValueError):
        PieceKind.FLOODGATE.edges(0)


def test_canonical_rotation_is_the_smallest_with_the_same_edges():
    for (kind, r), canonical in _CANONICAL.items():
        assert kind.edges(canonical) == kind.edges(r)
        assert all(kind.edges(s) != kind.edges(r) for s in range(canonical))


def _states(seed, turns):
    """States of a random game, one per turn."""
    state = new_game(3, seed, Mode.NORMAL)
    rng = random.Random(seed)
    out = [state]
    while not game_over(state) and len(out) < turns:
        player = state.current_player
        state = act(state, player, rng.choice(legal_actions(state, player)), rng)
        out.append(state)
    return out


@pytest.mark.parametrize("seed", [1, 2])
def test_board_after_and_derive_match_apply_and_replace(seed):
    checked = set()
    for state in _states(seed, 60):
        player = state.current_player
        assert _watered(state.board) == sorted(water(state.board))
        for action in legal_actions(state, player):
            if isinstance(action, Pass):
                continue
            snapshot = repr(state)
            board, watered = _board_after(state, player, action)
            after = apply(state, player, action, random.Random(0))
            assert repr(state) == snapshot
            assert board == after.board
            assert watered == sorted(water(after.board))
            rebuilt = replace(
                state.board,
                canals=board.canals,
                floodgates=board.floodgates,
                claims=board.claims,
            )
            assert repr(rebuilt) == repr(board)
            assert hash(rebuilt) == hash(board)
            checked.add(type(action))
            if isinstance(action, Bribe):
                break  # bribes are many; one per state is enough here
    assert checked == {PlaceCanal, PlaceFloodgate, Bribe}
