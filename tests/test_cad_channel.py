import math
from functools import cache

import pytest

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"
pytest.importorskip("build123d", reason=CAD_REASON)
trimesh = pytest.importorskip("trimesh", reason=CAD_REASON)

from build123d import Axis, Solid  # noqa: E402

from acequias.cad.channel import (  # noqa: E402
    CAP_DIAMETER,
    HOLE_DEPTH,
    HOLE_DIAMETER,
    MIN_WALL,
    canal_piece,
    edge_midpoints,
    floodgate,
    owner_token,
    token_hole_center,
)
from acequias.cad.hex_tile import export_stl, hex_tile  # noqa: E402
from acequias.hex import Direction, Hex  # noqa: E402
from acequias.model import PieceKind  # noqa: E402

TOL = 0.01
SIDE = 16.0
HEIGHT = 4.0
GROOVE_WIDTH = 6.0
GROOVE_DEPTH = 1.5
MID_GROOVE = HEIGHT - GROOVE_DEPTH / 2
INSET = 0.2
CANALS = [k for k in PieceKind if k.is_canal]
CLEARANCES = (0.0, 0.2)
NAN = float("nan")
INF = float("inf")


@cache
def _piece(kind, side=SIDE, clearance=0.0):
    return canal_piece(kind, side=side, clearance=clearance)


def _solid(shape, x, y, z):
    return shape.is_inside((x, y, z))


def _unit(v):
    length = math.hypot(*v)
    return (v[0] / length, v[1] / length)


def _inside_edge(mid, inset=INSET):
    """The point ``inset`` mm inside the edge whose midpoint is ``mid``."""
    ux, uy = _unit(mid)
    return (mid[0] - ux * inset, mid[1] - uy * inset)


def _across(mid):
    """Unit vector across the groove that ends at ``mid``."""
    ux, uy = _unit(mid)
    return (-uy, ux)


def _opened_edges(shape, clearance=0.0):
    """The directions whose edge probe at mid-groove depth is empty."""
    mids = edge_midpoints(SIDE, clearance)
    return frozenset(
        d for d in Direction if not _solid(shape, *_inside_edge(mids[d]), MID_GROOVE)
    )


def _cad_position(hex_, side=SIDE):
    x, y = hex_.to_pixel(side)
    return (x, -y)


def _intersection_volume(a, b):
    common = a & b
    if common is None:
        return 0.0
    return sum(s.volume for s in common.solids())


# Frame and edges


def test_edge_midpoints_at_the_default_side():
    expected = {
        Direction.E: (13.86, 0.0),
        Direction.NE: (6.93, 12.00),
        Direction.NW: (-6.93, 12.00),
        Direction.W: (-13.86, 0.0),
        Direction.SW: (-6.93, -12.00),
        Direction.SE: (6.93, -12.00),
    }
    mids = edge_midpoints()
    assert set(mids) == set(Direction)
    for d, (ex, ey) in expected.items():
        assert mids[d][0] == pytest.approx(ex, abs=TOL), d
        assert mids[d][1] == pytest.approx(ey, abs=TOL), d


def test_edge_midpoints_come_from_hex_corners_with_y_flipped():
    for clearance in CLEARANCES:
        inner = SIDE - 2 * clearance / math.sqrt(3)
        corners = [(x, -y) for x, y in Hex(0, 0).corners(inner)]
        mids = edge_midpoints(SIDE, clearance)
        for i, d in enumerate(Direction):
            a, b = corners[i], corners[(i + 1) % 6]
            assert mids[d] == pytest.approx(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))


# Canal pieces


@pytest.mark.parametrize("kind", CANALS)
def test_canal_piece_is_one_valid_solid(kind):
    piece = _piece(kind)
    assert isinstance(piece, Solid)
    assert piece.is_valid


def test_floodgate_kind_points_to_floodgate_function():
    with pytest.raises(ValueError, match=r"floodgate\(\)"):
        canal_piece(PieceKind.FLOODGATE)
    with pytest.raises(ValueError, match=r"floodgate\(\)"):
        token_hole_center(PieceKind.FLOODGATE)


@pytest.mark.parametrize("kind", ["straight", None, 0, Direction.E])
def test_non_piece_kind_raises_type_error(kind):
    with pytest.raises(TypeError, match="PieceKind"):
        canal_piece(kind)
    with pytest.raises(TypeError, match="PieceKind"):
        token_hole_center(kind)


@pytest.mark.parametrize("clearance", CLEARANCES)
@pytest.mark.parametrize("kind", CANALS)
def test_grooves_open_exactly_the_kinds_edges(kind, clearance):
    assert _opened_edges(_piece(kind, clearance=clearance), clearance) == kind.edges(0)


@pytest.mark.parametrize("clearance", CLEARANCES)
def test_grooves_match_the_readme_table_not_a_mirror(clearance):
    mids = edge_midpoints(SIDE, clearance)

    def empty(kind, d):
        return not _solid(
            _piece(kind, clearance=clearance), *_inside_edge(mids[d]), MID_GROOVE
        )

    # Sharp curve: E and NE (north-east is up and right in the CAD frame).
    assert mids[Direction.NE][0] > 0 and mids[Direction.NE][1] > 0
    assert empty(PieceKind.SHARP_CURVE, Direction.NE)
    assert not empty(PieceKind.SHARP_CURVE, Direction.SE)
    # Gentle curve: E and NW.
    assert empty(PieceKind.GENTLE_CURVE, Direction.NW)
    assert not empty(PieceKind.GENTLE_CURVE, Direction.SW)
    # Straight: E and W only.
    straight = {d for d in Direction if empty(PieceKind.STRAIGHT, d)}
    assert straight == {Direction.E, Direction.W}


@pytest.mark.parametrize("clearance", CLEARANCES)
@pytest.mark.parametrize("kind", CANALS)
def test_center_and_spokes_are_empty(kind, clearance):
    piece = _piece(kind, clearance=clearance)
    mids = edge_midpoints(SIDE, clearance)
    assert not _solid(piece, 0, 0, MID_GROOVE)
    for d in kind.edges(0):
        mx, my = mids[d]
        for f in (0.25, 0.5, 0.75):
            assert not _solid(piece, mx * f, my * f, MID_GROOVE), (d, f)


@pytest.mark.parametrize("clearance", CLEARANCES)
@pytest.mark.parametrize("kind", CANALS)
def test_groove_cross_section_at_every_opening(kind, clearance):
    piece = _piece(kind, clearance=clearance)
    mids = edge_midpoints(SIDE, clearance)
    floor = HEIGHT - GROOVE_DEPTH
    for d in kind.edges(0):
        px, py = _inside_edge(mids[d])
        ax, ay = _across(mids[d])
        for sign in (1, -1):
            o = sign * (GROOVE_WIDTH / 2 - 0.1)
            assert not _solid(piece, px + ax * o, py + ay * o, MID_GROOVE), (d, o)
            o = sign * (GROOVE_WIDTH / 2 + 0.1)
            assert _solid(piece, px + ax * o, py + ay * o, MID_GROOVE), (d, o)
        assert not _solid(piece, px, py, floor + 0.1), d
        assert _solid(piece, px, py, floor - 0.1), d


@pytest.mark.parametrize("clearance", CLEARANCES)
@pytest.mark.parametrize("kind", CANALS)
def test_rotating_the_solid_matches_the_rotated_edges(kind, clearance):
    piece = _piece(kind, clearance=clearance)
    for k in range(6):
        turned = piece.rotate(Axis.Z, 60 * k)
        assert _opened_edges(turned, clearance) == kind.edges(k), k


# Neighbors line up


NEIGHBOR_PAIRS = [
    # (kind at Hex(0, 0), neighbor hex, its kind, direction from Hex(0, 0))
    (PieceKind.STRAIGHT, Hex(1, 0), PieceKind.STRAIGHT, Direction.E),
    (PieceKind.SHARP_CURVE, Hex(1, -1), PieceKind.SYMMETRIC_Y, Direction.NE),
]


def test_cad_positions_of_neighbors():
    assert _cad_position(Hex(1, 0)) == pytest.approx((27.71, 0), abs=TOL)
    assert _cad_position(Hex(1, -1)) == pytest.approx((13.86, 24.00), abs=TOL)


@pytest.mark.parametrize("clearance", CLEARANCES)
@pytest.mark.parametrize(("kind", "other_hex", "other_kind", "direction"), NEIGHBOR_PAIRS)
def test_neighbors_do_not_overlap(kind, other_hex, other_kind, direction, clearance):
    x, y = _cad_position(other_hex)
    a = _piece(kind, clearance=clearance)
    b = _piece(other_kind, clearance=clearance).translate((x, y, 0))
    assert _intersection_volume(a, b) < 0.001


@pytest.mark.parametrize("clearance", CLEARANCES)
@pytest.mark.parametrize(("kind", "other_hex", "other_kind", "direction"), NEIGHBOR_PAIRS)
def test_neighbor_grooves_meet_without_a_step(
    kind, other_hex, other_kind, direction, clearance
):
    ox, oy = _cad_position(other_hex)
    a = _piece(kind, clearance=clearance)
    b = _piece(other_kind, clearance=clearance).translate((ox, oy, 0))
    mids = edge_midpoints(SIDE, clearance)
    # Each probe is measured from its own piece's face.
    mid_a = mids[direction]
    mid_b_local = mids[direction.opposite()]
    pa = _inside_edge(mid_a)
    pb_local = _inside_edge(mid_b_local)
    pb = (pb_local[0] + ox, pb_local[1] + oy)
    ax, ay = _across(mid_a)  # the same line for both pieces, up to sign
    floor = HEIGHT - GROOVE_DEPTH
    for piece, (px, py) in ((a, pa), (b, pb)):
        for z in (MID_GROOVE, floor + 0.1):
            for sign in (1, -1):
                o = sign * (GROOVE_WIDTH / 2 - 0.1)
                assert not _solid(piece, px + ax * o, py + ay * o, z)
        for sign in (1, -1):
            o = sign * (GROOVE_WIDTH / 2 + 0.1)
            assert _solid(piece, px + ax * o, py + ay * o, MID_GROOVE)
        assert _solid(piece, px, py, floor - 0.1)


# Owner-token hole


def test_hole_constants():
    assert HOLE_DIAMETER == 4
    assert HOLE_DEPTH == 2


@pytest.mark.parametrize("kind", CANALS)
def test_token_hole_center_is_stable(kind):
    first = token_hole_center(kind)
    assert token_hole_center(kind) == first
    assert token_hole_center(kind, 16, 0) == first
    assert token_hole_center(kind, side=18, clearance=0.2) == token_hole_center(
        kind, 18, 0.2
    )


def _ring(cx, cy, radius, n=36):
    for i in range(n):
        a = 2 * math.pi * i / n
        yield (cx + radius * math.cos(a), cy + radius * math.sin(a))


@pytest.mark.parametrize("clearance", CLEARANCES)
@pytest.mark.parametrize("side", (16.0, 18.0))
@pytest.mark.parametrize("kind", CANALS)
def test_hole_and_cap_fit_on_the_top_face(kind, side, clearance):
    piece = _piece(kind, side=side, clearance=clearance)
    cx, cy = token_hole_center(kind, side, clearance)
    r = HOLE_DIAMETER / 2
    bottom = HEIGHT - HOLE_DEPTH
    # The hole: round, flat-bottomed, HOLE_DIAMETER x HOLE_DEPTH.
    assert not _solid(piece, cx, cy, bottom + 0.1)
    assert _solid(piece, cx, cy, bottom - 0.1)
    for x, y in _ring(cx, cy, r - 0.1, 12):
        assert not _solid(piece, x, y, HEIGHT - HOLE_DEPTH / 2)
        assert not _solid(piece, x, y, bottom + 0.1)
    for x, y in _ring(cx, cy, r + 0.1, 12):
        assert _solid(piece, x, y, HEIGHT - HOLE_DEPTH / 2)
    # At least 0.8 mm of material around the hole, clear of groove and face.
    for radius in (r + 0.1, r + MIN_WALL / 2, r + MIN_WALL):
        for x, y in _ring(cx, cy, radius):
            assert _solid(piece, x, y, HEIGHT - 0.05), (radius, x, y)
            assert _solid(piece, x, y, MID_GROOVE), (radius, x, y)
    # The cap footprint lies on the solid top face.
    for radius in (r + 1.0, (r + CAP_DIAMETER / 2) / 2 + 0.5, CAP_DIAMETER / 2):
        for x, y in _ring(cx, cy, radius):
            assert _solid(piece, x, y, HEIGHT - 0.05), (radius, x, y)
    # At least 0.8 mm of material under the hole and under the groove.
    assert HEIGHT - HOLE_DEPTH >= MIN_WALL
    assert HEIGHT - GROOVE_DEPTH >= MIN_WALL
    for z in (0.05, MIN_WALL / 2, MIN_WALL - 0.05):
        assert _solid(piece, cx, cy, z)
        assert _solid(piece, 0, 0, z)


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"groove_width": 14.5}, "groove_width"),  # edge wall below 0.8 mm
        ({"groove_width": 9.0}, "groove_width"),  # no room for the cap
        ({"groove_depth": 3.3}, "groove_depth"),  # floor below 0.8 mm
        ({"hole_depth": 3.3}, "hole_depth"),  # floor below 0.8 mm
        ({"hole_diameter": 7.0}, "hole_diameter"),  # no wider than the cap
        ({"side": 10.0}, "groove_width"),  # too small for groove and cap
        ({"side": 0}, "side"),
        ({"side": -16}, "side"),
        ({"side": NAN}, "side"),
        ({"side": INF}, "side"),
        ({"height": 0}, "height"),
        ({"height": NAN}, "height"),
        ({"height": INF}, "height"),
        ({"clearance": -0.1}, "clearance"),
        ({"clearance": NAN}, "clearance"),
        ({"clearance": INF}, "clearance"),
        ({"clearance": 20}, "clearance"),
        ({"groove_width": 0}, "groove_width"),
        ({"groove_width": NAN}, "groove_width"),
        ({"groove_depth": -1}, "groove_depth"),
        ({"groove_depth": INF}, "groove_depth"),
        ({"hole_diameter": 0}, "hole_diameter"),
        ({"hole_diameter": NAN}, "hole_diameter"),
        ({"hole_depth": -2}, "hole_depth"),
        ({"hole_depth": INF}, "hole_depth"),
    ],
)
def test_invalid_piece_sizes_raise_value_error_naming_them(kwargs, name):
    with pytest.raises(ValueError, match=name):
        canal_piece(PieceKind.STRAIGHT, **kwargs)


def test_hole_too_close_to_the_groove_is_rejected():
    # A hole that still fits under the cap but crowds the groove.
    with pytest.raises(ValueError, match="hole_diameter"):
        canal_piece(PieceKind.STRAIGHT, side=16, groove_width=8.3, hole_diameter=6.5)


# Floodgate


def test_floodgate_bounding_box_at_defaults():
    bb = floodgate().bounding_box()
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((5.70, 2.00, 1.50), abs=TOL)
    assert bb.min.Z == pytest.approx(0, abs=TOL)
    assert (bb.min.X + bb.max.X, bb.min.Y + bb.max.Y) == pytest.approx((0, 0), abs=TOL)


def test_floodgate_follows_its_parameters():
    bb = floodgate(tolerance=0.2, groove_width=5, groove_depth=1.2, thickness=1.5)
    bb = bb.bounding_box()
    assert (bb.size.X, bb.size.Y, bb.size.Z) == pytest.approx((4.6, 1.5, 1.2), abs=TOL)


def test_floodgate_seated_in_the_e_opening_fits():
    tolerance = 0.15
    thickness = 2.0
    piece = _piece(PieceKind.STRAIGHT)
    apothem = edge_midpoints()[Direction.E][0]
    # Turn the gate so its width runs across the E-W groove (along y), then
    # put its outer face on the E face and its bottom on the groove floor.
    gate = floodgate().rotate(Axis.Z, 90).translate(
        (apothem - thickness / 2, 0, HEIGHT - GROOVE_DEPTH)
    )
    assert _intersection_volume(piece, gate) < 0.001
    gb = gate.bounding_box()
    tb = piece.bounding_box()
    assert gb.max.X == pytest.approx(apothem, abs=TOL)
    assert gb.min.Z == pytest.approx(HEIGHT - GROOVE_DEPTH, abs=TOL)
    assert gb.max.Z == pytest.approx(HEIGHT, abs=TOL)
    # tolerance of clearance to each groove wall.
    assert gb.max.Y == pytest.approx(GROOVE_WIDTH / 2 - tolerance, abs=TOL)
    assert gb.min.Y == pytest.approx(-(GROOVE_WIDTH / 2 - tolerance), abs=TOL)
    x = apothem - thickness / 2
    assert not _solid(piece, x, GROOVE_WIDTH / 2 - 0.05, MID_GROOVE)
    assert _solid(piece, x, GROOVE_WIDTH / 2 + 0.05, MID_GROOVE)
    assert not _solid(piece, x, -(GROOVE_WIDTH / 2 - 0.05), MID_GROOVE)
    assert _solid(piece, x, -(GROOVE_WIDTH / 2 + 0.05), MID_GROOVE)
    for axis in "XYZ":
        assert getattr(gb.min, axis) >= getattr(tb.min, axis) - 1e-6
        assert getattr(gb.max, axis) <= getattr(tb.max, axis) + 1e-6


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"tolerance": -0.1}, "tolerance"),
        ({"tolerance": NAN}, "tolerance"),
        ({"tolerance": INF}, "tolerance"),
        ({"tolerance": 2.65}, "tolerance"),  # gate 0.7 mm wide
        ({"thickness": 0.7}, "thickness"),
        ({"thickness": NAN}, "thickness"),
        ({"thickness": 0}, "thickness"),
        ({"groove_width": 0}, "groove_width"),
        ({"groove_depth": INF}, "groove_depth"),
    ],
)
def test_invalid_floodgate_raises_value_error_naming_them(kwargs, name):
    with pytest.raises(ValueError, match=name):
        floodgate(**kwargs)


def test_floodgate_minimums_are_allowed():
    floodgate(tolerance=0, thickness=MIN_WALL)
    floodgate(tolerance=2.55, thickness=MIN_WALL)  # gate 0.9 mm wide


# Owner token


def test_owner_token_is_one_solid_cap_down_peg_up():
    token = owner_token()
    assert isinstance(token, Solid)
    assert token.is_valid
    bb = token.bounding_box()
    assert bb.min.Z == pytest.approx(0, abs=TOL)
    assert (bb.min.X + bb.max.X, bb.min.Y + bb.max.Y) == pytest.approx((0, 0), abs=TOL)
    cap_height = 1.2
    # Cap at the bottom, full width; peg above it, narrower.
    assert _solid(token, CAP_DIAMETER / 2 - 0.1, 0, cap_height / 2)
    assert not _solid(token, CAP_DIAMETER / 2 - 0.1, 0, cap_height + 0.1)
    assert _solid(token, 0, 0, bb.max.Z - 0.1)


@pytest.mark.parametrize("tolerance", (0, 0.15, 0.3))
def test_owner_token_peg_fits_the_hole(tolerance):
    cap_height = 1.2
    token = owner_token(tolerance=tolerance)
    peg_r = (HOLE_DIAMETER - 2 * tolerance) / 2
    z = cap_height + 0.5
    for x, y in _ring(0, 0, peg_r - TOL / 2, 12):
        assert _solid(token, x, y, z)
    for x, y in _ring(0, 0, peg_r + TOL / 2, 12):
        assert not _solid(token, x, y, z)
    bb = token.bounding_box()
    peg_length = bb.max.Z - cap_height
    assert HOLE_DEPTH - 0.5 <= peg_length <= HOLE_DEPTH
    assert (bb.size.X, bb.size.Y) == pytest.approx((CAP_DIAMETER, CAP_DIAMETER), abs=TOL)


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"tolerance": -0.1}, "tolerance"),
        ({"tolerance": NAN}, "tolerance"),
        ({"tolerance": INF}, "tolerance"),
        ({"tolerance": 1.65}, "tolerance"),  # peg 0.7 mm across
        ({"cap_diameter": 0}, "cap_diameter"),
        ({"cap_diameter": 4}, "cap_diameter"),  # falls into the hole
        ({"cap_height": NAN}, "cap_height"),
        ({"cap_height": -1}, "cap_height"),
    ],
)
def test_invalid_owner_token_raises_value_error(kwargs, name):
    with pytest.raises(ValueError, match=name):
        owner_token(**kwargs)


# Export and checks


def _export_and_load(shape, tmp_path, name):
    path = export_stl(shape, tmp_path / f"{name}.stl")
    assert path.is_file()
    assert tmp_path in path.parents
    return trimesh.load_mesh(path)


def _assert_closed_single_body(mesh):
    assert mesh.is_watertight
    assert len(mesh.split(only_watertight=False)) == 1


@pytest.mark.parametrize(
    ("clearance", "size"),
    [(0.0, (27.71, 32.00, 4.00)), (0.2, (27.31, 31.54, 4.00))],
)
@pytest.mark.parametrize("kind", CANALS)
def test_canal_stl_is_closed_with_the_tiles_bounding_box(kind, clearance, size, tmp_path):
    mesh = _export_and_load(
        _piece(kind, clearance=clearance), tmp_path, kind.name.lower()
    )
    _assert_closed_single_body(mesh)
    assert tuple(mesh.extents) == pytest.approx(size, abs=TOL)
    tile = _export_and_load(hex_tile(SIDE, HEIGHT, clearance), tmp_path, "tile")
    assert tuple(mesh.extents) == pytest.approx(tuple(tile.extents), abs=TOL)
    assert mesh.bounds[0][2] == pytest.approx(0, abs=TOL)


def _tile_volume():
    return 3 * math.sqrt(3) / 2 * SIDE**2 * HEIGHT


def _hole_volume():
    return math.pi * (HOLE_DIAMETER / 2) ** 2 * HOLE_DEPTH


def test_straight_stl_volume(tmp_path):
    mesh = _export_and_load(_piece(PieceKind.STRAIGHT), tmp_path, "straight")
    flat_to_flat = SIDE * math.sqrt(3)
    expected = _tile_volume() - GROOVE_WIDTH * GROOVE_DEPTH * flat_to_flat - _hole_volume()
    assert expected == pytest.approx(2385.9, abs=0.1)
    assert mesh.volume == pytest.approx(expected, rel=0.005)


@pytest.mark.parametrize("kind", [k for k in CANALS if k is not PieceKind.STRAIGHT])
def test_other_canal_volumes_lose_more_than_one_spoke(kind, tmp_path):
    mesh = _export_and_load(_piece(kind), tmp_path, kind.name.lower())
    spoke = GROOVE_WIDTH * GROOVE_DEPTH * SIDE * math.sqrt(3) / 2
    assert mesh.volume < _tile_volume() - _hole_volume() - spoke


def test_floodgate_stl_is_closed(tmp_path):
    mesh = _export_and_load(floodgate(), tmp_path, "floodgate")
    _assert_closed_single_body(mesh)
    assert tuple(mesh.extents) == pytest.approx((5.70, 2.00, 1.50), abs=TOL)


def test_owner_token_stl_is_closed_with_its_bounding_box(tmp_path):
    cap_diameter, cap_height = 7.0, 1.2
    token = owner_token(cap_diameter=cap_diameter, cap_height=cap_height)
    peg_length = token.bounding_box().max.Z - cap_height
    mesh = _export_and_load(token, tmp_path, "owner_token")
    _assert_closed_single_body(mesh)
    expected = (cap_diameter, cap_diameter, cap_height + peg_length)
    assert tuple(mesh.extents) == pytest.approx(expected, abs=TOL)
    assert mesh.bounds[0][2] == pytest.approx(0, abs=TOL)
