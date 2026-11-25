"""Rules v3 planting spots on hex vertices (#151): the vertex type, the board,
plant legality, watering, scoring, and JSON."""

from dataclasses import replace

import pytest

from acequias.board import generate_board, planting_spots
from acequias.config import (
    FLASH,
    NORMAL,
    RULES_V1,
    PlantingRules,
    VarietalRules,
    preset,
    with_overrides,
)
from acequias.flow import can_plant, plantable_spots, vertex_water, wet_canals
from acequias.hex import Direction, Hex, Vertex
from acequias.model import (
    Board,
    Floodgate,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    PlantedVineyard,
    Player,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import calculate_score
from acequias.setup import new_game
from acequias.sim import _preset_values
from server.schemas import (
    overrides_from_json,
    planted_from_json,
    planted_to_json,
    spots_to_json,
    vertex_from_json,
    vertex_to_json,
    watered_vineyard_to_json,
)

V3 = with_overrides(NORMAL, planting=PlantingRules.VERTICES)

# River on (0, 0); a row of empty hexes east of it, and a stone south.
RIVER = Hex(0, 0)
A, B, C, D = Hex(1, 0), Hex(2, 0), Hex(3, 0), Hex(4, 0)
TILES = (
    Tile(RIVER, Terrain.RIVER),
    Tile(A, Terrain.EMPTY),
    Tile(B, Terrain.EMPTY),
    Tile(C, Terrain.EMPTY),
    Tile(D, Terrain.EMPTY),
    Tile(Hex(1, 1), Terrain.STONE),
)
# A straight E-W line from the river: p1, p2, p1.
CANALS = (
    PlacedCanal(A, PieceKind.STRAIGHT, 0, "p1"),
    PlacedCanal(B, PieceKind.STRAIGHT, 0, "p2"),
    PlacedCanal(C, PieceKind.STRAIGHT, 0, "p1"),
)
NORTH_OF_A = A.vertex(2)  # touches only A among the canals
A_AND_B = A.vertex(1)  # touches A and B
EAST_OF_C = C.vertex(0)  # touches C and D


def board(planted=(), floodgates=()) -> Board:
    return Board(
        tiles=TILES,
        canals=CANALS,
        floodgates=floodgates,
        spots=planting_spots(TILES),
        planted=planted,
    )


def state(b: Board, debt=(0, 0)) -> GameState:
    return GameState(
        board=b,
        players=(Player("p1", 1, debt=debt[0]), Player("p2", 2, debt=debt[1])),
        mode=Mode.NORMAL,
        round=1,
        start_player="p1",
        current_player="p1",
        preset=V3,
    )


def vineyard(vertex, owner, varietal=Varietal.MALBEC) -> PlantedVineyard:
    return PlantedVineyard(vertex, owner, varietal)


# --- Vertex ------------------------------------------------------------------


def test_a_vertex_is_the_same_from_each_of_its_hexes():
    v = Hex(0, 0).vertex(0)
    assert v.hexes == (Hex(0, 0), Hex(0, 1), Hex(1, 0))
    for h in v.hexes:
        assert v in h.vertices()
    assert Vertex((Hex(1, 0), Hex(0, 1), Hex(0, 0))) == v
    assert len({v, Vertex((Hex(0, 1), Hex(1, 0), Hex(0, 0)))}) == 1


def test_vertices_sit_on_the_hex_corners():
    h = Hex(2, -1)
    for v, corner in zip(h.vertices(), h.corners(10.0)):
        assert v.to_pixel(10.0) == pytest.approx(corner)


def test_three_hexes_around_a_point_have_thirteen_vertices():
    trio = Hex(0, 0).vertex(3).hexes
    assert len({v for h in trio for v in h.vertices()}) == 13


@pytest.mark.parametrize(
    "hexes, error",
    [
        ((Hex(0, 0), Hex(1, 0)), TypeError),
        ((Hex(0, 0), Hex(1, 0), (2, 0)), TypeError),
        ((Hex(0, 0), Hex(1, 0), Hex(2, 0)), ValueError),
        ((Hex(0, 0), Hex(0, 0), Hex(1, 0)), ValueError),
    ],
)
def test_a_vertex_needs_three_mutually_adjacent_hexes(hexes, error):
    with pytest.raises(error):
        Vertex(hexes)


def test_hex_vertex_rejects_a_bad_corner():
    with pytest.raises(ValueError):
        Hex(0, 0).vertex(6)
    with pytest.raises(TypeError):
        Hex(0, 0).vertex(True)


# --- Preset and board ----------------------------------------------------------


def test_shipped_and_v1_presets_plant_on_hexes():
    for p in (NORMAL, FLASH, *RULES_V1.values()):
        assert p.planting is PlantingRules.HEXES
        assert "planting" not in _preset_values(p)
    assert _preset_values(V3)["planting"] == "vertices"


def test_vertex_planting_needs_roulette_rules():
    with pytest.raises(ValueError, match="roulette"):
        with_overrides(RULES_V1[Mode.NORMAL], planting=PlantingRules.VERTICES)
    assert V3.varietal_rules is VarietalRules.ROULETTE
    assert V3.vineyard_tiles_per_player == 0
    assert NORMAL.vineyard_tiles_per_player == NORMAL.vineyards_per_player


@pytest.mark.parametrize("players", [2, 3, 5])
def test_a_v3_board_has_no_vineyards_and_every_land_vertex_is_a_spot(players):
    b = generate_board(players, 11, Mode.NORMAL, preset=V3)
    assert not [t for t in b.tiles if t.terrain is Terrain.VINEYARD]
    land = {t.hex for t in b.tiles if t.terrain is not Terrain.RIVER}
    expected = {v for h in land for v in h.vertices()}
    assert set(b.spots) == expected
    assert list(b.spots) == sorted(b.spots)
    assert all(b.is_spot(v) for v in expected)
    # Edge vertices touch fewer than 3 tiles.
    assert {len(b.vertex_tiles(v)) for v in b.spots} >= {1, 2, 3}
    assert b == generate_board(players, 11, Mode.NORMAL, preset=V3)


def test_a_shipped_board_has_no_spots():
    b = generate_board(3, 11, Mode.NORMAL)
    assert b.spots == () and b.planted == ()


def test_new_game_under_v3():
    s = new_game(2, 5, Mode.NORMAL, preset=V3)
    assert s.board.spots and not s.board.planted


# --- Board and state checks ----------------------------------------------------


def test_one_vineyard_per_vertex():
    with pytest.raises(ValueError, match="two vineyards"):
        board((vineyard(A_AND_B, "p1"), vineyard(A_AND_B, "p2")))


def test_a_vineyard_needs_a_land_tile():
    in_river = Vertex((Hex(-1, 0), Hex(-1, 1), Hex(0, 0)))  # only the river tile
    with pytest.raises(ValueError, match="non-river"):
        board((vineyard(in_river, "p1"),))
    with pytest.raises(ValueError, match="non-river"):
        Board(tiles=TILES, spots=(in_river,))


def test_planted_is_kept_in_vertex_order_and_indexed():
    b = board((vineyard(EAST_OF_C, "p1"), vineyard(NORTH_OF_A, "p2")))
    assert [v.vertex for v in b.planted] == sorted([EAST_OF_C, NORTH_OF_A])
    assert b.planted_at(NORTH_OF_A).owner == "p2"
    assert b.planted_at(A_AND_B) is None
    assert b == board((vineyard(NORTH_OF_A, "p2"), vineyard(EAST_OF_C, "p1")))


def test_derive_matches_replace_for_planted():
    b = board()
    planted = (vineyard(A_AND_B, "p1"),)
    assert b._derive(planted=planted) == replace(b, planted=planted)
    assert b._derive(planted=planted).planted_at(A_AND_B) is not None


def test_state_checks_planting_rules():
    state(board((vineyard(A_AND_B, "p1"),)))  # valid
    with pytest.raises(ValueError, match="unknown player"):
        state(board((vineyard(A_AND_B, "p9"),)))
    with pytest.raises(ValueError, match="no planting spots"):
        replace(state(board()), preset=NORMAL)
    vineyard_tile = Board(tiles=(*TILES, Tile(Hex(5, 0), Terrain.VINEYARD)))
    with pytest.raises(ValueError, match="no vineyard tiles"):
        state(vineyard_tile)


# --- Plant legality --------------------------------------------------------------


def test_wet_canals():
    assert wet_canals(board()) == {A, B, C}
    gated = board(floodgates=(Floodgate(A, Direction.E),))
    assert wet_canals(gated) == {A}


def test_plant_next_to_own_watered_canal_only():
    b = board()
    assert can_plant(b, "p1", NORTH_OF_A)
    assert can_plant(b, "p1", EAST_OF_C)
    assert not can_plant(b, "p2", NORTH_OF_A)  # p1's canal
    assert can_plant(b, "p2", A_AND_B)  # touches p2's canal B
    far = D.vertex(0)  # touches no canal
    assert not can_plant(b, "p1", far)


def test_no_planting_next_to_a_dry_canal_or_on_a_taken_spot():
    gated = board(floodgates=(Floodgate(A, Direction.E),))
    assert not can_plant(gated, "p1", EAST_OF_C)  # C is dry
    assert can_plant(gated, "p1", NORTH_OF_A)
    taken = board((vineyard(NORTH_OF_A, "p2"),))
    assert not can_plant(taken, "p1", NORTH_OF_A)


def test_plantable_spots_are_the_free_vertices_of_own_wet_canals():
    b = board((vineyard(NORTH_OF_A, "p2"),))
    spots = plantable_spots(b, "p1")
    expected = {v for h in (A, C) for v in h.vertices()} - {NORTH_OF_A}
    assert set(spots) == expected
    assert list(spots) == sorted(spots)
    assert all(can_plant(b, "p1", v) for v in spots)
    assert set(plantable_spots(b, "p2")) == set(B.vertices())


def test_legality_ignores_the_spot_list():
    # Derived from canals alone, so it also works on a board without spots.
    b = Board(tiles=TILES, canals=CANALS)
    assert can_plant(b, "p1", NORTH_OF_A)
    assert set(plantable_spots(b, "p1")) == set(plantable_spots(board(), "p1"))


# --- Watering and scoring ----------------------------------------------------------


def test_vertex_water_takes_the_cheapest_touching_canal_path():
    b = board((vineyard(A_AND_B, "p2"), vineyard(EAST_OF_C, "p1"), vineyard(D.vertex(0), "p1")))
    paths = vertex_water(b)
    assert set(paths) == {A_AND_B, EAST_OF_C}  # D's vertex touches no canal: dry
    # p2 at A|B: both paths cross p1's A; the shortest ends at A.
    assert [c.hex for c in paths[A_AND_B].canals] == [A]
    assert [c.hex for c in paths[EAST_OF_C].canals] == [A, B, C]
    assert paths[EAST_OF_C].owners == {"p1", "p2"}


def test_vertex_water_prefers_fewer_rivals():
    # p1 at a vertex touching A (p1) and B (p2): the path ending at A has no rival.
    b = board((vineyard(A_AND_B, "p1"),))
    assert [c.hex for c in vertex_water(b)[A_AND_B].canals] == [A]


def test_a_gated_canal_leaves_its_vineyard_dry():
    b = board((vineyard(EAST_OF_C, "p1"),), floodgates=(Floodgate(B, Direction.W),))
    assert vertex_water(b) == {}
    assert calculate_score(state(b))["p1"].vineyards == 0


def test_scoring_vertex_vineyards():
    planted = (
        vineyard(NORTH_OF_A, "p1", Varietal.MALBEC),
        vineyard(A.vertex(3), "p1", Varietal.BONARDA),
        vineyard(EAST_OF_C, "p1", Varietal.SYRAH),  # pays p2
        vineyard(A_AND_B, "p2", Varietal.MERLOT),  # pays p1
        vineyard(D.vertex(0), "p2", Varietal.MALBEC),  # dry
    )
    scores = calculate_score(state(board(planted), debt=(2, 1)))
    p1, p2 = scores["p1"], scores["p2"]
    assert p1.vineyards == 6 + 7 + 6
    assert p1.bodegas == 1 and p1.bodega == 6
    assert p1.rights_paid == 3 and p1.rights_collected == 3
    assert p1.total == 19 + 6 - 3 + 3 - 2
    assert p1.watered == 3
    assert [v.vertex for v in p1.watered_vineyards] == sorted(
        [NORTH_OF_A, A.vertex(3), EAST_OF_C]
    )
    assert all(v.hex is None for v in p1.watered_vineyards)
    assert p2.vineyards == 6 and p2.watered == 1
    assert p2.rights_paid == 3 and p2.rights_collected == 3
    assert p2.total == 6 - 3 + 3 - 1
    assert p1.watered_vineyards[-1].pays == ("p2",)


# --- JSON ------------------------------------------------------------------------


def test_vertex_and_planted_json_round_trip():
    assert vertex_to_json(A_AND_B) == [[1, 0], [2, -1], [2, 0]]
    assert vertex_from_json(vertex_to_json(A_AND_B)) == A_AND_B
    b = board((vineyard(A_AND_B, "p2", Varietal.TORRONTES),))
    data = planted_to_json(b)
    assert data == [{"hexes": [[1, 0], [2, -1], [2, 0]], "player": "p2", "varietal": "torrontes"}]
    assert tuple(planted_from_json(item) for item in data) == b.planted
    spots = spots_to_json(b)
    assert len(spots) == len(b.spots)
    assert tuple(vertex_from_json(s) for s in spots) == b.spots


def test_bad_vertex_json():
    with pytest.raises(TypeError):
        vertex_from_json("1,0")
    with pytest.raises(TypeError):
        vertex_from_json([[0, 0], [1, 0]])
    with pytest.raises(ValueError):
        vertex_from_json([[0, 0], [1], [2, 0]])
    with pytest.raises(ValueError):
        planted_from_json({"hexes": [[1, 0], [2, -1], [2, 0]], "player": "p1", "varietal": None})


def test_watered_vertex_vineyard_json():
    b = board((vineyard(NORTH_OF_A, "p1"),))
    (watered,) = calculate_score(state(b))["p1"].watered_vineyards
    data = watered_vineyard_to_json(watered)
    assert data["hexes"] == vertex_to_json(NORTH_OF_A)
    assert "q" not in data and data["pays"] == []


def test_planting_override_from_json():
    changes = overrides_from_json({"planting": "vertices"})
    assert with_overrides(preset(Mode.NORMAL), **changes) == V3
    with pytest.raises(ValueError):
        overrides_from_json({"planting": "edges"})
