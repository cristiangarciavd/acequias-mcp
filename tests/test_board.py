import os
import random
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

from acequias import board as board_module
from acequias.board import generate_board, reachable_vineyards
from acequias.config import FLASH, NORMAL, preset, with_overrides
from acequias.hex import Hex
from acequias.model import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    Board,
    Mode,
    Terrain,
    Tile,
    Varietal,
)

PLAYER_COUNTS = range(MIN_PLAYERS, MAX_PLAYERS + 1)
ROOT = Path(__file__).resolve().parent.parent


# --- Helpers ---------------------------------------------------------------


def rows_of(board):
    """Row r -> its hexes sorted west to east."""
    rows = {}
    for tile in board.tiles:
        rows.setdefault(tile.hex.r, []).append(tile)
    return {r: sorted(tiles, key=lambda t: t.hex.q) for r, tiles in sorted(rows.items())}


AROUND = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))


def count_reachable(board):
    """Distinct vineyards linked to the river by a chain of empty hexes.

    Written apart from ``reachable_vineyards`` so the test does not check
    the generator with its own code.
    """
    cells = {(t.hex.q, t.hex.r): t.terrain for t in board.tiles}

    def around(c):
        return [(c[0] + dq, c[1] + dr) for dq, dr in AROUND]

    frontier = [
        c for c, t in cells.items()
        if t is Terrain.EMPTY and any(cells.get(n) is Terrain.RIVER for n in around(c))
    ]
    seen = set(frontier)
    while frontier:
        c = frontier.pop()
        for n in around(c):
            if n not in seen and cells.get(n) is Terrain.EMPTY:
                seen.add(n)
                frontier.append(n)
    return sum(
        1 for c, t in cells.items()
        if t is Terrain.VINEYARD and any(n in seen for n in around(c))
    )


def river_distance(hex, rivers):
    return min(hex.distance(river) for river in rivers)


def check_board(board, players, p):
    """Assert every Shape and Content criterion for one generated board."""
    tiles = board.tiles
    by_hex = {t.hex: t for t in tiles}
    rivers = [t.hex for t in tiles if t.terrain is Terrain.RIVER]
    vineyards = [t for t in tiles if t.terrain is Terrain.VINEYARD]
    stones = [t for t in tiles if t.terrain is Terrain.STONE]
    non_river = len(tiles) - len(rivers)

    # Only tiles.
    assert board.canals == () and board.floodgates == () and board.claims == ()

    # Shape: each row starts with river, is unbroken, and river is only there.
    rows = rows_of(board)
    assert list(rows) == list(range(min(rows), max(rows) + 1))
    for row in rows.values():
        assert row[0].terrain is Terrain.RIVER
        assert all(t.terrain is not Terrain.RIVER for t in row[1:])
        qs = [t.hex.q for t in row]
        assert qs == list(range(qs[0], qs[0] + len(qs)))
    row_list = list(rows.values())
    for north, south in zip(row_list, row_list[1:]):
        assert north[0].hex.distance(south[0].hex) == 1

    # Shape: sizes and connectivity.
    assert non_river == players * p.hexes_per_player
    start = tiles[0].hex
    seen = {start}
    stack = [start]
    while stack:
        for n in stack.pop().neighbors():
            if n in by_hex and n not in seen:
                seen.add(n)
                stack.append(n)
    assert len(seen) == len(tiles)

    # Content: counts.
    assert len(vineyards) == players * p.vineyards_per_player
    assert len(stones) == -(-p.stone_share * non_river // 100)  # exact ceil, as in config
    assert len(tiles) == len(rivers) + len(vineyards) + len(stones) + sum(
        t.terrain is Terrain.EMPTY for t in tiles
    )

    # Content: varietals.
    counts = Counter(t.varietal for t in vineyards)
    assert all(isinstance(v, Varietal) for v in counts)
    if len(vineyards) >= len(Varietal):
        assert set(counts) == set(Varietal)
    else:
        assert all(n == 1 for n in counts.values())
    full = [counts.get(v, 0) for v in Varietal] if len(vineyards) >= len(Varietal) else list(
        counts.values()
    )
    assert max(full) - min(full) <= 1

    # Content: vineyard distances.
    low, high = p.vineyard_distance
    for v in vineyards:
        assert all(by_hex.get(n) is None or by_hex[n].terrain is not Terrain.RIVER
                   for n in v.hex.neighbors())
        assert low <= river_distance(v.hex, rivers) <= high

    # Content: reachable vineyards.
    assert count_reachable(board) >= players


# --- Result and determinism ------------------------------------------------


def test_returns_a_board_of_tiles():
    board = generate_board(3, 7, Mode.NORMAL)
    assert isinstance(board, Board)
    assert board.tiles
    assert all(isinstance(t, Tile) for t in board.tiles)
    assert {t.terrain for t in board.tiles} <= set(Terrain)
    check_board(board, 3, NORMAL)


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_same_inputs_give_equal_boards(players, mode):
    for seed in (0, 1, 42, -5, 2**40):
        assert generate_board(players, seed, mode) == generate_board(players, seed, mode)


def test_same_board_in_a_fresh_process_with_another_hash_seed():
    script = (
        "from acequias.board import generate_board\n"
        "from acequias.model import Mode\n"
        "for mode in Mode:\n"
        "    for players in range(2, 6):\n"
        "        for seed in range(5):\n"
        "            print(repr(generate_board(players, seed, mode).tiles))\n"
    )
    outputs = []
    for hash_seed in ("1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            cwd=ROOT,
            check=True,
        )
        outputs.append(result.stdout)
    expected = "".join(
        repr(generate_board(players, seed, mode).tiles) + "\n"
        for mode in Mode
        for players in range(2, 6)
        for seed in range(5)
    )
    assert outputs[0] == outputs[1] == expected


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_different_seeds_give_different_boards(players, mode):
    reference = generate_board(players, 0, mode)
    different = sum(generate_board(players, seed, mode) != reference for seed in range(1, 101))
    assert different >= 95


def test_global_random_state_is_unchanged():
    random.seed(1234)
    before = random.getstate()
    generate_board(4, 99, Mode.NORMAL)
    generate_board(2, 3, Mode.FLASH)
    assert random.getstate() == before


def test_uses_no_global_random_module_functions():
    source = Path(board_module.__file__).read_text(encoding="utf-8")
    for name in ("random.random(", "random.randrange(", "random.shuffle(", "random.choice(",
                 "random.sample(", "random.randint(", "random.seed("):
        assert name not in source


# --- Input validation ------------------------------------------------------


@pytest.mark.parametrize("players", [-1, 0, 1, 6, 7])
def test_player_count_outside_range_raises(players):
    with pytest.raises(ValueError, match="2 to 5"):
        generate_board(players, 0, Mode.NORMAL)


@pytest.mark.parametrize("players", [True, False, 2.0, "3", None])
def test_player_count_not_int_raises(players):
    with pytest.raises(TypeError):
        generate_board(players, 0, Mode.NORMAL)


@pytest.mark.parametrize("seed", [True, False, 1.5, "1", None])
def test_seed_not_int_raises(seed):
    with pytest.raises(TypeError):
        generate_board(2, seed, Mode.NORMAL)


@pytest.mark.parametrize("mode", ["normal", "flash", None, 0])
def test_mode_not_mode_raises(mode):
    with pytest.raises(TypeError):
        generate_board(2, 0, mode)


@pytest.mark.parametrize("bad", [{}, "NORMAL", Mode.NORMAL, 1])
def test_preset_not_preset_raises(bad):
    with pytest.raises(TypeError):
        generate_board(2, 0, Mode.NORMAL, preset=bad)


def test_preset_of_another_mode_raises():
    with pytest.raises(ValueError, match="mode"):
        generate_board(2, 0, Mode.NORMAL, preset=FLASH)
    with pytest.raises(ValueError, match="mode"):
        generate_board(2, 0, Mode.FLASH, preset=NORMAL)


def test_default_preset_is_the_shipped_one():
    for mode in Mode:
        assert generate_board(3, 5, mode) == generate_board(3, 5, mode, preset=preset(mode))


# --- Preset overrides ------------------------------------------------------


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_overrides_drive_sizes_and_counts(players):
    p = with_overrides(NORMAL, hexes_per_player=20, vineyards_per_player=3)
    for seed in range(50):
        board = generate_board(players, seed, Mode.NORMAL, preset=p)
        check_board(board, players, p)
        non_river = sum(t.terrain is not Terrain.RIVER for t in board.tiles)
        assert non_river == players * 20
        assert sum(t.terrain is Terrain.VINEYARD for t in board.tiles) == players * 3


def test_overrides_of_distance_and_stone_share():
    p = with_overrides(FLASH, vineyard_distance=(3, 4), stone_share=20, hexes_per_player=10)
    for players in PLAYER_COUNTS:
        for seed in range(50):
            check_board(generate_board(players, seed, Mode.FLASH, preset=p), players, p)


def test_one_vineyard_per_player_has_no_repeated_varietal():
    p = with_overrides(NORMAL, vineyards_per_player=1)
    board = generate_board(2, 0, Mode.NORMAL, preset=p)
    check_board(board, 2, p)
    grapes = [t.varietal for t in board.tiles if t.terrain is Terrain.VINEYARD]
    assert len(grapes) == len(set(grapes)) == 2


def test_unreachable_distance_raises():
    p = with_overrides(NORMAL, vineyard_distance=(40, 50))
    with pytest.raises(ValueError, match="vineyard_distance") as info:
        generate_board(2, 0, Mode.NORMAL, preset=p)
    assert "(40, 50)" in str(info.value)
    assert "hexes_per_player=12" in str(info.value)


def test_too_many_vineyards_for_the_distance_raises():
    # Distance 2 only: one candidate per row, far fewer than the vineyards.
    p = with_overrides(NORMAL, vineyard_distance=(2, 2), vineyards_per_player=5)
    with pytest.raises(ValueError, match="vineyards_per_player=5"):
        generate_board(2, 0, Mode.NORMAL, preset=p)


def test_layouts_that_never_pass_raise_after_the_retry_cap():
    # So much stone that no vineyard can be reached through empty hexes.
    p = with_overrides(NORMAL, stone_share=80, vineyards_per_player=1)
    with pytest.raises(ValueError, match="stone_share=80"):
        generate_board(5, 0, Mode.NORMAL, preset=p)


# --- Every board, every player count, both modes ---------------------------


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_every_board_meets_the_criteria(players, mode):
    p = preset(mode)
    for seed in range(200):
        check_board(generate_board(players, seed, mode), players, p)


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_enough_vineyards_reachable_over_1000_seeds(players, mode):
    for seed in range(1000):
        assert count_reachable(generate_board(players, seed, mode)) >= players


def test_reachable_vineyards_follows_empty_chains():
    # River at q=0; row 0 is river, empty, empty, vineyard; row 1 river, stone, vineyard.
    tiles = [
        Tile(Hex(0, 0), Terrain.RIVER),
        Tile(Hex(1, 0), Terrain.EMPTY),
        Tile(Hex(2, 0), Terrain.EMPTY),
        Tile(Hex(3, 0), Terrain.VINEYARD, Varietal.MALBEC),
        Tile(Hex(-1, 1), Terrain.RIVER),
        Tile(Hex(0, 1), Terrain.STONE),
        Tile(Hex(1, 1), Terrain.STONE),
        Tile(Hex(2, 1), Terrain.STONE),
        Tile(Hex(3, 1), Terrain.STONE),
        Tile(Hex(4, 1), Terrain.VINEYARD, Varietal.BONARDA),
    ]
    board = Board(tiles=tiles)
    assert reachable_vineyards(board) == [Hex(3, 0)]
    assert count_reachable(board) == 1


# --- Modes -----------------------------------------------------------------


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_flash_boards_are_smaller(players):
    def size(mode):
        board = generate_board(players, 0, mode)
        return sum(t.terrain is not Terrain.RIVER for t in board.tiles) / players

    assert size(Mode.FLASH) < size(Mode.NORMAL)


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_flash_vineyards_are_closer_to_the_river(players):
    def average(mode):
        distances = []
        for seed in range(100):
            board = generate_board(players, seed, mode)
            rivers = [t.hex for t in board.tiles if t.terrain is Terrain.RIVER]
            distances += [
                river_distance(t.hex, rivers)
                for t in board.tiles
                if t.terrain is Terrain.VINEYARD
            ]
        return sum(distances) / len(distances)

    assert average(Mode.FLASH) < average(Mode.NORMAL)
