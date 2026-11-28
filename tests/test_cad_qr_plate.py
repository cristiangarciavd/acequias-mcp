"""The QR plate (#196): the stored matrices and the printed plate."""

from importlib.resources import files

import pytest

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"
pytest.importorskip("build123d", reason=CAD_REASON)
trimesh = pytest.importorskip("trimesh", reason=CAD_REASON)

from acequias.cad.hex_tile import export_stl  # noqa: E402
from acequias.cad.qr_plate import (  # noqa: E402
    LABEL_FONT_RATIO,
    MIN_MODULE,
    QR_LABELS,
    QR_LANGUAGES,
    QR_URLS,
    QUIET_ZONE,
    qr_matrix,
    qr_plate,
)
from acequias.cad.text import text_faces  # noqa: E402

VERSION = 4
"""Both URLs (54 and 53 bytes) need QR version 4 at error correction M."""

SIDE = 4 * VERSION + 17 + 2 * QUIET_ZONE
"""Modules across the stored matrix: the version-4 code and its quiet zone."""

FINDER = [
    [1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1],
]


def _header(language):
    text = (files("acequias.cad") / "data" / f"qr_{language}.txt").read_text(encoding="ascii")
    return [line for line in text.splitlines() if line.startswith("#")]


@pytest.mark.parametrize("language", QR_LANGUAGES)
def test_matrix_is_square_with_the_version_4_module_count(language):
    matrix = qr_matrix(language)
    assert len(matrix) == SIDE == 41
    assert all(len(row) == SIDE for row in matrix)
    # URL length fits version 4 at M (62 bytes) but not version 3 (42 bytes).
    assert 42 < len(QR_URLS[language].encode()) <= 62


@pytest.mark.parametrize("language", QR_LANGUAGES)
def test_matrix_has_its_quiet_zone_and_finder_patterns(language):
    matrix = qr_matrix(language)
    q = QUIET_ZONE
    for i, row in enumerate(matrix):
        for j, dark in enumerate(row):
            if min(i, j) < q or max(i, j) >= SIDE - q:
                assert not dark, (i, j)
    code = SIDE - 2 * q
    for top, left in ((q, q), (q, q + code - 7), (q + code - 7, q)):
        block = [[int(matrix[top + i][left + j]) for j in range(7)] for i in range(7)]
        assert block == FINDER


@pytest.mark.parametrize("language", QR_LANGUAGES)
def test_matrix_file_names_its_url_and_the_segno_command(language):
    header = "\n".join(_header(language))
    url = QR_URLS[language]
    assert url in header
    assert f"uvx segno==1.6.6 --error M --border 4 --output qr_{language}.txt {url}" in header


def test_the_two_matrices_differ():
    assert qr_matrix("reglas") != qr_matrix("rules")


@pytest.mark.parametrize("language", QR_LANGUAGES)
def test_plate_size_module_size_and_watertight_stl(language, tmp_path):
    plate = qr_plate(language)
    box = plate.bounding_box()
    assert box.size.X == pytest.approx(45.0, abs=0.01)
    assert box.size.Y == pytest.approx(51.0, abs=0.01)
    assert box.size.Z == pytest.approx(1.6, abs=0.001)
    assert box.min.Z == pytest.approx(0, abs=1e-6)
    assert box.center().X == pytest.approx(0, abs=0.01)
    assert box.center().Y == pytest.approx(0, abs=0.01)
    assert 45.0 / SIDE >= MIN_MODULE

    # The plate, every raised module, and the label in the bundled font, 0.6 mm high.
    module = 45.0 / SIDE
    dark = sum(map(sum, qr_matrix(language)))
    label = sum(face.area for face in text_faces(QR_LABELS[language], LABEL_FONT_RATIO * 6.0))
    assert label > 10
    expected = 45.0 * 51.0 * 1.0 + 0.6 * (dark * module**2 + label)
    assert plate.volume == pytest.approx(expected, rel=0.01)

    mesh = trimesh.load_mesh(export_stl(plate, tmp_path / f"qr_{language}.stl"))
    assert mesh.is_watertight
    assert list(mesh.extents) == pytest.approx([45.0, 51.0, 1.6], abs=0.02)


@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"language": "es"}, "language"),
        ({"language": "rules", "size": 40.0}, "size"),
        ({"language": "rules", "size": float("nan")}, "size"),
        ({"language": "rules", "base_height": 0.7}, "base_height"),
        ({"language": "rules", "module_height": 0.3}, "module_height"),
        ({"language": "rules", "label_band": 5.9}, "label_band"),
        ({"language": "reglas", "size": 41.0, "label_band": 15.0}, "size"),
    ],
)
def test_bad_sizes_raise_naming_the_parameter(kwargs, name):
    with pytest.raises(ValueError, match=name):
        qr_plate(**kwargs)


@pytest.mark.parametrize("language", QR_LANGUAGES)
def test_label_is_centered_in_its_band_in_the_bundled_font(language):
    plate = qr_plate(language)
    # Only the label rises above the base south of the code.
    band = [
        face for face in plate.faces()
        if face.center().Z > 1.5 and face.center().Y < -51.0 / 2 + 6.0
    ]
    assert band
    from build123d import Compound

    box = Compound(band).bounding_box()
    letters = Compound(text_faces(QR_LABELS[language], LABEL_FONT_RATIO * 6.0)).bounding_box()
    assert box.size.X == pytest.approx(letters.size.X, abs=0.05)
    assert box.center().X == pytest.approx(0, abs=0.05)
    assert box.center().Y == pytest.approx(-51.0 / 2 + 3.0, abs=0.05)
