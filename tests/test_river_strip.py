"""Rules v3 open board (#154): the river strip, its unbounded table, the bag
size option, JSON, and the tune.py sweep."""

import importlib.util
import random
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from acequias.board import RIVER_BEND, generate_board, river_strip
from acequias.config import (
    FLASH,
    NORMAL,
    RIVER_HEXES_PER_SEGMENT,
    BoardShape,
    PlantingRules,
    with_overrides,
)
from acequias.flow import can_plant, plantable_spots, vertex_water
from acequias.hex import Hex
from acequias.model import (
    ActionsLeft,
    Board,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    PlantedVineyard,
    Player,
    RiverStrip,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import calculate_score
from acequias.setup import new_game
from acequias.sim import SimRules, _preset, _preset_values, simulate_game
from acequias.turn import PlaceCanal, _canal_candidates, _connecting_dirs, apply, legal_actions
from server.schemas import overrides_from_json, strip_from_json, strip_to_json

BAGS = {2: 30, 3: 45, 4: 60, 5: 75}
V3 = with_overrides(NORMAL, planting=PlantingRules.VERTICES)
STRIP = with_overrides(V3, board_shape=BoardShape.RIVER_STRIP, bag_size=BAGS)


def x_of(h: Hex) -> Fraction:
    """A hex's column in hex widths (``Hex.to_pixel`` x over the hex width)."""
    return h.q + Fraction(h.r, 2)


# --- The strip ------------------------------------------------------------------


@pytest.mark.parametrize("players", [2, 3, 4, 5])
@pytest.mark.parametrize("n", [4, 5, 6])
def test_strip_has_a_base_segment_and_one_per_extra_player(players, n):
    strip = river_strip(players, n)
    assert len(strip.segments) == players - 1
    assert all(len(seg) == n for seg in strip.segments)
    river = strip.river
    assert [h.r for h in river] == list(range((players - 1) * n))
    assert all(a.distance(b) == 1 for a, b in zip(river, river[1:]))


def test_two_player_strip_is_a_slight_inward_crescent():
    river = river_strip(2, 5).river
    assert river == (Hex(1, 0), Hex(0, 1), Hex(-1, 2), Hex(-1, 3), Hex(-1, 4))
    assert [x_of(h) for h in river] == [1, Fraction(1, 2), 0, Fraction(1, 2), 1]


@pytest.mark.parametrize("players", [2, 3, 4, 5])
def test_ends_bend_toward_the_table_and_the_bend_is_bounded(players):
    xs = [x_of(h) for h in river_strip(players, 5).river]
    middle = xs[len(xs) // 2]
    assert xs[0] >= middle + Fraction(1, 2) and xs[-1] >= middle
    assert max(xs) - min(xs) <= RIVER_BEND + Fraction(1, 2)


def test_bend_flattens_as_players_are_added():
    # The same end-to-middle offset over a longer river: less bend per row.
    def per_row(players):
        river = river_strip(players, 5).river
        return (x_of(river[0]) - min(x_of(h) for h in river)) / len(river)

    slopes = [per_row(p) for p in (2, 3, 4, 5)]
    assert slopes == sorted(slopes, reverse=True) and slopes[0] > slopes[-1]


def test_strip_checks_its_input():
    with pytest.raises(ValueError):
        river_strip(1, 5)
    with pytest.raises(ValueError):
        river_strip(2, 0)
    with pytest.raises(TypeError):
        river_strip(2, 5.0)
    with pytest.raises(ValueError, match="row"):
        RiverStrip(((Hex(0, 1),),))
    with pytest.raises(ValueError, match="touch"):
        RiverStrip(((Hex(0, 0), Hex(3, 1)),))
    with pytest.raises(ValueError):
        RiverStrip(())


def test_land_is_every_hex_east_of_the_river_on_its_rows():
    strip = river_strip(2, 5)
    assert strip.is_land(Hex(2, 0)) and strip.is_land(Hex(10_000, 0))
    assert strip.is_land(Hex(0, 4)) and strip.is_land(Hex(10_000, 4))
    assert not strip.is_land(Hex(1, 0))  # the river
    assert not strip.is_land(Hex(0, 0))  # the mountain, west of the river
    assert not strip.is_land(Hex(5, -1)) and not strip.is_land(Hex(5, 5))  # off the strip's rows
    shore = strip.shore()
    assert shore == tuple(sorted(shore))
    assert all(strip.is_land(h) and any(n in strip.river for n in h.neighbors()) for h in shore)


# --- Preset ---------------------------------------------------------------------


def test_shipped_presets_keep_the_field_board():
    for p in (NORMAL, FLASH):
        assert p.board_shape is BoardShape.FIELD
        assert p.river_hexes_per_segment == RIVER_HEXES_PER_SEGMENT == 5
        assert dict(p.bag_size) == {}


def test_river_strip_needs_vertex_planting_and_a_bag_per_player_count():
    with pytest.raises(ValueError, match="vertex planting"):
        with_overrides(NORMAL, board_shape=BoardShape.RIVER_STRIP, bag_size=BAGS)
    with pytest.raises(ValueError, match="bag_size"):
        with_overrides(V3, board_shape=BoardShape.RIVER_STRIP, bag_size={2: 30})
    with pytest.raises(ValueError, match="bag_size"):
        with_overrides(FLASH, bag_size={4: 30})  # Flash is for 2 or 3 players
    with pytest.raises(ValueError):
        with_overrides(NORMAL, bag_size={2: 0})
    with pytest.raises(ValueError):
        with_overrides(STRIP, river_hexes_per_segment=0)
    with pytest.raises(TypeError):
        with_overrides(NORMAL, board_shape="river_strip")
    assert list(with_overrides(NORMAL, bag_size={5: 9, 2: 7}).bag_size) == [2, 5]


# --- Board and setup --------------------------------------------------------------


@pytest.mark.parametrize("players", [2, 3, 4, 5])
def test_generate_board_gives_the_strip_alone(players):
    b = generate_board(players, 7, Mode.NORMAL, preset=STRIP)
    assert b.strip == river_strip(players, 5)
    assert b.tiles == tuple(sorted((Tile(h, Terrain.RIVER) for h in b.strip.river), key=lambda t: t.hex))
    assert b.spots == ()
    assert generate_board(players, 8, Mode.NORMAL, preset=STRIP) == b  # no randomness


def test_open_board_has_empty_tiles_everywhere_east():
    b = generate_board(2, 1, Mode.NORMAL, preset=STRIP)
    assert b.tile_at(Hex(500, 2)) == Tile(Hex(500, 2), Terrain.EMPTY)
    assert b.tile_at(Hex(-1, 2)).terrain is Terrain.RIVER
    assert b.tile_at(Hex(-2, 2)) is None and b.tile_at(Hex(3, 9)) is None
    far = Hex(40, 1)
    b2 = Board(tiles=b.tiles, strip=b.strip, canals=(PlacedCanal(far, PieceKind.STRAIGHT, 0, "p1"),))
    assert b2.canal_at(far) is not None
    with pytest.raises(ValueError, match="no tile"):
        Board(tiles=b.tiles, strip=b.strip, canals=(PlacedCanal(Hex(-3, 2), PieceKind.STRAIGHT, 0, "p1"),))
    with pytest.raises(ValueError, match="exactly its river"):
        Board(tiles=b.tiles + (Tile(Hex(5, 1), Terrain.STONE),), strip=b.strip)


@pytest.mark.parametrize("players", [2, 5])
def test_bag_size_sets_the_bag(players):
    s = new_game(players, 3, Mode.NORMAL, preset=STRIP)
    assert len(s.market) + len(s.bag) == BAGS[players]
    # bag_size works on the field board too; a count it does not list keeps the board's capacity.
    field = new_game(players, 3, Mode.NORMAL, preset=with_overrides(NORMAL, bag_size={players: 11}))
    assert len(field.market) + len(field.bag) == 11
    other = new_game(3, 3, Mode.NORMAL, preset=with_overrides(NORMAL, bag_size={2: 11}))
    assert len(other.market) + len(other.bag) == len(new_game(3, 3, Mode.NORMAL).bag) + 4


def test_a_strip_board_needs_vertex_planting():
    b = generate_board(2, 1, Mode.NORMAL, preset=STRIP)
    with pytest.raises(ValueError, match="vertex planting"):
        GameState(board=b, players=(Player("p1", 1), Player("p2", 2)), mode=Mode.NORMAL,
                  round=1, start_player="p1", current_player="p1", market=(), preset=NORMAL)


# --- Placement on the open table -------------------------------------------------------


def _state(b: Board) -> GameState:
    return GameState(
        board=b, players=(Player("p1", 1), Player("p2", 2)), mode=Mode.NORMAL, round=1,
        start_player="p1", current_player="p1", market=(PieceKind.STRAIGHT,) * 4, preset=STRIP,
        actions_left=ActionsLeft(1, 1),
    )


def _chain(strip: RiverStrip, row: int, length: int, owners=("p1",)) -> tuple[PlacedCanal, ...]:
    """Straight E-W canals from the river eastward along ``row``, owners in turn."""
    start = next(h for h in strip.river if h.r == row)
    return tuple(
        PlacedCanal(Hex(start.q + k, row), PieceKind.STRAIGHT, 0, owners[(k - 1) % len(owners)])
        for k in range(1, length + 1)
    )


def _brute_candidates(b: Board, reach: int) -> set[Hex]:
    """Every free land hex of a bounded window where some opening connects."""
    return {
        h
        for r in range(len(b.strip.river))
        for q in range(-reach, reach)
        if b.strip.is_land(h := Hex(q, r)) and not b.canal_at(h) and _connecting_dirs(b, h)
    }


def test_first_canals_go_only_on_the_shore():
    s = _state(generate_board(2, 1, Mode.NORMAL, preset=STRIP))
    hexes = {a.hex for a in legal_actions(s, "p1") if isinstance(a, PlaceCanal)}
    assert hexes and hexes <= set(s.board.strip.shore())


def test_placements_follow_the_canals_far_east():
    b = generate_board(2, 1, Mode.NORMAL, preset=STRIP)
    chain = _chain(b.strip, 2, 30)
    s = _state(Board(tiles=b.tiles, strip=b.strip, canals=chain))
    end = chain[-1].hex
    east = Hex(end.q + 1, end.r)
    legal = [a for a in legal_actions(s, "p1") if isinstance(a, PlaceCanal)]
    assert any(a.hex == east for a in legal)
    after = apply(s, "p1", next(a for a in legal if a.hex == east), random.Random(0))
    assert after.board.canal_at(east).owner == "p1"
    # The derived candidates are exactly what a brute-force scan finds.
    brute = _brute_candidates(s.board, 40)
    derived = _canal_candidates(s.board)
    assert {h for h in derived if not s.board.canal_at(h) and _connecting_dirs(s.board, h)} == brute
    assert {a.hex for a in legal} == brute


def test_planting_and_split_scoring_work_on_the_open_table():
    b = generate_board(3, 1, Mode.NORMAL, preset=STRIP)
    chain = _chain(b.strip, 4, 25, owners=("p2",) * 24 + ("p1",))
    board = Board(tiles=b.tiles, strip=b.strip, canals=chain)
    end = chain[-1].hex
    spot = end.vertex(0)
    assert can_plant(board, "p1", spot) and spot in plantable_spots(board, "p1")
    planted = Board(tiles=b.tiles, strip=b.strip, canals=chain,
                    planted=(PlantedVineyard(spot, "p1", Varietal.MALBEC),))
    assert len(vertex_water(planted)[spot].canals) == 25
    s = GameState(board=planted, players=(Player("p1", 1), Player("p2", 2)), mode=Mode.NORMAL,
                  round=1, start_player="p1", current_player="p1", market=(), preset=STRIP)
    scores = calculate_score(s)
    # Split scoring (#160): p1's watered third of the Malbec; no water rights.
    assert scores["p1"].vineyards == STRIP.varietal_points[Varietal.MALBEC] // 3
    assert scores["p1"].rights_paid == scores["p2"].rights_collected == 0


@pytest.mark.parametrize("players", [2, 5])
def test_random_games_run_on_the_strip_and_end_when_the_bag_runs_out(players):
    rules = SimRules(Mode.NORMAL, players, ("random",) * players, {
        "planting": PlantingRules.VERTICES, "board_shape": BoardShape.RIVER_STRIP,
        "bag_size": {n: 3 * n for n in (2, 3, 4, 5)}, "river_hexes_per_segment": 4,
    })
    result = simulate_game(rules, 3, 1)
    assert result == simulate_game(rules, 3, 1)
    assert result.actions_per_game["canal"] <= 3 * players


# --- JSON ---------------------------------------------------------------------------


def test_strip_json_round_trips():
    b = generate_board(3, 1, Mode.NORMAL, preset=STRIP)
    data = strip_to_json(b)
    assert data == {"segments": [[[h.q, h.r] for h in seg] for seg in b.strip.segments]}
    assert len(data["segments"]) == 2 and len(data["segments"][0]) == 5
    assert strip_from_json(data) == b
    assert strip_to_json(generate_board(2, 1, Mode.NORMAL)) is None
    with pytest.raises(ValueError):
        strip_from_json({"segments": [[[0, 0]]], "extra": 1})


def test_new_options_in_overrides_and_sim_json():
    changes = overrides_from_json(
        {"board_shape": "river_strip", "bag_size": {"2": 30}, "river_hexes_per_segment": 6}
    )
    assert changes == {"board_shape": BoardShape.RIVER_STRIP, "bag_size": {2: 30},
                       "river_hexes_per_segment": 6}
    with pytest.raises(ValueError):
        overrides_from_json({"board_shape": "round"})
    values = _preset_values(with_overrides(STRIP, river_hexes_per_segment=6))
    assert values["board_shape"] == "river_strip" and values["river_hexes_per_segment"] == 6
    assert dict(values["bag_size"]) == BAGS
    shipped = _preset_values(NORMAL)
    assert not {"board_shape", "river_hexes_per_segment", "bag_size"} & set(shipped)


# --- tune.py ---------------------------------------------------------------------------


def _tune():
    path = Path(__file__).resolve().parent.parent / "scripts" / "tune.py"
    spec = importlib.util.spec_from_file_location("tune_strip", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["tune_strip"] = module
    spec.loader.exec_module(module)
    return module


def test_tune_strip_sweep_grid_builds_valid_presets():
    tune = _tune()
    (sweep,) = tune.strip_sweeps()
    assert sweep.name == "strip" and "strip" in tune.SWEEP_NAMES
    for mode in Mode:
        candidates = sweep.candidates[mode]
        assert len(candidates) == 9  # river hexes 4/5/6 x bag 12/16/20 per player
        for label, changes in candidates:
            job = tune.Job(label, mode, 2, "score_aware", {**sweep.base[mode], **changes}, 1, 1)
            p = _preset(tune.rules_of(job))
            assert p.board_shape is BoardShape.RIVER_STRIP
            assert p.river_hexes_per_segment in (4, 5, 6)
            assert p.bag_size[2] in (24, 32, 40)
    (custom,) = tune.strip_sweeps((5,), (10,))
    assert [label for label, _ in custom.candidates[Mode.NORMAL]] == [
        "5 river hexes/segment, bag 10/player"
    ]
