import ast
import math
import dataclasses
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from acequias.hex import Direction, Hex

ORIGIN = Hex(0, 0)
SAMPLE = [Hex(0, 0), Hex(2, -1), Hex(-3, 4), Hex(5, 5), Hex(-2, -2)]

# Bounded coordinates keep generated hexes in a sane range. deadline=None on
# the tests avoids flaky timing failures on slow CI runners.
COORD = st.integers(min_value=-1000, max_value=1000)
hexes = st.builds(Hex, COORD, COORD)


# --- Immutability and hashing ---------------------------------------------

def test_hex_is_immutable():
    h = Hex(1, 2)
    with pytest.raises(dataclasses.FrozenInstanceError):
        h.q = 5


def test_equal_hexes_are_equal_and_hash_the_same():
    assert Hex(1, 2) == Hex(1, 2)
    assert hash(Hex(1, 2)) == hash(Hex(1, 2))
    assert Hex(1, 2) != Hex(2, 1)


def test_hex_works_as_dict_key():
    board = {Hex(0, 0): "river", Hex(1, 0): "vineyard"}
    assert board[Hex(1, 0)] == "vineyard"


@pytest.mark.parametrize("bad", [1.5, "1", None, True])
def test_non_int_coordinates_are_rejected(bad):
    with pytest.raises(TypeError):
        Hex(bad, 0)
    with pytest.raises(TypeError):
        Hex(0, bad)


def test_ordering_is_lexicographic_on_q_then_r():
    assert sorted([Hex(1, 0), Hex(0, 5), Hex(0, -1)]) == [Hex(0, -1), Hex(0, 5), Hex(1, 0)]


# --- Neighbors --------------------------------------------------------------

def test_origin_neighbors_are_the_six_axial_directions():
    assert set(ORIGIN.neighbors()) == {
        Hex(1, 0), Hex(1, -1), Hex(0, -1), Hex(-1, 0), Hex(-1, 1), Hex(0, 1),
    }


@pytest.mark.parametrize("h", SAMPLE)
def test_every_hex_has_exactly_six_distinct_neighbors(h):
    neighbors = h.neighbors()
    assert len(neighbors) == 6
    assert len(set(neighbors)) == 6
    assert h not in neighbors


@pytest.mark.parametrize("h", SAMPLE)
def test_neighbor_relation_is_symmetric(h):
    for n in h.neighbors():
        assert h in n.neighbors()


def test_east_and_west_are_neighbors():
    assert ORIGIN.neighbor(Direction.E) == Hex(1, 0)
    assert ORIGIN.neighbor(Direction.W) == Hex(-1, 0)


@pytest.mark.parametrize("d", list(Direction))
def test_opposite_direction_walks_back(d):
    assert ORIGIN.neighbor(d).neighbor(d.opposite()) == ORIGIN
    assert d.opposite().opposite() == d


# --- Distance ---------------------------------------------------------------

@pytest.mark.parametrize("h", SAMPLE)
def test_distance_to_self_is_zero(h):
    assert h.distance(h) == 0


@pytest.mark.parametrize("h", SAMPLE)
def test_distance_to_every_neighbor_is_one(h):
    assert all(h.distance(n) == 1 for n in h.neighbors())


@settings(deadline=None)
@given(hexes, hexes)
def test_distance_is_symmetric(a, b):
    assert a.distance(b) == b.distance(a)


@settings(deadline=None)
@given(hexes, hexes, hexes)
def test_distance_obeys_triangle_inequality(a, b, c):
    assert a.distance(c) <= a.distance(b) + b.distance(c)


@pytest.mark.parametrize(
    "target, expected",
    [(Hex(3, 0), 3), (Hex(0, -4), 4), (Hex(2, 2), 4), (Hex(3, -3), 3), (Hex(-2, 5), 5)],
)
def test_known_distances_from_origin(target, expected):
    assert ORIGIN.distance(target) == expected


# --- Conversions ------------------------------------------------------------

@pytest.mark.parametrize("h", SAMPLE)
def test_cube_round_trip(h):
    q, r, s = h.to_cube()
    assert q + r + s == 0
    assert Hex.from_cube(q, r, s) == h


def test_from_cube_rejects_invalid_coordinates():
    with pytest.raises(ValueError):
        Hex.from_cube(1, 1, 1)


@pytest.mark.parametrize("h", SAMPLE)
def test_pixel_round_trip(h):
    x, y = h.to_pixel(16.0)
    assert Hex.from_pixel(x, y, 16.0) == h


def test_pixel_spacing_matches_pointy_top_geometry():
    size = 16.0
    x0, y0 = ORIGIN.to_pixel(size)
    xe, ye = Hex(1, 0).to_pixel(size)
    assert (x0, y0) == (0.0, 0.0)
    # East neighbor is one flat-to-flat width away, on the same row.
    assert xe == pytest.approx(size * 3 ** 0.5)
    assert ye == 0.0
    # Every neighbor center is the same distance away.
    for n in ORIGIN.neighbors():
        nx, ny = n.to_pixel(size)
        assert (nx**2 + ny**2) ** 0.5 == pytest.approx(size * 3 ** 0.5)


def test_point_near_a_center_maps_to_that_hex():
    x, y = Hex(2, -1).to_pixel(16.0)
    assert Hex.from_pixel(x + 3.0, y - 2.0, 16.0) == Hex(2, -1)


# --- Size checks ------------------------------------------------------------

BAD_SIZES = [0, 0.0, -1.0, -16]
NON_FINITE_SIZES = [math.nan, math.inf, -math.inf]


@pytest.mark.parametrize("size", BAD_SIZES)
def test_to_pixel_rejects_non_positive_size(size):
    with pytest.raises(ValueError, match="size"):
        Hex(1, 2).to_pixel(size)


@pytest.mark.parametrize("size", BAD_SIZES)
def test_from_pixel_rejects_non_positive_size(size):
    with pytest.raises(ValueError, match="size"):
        Hex.from_pixel(3.0, 4.0, size)


@pytest.mark.parametrize("size", BAD_SIZES)
def test_corners_rejects_non_positive_size(size):
    with pytest.raises(ValueError, match="size"):
        Hex(1, 2).corners(size)


@pytest.mark.parametrize("size", NON_FINITE_SIZES)
def test_non_finite_size_is_rejected_everywhere(size):
    with pytest.raises(ValueError, match="size"):
        Hex(1, 2).to_pixel(size)
    with pytest.raises(ValueError, match="size"):
        Hex.from_pixel(3.0, 4.0, size)
    with pytest.raises(ValueError, match="size"):
        Hex(1, 2).corners(size)


# --- Rotation ---------------------------------------------------------------

DIRECTION_ORDER = [Direction.E, Direction.NE, Direction.NW, Direction.W, Direction.SW, Direction.SE]


def test_rotating_one_step_follows_direction_order():
    for i, d in enumerate(DIRECTION_ORDER):
        assert d.rotated(1) == DIRECTION_ORDER[(i + 1) % 6]
    assert Direction.E.rotated(1) == Direction.NE
    assert Direction.SE.rotated(1) == Direction.E


@pytest.mark.parametrize("d", list(Direction))
def test_rotating_zero_steps_keeps_direction(d):
    assert d.rotated(0) == d


def test_negative_steps_turn_clockwise():
    assert Direction.E.rotated(-1) == Direction.SE
    assert Direction.NE.rotated(-1) == Direction.E
    assert Direction.E.rotated(-2) == Direction.SW
    for d in Direction:
        assert d.rotated(1).rotated(-1) == d


@pytest.mark.parametrize("d", list(Direction))
@pytest.mark.parametrize("k", [-12, -6, 6, 12, 60])
def test_multiples_of_six_give_the_same_direction(d, k):
    assert d.rotated(k) == d
    assert d.rotated(k + 2) == d.rotated(2)


@pytest.mark.parametrize("d", list(Direction))
def test_rotating_three_steps_is_the_opposite(d):
    assert d.rotated(3) == d.opposite()


@pytest.mark.parametrize("bad", [1.5, True, False, "1", None, 1.0])
def test_rotated_rejects_non_int_steps(bad):
    with pytest.raises(TypeError):
        Direction.E.rotated(bad)


# --- Corners ----------------------------------------------------------------

SIZE = 16.0


@pytest.mark.parametrize("h", SAMPLE)
def test_corners_are_size_away_from_center(h):
    cx, cy = h.to_pixel(SIZE)
    corners = h.corners(SIZE)
    assert len(corners) == 6
    for x, y in corners:
        assert math.hypot(x - cx, y - cy) == pytest.approx(SIZE)


@pytest.mark.parametrize("h", SAMPLE)
def test_neighboring_corners_are_size_apart(h):
    corners = h.corners(SIZE)
    for i in range(6):
        (x1, y1), (x2, y2) = corners[i], corners[(i + 1) % 6]
        assert math.hypot(x2 - x1, y2 - y1) == pytest.approx(SIZE)


@pytest.mark.parametrize("h", SAMPLE)
def test_hex_is_pointy_top(h):
    cx, cy = h.to_pixel(SIZE)
    corners = h.corners(SIZE)
    north = min(corners, key=lambda p: p[1])
    south = max(corners, key=lambda p: p[1])
    assert north == pytest.approx((cx, cy - SIZE))
    assert south == pytest.approx((cx, cy + SIZE))


def test_corner_order_is_fixed():
    s = SIZE
    half = s / 2
    w = s * math.sqrt(3) / 2
    expected = [
        (w, half),    # 0: ESE
        (w, -half),   # 1: ENE
        (0.0, -s),    # 2: N
        (-w, -half),  # 3: WNW
        (-w, half),   # 4: WSW
        (0.0, s),     # 5: S
    ]
    for got, want in zip(ORIGIN.corners(s), expected, strict=True):
        assert got == pytest.approx(want, abs=1e-9)


@pytest.mark.parametrize("h", SAMPLE)
@pytest.mark.parametrize("i, d", list(enumerate(Direction)))
def test_edge_facing_a_direction_is_shared_with_that_neighbor(h, i, d):
    # Edge i (corners i and i+1) faces list(Direction)[i]; on the neighbor it
    # is the edge facing back, d.opposite(), with its two corners swapped.
    mine = h.corners(SIZE)
    edge = (mine[i], mine[(i + 1) % 6])
    j = list(Direction).index(d.opposite())
    theirs = h.neighbor(d).corners(SIZE)
    their_edge = (theirs[(j + 1) % 6], theirs[j])
    for (x1, y1), (x2, y2) in zip(edge, their_edge):
        assert abs(x1 - x2) <= 1e-9 and abs(y1 - y2) <= 1e-9


@pytest.mark.parametrize("d", list(Direction))
def test_neighbor_shares_exactly_two_corners(d):
    def close(p, q):
        return abs(p[0] - q[0]) <= 1e-9 and abs(p[1] - q[1]) <= 1e-9

    mine = ORIGIN.corners(SIZE)
    theirs = ORIGIN.neighbor(d).corners(SIZE)
    shared = [p for p in mine if any(close(p, q) for q in theirs)]
    assert len(shared) == 2


# --- Purity -----------------------------------------------------------------

def test_hex_module_imports_nothing_from_acequias():
    source = Path(__file__).parents[1].joinpath("acequias", "hex.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("acequias")
        elif isinstance(node, ast.Import):
            assert not any(a.name.startswith("acequias") for a in node.names)
