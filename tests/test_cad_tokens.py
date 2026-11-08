import math
import subprocess
import sys
import textwrap

import pytest

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"
pytest.importorskip("build123d", reason=CAD_REASON)
trimesh = pytest.importorskip("trimesh", reason=CAD_REASON)

import numpy as np  # noqa: E402
from build123d import Axis, GeomType, Solid  # noqa: E402
from OCP.BRepAdaptor import BRepAdaptor_Surface  # noqa: E402

from acequias.cad.hex_tile import export_stl, hex_tile  # noqa: E402
from acequias.cad.tokens import (  # noqa: E402
    MIN_GRAPE_DIAMETER,
    MIN_GRAPE_TIERS,
    PIP_DEPTH,
    PIP_DIAMETER,
    debt_token,
    grape_cluster,
    grape_radius,
    pip_positions,
)

# (name, builder, footprint diameter, height, z tolerance of the bbox)
PIECES = {
    "grape": (lambda: grape_cluster(), 14.0, 15.0, 0.05),
    "debt1": (lambda: debt_token(1), 12.0, 2.0, 0.01),
    "debt5": (lambda: debt_token(5), 12.0, 2.0, 0.01),
}
# Other grape sizes across the allowed range: the smallest base and height,
# the tallest for the smallest base, a wide one, exactly 1.5 x the base.
GRAPE_SIZES = [(8, 6), (8, 12), (20, 10), (10, 15)]
GAME_MODULES = (
    "acequias.hex",
    "acequias.model",
    "acequias.config",
    "acequias.flow",
    "acequias.board",
    "acequias.assembly",
    "acequias.scoring",
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Each piece's solid and its STL reloaded with trimesh, built once."""
    folder = tmp_path_factory.mktemp("tokens")
    out = {}
    for name, (build, *_rest) in PIECES.items():
        solid = build()
        mesh = trimesh.load_mesh(export_stl(solid, folder / f"{name}.stl"))
        out[name] = (solid, mesh)
    return out


@pytest.fixture(scope="module")
def grape_sizes(tmp_path_factory):
    """A function giving the solid and reloaded STL of a grape size, cached."""
    folder = tmp_path_factory.mktemp("grapes")
    cache = {}

    def get(size):
        if size not in cache:
            solid = grape_cluster(*size)
            path = folder / f"grape_{size[0]}x{size[1]}.stl"
            cache[size] = (solid, trimesh.load_mesh(export_stl(solid, path)))
        return cache[size]

    return get


def _check_printable(mesh, footprint):
    """The shared mesh checks: one watertight body, no supports, footprint."""
    assert mesh.is_watertight
    assert len(mesh.split(only_watertight=False)) == 1
    down = mesh.face_normals[:, 2] < -0.71
    assert down.any()
    down_z = mesh.vertices[mesh.faces[down]][..., 2]
    assert np.abs(down_z).max() <= 0.001
    rho = np.hypot(mesh.vertices[:, 0], mesh.vertices[:, 1])
    assert rho.max() <= footprint / 2 + 0.01


def _check_bbox(mesh, footprint, height, z_tol):
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds
    assert x1 - x0 == pytest.approx(footprint, abs=0.05)
    assert y1 - y0 == pytest.approx(footprint, abs=0.05)
    assert z1 - z0 == pytest.approx(height, abs=z_tol)
    assert z0 == pytest.approx(0.0, abs=1e-6)
    assert (x0 + x1) / 2 == pytest.approx(0.0, abs=0.05)
    assert (y0 + y1) / 2 == pytest.approx(0.0, abs=0.05)


# Frame and shared checks


@pytest.mark.parametrize("name", PIECES)
def test_piece_is_one_valid_solid(built, name):
    solid, _ = built[name]
    assert isinstance(solid, Solid)
    assert solid.is_valid


@pytest.mark.parametrize("name", PIECES)
def test_stl_is_one_watertight_body_without_supports_inside_footprint(built, name):
    _, footprint, _, _ = PIECES[name]
    _check_printable(built[name][1], footprint)


@pytest.mark.parametrize("name", PIECES)
def test_bounding_box_is_centered_on_z_zero(built, name):
    _, footprint, height, z_tol = PIECES[name]
    _check_bbox(built[name][1], footprint, height, z_tol)


@pytest.mark.parametrize("size", GRAPE_SIZES)
def test_grape_cluster_other_sizes_print(grape_sizes, size):
    base_diameter, height = size
    mesh = grape_sizes(size)[1]
    _check_printable(mesh, base_diameter)
    _check_bbox(mesh, base_diameter, height, 0.05)


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf, 0, -1])
@pytest.mark.parametrize(
    ("build", "name"),
    [
        (lambda v: grape_cluster(base_diameter=v), "base_diameter"),
        (lambda v: grape_cluster(height=v), "height"),
        (lambda v: debt_token(1, diameter=v), "diameter"),
        (lambda v: debt_token(5, diameter=v), "diameter"),
        (lambda v: debt_token(1, thickness=v), "thickness"),
        (lambda v: debt_token(5, thickness=v), "thickness"),
    ],
)
def test_sizes_not_finite_or_not_positive_raise_naming_them(build, name, value):
    with pytest.raises(ValueError, match=name):
        build(value)


# Grape cluster


def _spheres(solid):
    """(x, y, z, radius) of every distinct grape sphere."""
    found = {}
    for face in solid.faces():
        if face.geom_type != GeomType.SPHERE:
            continue
        sphere = BRepAdaptor_Surface(face.wrapped).Sphere()
        c = sphere.Location()
        key = (round(c.X(), 3), round(c.Y(), 3), round(c.Z(), 3))
        found[key] = sphere.Radius()
    return [(*k, r) for k, r in found.items()]


def test_grapes_are_at_least_2_mm_across():
    assert MIN_GRAPE_DIAMETER == 2.0
    for size in [(14, 15), (8, 6), (8, 12), (100, 6), (8, 8)]:
        assert 2 * grape_radius(*size) >= MIN_GRAPE_DIAMETER


def test_every_grape_sphere_is_at_least_2_mm(built):
    spheres = _spheres(built["grape"][0])
    assert len(spheres) > 10
    for *_center, radius in spheres:
        assert 2 * radius >= MIN_GRAPE_DIAMETER


@pytest.mark.parametrize("size", [None] + GRAPE_SIZES)
def test_grapes_stack_in_tiers_widest_at_the_bottom(built, grape_sizes, size):
    solid = built["grape"][0] if size is None else grape_sizes(size)[0]
    centers = _spheres(solid)
    tiers = {}
    for x, y, z, r in centers:
        tiers.setdefault(round(z, 2), []).append(math.hypot(x, y) + r)
    assert len(tiers) >= MIN_GRAPE_TIERS
    widths = [max(tiers[z]) for z in sorted(tiers)]
    assert widths == sorted(widths, reverse=True)
    assert widths[0] > widths[1]
    # A ring of several grapes at the bottom, a single grape on top.
    assert len(tiers[min(tiers)]) > 1
    assert len(tiers[max(tiers)]) == 1


def test_bottom_faces_form_a_full_disc(built):
    mesh = built["grape"][1]
    on_plate = np.all(np.abs(mesh.vertices[mesh.faces][..., 2]) <= 0.001, axis=1)
    area = mesh.area_faces[on_plate].sum()
    assert area == pytest.approx(math.pi * 7.0**2, rel=0.01)


def test_center_of_mass_is_over_the_base(built):
    x, y, _ = built["grape"][1].center_mass
    assert abs(x) <= 14 / 4
    assert abs(y) <= 14 / 4


def test_base_fits_on_a_vineyard_tile_with_1_mm_to_spare(built):
    tile = hex_tile(16, 4, 0.2)
    top = tile.faces().sort_by(Axis.Z)[-1]
    corners = [(v.X, v.Y) for v in top.vertices()]
    base_radius = built["grape"][0].bounding_box().size.X / 2
    assert base_radius == pytest.approx(7.0, abs=0.05)
    inscribed = math.sqrt(3) / 2 * (16 - 2 * 0.2 / math.sqrt(3))
    assert inscribed == pytest.approx(13.65, abs=0.01)
    # Distance from the center to each edge line of the tile's outline.
    for i, (ax, ay) in enumerate(corners):
        bx, by = corners[(i + 1) % len(corners)]
        distance = abs(ax * by - ay * bx) / math.hypot(bx - ax, by - ay)
        assert distance == pytest.approx(inscribed, abs=0.01)
        assert distance - base_radius >= 1.0


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"base_diameter": 10, "height": 15.01}, "height"),
        ({"base_diameter": 14, "height": 21.01}, "height"),
        ({"base_diameter": 7.99}, "base_diameter"),
        ({"base_diameter": 4}, "base_diameter"),
        ({"height": 5.99}, "height"),
        ({"height": 1}, "height"),
    ],
)
def test_grape_cluster_limits_raise_naming_the_parameter(kwargs, name):
    with pytest.raises(ValueError, match=name):
        grape_cluster(**kwargs)


# Debt token


def test_pip_constants():
    from acequias.cad import tokens

    assert PIP_DIAMETER == 2
    assert PIP_DEPTH == 0.6
    assert tokens.MIN_DEBT_THICKNESS == pytest.approx(1.4)


def test_pip_positions_are_a_die_face():
    assert pip_positions(1, 12) == [(0.0, 0.0)]
    five = pip_positions(5, 12)
    assert len(five) == 5
    assert (0.0, 0.0) in five
    expected = {(2.4, 2.4), (-2.4, 2.4), (-2.4, -2.4), (2.4, -2.4)}
    actual = {(round(x, 9), round(y, 9)) for x, y in five if (x, y) != (0.0, 0.0)}
    assert actual == expected


OUTER = [(2.4, 2.4), (-2.4, 2.4), (-2.4, -2.4), (2.4, -2.4)]


@pytest.mark.parametrize("value", [1, 5])
def test_probes_find_pips_and_solid_floor(built, value):
    solid = built[f"debt{value}"][0]
    thickness, diameter = 2.0, 12.0
    z_pip = thickness - PIP_DEPTH / 2
    z_floor = thickness - PIP_DEPTH - 0.1
    pips = [(0.0, 0.0)] + (OUTER if value == 5 else [])
    for x, y in pips:
        assert not solid.is_inside((x, y, z_pip)), (x, y)
        assert solid.is_inside((x, y, z_floor)), (x, y)
    if value == 1:
        for x, y in OUTER:
            assert solid.is_inside((x, y, z_pip)), (x, y)
    assert solid.is_inside((0.2 * diameter, 0.0, z_pip))


@pytest.mark.parametrize(("value", "expected"), [(1, 224.31), (5, 216.77)])
def test_volume_is_disc_minus_pips(built, value, expected):
    pips = 1 if value == 1 else 5
    formula = math.pi * 6.0**2 * 2.0 - pips * math.pi * 1.0**2 * PIP_DEPTH
    assert formula == pytest.approx(expected, abs=0.01)
    solid, mesh = built[f"debt{value}"]
    assert solid.volume == pytest.approx(formula, rel=0.005)
    assert mesh.volume == pytest.approx(formula, rel=0.005)


@pytest.mark.parametrize("value", [0, 2, 6, -1, 1.0, "1", True, None, 5.0])
def test_value_must_be_int_1_or_5(value):
    with pytest.raises(ValueError, match="value"):
        debt_token(value)


@pytest.mark.parametrize("value", [1, 5])
@pytest.mark.parametrize(
    ("kwargs", "name", "ok"),
    [
        ({"diameter": 9.89}, "diameter", False),
        ({"diameter": 9.91}, "diameter", True),
        ({"thickness": 1.39}, "thickness", False),
        ({"thickness": 1.41}, "thickness", True),
    ],
)
def test_debt_token_size_limits(value, kwargs, name, ok):
    if ok:
        solid = debt_token(value, **kwargs)
        assert solid.is_valid
    else:
        with pytest.raises(ValueError, match=name):
            debt_token(value, **kwargs)


def test_debt_token_other_size_prints(tmp_path):
    mesh = trimesh.load_mesh(export_stl(debt_token(5, 20, 3), tmp_path / "d.stl"))
    _check_printable(mesh, 20)
    _check_bbox(mesh, 20, 3, 0.01)


# Imports


def test_game_and_server_do_not_load_tokens():
    code = f"""
        import sys
        for name in {GAME_MODULES!r} + ("server", "server.app", "acequias.cad"):
            __import__(name)
        print("acequias.cad.tokens" in sys.modules)
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "False"
