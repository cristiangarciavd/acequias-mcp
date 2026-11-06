import ast
import dataclasses
from pathlib import Path

import pytest

from acequias.config import FLASH, NORMAL, with_overrides
from acequias.hex import Direction, Hex
from acequias.model import (
    Board,
    Floodgate,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    Player,
    Terrain,
    Tile,
    Varietal,
)

E, NE, NW, W, SW, SE = (
    Direction.E,
    Direction.NE,
    Direction.NW,
    Direction.W,
    Direction.SW,
    Direction.SE,
)
CANAL_SHAPES = [k for k in PieceKind if k is not PieceKind.FLOODGATE]
A = Hex(0, 0)
B = A.neighbor(E)


def empty(h):
    return Tile(h, Terrain.EMPTY)


def vineyard(h, varietal=Varietal.MALBEC):
    return Tile(h, Terrain.VINEYARD, varietal)


def players(n=2):
    return tuple(Player(f"p{i}", i) for i in range(n))


def state(**overrides):
    values = dict(
        board=Board(),
        players=players(),
        mode=Mode.NORMAL,
        round=1,
        start_player="p0",
        current_player="p0",
        market=(PieceKind.STRAIGHT, PieceKind.FLOODGATE),
        bag=(PieceKind.CLAW,),
    )
    values.update(overrides)
    return GameState(**values)


# --- Enums -----------------------------------------------------------------


def test_terrain_has_four_members():
    assert {t.name for t in Terrain} == {"RIVER", "VINEYARD", "STONE", "EMPTY"}


def test_varietal_points():
    assert len(Varietal) == 3
    assert Varietal.MALBEC.points == 3
    assert Varietal.BONARDA.points == 2
    assert Varietal.TORRONTES.points == 1


def test_varietal_identifiers_are_ascii_and_display_name_keeps_accent():
    for v in Varietal:
        assert v.name.isascii()
    assert Varietal.TORRONTES.display_name == "Torrontés"
    assert Varietal.MALBEC.display_name == "Malbec"
    assert Varietal.BONARDA.display_name == "Bonarda"


def test_piece_kind_has_seven_members():
    assert {k.name for k in PieceKind} == {
        "STRAIGHT",
        "GENTLE_CURVE",
        "SHARP_CURVE",
        "SYMMETRIC_Y",
        "T_BRANCH",
        "CLAW",
        "FLOODGATE",
    }


def test_mode_has_two_members():
    assert {m.name for m in Mode} == {"NORMAL", "FLASH"}


# --- Canal shapes ----------------------------------------------------------

README_EDGES = {
    PieceKind.STRAIGHT: {E, W},
    PieceKind.GENTLE_CURVE: {E, NW},
    PieceKind.SHARP_CURVE: {E, NE},
    PieceKind.SYMMETRIC_Y: {E, NW, SW},
    PieceKind.T_BRANCH: {E, W, NE},
    PieceKind.CLAW: {E, NE, NW},
}


@pytest.mark.parametrize("kind", CANAL_SHAPES)
def test_rotation_zero_matches_readme(kind):
    edges = kind.edges(0)
    assert isinstance(edges, frozenset)
    assert all(isinstance(d, Direction) for d in edges)
    assert edges == README_EDGES[kind]


def test_readme_table_matches_test_table():
    text = Path(__file__).resolve().parent.parent.joinpath("README.md").read_text("utf-8")
    rows = {
        "Straight": PieceKind.STRAIGHT,
        "Gentle curve": PieceKind.GENTLE_CURVE,
        "Sharp curve": PieceKind.SHARP_CURVE,
        "Symmetric Y": PieceKind.SYMMETRIC_Y,
        "T branch": PieceKind.T_BRANCH,
        "Claw": PieceKind.CLAW,
    }
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 2 and cells[0] in rows:
            names = cells[1].split("(")[0].replace(" ", "").split(",")
            assert {Direction[n] for n in names} == README_EDGES[rows.pop(cells[0])]
    assert rows == {}


def test_shapes_have_the_described_geometry():
    def gap(edges):
        a, b = (list(Direction).index(d) for d in edges)
        return min((a - b) % 6, (b - a) % 6)

    assert gap(PieceKind.STRAIGHT.edges(0)) == 3
    assert gap(PieceKind.GENTLE_CURVE.edges(0)) == 2
    assert gap(PieceKind.SHARP_CURVE.edges(0)) == 1


@pytest.mark.parametrize("kind", CANAL_SHAPES)
@pytest.mark.parametrize("rotation", range(6))
def test_each_rotation_turns_rotation_zero(kind, rotation):
    assert kind.edges(rotation) == frozenset(d.rotated(rotation) for d in kind.edges(0))


def test_rotation_step_is_counterclockwise():
    assert PieceKind.SHARP_CURVE.edges(1) == {NE, NW}


def test_symmetric_rotations_are_equal():
    assert PieceKind.STRAIGHT.edges(3) == PieceKind.STRAIGHT.edges(0)
    y = PieceKind.SYMMETRIC_Y
    assert y.edges(0) == y.edges(2) == y.edges(4)
    assert y.edges(1) != y.edges(0)


@pytest.mark.parametrize("rotation", [-1, 6, 7, 100])
def test_rotation_out_of_range_is_rejected(rotation):
    with pytest.raises(ValueError):
        PieceKind.STRAIGHT.edges(rotation)
    with pytest.raises(ValueError):
        PlacedCanal(A, PieceKind.STRAIGHT, rotation, "p0")


@pytest.mark.parametrize("rotation", [True, False, 1.0, "1", None])
def test_rotation_not_an_int_is_rejected(rotation):
    with pytest.raises(TypeError):
        PieceKind.STRAIGHT.edges(rotation)
    with pytest.raises(TypeError):
        PlacedCanal(A, PieceKind.STRAIGHT, rotation, "p0")


def test_floodgate_kind_has_no_edges():
    with pytest.raises(ValueError):
        PieceKind.FLOODGATE.edges(0)


# --- Floodgate -------------------------------------------------------------


def test_floodgate_records_hex_and_direction_only():
    gate = Floodgate(A, E)
    assert gate.hex == A
    assert gate.direction is E
    assert [f.name for f in dataclasses.fields(Floodgate)] == ["hex", "direction"]


def test_floodgate_is_the_same_from_either_side():
    assert Floodgate(A, E) == Floodgate(B, W)
    assert hash(Floodgate(A, E)) == hash(Floodgate(B, W))
    assert len({Floodgate(A, E), Floodgate(B, W)}) == 1
    assert Floodgate(A, E) != Floodgate(A, W)
    assert Floodgate(A, E) != Floodgate(B, E)


def test_board_rejects_floodgate_on_hex_without_canal():
    with pytest.raises(ValueError):
        Board(tiles=(empty(A),), floodgates=(Floodgate(A, E),))


def test_board_rejects_floodgate_on_edge_the_canal_does_not_open():
    canal = PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0")
    with pytest.raises(ValueError):
        Board(tiles=(empty(A),), canals=(canal,), floodgates=(Floodgate(A, NE),))


def test_board_rejects_two_floodgates_on_the_same_edge():
    canal = PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0")
    with pytest.raises(ValueError):
        Board(
            tiles=(empty(A),),
            canals=(canal,),
            floodgates=(Floodgate(A, E), Floodgate(A, E)),
        )


def test_board_rejects_two_floodgates_on_the_same_edge_from_both_sides():
    tiles = (empty(A), empty(B))
    canals = (
        PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0"),
        PlacedCanal(B, PieceKind.STRAIGHT, 0, "p1"),
    )
    with pytest.raises(ValueError):
        Board(tiles=tiles, canals=canals, floodgates=(Floodgate(A, E), Floodgate(B, W)))


def test_floodgate_accepted_on_any_open_edge():
    # A straight canal at A opens E and W: W faces the river, E faces a
    # canal whose side toward A is closed. A sharp curve at C faces a vineyard.
    river = A.neighbor(W)
    c = Hex(0, 2)
    vine = c.neighbor(E)
    board = Board(
        tiles=(
            Tile(river, Terrain.RIVER),
            empty(A),
            empty(B),
            empty(c),
            vineyard(vine),
        ),
        canals=(
            PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0"),
            PlacedCanal(B, PieceKind.SHARP_CURVE, 1, "p1"),  # opens NE, NW
            PlacedCanal(c, PieceKind.SHARP_CURVE, 0, "p0"),  # opens E, NE
        ),
        floodgates=(Floodgate(A, W), Floodgate(A, E), Floodgate(c, E)),
    )
    assert board.has_floodgate(A, W)
    assert board.has_floodgate(river, E)
    assert board.has_floodgate(B, W)
    assert board.has_floodgate(vine, W)


# --- Tiles and canals ------------------------------------------------------


def test_tile_records_hex_and_terrain():
    tile = Tile(A, Terrain.STONE)
    assert tile.hex == A
    assert tile.terrain is Terrain.STONE
    assert tile.varietal is None


def test_vineyard_tile_needs_a_varietal():
    assert vineyard(A, Varietal.BONARDA).varietal is Varietal.BONARDA
    with pytest.raises(ValueError):
        Tile(A, Terrain.VINEYARD)


@pytest.mark.parametrize("terrain", [Terrain.RIVER, Terrain.STONE, Terrain.EMPTY])
def test_non_vineyard_tile_cannot_have_a_varietal(terrain):
    with pytest.raises(ValueError):
        Tile(A, terrain, Varietal.MALBEC)


def test_placed_canal_records_its_fields():
    canal = PlacedCanal(A, PieceKind.CLAW, 2, "p1")
    assert (canal.hex, canal.kind, canal.rotation, canal.owner) == (
        A,
        PieceKind.CLAW,
        2,
        "p1",
    )
    assert canal.edges == PieceKind.CLAW.edges(2)


def test_placed_canal_cannot_be_a_floodgate():
    with pytest.raises(ValueError):
        PlacedCanal(A, PieceKind.FLOODGATE, 0, "p0")


def test_vineyard_starts_unclaimed():
    board = Board(tiles=(vineyard(A),))
    assert board.claimant(A) is None
    claimed = Board(tiles=(vineyard(A),), claims=((A, "p0"),))
    assert claimed.claimant(A) == "p0"


def test_board_rejects_two_tiles_on_same_hex():
    with pytest.raises(ValueError):
        Board(tiles=(empty(A), Tile(A, Terrain.STONE)))


def test_board_rejects_two_canals_on_same_hex():
    canals = (
        PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0"),
        PlacedCanal(A, PieceKind.CLAW, 0, "p1"),
    )
    with pytest.raises(ValueError):
        Board(tiles=(empty(A),), canals=canals)


def test_board_rejects_canal_without_tile():
    with pytest.raises(ValueError):
        Board(canals=(PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0"),))


@pytest.mark.parametrize(
    "tile", [Tile(A, Terrain.RIVER), Tile(A, Terrain.STONE), vineyard(A)]
)
def test_board_rejects_canal_on_non_empty_terrain(tile):
    with pytest.raises(ValueError):
        Board(tiles=(tile,), canals=(PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0"),))


@pytest.mark.parametrize("tiles", [(empty(A),), (Tile(A, Terrain.RIVER),), ()])
def test_board_rejects_claim_on_non_vineyard(tiles):
    with pytest.raises(ValueError):
        Board(tiles=tiles, claims=((A, "p0"),))


def test_board_rejects_two_claims_on_same_hex():
    with pytest.raises(ValueError):
        Board(tiles=(vineyard(A),), claims=((A, "p0"), (A, "p1")))


def test_board_lookups():
    vine = Hex(3, 3)
    canal = PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0")
    board = Board(
        tiles=(empty(A), empty(B), vineyard(vine)),
        canals=(canal,),
        floodgates=(Floodgate(A, E),),
        claims=((vine, "p1"),),
    )
    assert board.tile_at(A) == empty(A)
    assert board.tile_at(Hex(9, 9)) is None
    assert board.canal_at(A) == canal
    assert board.canal_at(B) is None
    assert board.claimant(vine) == "p1"
    assert board.claimant(A) is None
    assert board.claimant(Hex(9, 9)) is None
    assert board.floodgate_at(A, E) == Floodgate(A, E)
    assert board.floodgate_at(B, W) == Floodgate(A, E)
    assert board.has_floodgate(B, W)
    assert board.floodgate_at(A, W) is None
    assert not board.has_floodgate(A, NE)


def test_board_equality_ignores_input_order():
    one = Board(tiles=(empty(A), empty(B)))
    two = Board(tiles=[empty(B), empty(A)])
    assert one == two
    assert hash(one) == hash(two)


# --- Players and game state ------------------------------------------------


def test_player_fields_and_default_debt():
    p = Player("ana", 2)
    assert (p.id, p.seat, p.debt) == ("ana", 2, 0)
    assert Player("ana", 2, 5).debt == 5


def test_negative_debt_is_rejected():
    with pytest.raises(ValueError):
        Player("ana", 0, -1)


def test_game_state_holds_its_fields():
    board = Board(tiles=(empty(A),))
    s = state(board=board, players=players(3), round=4, start_player="p1", current_player="p2")
    assert s.board is board
    assert s.players == players(3)
    assert s.mode is Mode.NORMAL
    assert s.round == 4
    assert s.start_player == "p1"
    assert s.current_player == "p2"
    assert s.market == (PieceKind.STRAIGHT, PieceKind.FLOODGATE)
    assert s.bag == (PieceKind.CLAW,)
    assert s.player("p1") == Player("p1", 1)
    assert s.player("nobody") is None


@pytest.mark.parametrize("n", [2, 5])
def test_game_state_accepts_two_to_five_players(n):
    assert len(state(players=players(n)).players) == n


@pytest.mark.parametrize("n", [0, 1, 6])
def test_game_state_rejects_wrong_player_count(n):
    with pytest.raises(ValueError):
        state(players=players(n))


def test_game_state_rejects_duplicate_player_ids():
    with pytest.raises(ValueError):
        state(players=(Player("p0", 0), Player("p0", 1)))


def test_game_state_rejects_duplicate_seats():
    with pytest.raises(ValueError):
        state(players=(Player("p0", 0), Player("p1", 0)))


@pytest.mark.parametrize("round", [0, -1])
def test_game_state_rejects_round_below_one(round):
    with pytest.raises(ValueError):
        state(round=round)


def test_game_state_rejects_unknown_start_or_current_player():
    with pytest.raises(ValueError):
        state(start_player="x")
    with pytest.raises(ValueError):
        state(current_player="x")


def test_game_state_rejects_unknown_canal_owner():
    board = Board(tiles=(empty(A),), canals=(PlacedCanal(A, PieceKind.STRAIGHT, 0, "x"),))
    with pytest.raises(ValueError):
        state(board=board)


def test_game_state_rejects_unknown_claim_owner():
    board = Board(tiles=(vineyard(A),), claims=((A, "x"),))
    with pytest.raises(ValueError):
        state(board=board)


def test_game_state_preset_defaults_to_none():
    assert state().preset is None


def test_game_state_keeps_its_preset():
    assert state(preset=NORMAL).preset is NORMAL


def test_game_state_rejects_a_preset_for_another_mode():
    with pytest.raises(ValueError):
        state(mode=Mode.NORMAL, preset=FLASH)
    with pytest.raises(ValueError):
        state(mode=Mode.FLASH, preset=NORMAL)


def test_game_state_rejects_a_non_preset():
    with pytest.raises(TypeError):
        state(preset="normal")


def test_game_state_preset_is_in_equality_but_not_in_the_hash():
    tuned = with_overrides(NORMAL, bodega_points=9)
    assert state(preset=NORMAL) == state(preset=NORMAL)
    assert state(preset=NORMAL) == state(preset=with_overrides(NORMAL))
    assert state(preset=NORMAL) != state(preset=tuned)
    assert state(preset=NORMAL) != state()
    assert hash(state(preset=NORMAL)) == hash(state(preset=tuned)) == hash(state())


# --- Immutability ----------------------------------------------------------


@pytest.mark.parametrize(
    "value, name",
    [
        (Tile(A, Terrain.EMPTY), "terrain"),
        (PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0"), "rotation"),
        (Floodgate(A, E), "direction"),
        (Board(), "tiles"),
        (Player("p0", 0), "debt"),
        (state(), "round"),
    ],
)
def test_assigning_a_field_raises(value, name):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(value, name, None)


def test_update_produces_a_new_value():
    p = Player("p0", 0)
    q = dataclasses.replace(p, debt=4)
    assert p.debt == 0 and q.debt == 4


def test_board_collections_cannot_be_mutated():
    board = Board(
        tiles=[empty(A), vineyard(B)],
        canals=[PlacedCanal(A, PieceKind.STRAIGHT, 0, "p0")],
        floodgates=[Floodgate(A, W)],
        claims=[(B, "p0")],
    )
    for name in ("tiles", "canals", "floodgates", "claims"):
        collection = getattr(board, name)
        assert isinstance(collection, tuple)
        with pytest.raises((TypeError, AttributeError)):
            collection.append(None)
        with pytest.raises(TypeError):
            collection[0] = None


def test_game_state_collections_cannot_be_mutated():
    s = state(players=list(players()), market=[PieceKind.CLAW], bag=[PieceKind.FLOODGATE])
    for name in ("players", "market", "bag"):
        collection = getattr(s, name)
        assert isinstance(collection, tuple)
        with pytest.raises(TypeError):
            collection[0] = None


def test_board_does_not_share_the_input_list():
    tiles = [empty(A)]
    board = Board(tiles=tiles)
    tiles.append(empty(B))
    assert board.tile_at(B) is None


# --- Dependencies ----------------------------------------------------------


def _lazy_or_type_checking_nodes(tree):
    """Ids of every node inside a function or an ``if TYPE_CHECKING:`` block."""
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or (
            isinstance(node, ast.If) and getattr(node.test, "id", None) == "TYPE_CHECKING"
        ):
            nodes.update(id(n) for n in ast.walk(node))
    return nodes


def test_model_imports_only_hex_from_acequias():
    # config imports model, so model may import acequias.config only under
    # TYPE_CHECKING or inside a function, never when it is loaded.
    source = Path(__file__).resolve().parent.parent.joinpath("acequias", "model.py")
    tree = ast.parse(source.read_text("utf-8"))
    lazy = _lazy_or_type_checking_nodes(tree)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("acequias"):
                if node.module == "acequias.config":
                    assert id(node) in lazy
                else:
                    assert node.module == "acequias.hex"
            else:
                assert node.module.split(".")[0] in {
                    "__future__",
                    "collections",
                    "dataclasses",
                    "enum",
                    "types",
                    "typing",
                }
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("acequias")
