import ast
import dataclasses
from pathlib import Path

import pytest

from acequias.flow import WaterPath, water
from acequias.hex import Direction, Hex
from acequias.model import Board, Floodgate, PieceKind, PlacedCanal, Terrain, Tile, Varietal

E, NE, NW, W, SW, SE = (
    Direction.E,
    Direction.NE,
    Direction.NW,
    Direction.W,
    Direction.SW,
    Direction.SE,
)


# --- Helpers -----------------------------------------------------------------


def canal(hex, edges, owner="a"):
    """The canal on ``hex`` whose shape and rotation open exactly ``edges``."""
    wanted = frozenset(edges)
    for kind in PieceKind:
        if not kind.is_canal:
            continue
        for rotation in range(6):
            if kind.edges(rotation) == wanted:
                return PlacedCanal(hex, kind, rotation, owner)
    raise AssertionError(f"no canal shape opens {sorted(d.name for d in wanted)}")


def board(river=(), vineyards=(), stones=(), empties=(), canals=(), floodgates=(), claims=()):
    """A hand-built board; every canal gets an empty tile under it."""
    tiles = [Tile(h, Terrain.RIVER) for h in river]
    tiles += [Tile(h, Terrain.VINEYARD, Varietal.MALBEC) for h in vineyards]
    tiles += [Tile(h, Terrain.STONE) for h in stones]
    tiles += [Tile(h, Terrain.EMPTY) for h in empties]
    tiles += [Tile(c.hex, Terrain.EMPTY) for c in canals]
    return Board(
        tiles=tuple(tiles),
        canals=tuple(canals),
        floodgates=tuple(floodgates),
        claims=tuple(claims),
    )


def path_hexes(path):
    return tuple(c.hex for c in path.canals)


R = Hex(0, 0)  # river
C1 = Hex(1, 0)
C2 = Hex(2, 0)
C3 = Hex(3, 0)
V2 = Hex(2, 0)
V3 = Hex(3, 0)


def chain(floodgates=()):
    """River -> straight on C1 -> straight on C2 -> vineyard on V3."""
    return board(
        river=[R],
        vineyards=[V3],
        canals=[canal(C1, {W, E}), canal(C2, {W, E})],
        floodgates=floodgates,
    )


# Ring of six canals around a stone at (3, 0), fed from the west through
# C1 and draining east into a vineyard at (5, 0). Two routes of 5 canals:
# bottom (2,0) (2,1) (3,1) (4,0) and top (2,0) (3,-1) (4,-1) (4,0).
RING_V = Hex(5, 0)
RING_BOTTOM = (C1, Hex(2, 0), Hex(2, 1), Hex(3, 1), Hex(4, 0))
RING_TOP = (C1, Hex(2, 0), Hex(3, -1), Hex(4, -1), Hex(4, 0))


def ring(floodgates=(), owner="a"):
    canals = [
        canal(C1, {W, E}, owner),
        canal(Hex(2, 0), {W, NE, SE}, owner),
        canal(Hex(3, -1), {SW, E}, owner),
        canal(Hex(4, -1), {W, SE}, owner),
        canal(Hex(4, 0), {NW, SW, E}, owner),
        canal(Hex(3, 1), {W, NE}, owner),
        canal(Hex(2, 1), {NW, E}, owner),
    ]
    return board(
        river=[R],
        vineyards=[RING_V],
        stones=[Hex(3, 0)],
        canals=canals,
        floodgates=floodgates,
    )


# --- How water moves ---------------------------------------------------------


def test_water_enters_a_canal_with_an_open_edge_facing_the_river():
    b = board(river=[R], vineyards=[V2], canals=[canal(C1, {W, E})])
    assert set(water(b)) == {V2}


def test_water_does_not_enter_a_canal_with_no_open_edge_facing_the_river():
    v = C1.neighbor(NE)
    b = board(river=[R], vineyards=[v], canals=[canal(C1, {NE, SW})])
    assert water(b) == {}


def test_water_passes_between_canals_that_both_open_the_shared_edge():
    assert set(water(chain())) == {V3}


def test_water_does_not_pass_into_a_canal_whose_facing_edge_is_closed():
    # C1 opens E toward C2, but C2 is closed on its W side.
    v = C2.neighbor(NE)
    b = board(river=[R], vineyards=[v], canals=[canal(C1, {W, E}), canal(C2, {NE, SW})])
    assert water(b) == {}


def test_water_does_not_pass_out_of_a_canal_whose_facing_edge_is_closed():
    # C1 is wet but closed on its E side; C2 opens W toward it.
    b = board(
        river=[R],
        vineyards=[V3],
        stones=[C1.neighbor(SW)],
        canals=[canal(C1, {W, SW}), canal(C2, {W, E})],
    )
    assert water(b) == {}


@pytest.mark.parametrize(
    "edges",
    [{NE, W, SE}, {E, W, NE}, {NW, W, SW}, {W, NW, NE}, {W, SW, E}],
    ids=["symmetric Y", "T branch", "claw", "claw other side", "T branch side"],
)
def test_inside_a_piece_water_reaches_all_three_openings(edges):
    piece = canal(C1, edges)
    vineyards = [C1.neighbor(d) for d in edges if d is not W]
    b = board(river=[R], vineyards=vineyards, canals=[piece])
    assert set(water(b)) == set(vineyards)


def test_water_entering_through_a_branch_reaches_the_other_openings():
    # T branch whose river intake is its side branch.
    river = C1.neighbor(NE)
    vineyards = [C1.neighbor(E), C1.neighbor(W)]
    b = board(river=[river], vineyards=vineyards, canals=[canal(C1, {E, W, NE})])
    assert set(water(b)) == set(vineyards)


def test_a_vineyard_is_watered_by_an_open_edge_facing_it():
    b = board(river=[R], vineyards=[V2], canals=[canal(C1, {W, E})])
    assert water(b)[V2].canals == (canal(C1, {W, E}),)


def test_a_vineyard_next_to_a_closed_side_is_not_watered():
    v = C1.neighbor(SE)
    b = board(river=[R], vineyards=[v], canals=[canal(C1, {W, E})])
    assert water(b) == {}


def test_a_vineyard_does_not_pass_water_on():
    far = Hex(4, 0)
    b = board(
        river=[R],
        vineyards=[V2, far],
        canals=[canal(C1, {W, E}), canal(C3, {W, E})],
    )
    assert set(water(b)) == {V2}


@pytest.mark.parametrize("blocker", ["stone", "empty", "off board", "vineyard"])
def test_an_open_edge_facing_a_non_canal_passes_nothing_but_the_piece_still_flows(blocker):
    # T branch on C1: W river, NE vineyard, E faces the blocker on C2.
    # Beyond the blocker, a straight on C3 would feed a vineyard on (4, 0).
    side = C1.neighbor(NE)
    far = Hex(4, 0)
    kwargs = {"stone": {"stones": [C2]}, "empty": {"empties": [C2]}, "off board": {}}
    extra = kwargs.get(blocker, {})
    vineyards = [side, far] + ([C2] if blocker == "vineyard" else [])
    b = board(
        river=[R],
        vineyards=vineyards,
        canals=[canal(C1, {W, E, NE}), canal(C3, {W, E})],
        **extra,
    )
    expected = {side} | ({C2} if blocker == "vineyard" else set())
    assert set(water(b)) == expected


def test_a_loop_of_canals_does_not_hang():
    result = water(ring())
    assert set(result) == {RING_V}


def test_a_loop_not_connected_to_the_river_does_not_hang():
    b = ring()
    dry = Board(
        tiles=tuple(t for t in b.tiles if t.terrain is not Terrain.RIVER),
        canals=b.canals,
    )
    assert water(dry) == {}


# --- Floodgates --------------------------------------------------------------


@pytest.mark.parametrize(
    "gate", [Floodgate(C1, E), Floodgate(C2, W)], ids=["from upstream", "from downstream"]
)
def test_water_never_crosses_a_floodgate(gate):
    assert water(chain([gate])) == {}


def test_water_never_crosses_a_floodgate_flowing_the_other_way():
    # Mirror of the chain: river on the east, vineyard on the west.
    river, v = Hex(3, 0), Hex(0, 0)
    canals = [canal(C1, {W, E}), canal(C2, {W, E})]
    assert set(water(board(river=[river], vineyards=[v], canals=canals))) == {v}
    for gate in (Floodgate(C1, E), Floodgate(C2, W)):
        b = board(river=[river], vineyards=[v], canals=canals, floodgates=[gate])
        assert water(b) == {}


def test_a_floodgate_on_the_only_entrance_dries_the_piece_and_downstream():
    side = C1.neighbor(NE)
    b = board(
        river=[R],
        vineyards=[side, V3],
        canals=[canal(C1, {W, E, NE}), canal(C2, {W, E})],
        floodgates=[Floodgate(C1, W)],
    )
    assert water(b) == {}


def test_a_floodgate_on_one_exit_cuts_only_that_branch():
    side = C1.neighbor(NE)
    b = board(
        river=[R],
        vineyards=[side, V3],
        canals=[canal(C1, {W, E, NE}), canal(C2, {W, E})],
    )
    assert set(water(b)) == {side, V3}
    gated = dataclasses.replace(b, floodgates=(Floodgate(C1, E),))
    assert set(water(gated)) == {side}


def test_a_floodgate_facing_the_river_stops_that_intake():
    b = board(river=[R], vineyards=[V2], canals=[canal(C1, {W, E})], floodgates=[Floodgate(C1, W)])
    assert water(b) == {}


def test_a_floodgate_on_one_of_two_intakes_leaves_the_other():
    rivers = [C1.neighbor(W), C1.neighbor(SW)]
    piece = canal(C1, {W, SW, E})
    b = board(river=rivers, vineyards=[V2], canals=[piece], floodgates=[Floodgate(C1, W)])
    assert set(water(b)) == {V2}
    both = dataclasses.replace(b, floodgates=(Floodgate(C1, W), Floodgate(C1, SW)))
    assert water(both) == {}


def test_a_floodgate_facing_a_vineyard_stops_it_being_watered_through_that_edge():
    b = board(river=[R], vineyards=[V2], canals=[canal(C1, {W, E})], floodgates=[Floodgate(C1, E)])
    assert water(b) == {}


def test_a_floodgate_facing_a_vineyard_leaves_its_other_edges():
    # V2 is fed by C1 (gated) and by a second canal on (1, 1) opening NE.
    other = Hex(1, 1)
    b = board(
        river=[R, other.neighbor(W)],
        vineyards=[V2],
        canals=[canal(C1, {W, E}), canal(other, {W, NE}, "b")],
        floodgates=[Floodgate(C1, E)],
    )
    assert path_hexes(water(b)[V2]) == (other,)


def test_a_second_route_around_a_floodgate_keeps_the_vineyard_watered():
    assert path_hexes(water(ring())[RING_V]) == RING_BOTTOM
    bottom_cut = ring([Floodgate(Hex(2, 1), E)])
    assert path_hexes(water(bottom_cut)[RING_V]) == RING_TOP
    top_cut = ring([Floodgate(Hex(3, -1), E)])
    assert path_hexes(water(top_cut)[RING_V]) == RING_BOTTOM
    both_cut = ring([Floodgate(Hex(2, 1), E), Floodgate(Hex(3, -1), E)])
    assert water(both_cut) == {}


# --- Result ------------------------------------------------------------------


def test_water_maps_every_watered_vineyard_claimed_or_not_and_no_dry_ones():
    side = C1.neighbor(NE)
    dry = Hex(1, 2)
    b = board(
        river=[R],
        vineyards=[side, V3, dry],
        canals=[canal(C1, {W, E, NE}), canal(C2, {W, E})],
        claims=[(V3, "a")],
    )
    result = water(b)
    assert set(result) == {side, V3}
    assert all(isinstance(p, WaterPath) for p in result.values())


@pytest.mark.parametrize("value", [None, (), {}, "board", [Tile(R, Terrain.RIVER)]])
def test_water_rejects_anything_but_a_board(value):
    with pytest.raises(TypeError):
        water(value)


def test_water_path_is_immutable():
    path = water(chain())[V3]
    with pytest.raises(dataclasses.FrozenInstanceError):
        path.canals = ()
    with pytest.raises(dataclasses.FrozenInstanceError):
        path.owners = frozenset()


def test_water_path_lists_canals_from_river_to_vineyard_with_their_owners():
    b = board(
        river=[R],
        vineyards=[V3],
        canals=[canal(C2, {W, E}, "b"), canal(C1, {W, E}, "a")],
        claims=[(V3, "a")],
    )
    path = water(b)[V3]
    assert isinstance(path.canals, tuple)
    assert path.canals == (b.canal_at(C1), b.canal_at(C2))
    assert all(isinstance(c, PlacedCanal) for c in path.canals)
    assert isinstance(path.owners, frozenset)
    assert path.owners == frozenset({"a", "b"})


def test_a_path_through_a_loop_has_no_canal_twice():
    path = water(ring())[RING_V]
    assert len(set(path.canals)) == len(path.canals)


# Two routes to V3: a short one of two "b" canals along row 0, and a long one
# of three "a" canals along row 1, turning NW into V3.
SHORT = (Hex(1, 0), Hex(2, 0))
LONG = (Hex(1, 1), Hex(2, 1), Hex(3, 1))


def two_routes(claims=(), short=("b", "b"), long=("a", "a", "a")):
    return board(
        river=[Hex(0, 0), Hex(0, 1)],
        vineyards=[V3],
        canals=[
            canal(SHORT[0], {W, E}, short[0]),
            canal(SHORT[1], {W, E}, short[1]),
            canal(LONG[0], {W, E}, long[0]),
            canal(LONG[1], {W, E}, long[1]),
            canal(LONG[2], {W, NW}, long[2]),
        ],
        claims=claims,
    )


def test_a_longer_path_of_the_claimants_own_canals_beats_a_shorter_rival_path():
    path = water(two_routes(claims=[(V3, "a")]))[V3]
    assert path_hexes(path) == LONG
    assert path.owners == frozenset({"a"})


def test_the_claimant_comes_from_the_board_claim():
    path = water(two_routes(claims=[(V3, "b")]))[V3]
    assert path_hexes(path) == SHORT
    assert path.owners == frozenset({"b"})


def test_with_equal_rivals_the_path_with_fewer_canals_wins():
    # A third player: both routes have one rival, so the shorter wins.
    assert path_hexes(water(two_routes(claims=[(V3, "c")]))[V3]) == SHORT
    # Unclaimed: both routes have one owner, so the shorter wins.
    assert path_hexes(water(two_routes())[V3]) == SHORT


def test_fewer_rivals_wins_over_fewer_canals():
    # Short route owned by a and b, long route by c alone.
    b = two_routes(claims=[(V3, "a")], short=("a", "b"), long=("c", "c", "c"))
    path = water(b)[V3]
    assert path_hexes(path) == SHORT  # one rival each: shorter wins
    assert path.owners == frozenset({"a", "b"})


def test_an_unclaimed_vineyard_counts_every_owner_as_a_rival():
    # Same board unclaimed: short route has two rivals, long route one.
    b = two_routes(short=("a", "b"), long=("c", "c", "c"))
    path = water(b)[V3]
    assert path_hexes(path) == LONG
    assert path.owners == frozenset({"c"})


def tie_board(order=1):
    # Two 2-canal routes into (3, 1), owned by the same player. Route P1
    # starts on the smaller hex but ends on the larger one, so only the
    # river-end-first rule picks it.
    v = Hex(3, 1)
    canals = [
        canal(Hex(3, 0), {NW, E}),
        canal(Hex(4, 0), {W, SW}),
        canal(Hex(3, 2), {SE, W}),
        canal(Hex(2, 2), {E, NE}),
    ][::order]
    return v, board(river=[Hex(3, -1), Hex(3, 3)], vineyards=[v], canals=canals)


def test_a_tie_on_owners_and_length_is_broken_by_hex_order_from_the_river_end():
    v, b = tie_board()
    first = path_hexes(water(b)[v])
    assert first == (Hex(3, 0), Hex(4, 0))
    for _ in range(20):
        assert path_hexes(water(b)[v]) == first
    v, reversed_board = tie_board(order=-1)
    assert path_hexes(water(reversed_board)[v]) == first


def test_a_tie_in_a_loop_is_broken_hex_by_hex():
    assert path_hexes(water(ring())[RING_V]) == RING_BOTTOM


def test_a_board_with_no_canals_waters_nothing():
    b = board(river=[R], vineyards=[V2], empties=[C1])
    assert water(b) == {}


def test_a_board_with_no_vineyards_returns_an_empty_mapping():
    b = board(river=[R], canals=[canal(C1, {W, E}), canal(C2, {W, E})])
    assert water(b) == {}
    assert water(Board()) == {}


def test_a_vineyard_next_to_several_watered_canals_appears_once():
    other = Hex(1, 1)
    b = board(
        river=[R, other.neighbor(W)],
        vineyards=[V2],
        canals=[canal(C1, {W, E}), canal(other, {W, NE})],
    )
    result = water(b)
    assert list(result) == [V2]
    assert path_hexes(result[V2]) == (C1,)


def test_water_does_not_change_the_board():
    b = ring([Floodgate(Hex(2, 1), E)])
    before = dataclasses.replace(b)
    water(b)
    assert b == before


def test_flow_imports_only_hex_and_model_from_acequias():
    source = Path(__file__).resolve().parent.parent.joinpath("acequias", "flow.py")
    tree = ast.parse(source.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("acequias"):
                assert node.module in {"acequias.hex", "acequias.model"}
            else:
                assert node.module.split(".")[0] in {
                    "__future__",
                    "collections",
                    "dataclasses",
                    "itertools",
                    "types",
                }
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("acequias")
                assert alias.name != "random"
