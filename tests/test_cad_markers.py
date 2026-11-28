"""Rules v3 pieces part A (#200): bundled font, vineyard cluster, bodega token, set counts."""

import importlib.util
import math
from collections import Counter
from importlib.resources import files

import pytest

from acequias.cad.footprints import piece_footprint
from acequias.cad.piece_set import (
    BODEGAS_PER_PLAYER,
    CLUSTER_COLORS,
    CLUSTERS_PER_VARIETAL,
    OWNER_PEGS_PER_PLAYER,
    cluster_entries,
    player_entries,
)
from acequias.model import Varietal
from acequias.plate import CircleFootprint, Piece, RectFootprint, layout_plates
from server.schemas import PlateEntryJSON, piece_params, piece_variant

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"

# --- Set counts (no CAD) ------------------------------------------------------


def test_a_set_has_20_clusters_three_of_each_common_varietal():
    assert sum(CLUSTERS_PER_VARIETAL.values()) == 20
    assert set(CLUSTERS_PER_VARIETAL) == set(Varietal)
    assert CLUSTERS_PER_VARIETAL[Varietal.BONARDA] == 1
    assert CLUSTERS_PER_VARIETAL[Varietal.CABERNET_FRANC] == 1
    others = set(Varietal) - {Varietal.BONARDA, Varietal.CABERNET_FRANC}
    assert all(CLUSTERS_PER_VARIETAL[v] == 3 for v in others)


def test_every_varietal_has_one_of_the_three_cluster_colors():
    assert list(CLUSTER_COLORS) == ["violet", "red", "fluorescent_green"]
    listed = [v for varietals in CLUSTER_COLORS.values() for v in varietals]
    assert sorted(listed, key=str) == sorted(Varietal, key=str)
    per_color = {
        color: sum(CLUSTERS_PER_VARIETAL[v] for v in varietals)
        for color, varietals in CLUSTER_COLORS.items()
    }
    assert per_color == {"violet": 7, "red": 7, "fluorescent_green": 6}


def test_pegs_and_bodega_per_player():
    assert OWNER_PEGS_PER_PLAYER == 28
    assert BODEGAS_PER_PLAYER == 1
    entries = player_entries("blue")
    assert [(e["piece"]["type"], e["count"], e["color"]) for e in entries] == [
        ("owner_token", 28, "blue"),
        ("bodega_token", 1, "blue"),
    ]


def _layout(raw_entries):
    pieces = []
    for n, raw in enumerate(raw_entries):
        entry = PlateEntryJSON.model_validate(raw)
        params = piece_params(entry.piece)
        footprint = piece_footprint(entry.piece.type, piece_variant(entry.piece), **params)
        pieces += [Piece(f"{n}-{i}", footprint, entry.color) for i in range(entry.count)]
    return layout_plates(pieces)


def test_a_full_set_lays_out_one_plate_per_color():
    raw = cluster_entries() + player_entries("blue") + player_entries("orange")
    plates = _layout(raw)
    assert [plate.color_group for plate in plates] == [
        "violet", "red", "fluorescent_green", "blue", "orange"
    ]
    counts = {plate.color_group: len(plate.placements) for plate in plates}
    assert counts == {"violet": 7, "red": 7, "fluorescent_green": 6, "blue": 29, "orange": 29}


def test_footprints_of_the_new_pieces():
    assert piece_footprint("vineyard_cluster", Varietal.MALBEC, base_diameter=13.0) == (
        RectFootprint(13.0, 9.75)
    )
    assert piece_footprint("bodega_token", base_diameter=13.0) == CircleFootprint(13.0)


# --- CAD ------------------------------------------------------------------------

cad = pytest.mark.skipif(
    not all(importlib.util.find_spec(m) for m in ("build123d", "trimesh")), reason=CAD_REASON
)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    """Solids and reloaded STL meshes, built once and cached by name."""
    trimesh = pytest.importorskip("trimesh", reason=CAD_REASON)
    from acequias.cad.hex_tile import export_stl
    from acequias.cad.markers import bodega_token, vineyard_cluster

    folder = tmp_path_factory.mktemp("markers")
    cache = {}

    def get(name):
        if name not in cache:
            if name == "bodega":
                solid = bodega_token()
            else:
                solid = vineyard_cluster(Varietal[name])
            mesh = trimesh.load_mesh(export_stl(solid, folder / f"{name}.stl"))
            cache[name] = (solid, mesh)
        return cache[name]

    return get


def _overhang(mesh):
    """Area and centers of faces steeper than 45 degrees down, off the bed."""
    down = mesh.face_normals[:, 2] < -0.71
    centers = mesh.triangles_center[down]
    off_bed = centers[:, 2] > 0.001
    return mesh.area_faces[down][off_bed].sum(), centers[off_bed]


@cad
def test_font_file_and_license_are_bundled():
    from acequias.cad.text import FONT_FILE, font_path

    assert font_path().is_file()
    assert font_path().name == FONT_FILE
    license_text = (files("acequias.cad") / "fonts" / "OFL.txt").read_text(encoding="utf-8")
    assert "SIL Open Font License" in license_text


@cad
def test_text_faces_are_centered_and_scale_with_the_size():
    from build123d import Compound

    from acequias.cad.text import text_faces

    small = Compound(text_faces("CS", 5.0)).bounding_box()
    large = Compound(text_faces("CS", 10.0)).bounding_box()
    assert small.center().X == pytest.approx(0, abs=1e-6)
    assert small.center().Y == pytest.approx(0, abs=1e-6)
    assert large.size.X == pytest.approx(2 * small.size.X, rel=1e-3)
    assert 2.5 < small.size.Y < 4.5  # capitals about 0.66 em
    # An "o" keeps its hole: the face has an inner wire.
    assert any(face.inner_wires() for face in text_faces("o", 5.0))


@cad
@pytest.mark.parametrize("text, size", [("", 5.0), ("  ", 5.0), ("Ma", 0), ("Ma", -1), ("Ma", True)])
def test_text_faces_rejects_bad_input(text, size):
    from acequias.cad.text import text_faces

    with pytest.raises(ValueError):
        text_faces(text, size)


@cad
def test_text_faces_never_use_a_system_font(monkeypatch):
    from build123d import Compound

    import acequias.cad.text as text

    monkeypatch.setattr(Compound, "resolve_font", staticmethod(lambda *a: ("Arial", "C:/arial.ttf", None)))
    with pytest.raises(RuntimeError, match="bundled"):
        text.text_faces("Ma", 5.0)


@cad
@pytest.mark.parametrize("name", [v.name for v in Varietal])
def test_vineyard_cluster_prints_for_every_varietal(built, name):
    from acequias.cad.markers import CLUSTER_FLAT_RATIO, INITIALS_DEPTH

    solid, mesh = built(name)
    assert solid.is_valid
    assert mesh.is_watertight
    assert len(mesh.split(only_watertight=False)) == 1
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds
    assert x1 - x0 == pytest.approx(13.0, abs=0.05)
    assert y1 - y0 == pytest.approx(13.0 * CLUSTER_FLAT_RATIO, abs=0.05)
    assert (z0, z1) == pytest.approx((0.0, 13.0), abs=1e-3)
    assert (x0 + x1) / 2 == pytest.approx(0, abs=0.05)
    assert (y0 + y1) / 2 == pytest.approx(0, abs=0.05)
    # Only the tops of the debossed letters, in the flat sides, bridge.
    area, centers = _overhang(mesh)
    assert area < 25.0
    flat = 6.5 * CLUSTER_FLAT_RATIO
    assert (abs(centers[:, 1]) >= flat - INITIALS_DEPTH - 0.01).all()


@cad
def test_vineyard_cluster_stands_on_its_small_center_foot(built):
    from acequias.cad.markers import CLUSTER_FOOT_DIAMETER

    _, mesh = built("MALBEC")
    bottom = (mesh.face_normals[:, 2] < -0.99) & (mesh.triangles_center[:, 2] < 0.001)
    contact = mesh.area_faces[bottom].sum()
    assert contact == pytest.approx(math.pi * (CLUSTER_FOOT_DIAMETER / 2) ** 2, rel=0.02)
    rho = (mesh.vertices[:, 0] ** 2 + mesh.vertices[:, 1] ** 2) ** 0.5
    on_bed = mesh.vertices[:, 2] < 0.001
    assert rho[on_bed].max() == pytest.approx(CLUSTER_FOOT_DIAMETER / 2, abs=0.01)


@cad
def test_vineyard_cluster_has_a_flat_top_with_the_owner_peg_hole(built):
    from acequias.cad.channel import HOLE_DEPTH, HOLE_DIAMETER
    from acequias.cad.markers import CLUSTER_TOP_DIAMETER

    solid, mesh = built("SYRAH")
    top = (mesh.face_normals[:, 2] > 0.99) & (mesh.triangles_center[:, 2] > 13.0 - 1e-3)
    ring = math.pi / 4 * (CLUSTER_TOP_DIAMETER**2 - HOLE_DIAMETER**2)
    assert mesh.area_faces[top].sum() == pytest.approx(ring, rel=0.05)
    assert not solid.is_inside((0, 0, 13.0 - HOLE_DEPTH + 0.1))
    assert not solid.is_inside((HOLE_DIAMETER / 2 - 0.05, 0, 13.0 - 0.5))
    assert solid.is_inside((0, 0, 13.0 - HOLE_DEPTH - 0.1))
    assert solid.is_inside((HOLE_DIAMETER / 2 + 0.1, 0, 13.0 - 0.5))


@cad
def test_vineyard_cluster_initials_are_debossed_on_both_flat_sides(built):
    from acequias.cad.markers import CLUSTER_FLAT_RATIO, INITIALS_DEPTH, VARIETAL_INITIALS

    assert sorted(VARIETAL_INITIALS.values()) == sorted(
        ["Ma", "Sy", "Bo", "CS", "Me", "CF", "To", "Ch"]
    )
    solid, mesh = built("CABERNET_SAUVIGNON")
    flat = 6.5 * CLUSTER_FLAT_RATIO
    # Letter floors: faces parallel to each flat side, INITIALS_DEPTH inside it.
    for sign in (-1, 1):
        floor = (mesh.face_normals[:, 1] * sign > 0.99) & (
            abs(abs(mesh.triangles_center[:, 1]) - (flat - INITIALS_DEPTH)) < 0.01
        )
        floor &= mesh.triangles_center[:, 1] * sign > 0
        assert mesh.area_faces[floor].sum() > 3.0
    # Different initials cut different amounts.
    volumes = {name: built(name)[0].volume for name in ("CABERNET_SAUVIGNON", "MALBEC", "MERLOT")}
    assert len({round(v, 2) for v in volumes.values()}) == 3


@cad
def test_vineyard_cluster_other_size_scales():
    from acequias.cad.markers import vineyard_cluster

    box = vineyard_cluster(Varietal.TORRONTES, base_diameter=16.0, height=15.0).bounding_box()
    assert (box.size.X, box.size.Y, box.size.Z) == pytest.approx((16.0, 12.0, 15.0), abs=0.05)


@cad
@pytest.mark.parametrize(
    "args, kwargs, name",
    [
        (("malbec",), {}, "varietal"),
        ((None,), {}, "varietal"),
        ((Varietal.MALBEC,), {"base_diameter": 10.9}, "base_diameter"),
        ((Varietal.MALBEC,), {"base_diameter": 21}, "base_diameter"),
        ((Varietal.MALBEC,), {"base_diameter": math.nan}, "base_diameter"),
        ((Varietal.MALBEC,), {"height": 9.9}, "height"),
        ((Varietal.MALBEC,), {"height": 21}, "height"),
        ((Varietal.MALBEC,), {"height": True}, "height"),
    ],
)
def test_vineyard_cluster_rejects_bad_values(args, kwargs, name):
    from acequias.cad.markers import vineyard_cluster

    with pytest.raises(ValueError, match=name):
        vineyard_cluster(*args, **kwargs)


@cad
def test_bodega_token_prints_and_differs_from_the_cluster(built):
    solid, mesh = built("bodega")
    assert solid.is_valid
    assert mesh.is_watertight
    assert len(mesh.split(only_watertight=False)) == 1
    (x0, y0, z0), (x1, y1, z1) = mesh.bounds
    assert (x1 - x0, y1 - y0, z1 - z0) == pytest.approx((13.0, 13.0, 12.0), abs=0.05)
    assert z0 == pytest.approx(0, abs=1e-6)
    # Only the crowns of the two arched doors bridge.
    area, centers = _overhang(mesh)
    assert area < 5.0
    assert (abs(centers[:, 0]) > 4.0).all()
    # It sits on its whole base, unlike the cluster on its foot.
    bottom = (mesh.face_normals[:, 2] < -0.99) & (mesh.triangles_center[:, 2] < 0.001)
    assert mesh.area_faces[bottom].sum() == pytest.approx(math.pi * 6.5**2, rel=0.02)
    # The vault: the top is a ridge along x, not a flat top.
    top = mesh.vertices[mesh.vertices[:, 2] > 11.9]
    assert top[:, 0].max() - top[:, 0].min() > 9.0
    assert top[:, 1].max() - top[:, 1].min() < 2.0


@cad
@pytest.mark.parametrize(
    "kwargs, name",
    [
        ({"base_diameter": 9.9}, "base_diameter"),
        ({"base_diameter": 26}, "base_diameter"),
        ({"height": 5.0}, "height"),
        ({"height": 27.0}, "height"),
        ({"height": -1}, "height"),
    ],
)
def test_bodega_token_rejects_bad_values(kwargs, name):
    from acequias.cad.markers import bodega_token

    with pytest.raises(ValueError, match=name):
        bodega_token(**kwargs)


@cad
def test_registry_builds_the_new_pieces():
    from acequias.cad.pieces import PIECE_TYPES, build_piece

    assert PIECE_TYPES[-2:] == ("vineyard_cluster", "bodega_token")
    with pytest.raises(ValueError, match="needs its variant"):
        build_piece("vineyard_cluster")
    with pytest.raises(ValueError, match="no variant"):
        build_piece("bodega_token", "x")


def test_entries_count_every_cluster_by_color():
    totals = Counter()
    for entry in cluster_entries():
        PlateEntryJSON.model_validate(entry)
        totals[entry["color"]] += entry["count"]
    assert totals == {"violet": 7, "red": 7, "fluorescent_green": 6}
