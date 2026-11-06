import ast
import dataclasses
from collections import Counter
from pathlib import Path

import pytest

from acequias.assembly import AssemblyStep, assembly_instructions
from acequias.board import generate_board
from acequias.hex import Direction, Hex
from acequias.model import (
    MAX_PLAYERS,
    MIN_PLAYERS,
    Board,
    Floodgate,
    Mode,
    PieceKind,
    PlacedCanal,
    Terrain,
    Tile,
    Varietal,
)

R = Terrain.RIVER
V = Terrain.VINEYARD
S = Terrain.STONE
E = Terrain.EMPTY


def tile(q, r, terrain, varietal=None):
    return Tile(Hex(q, r), terrain, varietal)


def small_board(**extra):
    """Three rows: row 2 steps south-east of row 1, row 3 south-west of row 2."""
    return Board(
        tiles=(
            tile(0, 0, R),
            tile(1, 0, V, Varietal.TORRONTES),
            tile(2, 0, S),
            tile(0, 1, R),
            tile(1, 1, E),
            tile(2, 1, V, Varietal.MALBEC),
            tile(-1, 2, R),
            tile(0, 2, V, Varietal.BONARDA),
        ),
        **extra,
    )


SMALL_BOARD_STEPS = [
    AssemblyStep(1, 1, Hex(0, 0), R, None, "Row 1, hex 1: river"),
    AssemblyStep(
        1, 2, Hex(1, 0), V, Varietal.TORRONTES, "Row 1, hex 2: vineyard, Torrontés"
    ),
    AssemblyStep(1, 3, Hex(2, 0), S, None, "Row 1, hex 3: stone"),
    AssemblyStep(
        2, 1, Hex(0, 1), R, None, "Row 2, hex 1: river, south-east of row 1, hex 1"
    ),
    AssemblyStep(2, 2, Hex(1, 1), E, None, "Row 2, hex 2: empty"),
    AssemblyStep(2, 3, Hex(2, 1), V, Varietal.MALBEC, "Row 2, hex 3: vineyard, Malbec"),
    AssemblyStep(
        3, 1, Hex(-1, 2), R, None, "Row 3, hex 1: river, south-west of row 2, hex 1"
    ),
    AssemblyStep(3, 2, Hex(0, 2), V, Varietal.BONARDA, "Row 3, hex 2: vineyard, Bonarda"),
]


def generated_boards(player_counts=range(MIN_PLAYERS, MAX_PLAYERS + 1), seeds=range(3)):
    for mode in Mode:
        for players in player_counts:
            for seed in seeds:
                yield mode, players, seed, generate_board(players, seed, mode)


# --- AssemblyStep ----------------------------------------------------------


def test_assembly_step_is_frozen_with_the_named_fields():
    step = SMALL_BOARD_STEPS[0]
    assert [f.name for f in dataclasses.fields(AssemblyStep)] == [
        "row",
        "position",
        "hex",
        "terrain",
        "varietal",
        "text",
    ]
    with pytest.raises(dataclasses.FrozenInstanceError):
        step.row = 2


# --- Hand-built board ------------------------------------------------------


def test_small_board_gives_the_exact_steps():
    assert assembly_instructions(small_board()) == SMALL_BOARD_STEPS


def test_canals_floodgates_and_claims_are_ignored():
    board = small_board(
        canals=(PlacedCanal(Hex(1, 1), PieceKind.STRAIGHT, 0, "p1"),),
        floodgates=(Floodgate(Hex(1, 1), Direction.E),),
        claims=((Hex(2, 1), "p1"),),
    )
    assert assembly_instructions(board) == SMALL_BOARD_STEPS


def test_row_1_is_the_northernmost_row_whatever_its_r():
    shifted = Board(
        tiles=tuple(
            Tile(Hex(t.hex.q, t.hex.r - 5), t.terrain, t.varietal) for t in small_board().tiles
        )
    )
    steps = assembly_instructions(shifted)
    assert [s.text for s in steps] == [s.text for s in SMALL_BOARD_STEPS]
    assert steps[0].hex == Hex(0, -5)


def test_north_west_neighbour_is_named_when_both_are_on_the_board():
    board = Board(
        tiles=(
            tile(0, 0, S),
            tile(1, 0, S),
            tile(0, 1, V, Varietal.MALBEC),
        )
    )
    steps = assembly_instructions(board)
    assert steps[-1].text == "Row 2, hex 1: vineyard, Malbec, south-east of row 1, hex 1"


def test_the_position_named_is_the_neighbour_above_not_always_hex_1():
    board = Board(
        tiles=(
            tile(0, 0, S),
            tile(1, 0, S),
            tile(2, 0, S),
            tile(1, 1, E),
        )
    )
    steps = assembly_instructions(board)
    assert steps[-1].text == "Row 2, hex 1: empty, south-east of row 1, hex 2"


def test_empty_board_gives_no_steps():
    assert assembly_instructions(Board()) == []


def test_not_a_board_raises_type_error():
    with pytest.raises(TypeError):
        assembly_instructions([])


def test_same_board_gives_the_same_steps():
    board = generate_board(4, 7, Mode.NORMAL)
    assert assembly_instructions(board) == assembly_instructions(board)
    assert assembly_instructions(board) == assembly_instructions(
        generate_board(4, 7, Mode.NORMAL)
    )


# --- Boards that cannot be laid out ----------------------------------------


def test_rows_that_skip_an_r_raise():
    board = Board(tiles=(tile(0, 0, R), tile(0, 1, R), tile(0, 3, R)))
    with pytest.raises(ValueError, match="row 3"):
        assembly_instructions(board)


def test_row_with_a_gap_in_q_raises():
    board = Board(tiles=(tile(0, 0, R), tile(0, 1, R), tile(1, 1, E), tile(3, 1, S)))
    with pytest.raises(ValueError, match="row 2"):
        assembly_instructions(board)


def test_hex_1_touching_no_hex_of_the_row_above_raises():
    board = Board(tiles=(tile(0, 0, R), tile(1, 0, E), tile(3, 1, S), tile(4, 1, S)))
    with pytest.raises(ValueError, match="row 2"):
        assembly_instructions(board)


# --- Generated boards ------------------------------------------------------


@pytest.mark.parametrize("players", [MIN_PLAYERS, MAX_PLAYERS])
@pytest.mark.parametrize("mode", list(Mode))
def test_every_tile_appears_exactly_once(mode, players):
    for seed in range(5):
        board = generate_board(players, seed, mode)
        steps = assembly_instructions(board)
        assert len(steps) == len(board.tiles)
        assert Counter(s.hex for s in steps) == Counter(t.hex for t in board.tiles)
        by_hex = {t.hex: t for t in board.tiles}
        for step in steps:
            assert step.terrain is by_hex[step.hex].terrain
            assert step.varietal is by_hex[step.hex].varietal


def test_generated_steps_go_north_to_south_and_west_to_east():
    for _, _, _, board in generated_boards():
        steps = assembly_instructions(board)
        keys = [(s.hex.r, s.hex.q) for s in steps]
        assert keys == sorted(keys)
        assert [(s.row, s.position) for s in steps] == sorted((s.row, s.position) for s in steps)


def test_on_generated_boards_hex_1_is_the_river_and_names_the_river_above():
    for mode, players, seed, board in generated_boards():
        steps = assembly_instructions(board)
        firsts = [s for s in steps if s.position == 1]
        assert [s.row for s in firsts] == list(range(1, len(firsts) + 1))
        for step in firsts:
            assert step.terrain is Terrain.RIVER, (mode, players, seed)
            if step.row > 1:
                assert step.text.endswith(f"of row {step.row - 1}, hex 1"), (
                    mode,
                    players,
                    seed,
                    step.text,
                )


def test_vineyard_text_names_the_varietal():
    for _, _, _, board in generated_boards(seeds=range(1)):
        for step in assembly_instructions(board):
            prefix = f"Row {step.row}, hex {step.position}: {step.terrain.value}"
            if step.terrain is Terrain.VINEYARD:
                assert step.text.startswith(f"{prefix}, {step.varietal.display_name}")
            else:
                assert step.varietal is None
                assert step.text.startswith(prefix)


# --- Dependencies ----------------------------------------------------------


def test_assembly_imports_only_hex_and_model_from_acequias():
    source = Path(__file__).resolve().parent.parent.joinpath("acequias", "assembly.py")
    tree = ast.parse(source.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("acequias"):
                assert node.module in {"acequias.hex", "acequias.model"}
            else:
                assert node.module.split(".")[0] in {"__future__", "dataclasses"}
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("acequias")
