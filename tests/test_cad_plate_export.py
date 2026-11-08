import ast
import re
import time
import zipfile
from pathlib import Path

import pytest

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"
pytest.importorskip("build123d", reason=CAD_REASON)
trimesh = pytest.importorskip("trimesh", reason=CAD_REASON)

import numpy as np  # noqa: E402
from build123d import Mesher, Solid, Unit  # noqa: E402

from acequias.cad import plate_export  # noqa: E402
from acequias.cad.pieces import build_piece  # noqa: E402
from acequias.cad.plate_export import (  # noqa: E402
    METADATA_NAMESPACE,
    TESSELLATION_TOLERANCE,
    export_plate,
)
from acequias.model import PieceKind, Terrain  # noqa: E402
from acequias.plate import (  # noqa: E402
    CircleFootprint,
    HexFootprint,
    Piece,
    Placement,
    Plate,
    RectFootprint,
    layout_plates,
)

FLAT_TOLERANCE = 0.01
CURVED = ("owner_token", "grape_cluster", "debt_token")


# --- Helpers -----------------------------------------------------------------


def _bbox(shape):
    box = shape.bounding_box()
    return np.array([box.min.X, box.min.Y, box.min.Z, box.max.X, box.max.Y, box.max.Z])


def _reload(path):
    """Reload ``path`` with build123d's Mesher: (mesher, shapes)."""
    mesher = Mesher()
    shapes = mesher.read(path)
    return mesher, shapes


def _mesh_arrays(mesh):
    """Vertices and triangles of one 3MF mesh object, as numpy arrays."""
    vertices = np.array([v.Coordinates[0:3] for v in mesh.GetVertices()], dtype=float)
    faces = np.array(
        [mesh.GetTriangle(i).Indices[0:3] for i in range(mesh.GetTriangleCount())], dtype=int
    )
    return vertices, faces


def _expected_bbox(solid, placement):
    """The source solid's bbox moved by (x, y, -its min z), for rotation 0."""
    box = _bbox(solid)
    shift = np.array([placement.x, placement.y, -box[2]] * 2)
    return box + shift


def _model_xml(path):
    with zipfile.ZipFile(path) as archive:
        return archive.read("3D/3dmodel.model").decode("utf-8")


def _listing(folder):
    return sorted(p.name for p in folder.iterdir())


# --- Pieces ------------------------------------------------------------------

# Piece id -> (piece type, variant, footprint).
MIXED = {
    "terrain-vineyard-01": ("terrain", Terrain.VINEYARD, HexFootprint(16.0)),
    "terrain-stone-01": ("terrain", Terrain.STONE, HexFootprint(16.0)),
    "canal-straight-03": ("canal", PieceKind.STRAIGHT, HexFootprint(16.0)),
    "canal-claw-01": ("canal", PieceKind.CLAW, HexFootprint(16.0)),
    "floodgate-01": ("floodgate", None, RectFootprint(5.7, 2.0)),
    "owner-token-01": ("owner_token", None, CircleFootprint(7.0)),
    "grape-cluster-01": ("grape_cluster", None, CircleFootprint(14.0)),
    "debt-token-1-01": ("debt_token", 1, CircleFootprint(12.0)),
    "debt-token-5-01": ("debt_token", 5, CircleFootprint(12.0)),
}


@pytest.fixture(scope="module")
def mixed(tmp_path_factory):
    """Every mixed piece laid out by layout_plates, each plate exported and reloaded."""
    solids = {pid: build_piece(kind, variant) for pid, (kind, variant, _) in MIXED.items()}
    pieces = [Piece(pid, fp, "red") for pid, (_, _, fp) in MIXED.items()]
    plates = layout_plates(pieces)
    folder = tmp_path_factory.mktemp("mixed")
    boxes_before = {pid: _bbox(s) for pid, s in solids.items()}
    results = []
    for plate in plates:
        # One mapping for every plate: each plate ignores the other's ids.
        path = export_plate(plate, solids, folder / f"plate-{plate.number}.3mf")
        mesher, shapes = _reload(path)
        results.append((plate, path, mesher, shapes))
    return solids, boxes_before, results


# --- The file ----------------------------------------------------------------


def test_mixed_layout_covers_every_required_piece(mixed):
    _, _, results = mixed
    # Hexes and the square-grid pieces go on separate plates (#18).
    assert len(results) == 2
    placed = [p.piece_id for plate, *_ in results for p in plate.placements]
    assert sorted(placed) == sorted(MIXED)


def test_reload_gives_one_named_object_per_placement_in_order(mixed):
    _, _, results = mixed
    for plate, _, mesher, shapes in results:
        names = [p.piece_id for p in plate.placements]
        assert len(shapes) == len(names)
        assert mesher.mesh_count == len(names)
        assert [s.label for s in shapes] == names
        assert [m["name"] for m in mesher.get_mesh_properties()] == names
        assert all(isinstance(s, Solid) for s in shapes)


def test_unit_is_millimetre(mixed):
    _, _, results = mixed
    for _, path, mesher, _ in results:
        assert mesher.model_unit == Unit.MM
        assert 'unit="millimeter"' in _model_xml(path)


def test_plate_number_and_color_group_are_metadata(mixed):
    _, _, results = mixed
    for plate, _, mesher, _ in results:
        number = mesher.get_meta_data_by_key(METADATA_NAMESPACE, "plate")
        color = mesher.get_meta_data_by_key(METADATA_NAMESPACE, "color_group")
        assert number["value"] == str(plate.number)
        assert color["value"] == "red"


def test_no_colors_or_materials_are_written(mixed):
    _, _, results = mixed
    for _, path, _, shapes in results:
        assert all(s.color is None for s in shapes)
        xml = _model_xml(path)
        assert "basematerials" not in xml
        assert "colorgroup" not in xml
        assert "pid=" not in xml


def test_bounding_boxes_match_the_placed_source_solids(mixed):
    solids, _, results = mixed
    for plate, _, _, shapes in results:
        for placement, shape in zip(plate.placements, shapes):
            kind = MIXED[placement.piece_id][0]
            tolerance = TESSELLATION_TOLERANCE if kind in CURVED else FLAT_TOLERANCE
            expected = _expected_bbox(solids[placement.piece_id], placement)
            np.testing.assert_allclose(
                _bbox(shape), expected, rtol=0, atol=tolerance, err_msg=placement.piece_id
            )


def test_every_object_sits_on_z_zero(mixed):
    _, _, results = mixed
    for _, _, _, shapes in results:
        for shape in shapes:
            assert abs(shape.bounding_box().min.Z) <= FLAT_TOLERANCE, shape.label


def test_every_object_is_a_closed_mesh(mixed):
    _, _, results = mixed
    for _, _, mesher, _ in results:
        for mesh in mesher.meshes:
            vertices, faces = _mesh_arrays(mesh)
            assert trimesh.Trimesh(vertices, faces).is_watertight, mesh.GetName()


def test_all_objects_lie_inside_the_bed(mixed):
    _, _, results = mixed
    for _, _, mesher, _ in results:
        points = np.vstack([_mesh_arrays(m)[0] for m in mesher.meshes])
        assert points[:, 0].min() >= 0 and points[:, 1].min() >= 0
        assert points[:, 0].max() <= 256 and points[:, 1].max() <= 256


def test_source_solids_are_not_changed(mixed):
    solids, boxes_before, _ = mixed
    for pid, solid in solids.items():
        np.testing.assert_array_equal(_bbox(solid), boxes_before[pid])
        assert solid.label != pid


# --- Hand-made plates --------------------------------------------------------


def test_rotation_90_swaps_x_and_y_sizes(tmp_path):
    gate = build_piece("floodgate")
    before = _bbox(gate)
    plate = Plate(
        1,
        "blue",
        (Placement("gate-0", 50.0, 50.0, 0.0), Placement("gate-90", 100.0, 50.0, 90.0)),
    )
    # The same solid object serves both ids.
    path = export_plate(plate, {"gate-0": gate, "gate-90": gate}, tmp_path / "gates.3mf")
    _, shapes = _reload(path)
    flat, turned = (s.bounding_box() for s in shapes)
    assert flat.size.X == pytest.approx(turned.size.Y, abs=FLAT_TOLERANCE)
    assert flat.size.Y == pytest.approx(turned.size.X, abs=FLAT_TOLERANCE)
    assert flat.size.X != pytest.approx(flat.size.Y, abs=1.0)
    # Rotated around the solid's own origin, which sits at (x, y).
    assert turned.center().X == pytest.approx(100.0, abs=FLAT_TOLERANCE)
    assert turned.center().Y == pytest.approx(50.0, abs=FLAT_TOLERANCE)
    assert turned.min.Z == pytest.approx(0.0, abs=FLAT_TOLERANCE)
    np.testing.assert_array_equal(_bbox(gate), before)


def test_lowest_point_goes_to_z_zero_for_a_raised_solid(tmp_path):
    raised = build_piece("floodgate").translate((0, 0, 7.5))
    plate = Plate(1, "blue", (Placement("gate", 40.0, 40.0),))
    _, shapes = _reload(export_plate(plate, {"gate": raised}, tmp_path / "raised.3mf"))
    box = shapes[0].bounding_box()
    assert box.min.Z == pytest.approx(0.0, abs=FLAT_TOLERANCE)
    assert box.max.Z == pytest.approx(1.5, abs=FLAT_TOLERANCE)


def _hex_plate(count):
    pieces = [Piece(f"terrain-{i:02d}", HexFootprint(16.0), "green") for i in range(count)]
    plates = layout_plates(pieces)
    assert len(plates) == 1
    return plates[0], {p.id: build_piece("terrain", Terrain.EMPTY) for p in pieces}


def test_export_is_deterministic(tmp_path):
    plate, solids = _hex_plate(4)
    solids["canal-straight-01"] = build_piece("canal", PieceKind.STRAIGHT)
    plate = Plate(1, "green", (*plate.placements, Placement("canal-straight-01", 128.0, 128.0)))
    runs = []
    for name in ("a.3mf", "b.3mf"):
        path = export_plate(plate, solids, tmp_path / name)
        mesher, shapes = _reload(path)
        uuids = sorted(re.findall(r'UUID="([^"]+)"', _model_xml(path)))
        runs.append(
            (
                [s.label for s in shapes],
                mesher.triangle_counts,
                [tuple(np.round(_bbox(s), 6)) for s in shapes],
                [m["uuid"] for m in mesher.get_mesh_properties()],
                uuids,
            )
        )
    assert runs[0] == runs[1]
    # Every object, item, and component has a UUID, and none is repeated.
    assert len(runs[0][4]) == len(set(runs[0][4]))


def test_full_plate_of_68_hexes_exports_and_reloads(tmp_path):
    plate, solids = _hex_plate(68)
    assert len(plate.placements) == 68
    start = time.perf_counter()
    path = export_plate(plate, solids, tmp_path / "full.3mf")
    elapsed = time.perf_counter() - start
    mesher, shapes = _reload(path)
    assert [s.label for s in shapes] == [p.piece_id for p in plate.placements]
    assert mesher.model_unit == Unit.MM
    points = np.vstack([_mesh_arrays(m)[0] for m in mesher.meshes])
    assert points[:, :2].min() >= 0 and points[:, :2].max() <= 256
    assert abs(points[:, 2].min()) <= FLAT_TOLERANCE
    print(f"\n68-hex plate: {path.stat().st_size} bytes, exported in {elapsed:.2f} s")


# --- Paths -------------------------------------------------------------------


def test_returns_the_path_creates_parents_and_accepts_str(tmp_path):
    plate, solids = _hex_plate(1)
    target = tmp_path / "out" / "deeper" / "plate.3mf"
    result = export_plate(plate, solids, str(target))
    assert result == target
    assert target.is_file()
    assert _listing(target.parent) == ["plate.3mf"]


def test_overwrites_an_existing_file(tmp_path):
    plate, solids = _hex_plate(1)
    target = tmp_path / "plate.3mf"
    target.write_bytes(b"old")
    export_plate(plate, solids, target)
    assert target.read_bytes() != b"old"
    assert zipfile.is_zipfile(target)
    assert _listing(tmp_path) == ["plate.3mf"]


# --- Errors ------------------------------------------------------------------


def _hex():
    return build_piece("terrain", Terrain.EMPTY)


@pytest.mark.parametrize(
    "plate, solids, name, match",
    [
        pytest.param(Plate(3, "red", ()), {"a": None}, "p.3mf", "no placements", id="empty"),
        pytest.param(
            Plate(1, "red", (Placement("hex-1", 50, 50), Placement("hex-2", 90, 50))),
            {"hex-1": "hex"},
            "p.3mf",
            "'hex-2'",
            id="missing-solid",
        ),
        pytest.param(
            Plate(1, "red", (Placement("hex-1", 5, 50),)),
            {"hex-1": "hex"},
            "p.3mf",
            "'hex-1' sticks out",
            id="off-left",
        ),
        pytest.param(
            Plate(1, "red", (Placement("hex-1", 50, 250),)),
            {"hex-1": "hex"},
            "p.3mf",
            "'hex-1' sticks out",
            id="off-back",
        ),
        pytest.param(
            Plate(1, "red", (Placement("hex-1", 50, 50),)),
            {"hex-1": "hex"},
            "plate.stl",
            "plate.stl",
            id="not-3mf",
        ),
    ],
)
def test_errors_raise_and_write_nothing(tmp_path, plate, solids, name, match):
    solids = {k: (_hex() if v == "hex" else v) for k, v in solids.items()}
    target = tmp_path / name
    with pytest.raises(ValueError, match=match):
        export_plate(plate, solids, target)
    assert _listing(tmp_path) == []


def test_failed_export_leaves_an_existing_file_unchanged(tmp_path):
    target = tmp_path / "plate.3mf"
    target.write_bytes(b"old")
    plate = Plate(1, "red", (Placement("hex-1", 5, 50),))
    with pytest.raises(ValueError, match="hex-1"):
        export_plate(plate, {"hex-1": _hex()}, target)
    assert target.read_bytes() == b"old"
    assert _listing(tmp_path) == ["plate.3mf"]


def test_failed_write_leaves_no_temporary_file(tmp_path, monkeypatch):
    target = tmp_path / "plate.3mf"
    target.write_bytes(b"old")
    plate, solids = _hex_plate(1)

    def broken_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(plate_export.os, "replace", broken_replace)
    with pytest.raises(OSError, match="disk full"):
        export_plate(plate, solids, target)
    assert target.read_bytes() == b"old"
    assert _listing(tmp_path) == ["plate.3mf"]


def test_a_piece_id_twice_on_a_plate_is_rejected(tmp_path):
    plate = Plate(1, "red", (Placement("hex-1", 50, 50), Placement("hex-1", 90, 50)))
    with pytest.raises(ValueError, match="'hex-1'"):
        export_plate(plate, {"hex-1": _hex()}, tmp_path / "p.3mf")
    assert _listing(tmp_path) == []


@pytest.mark.parametrize("bed", [(0, 256), (256,), (256, float("nan")), "big"])
def test_a_bad_bed_is_rejected(tmp_path, bed):
    plate, solids = _hex_plate(1)
    with pytest.raises(ValueError, match="bed"):
        export_plate(plate, solids, tmp_path / "p.3mf", bed=bed)
    assert _listing(tmp_path) == []


def test_a_smaller_bed_rejects_a_piece_beyond_it(tmp_path):
    plate = Plate(1, "red", (Placement("hex-1", 100, 100),))
    with pytest.raises(ValueError, match="'hex-1' sticks out"):
        export_plate(plate, {"hex-1": _hex()}, tmp_path / "p.3mf", bed=(110, 256))


# --- Imports -----------------------------------------------------------------


def test_plate_export_does_not_import_the_server():
    tree = ast.parse(Path(plate_export.__file__).read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")
    assert "acequias.plate" in imported
    assert not any(name == "server" or name.startswith("server.") for name in imported)
