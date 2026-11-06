import ast
from collections import Counter
from pathlib import Path

import pytest

from acequias.board import generate_board
from acequias.config import FLASH, NORMAL, PLAYER_COUNTS, preset, with_overrides
from acequias.model import GameState, Mode, PieceKind, Player, Terrain
from acequias.setup import bag_counts, new_game

MODES = list(Mode)
STRAIGHT, GENTLE, SHARP, Y, T, CLAW, GATE = list(PieceKind)


def empty_hexes(board):
    return sum(1 for tile in board.tiles if tile.terrain is Terrain.EMPTY)


def mix(**shares):
    """A bag mix with the given shares by kind name and 0 for the rest."""
    return {kind: shares.get(kind.name, 0) for kind in PieceKind}


# --- Signature and preset ----------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_board_is_the_generated_board(players, mode):
    state = new_game(players, 7, mode)
    assert isinstance(state, GameState)
    assert state.mode is mode
    assert state.board == generate_board(players, 7, mode)


@pytest.mark.parametrize("mode", MODES)
def test_no_preset_uses_and_records_the_shipped_preset(mode):
    state = new_game(3, 1, mode)
    assert state.preset is preset(mode)


def test_an_overridden_preset_changes_the_board_and_the_bag():
    bigger = with_overrides(NORMAL, hexes_per_player=16)
    shipped = new_game(3, 5, Mode.NORMAL)
    tuned = new_game(3, 5, Mode.NORMAL, preset=bigger)
    assert tuned.preset is bigger
    assert tuned.board == generate_board(3, 5, Mode.NORMAL, preset=bigger)
    assert tuned.board != shipped.board
    shipped_total = len(shipped.market) + len(shipped.bag)
    tuned_total = len(tuned.market) + len(tuned.bag)
    assert tuned_total == empty_hexes(tuned.board)
    assert tuned_total > shipped_total


def test_a_preset_for_another_mode_is_rejected():
    with pytest.raises(ValueError):
        new_game(2, 1, Mode.NORMAL, preset=FLASH)
    with pytest.raises(ValueError):
        new_game(2, 1, Mode.FLASH, preset=NORMAL)


@pytest.mark.parametrize(
    "args, kwargs",
    [
        ((2, 1, Mode.NORMAL), {"preset": "normal"}),
        ((2, 1, Mode.NORMAL), {"preset": {}}),
        (("2", 1, Mode.NORMAL), {}),
        ((2.0, 1, Mode.NORMAL), {}),
        ((True, 1, Mode.NORMAL), {}),
        ((2, "1", Mode.NORMAL), {}),
        ((2, None, Mode.NORMAL), {}),
        ((2, 1, "normal"), {}),
        ((2, 1, None), {}),
    ],
)
def test_wrong_types_are_rejected(args, kwargs):
    with pytest.raises(TypeError):
        new_game(*args, **kwargs)


@pytest.mark.parametrize("players", [0, 1, 6, -2])
def test_player_counts_outside_two_to_five_are_rejected(players):
    with pytest.raises(ValueError, match="2 to 5"):
        new_game(players, 1, Mode.NORMAL)


def test_preset_is_keyword_only():
    with pytest.raises(TypeError):
        new_game(2, 1, Mode.NORMAL, NORMAL)


# --- Players and round -------------------------------------------------------


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_players_seats_and_round(players):
    state = new_game(players, 3, Mode.FLASH)
    assert state.round == 1
    assert state.players == tuple(Player(f"p{i}", i, 0) for i in range(1, players + 1))
    assert state.current_player == state.start_player
    assert state.player(state.start_player) is not None


def test_board_starts_with_no_canals_floodgates_or_claims():
    board = new_game(4, 9, Mode.NORMAL).board
    assert board.canals == ()
    assert board.floodgates == ()
    assert board.claims == ()


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_every_seat_can_start(players):
    starts = {new_game(players, seed, Mode.FLASH).start_player for seed in range(60)}
    assert starts == {f"p{i}" for i in range(1, players + 1)}


# --- Bag and market ----------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_pieces_fill_the_empty_hexes_by_the_bag_mix(players, mode):
    state = new_game(players, 11, mode)
    pieces = state.market + state.bag
    capacity = empty_hexes(state.board)
    assert len(pieces) == capacity
    counts = Counter(pieces)
    assert {kind: counts[kind] for kind in PieceKind} == bag_counts(capacity, state.preset)


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_shipped_presets_deal_a_market_of_four(players, mode):
    for seed in range(5):
        assert len(new_game(players, seed, mode).market) == 4


def test_bag_counts_with_a_total_that_does_not_divide_evenly():
    # Shares 40/20/15/5/5/5/10 of 13: 5.2, 2.6, 1.95, 0.65, 0.65, 0.65, 1.3.
    # Floors 5+2+1+0+0+0+1 = 9; the 4 left go to remainders .95, .65, .65, .65.
    counts = bag_counts(13, NORMAL)
    assert counts == {STRAIGHT: 5, GENTLE: 2, SHARP: 2, Y: 1, T: 1, CLAW: 1, GATE: 1}
    assert sum(counts.values()) == 13
    assert list(counts) == list(PieceKind)


def test_bag_counts_breaks_remainder_ties_by_declaration_order():
    even = with_overrides(NORMAL, bag_mix=mix(STRAIGHT=25, GENTLE_CURVE=25, CLAW=25, FLOODGATE=25))
    # Each kind's share of 2 is 0.5: the two left over go to the first two kinds.
    assert bag_counts(2, even) == {STRAIGHT: 1, GENTLE: 1, SHARP: 0, Y: 0, T: 0, CLAW: 0, GATE: 0}
    assert bag_counts(3, even)[CLAW] == 1
    assert bag_counts(3, even)[GATE] == 0


@pytest.mark.parametrize("total", range(0, 101))
def test_bag_counts_always_add_up(total):
    assert sum(bag_counts(total, NORMAL).values()) == total


def test_a_kind_with_no_share_gets_no_pieces():
    no_gates = with_overrides(NORMAL, bag_mix=mix(STRAIGHT=50, GENTLE_CURVE=30, CLAW=20))
    for total in range(0, 60):
        counts = bag_counts(total, no_gates)
        for kind in (SHARP, Y, T, GATE):
            assert counts[kind] == 0
    for seed in range(5):
        state = new_game(3, seed, Mode.NORMAL, preset=no_gates)
        assert set(state.market + state.bag) <= {STRAIGHT, GENTLE, CLAW}
        assert len(state.market + state.bag) == empty_hexes(state.board)


def test_market_is_the_top_of_the_shuffle_and_bag_the_rest():
    state = new_game(3, 21, Mode.NORMAL)
    pieces = state.market + state.bag
    assert len(state.market) == state.preset.market_size
    # The pieces are shuffled, not dealt in PieceKind order.
    ordered = tuple(sorted(pieces, key=list(PieceKind).index))
    assert pieces != ordered


def test_market_size_comes_from_the_preset():
    two = with_overrides(NORMAL, market_size=2)
    state = new_game(3, 4, Mode.NORMAL, preset=two)
    assert len(state.market) == 2
    # Same seed, same shuffle: only the market/bag split differs.
    shipped = new_game(3, 4, Mode.NORMAL)
    assert state.market + state.bag == shipped.market + shipped.bag
    assert state.bag[:2] == shipped.market[2:]


def test_a_market_larger_than_the_empty_hexes_holds_every_piece():
    huge = with_overrides(FLASH, market_size=1000)
    state = new_game(2, 1, Mode.FLASH, preset=huge)
    assert empty_hexes(state.board) < 1000
    assert len(state.market) == empty_hexes(state.board)
    assert state.bag == ()


# --- Determinism -------------------------------------------------------------


@pytest.mark.parametrize("mode", MODES)
def test_same_arguments_give_an_equal_state(mode):
    tuned = with_overrides(preset(mode), market_size=3)
    assert new_game(4, 99, mode) == new_game(4, 99, mode)
    assert new_game(4, 99, mode, preset=tuned) == new_game(4, 99, mode, preset=tuned)


def test_different_seeds_give_different_bags_or_start_players():
    states = [new_game(3, seed, Mode.NORMAL) for seed in range(5)]
    deals = {(s.market, s.bag, s.start_player) for s in states}
    assert len(deals) > 1


def test_new_game_does_not_use_the_global_random_state():
    import random

    random.seed(1)
    one = new_game(3, 8, Mode.NORMAL)
    random.seed(2)
    two = new_game(3, 8, Mode.NORMAL)
    assert one == two


def test_setup_imports_only_acequias_modules_and_the_standard_library():
    source = Path(__file__).parent.parent / "acequias" / "setup.py"
    tree = ast.parse(source.read_text("utf-8"))
    stdlib = {"__future__", "random"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if not node.module.startswith("acequias"):
                assert node.module.split(".")[0] in stdlib
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in stdlib
