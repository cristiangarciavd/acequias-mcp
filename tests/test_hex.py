import ast
import dataclasses
import itertools
from pathlib import Path

import pytest

from acequias.hex import Direction, Hex

ORIGIN = Hex(0, 0)
SAMPLE = [Hex(0, 0), Hex(2, -1), Hex(-3, 4), Hex(5, 5), Hex(-2, -2)]


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


@pytest.mark.parametrize("a, b", list(itertools.combinations(SAMPLE, 2)))
def test_distance_is_symmetric(a, b):
    assert a.distance(b) == b.distance(a)


@pytest.mark.parametrize("a, b, c", list(itertools.combinations(SAMPLE, 3)))
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


# --- Purity -----------------------------------------------------------------

def test_hex_module_imports_nothing_from_acequias():
    source = Path(__file__).parents[1].joinpath("acequias", "hex.py").read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0 and not (node.module or "").startswith("acequias")
        elif isinstance(node, ast.Import):
            assert not any(a.name.startswith("acequias") for a in node.names)
