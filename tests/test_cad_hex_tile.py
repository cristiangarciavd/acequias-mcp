import math
import subprocess
import sys
import textwrap

import pytest

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"
pytest.importorskip("build123d", reason=CAD_REASON)
trimesh = pytest.importorskip("trimesh", reason=CAD_REASON)

from build123d import Axis, Box, Solid  # noqa: E402

from acequias.cad.hex_tile import export_stl, hex_tile  # noqa: E402
from acequias.hex import Hex  # noqa: E402

TOL = 0.01
GAME_MODULES = (
    "acequias.hex",
    "acequias.model",
    "acequias.config",
    "acequias.flow",
    "acequias.board",
    "acequias.assembly",
    "acequias.scoring",
)


def _flipped_corners(side):
    return [(x, -y) for x, y in Hex(0, 0).corners(side)]


def _top_corners(tile):
    top = tile.faces().sort_by(Axis.Z)[-1]
    return [(v.X, v.Y, v.Z) for v in top.vertices()]


def _load(path):
    return trimesh.load_mesh(path)


def _run_fresh(code):
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout


# Shape


def test_defaults_are_16_side_4_height_0_clearance():
    tile = hex_tile()
    assert isinstance(tile, Solid)
    assert tile.is_valid
    assert tile.volume == pytest.approx(hex_tile(16, 4, 0).volume)


def test_top_face_corners_match_hex_corners_with_y_flipped():
    side = 16.0
    tile = hex_tile(side)
    actual = _top_corners(tile)
    assert len(actual) == 6
    for z in (p[2] for p in actual):
        assert z == pytest.approx(4.0, abs=TOL)
    for ex, ey in _flipped_corners(side):
        assert any(
            math.hypot(ax - ex, ay - ey) <= TOL for ax, ay, _ in actual
        ), f"no top corner near {(ex, ey)}"
    # Pointy-top, not mirrored: N corner at +y, S corner at -y.
    assert any(math.hypot(x, y - side) <= TOL for x, y, _ in actual)
    assert any(math.hypot(x, y + side) <= TOL for x, y, _ in actual)


def test_edges_face_the_same_directions_as_the_game_model():
    # Corner 0 is ESE and corner 1 is ENE, so edge 0-1 (Direction.E) is
    # the vertical edge at max x; corner 2 is N, at max y.
    corners = _flipped_corners(16.0)
    assert corners[0][1] < 0 < corners[1][1]
    assert corners[0][0] == pytest.approx(corners[1][0])
    assert corners[2] == pytest.approx((0.0, 16.0))
    assert corners[5] == pytest.approx((0.0, -16.0))


def test_tile_is_centered_and_sits_on_z_zero():
    tile = hex_tile(16, 4)
    box = tile.bounding_box()
    assert box.min.X == pytest.approx(-box.max.X, abs=TOL)
    assert box.min.Y == pytest.approx(-box.max.Y, abs=TOL)
    assert box.min.Z == pytest.approx(0.0, abs=TOL)
    assert box.max.Z == pytest.approx(4.0, abs=TOL)
    center = tile.center()
    assert (center.X, center.Y) == pytest.approx((0.0, 0.0), abs=TOL)


def test_clearance_uses_the_corners_of_the_shrunk_hexagon():
    side, clearance = 16.0, 0.2
    inner = side - 2 * clearance / math.sqrt(3)
    actual = _top_corners(hex_tile(side, 4, clearance))
    for ex, ey in _flipped_corners(inner):
        assert any(math.hypot(ax - ex, ay - ey) <= TOL for ax, ay, _ in actual)


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"side": 0}, "side"),
        ({"side": -1}, "side"),
        ({"side": math.nan}, "side"),
        ({"side": math.inf}, "side"),
        ({"height": 0}, "height"),
        ({"height": -4}, "height"),
        ({"height": math.nan}, "height"),
        ({"height": -math.inf}, "height"),
        ({"clearance": -0.1}, "clearance"),
        ({"clearance": math.nan}, "clearance"),
        ({"clearance": math.inf}, "clearance"),
        # Remaining side 16 - 2c/sqrt(3) at or below 0.
        ({"clearance": 8 * math.sqrt(3)}, "clearance"),
        ({"clearance": 20}, "clearance"),
    ],
)
def test_invalid_parameters_raise_value_error_naming_them(kwargs, name):
    with pytest.raises(ValueError, match=name):
        hex_tile(**kwargs)


# Export and checks


def test_export_writes_binary_stl_and_returns_path(tmp_path):
    path = tmp_path / "tile.stl"
    returned = export_stl(hex_tile(), path)
    assert returned == path
    data = path.read_bytes()
    # Binary STL: 80-byte header, uint32 triangle count, 50 bytes each.
    count = int.from_bytes(data[80:84], "little")
    assert count > 0
    assert len(data) == 84 + 50 * count


def test_export_creates_parent_folder_and_accepts_str(tmp_path):
    path = tmp_path / "a" / "b" / "tile.stl"
    returned = export_stl(hex_tile(), str(path))
    assert path.is_file()
    assert returned == path


def test_export_overwrites_an_existing_file(tmp_path):
    path = tmp_path / "tile.stl"
    path.write_bytes(b"old contents")
    export_stl(hex_tile(), path)
    assert _load(path).is_watertight


def test_export_takes_any_build123d_shape(tmp_path):
    path = export_stl(Box(10, 10, 10), tmp_path / "box.stl")
    mesh = _load(path)
    assert mesh.is_watertight
    assert mesh.volume == pytest.approx(1000, rel=1e-6)


@pytest.mark.parametrize(
    ("side", "clearance", "width", "depth"),
    [
        (16, 0, 27.71, 32.00),
        (18, 0, 31.18, 36.00),
        (16, 0.2, 27.71 - 0.40, 32.00 - 0.46),
    ],
)
def test_stl_is_watertight_with_expected_size_and_volume(
    tmp_path, side, clearance, width, depth
):
    height = 4.0
    path = export_stl(hex_tile(side, height, clearance), tmp_path / "tile.stl")
    mesh = _load(path)
    assert mesh.is_watertight
    (min_x, min_y, min_z), (max_x, max_y, max_z) = mesh.bounds
    assert max_x - min_x == pytest.approx(width, abs=TOL)
    assert max_y - min_y == pytest.approx(depth, abs=TOL)
    assert max_z - min_z == pytest.approx(height, abs=TOL)
    assert min_z == pytest.approx(0.0, abs=TOL)
    s = side - 2 * clearance / math.sqrt(3)
    assert mesh.volume == pytest.approx(3 * math.sqrt(3) / 2 * s**2 * height, rel=0.005)


# Import isolation: the game logic stays CAD-free.


def test_game_modules_do_not_load_cad_libraries():
    out = _run_fresh(
        f"""
        import importlib, sys
        for name in {GAME_MODULES!r}:
            importlib.import_module(name)
        print(sorted(m for m in ("build123d", "trimesh") if m in sys.modules))
        """
    )
    assert out.strip() == "[]"


def test_game_and_server_import_without_cad_libraries():
    out = _run_fresh(
        f"""
        import importlib, sys
        sys.modules["build123d"] = None
        sys.modules["trimesh"] = None
        for name in {GAME_MODULES!r} + ("server", "server.app", "acequias.cad"):
            importlib.import_module(name)
        print("ok")
        """
    )
    assert out.strip() == "ok"
