import ast
import dataclasses
import math
import subprocess
import sys
from collections import Counter
from itertools import combinations
from pathlib import Path

import pytest

from acequias.hex import Hex
from acequias.plate import (
    CircleFootprint,
    HexFootprint,
    Piece,
    Placement,
    Plate,
    RectFootprint,
    layout_plates,
)

TOL = 1e-6
BED = (256, 256)
MARGIN = 5
GAP = 3


def hexes(n, side=16, color="neutral", prefix="h"):
    return [Piece(f"{prefix}{i}", HexFootprint(side), color) for i in range(n)]


def circles(n, diameter=12, color="red", prefix="c"):
    return [Piece(f"{prefix}{i}", CircleFootprint(diameter), color) for i in range(n)]


def rects(n, width=20, depth=10, color="neutral", prefix="r"):
    return [Piece(f"{prefix}{i}", RectFootprint(width, depth), color) for i in range(n)]


# --- Geometry helpers: true outlines, not bounding boxes ------------------


def outline(footprint, x, y):
    """A polygon for hexes and rectangles; ``None`` for circles."""
    if isinstance(footprint, HexFootprint):
        return footprint.outline(x, y)
    if isinstance(footprint, RectFootprint):
        w, d = footprint.width / 2, footprint.depth / 2
        return ((x - w, y - d), (x + w, y - d), (x + w, y + d), (x - w, y + d))
    return None


def point_segment_distance(p, a, b):
    ax, ay = a
    bx, by = b
    px, py = p
    dx, dy = bx - ax, by - ay
    t = ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def segments_cross(a, b, c, d):
    return (cross(a, b, c) * cross(a, b, d) < 0) and (cross(c, d, a) * cross(c, d, b) < 0)


def segment_distance(a, b, c, d):
    if segments_cross(a, b, c, d):
        return 0.0
    return min(
        point_segment_distance(a, c, d),
        point_segment_distance(b, c, d),
        point_segment_distance(c, a, b),
        point_segment_distance(d, a, b),
    )


def edges(poly):
    return [(poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly))]


def inside(point, poly):
    """Strictly inside a convex polygon (any winding)."""
    signs = [cross(a, b, point) for a, b in edges(poly)]
    return all(s > TOL for s in signs) or all(s < -TOL for s in signs)


def boundary_distance(point, poly):
    return min(point_segment_distance(point, a, b) for a, b in edges(poly))


def clearance(fp1, c1, fp2, c2):
    """Distance between two outlines; <= 0 means they touch or overlap."""
    p1, p2 = outline(fp1, *c1), outline(fp2, *c2)
    if p1 is None and p2 is None:
        return math.dist(c1, c2) - fp1.diameter / 2 - fp2.diameter / 2
    if p1 is None or p2 is None:
        (circle, center), poly = ((fp1, c1), p2) if p1 is None else ((fp2, c2), p1)
        if inside(center, poly):
            return -1.0
        return boundary_distance(center, poly) - circle.diameter / 2
    if any(inside(v, p2) for v in p1) or any(inside(v, p1) for v in p2):
        return -1.0
    return min(segment_distance(a, b, c, d) for a, b in edges(p1) for c, d in edges(p2))


def check_plates(pieces, plates, bed=BED, margin=MARGIN, gap=GAP):
    """No overlap, every gap >= ``gap``, every footprint inside the margin."""
    by_id = {p.id: p for p in pieces}
    min_seen = math.inf
    for plate in plates:
        placed = [(by_id[pl.piece_id].footprint, (pl.x, pl.y)) for pl in plate.placements]
        for fp, (x, y) in placed:
            assert x - fp.width / 2 >= margin - TOL
            assert y - fp.depth / 2 >= margin - TOL
            assert x + fp.width / 2 <= bed[0] - margin + TOL
            assert y + fp.depth / 2 <= bed[1] - margin + TOL
        for (fp1, c1), (fp2, c2) in combinations(placed, 2):
            d = clearance(fp1, c1, fp2, c2)
            assert d >= gap - TOL, (fp1, c1, fp2, c2, d)
            min_seen = min(min_seen, d)
    return min_seen


def rows_of(plate):
    """Placements per row, front to back, as a list of counts."""
    counts = Counter(round(pl.y, 6) for pl in plate.placements)
    return [counts[y] for y in sorted(counts)]


# --- Input values ---------------------------------------------------------


def test_values_are_frozen():
    piece = Piece("a", HexFootprint(16), "neutral")
    with pytest.raises(dataclasses.FrozenInstanceError):
        piece.id = "b"
    with pytest.raises(dataclasses.FrozenInstanceError):
        piece.footprint.side = 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        CircleFootprint(12).diameter = 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        RectFootprint(1, 2).width = 3


def test_hex_footprint_dimensions_match_the_tile():
    fp = HexFootprint(16)
    assert round(fp.width, 2) == 27.71
    assert round(fp.depth, 2) == 32.00


def test_hex_outline_is_the_hex_corners_moved_to_the_center():
    fp = HexFootprint(16)
    expected = [(x + 50, y + 70) for x, y in Hex(0, 0).corners(16)]
    assert fp.outline(50, 70) == tuple(expected)
    xs = [x for x, _ in fp.outline(0, 0)]
    ys = [y for _, y in fp.outline(0, 0)]
    # Corners point to +-y, flats face +-x.
    assert max(ys) == pytest.approx(16) and min(ys) == pytest.approx(-16)
    assert max(xs) == pytest.approx(fp.width / 2)


@pytest.mark.parametrize("bad", [0, -1, math.inf, -math.inf, math.nan])
def test_bad_sizes_are_rejected(bad):
    with pytest.raises(ValueError, match="side"):
        HexFootprint(bad)
    with pytest.raises(ValueError, match="diameter"):
        CircleFootprint(bad)
    with pytest.raises(ValueError, match="width"):
        RectFootprint(bad, 10)
    with pytest.raises(ValueError, match="depth"):
        RectFootprint(10, bad)
    with pytest.raises(ValueError, match="bed width"):
        layout_plates([], bed=(bad, 256))
    with pytest.raises(ValueError, match="bed depth"):
        layout_plates([], bed=(256, bad))


@pytest.mark.parametrize("bad", [-1, math.inf, math.nan])
def test_bad_margin_and_gap_are_rejected(bad):
    with pytest.raises(ValueError, match="margin"):
        layout_plates([], margin=bad)
    with pytest.raises(ValueError, match="gap"):
        layout_plates([], gap=bad)


def test_zero_margin_and_gap_are_allowed():
    pieces = hexes(5)
    plates = layout_plates(pieces, margin=0, gap=0)
    check_plates(pieces, plates, margin=0, gap=0)


@pytest.mark.parametrize("bed, margin", [((10, 256), 5), ((256, 8), 4), ((256, 256), 128)])
def test_bed_with_no_room_inside_the_margins_is_rejected(bed, margin):
    with pytest.raises(ValueError, match="no room"):
        layout_plates([], bed=bed, margin=margin)


def test_empty_id_is_rejected():
    with pytest.raises(ValueError, match="id"):
        Piece("", HexFootprint(16), "neutral")


def test_duplicate_id_is_rejected():
    pieces = [Piece("x", HexFootprint(16), "a"), Piece("x", CircleFootprint(12), "b")]
    with pytest.raises(ValueError, match="'x'"):
        layout_plates(pieces)


# --- Output shape ---------------------------------------------------------


def test_empty_list_gives_zero_plates():
    assert layout_plates([]) == []


def test_plates_are_numbered_and_carry_their_color_group():
    plates = layout_plates(hexes(70) + circles(3))
    assert [p.number for p in plates] == [1, 2, 3]
    assert [p.color_group for p in plates] == ["neutral", "neutral", "red"]
    assert all(isinstance(p, Plate) for p in plates)
    for plate in plates:
        for pl in plate.placements:
            assert isinstance(pl, Placement)
            assert pl.rotation == 0


def test_same_input_gives_the_same_layout():
    pieces = hexes(80) + circles(10) + rects(4) + circles(3, color="blue", prefix="b")
    assert layout_plates(pieces) == layout_plates(list(pieces))


def test_piece_too_big_for_an_empty_plate_names_the_piece():
    pieces = hexes(2) + [Piece("giant", HexFootprint(130), "neutral")]
    with pytest.raises(ValueError, match="'giant'"):
        layout_plates(pieces)
    with pytest.raises(ValueError, match="'wide'"):
        layout_plates([Piece("wide", RectFootprint(247, 10), "x")])
    # Exactly the room inside the margins still fits.
    plates = layout_plates([Piece("snug", RectFootprint(246, 246), "x")])
    assert plates[0].placements[0] == Placement("snug", 128, 128, 0)


# --- Grid rules -----------------------------------------------------------


def test_hex_grid_starts_front_left_and_fills_rows_in_input_order():
    plate = layout_plates(hexes(68))[0]
    pitch = 16 + GAP / math.sqrt(3)
    step_x = math.sqrt(3) * pitch
    width = math.sqrt(3) * 16
    first = plate.placements[0]
    assert (first.x, first.y) == pytest.approx((MARGIN + width / 2, MARGIN + 16))
    # Row 0 (front, unshifted) holds h0..h7, left to right.
    for c in range(8):
        pl = plate.placements[c]
        assert pl.piece_id == f"h{c}"
        assert (pl.x, pl.y) == pytest.approx((first.x + c * step_x, first.y))
    # Row 1 is shifted by half a step and sits further back.
    second_row = plate.placements[8]
    assert second_row.piece_id == "h8"
    assert second_row.x == pytest.approx(first.x + step_x / 2)
    assert second_row.y == pytest.approx(first.y + 1.5 * pitch)
    # Row 2 is not shifted again.
    assert plate.placements[15].x == pytest.approx(first.x)


def test_hex_centers_come_from_hex_to_pixel():
    plate = layout_plates(hexes(68))[0]
    pitch = 16 + GAP / math.sqrt(3)
    x0, y0 = plate.placements[0].x, plate.placements[0].y
    i = 0
    for r, n in enumerate([8, 7] * 4 + [8]):
        for c in range(n):
            px, py = Hex(c - r // 2, r).to_pixel(pitch)
            pl = plate.placements[i]
            assert (pl.x, pl.y) == pytest.approx((x0 + px, y0 + py))
            i += 1


def test_neighboring_hexes_are_exactly_gap_apart():
    pieces = hexes(68)
    plates = layout_plates(pieces)
    assert check_plates(pieces, plates) == pytest.approx(GAP, abs=TOL)
    # Slanted neighbors (first row and the shifted row) are exactly gap apart
    # even though their bounding boxes overlap.
    by_id = {p.id: p for p in pieces}
    a, b = plates[0].placements[0], plates[0].placements[8]
    assert b.y - a.y < 32  # bounding boxes overlap in y
    assert abs(b.x - a.x) < 27.72  # and in x
    d = clearance(by_id[a.piece_id].footprint, (a.x, a.y), by_id[b.piece_id].footprint, (b.x, b.y))
    assert d == pytest.approx(GAP, abs=TOL)


def test_square_grid_cells_are_bounding_box_plus_gap():
    plate = layout_plates(rects(5, width=20, depth=10))[0]
    xs = [pl.x for pl in plate.placements[:3]]
    assert xs == pytest.approx([MARGIN + 10, MARGIN + 10 + 23, MARGIN + 10 + 46])
    assert plate.placements[0].y == pytest.approx(MARGIN + 5)


def test_smaller_pieces_sit_centered_in_cells_sized_to_the_largest():
    mixed_hexes = [
        Piece("small", HexFootprint(10), "n"),
        Piece("big", HexFootprint(18), "n"),
        Piece("mid", HexFootprint(14), "n"),
    ]
    same = [Piece(p.id, HexFootprint(18), "n") for p in mixed_hexes]
    assert layout_plates(mixed_hexes) == layout_plates(same)
    check_plates(mixed_hexes, layout_plates(mixed_hexes))

    square = [
        Piece("coin", CircleFootprint(12), "n"),
        Piece("bar", RectFootprint(30, 8), "n"),
        Piece("block", RectFootprint(10, 20), "n"),
    ]
    plates = layout_plates(square)
    cell = [Piece(p.id, RectFootprint(30, 20), "n") for p in square]
    assert plates == layout_plates(cell)
    check_plates(square, plates)


def test_custom_bed_margin_and_gap_are_respected():
    pieces = hexes(40) + circles(30)
    bed, margin, gap = (180, 150), 8, 2
    plates = layout_plates(pieces, bed=bed, margin=margin, gap=gap)
    check_plates(pieces, plates, bed=bed, margin=margin, gap=gap)
    assert sum(len(p.placements) for p in plates) == 70


# --- Grouping and spilling ------------------------------------------------


def test_one_plate_holds_68_hexes_of_16_mm():
    pieces = hexes(68)
    plates = layout_plates(pieces)
    assert len(plates) == 1
    assert rows_of(plates[0]) == [8, 7, 8, 7, 8, 7, 8, 7, 8]
    check_plates(pieces, plates)


def test_69_hexes_spill_onto_a_second_plate():
    pieces = hexes(69)
    plates = layout_plates(pieces)
    assert [len(p.placements) for p in plates] == [68, 1]
    assert plates[1].placements[0].piece_id == "h68"
    # The spilled piece starts the new plate's grid at the front-left cell.
    first = plates[0].placements[0]
    spilled = plates[1].placements[0]
    assert (spilled.x, spilled.y) == (first.x, first.y)
    check_plates(pieces, plates)


def test_one_plate_holds_52_hexes_of_18_mm():
    pieces = hexes(53, side=18)
    plates = layout_plates(pieces)
    assert [len(p.placements) for p in plates] == [52, 1]
    assert rows_of(plates[0]) == [7, 6, 7, 6, 7, 6, 7, 6]
    check_plates(pieces, plates)


def test_one_plate_holds_256_circles_of_12_mm():
    pieces = circles(257)
    plates = layout_plates(pieces)
    assert [len(p.placements) for p in plates] == [256, 1]
    assert rows_of(plates[0]) == [16] * 16
    check_plates(pieces, plates)


def test_every_plate_but_the_last_is_full():
    pieces = hexes(150)
    plates = layout_plates(pieces)
    assert [len(p.placements) for p in plates] == [68, 68, 14]
    ids = [pl.piece_id for p in plates for pl in p.placements]
    assert ids == [p.id for p in pieces]
    check_plates(pieces, plates)


def test_mixed_list_gives_one_plate_per_group_in_first_appearance_order():
    pieces = (
        hexes(10, color="neutral")
        + circles(4, color="red", prefix="red")
        + circles(4, color="blue", prefix="blue")
        + rects(3, color="neutral")
    )
    plates = layout_plates(pieces)
    assert [(p.number, p.color_group) for p in plates] == [
        (1, "neutral"),
        (2, "red"),
        (3, "blue"),
        (4, "neutral"),
    ]
    assert [[pl.piece_id for pl in p.placements] for p in plates] == [
        [f"h{i}" for i in range(10)],
        [f"red{i}" for i in range(4)],
        [f"blue{i}" for i in range(4)],
        [f"r{i}" for i in range(3)],
    ]
    check_plates(pieces, plates)


def test_interleaved_input_keeps_input_order_within_groups():
    pieces = [
        Piece("c1", CircleFootprint(12), "red"),
        Piece("h1", HexFootprint(16), "red"),
        Piece("c2", CircleFootprint(12), "red"),
        Piece("h2", HexFootprint(16), "red"),
    ]
    plates = layout_plates(pieces)
    assert [[pl.piece_id for pl in p.placements] for p in plates] == [["c1", "c2"], ["h1", "h2"]]


# --- Purity ---------------------------------------------------------------


def test_plate_imports_only_the_standard_library_and_hex():
    source = Path(__file__).parent.parent / "acequias" / "plate.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module)
    assert modules <= {"__future__", "math", "dataclasses", "typing", "acequias.hex"}


def test_importing_plate_loads_no_cad_modules():
    code = (
        "import sys, acequias.plate\n"
        "bad = [m for m in sys.modules if m.split('.')[0] in ('build123d', 'trimesh')"
        " or m.startswith('acequias.cad')]\n"
        "assert not bad, bad\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
