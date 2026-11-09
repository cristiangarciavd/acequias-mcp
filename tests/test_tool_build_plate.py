"""The `build_plate` MCP tool: entries in, A1 print plates out as 3MF files.

Every test that may write a file points `ACEQUIAS_OUTPUT_DIR` at pytest's
temporary folder. Tests that build pieces need the optional `cad` extra and
skip without it; the schema, id, job-hash, input-error, and no-extra tests
run on a plain install too.
"""

import importlib.util
import json
import math
import os
import subprocess
import sys
import textwrap

import pytest
from mcp import Client

from acequias.plate import CircleFootprint, HexFootprint, Piece, RectFootprint, layout_plates
from server.app import app
from server.output import OUTPUT_DIR_ENV
from server.schemas import PlateEntryJSON
from server.tools.plate import CAD_EXTRA_MESSAGE, job_id, piece_ids

pytestmark = pytest.mark.anyio

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"
HAS_CAD = all(importlib.util.find_spec(name) for name in ("build123d", "trimesh"))
needs_cad = pytest.mark.skipif(not HAS_CAD, reason=CAD_REASON)

TOOL = "build_plate"
TYPES = ["terrain", "canal", "floodgate", "owner_token", "grape_cluster", "debt_token"]
TERRAINS = ["river", "vineyard", "stone", "empty"]
KINDS = ["straight", "gentle_curve", "sharp_curve", "symmetric_y", "t_branch", "claw"]
EVERY_PIECE = (
    [{"type": "terrain", "terrain": terrain} for terrain in TERRAINS]
    + [{"type": "terrain", "terrain": "river", "clearance": 0.2}]
    + [{"type": "canal", "kind": kind} for kind in KINDS]
    + [{"type": "canal", "kind": "straight", "clearance": 0.2}]
    + [
        {"type": "floodgate"},
        {"type": "owner_token"},
        {"type": "grape_cluster"},
        {"type": "debt_token", "value": 1},
        {"type": "debt_token", "value": 5},
    ]
)

TERRAIN = {"type": "terrain", "terrain": "river"}
TOKEN = {"type": "owner_token"}
# The known list: 10 terrain hexes, and 4 owner tokens in each of two colors.
KNOWN = [
    {"piece": TERRAIN, "count": 10, "color": "neutral"},
    {"piece": TOKEN, "count": 4, "color": "red"},
    {"piece": TOKEN, "count": 4, "color": "blue"},
]
SMALL = [{"piece": {"type": "debt_token", "value": 1}, "count": 2, "color": "red"}]


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def out(tmp_path, monkeypatch):
    """An output folder in pytest's temporary folder (not created yet)."""
    folder = tmp_path / "out"
    monkeypatch.setenv(OUTPUT_DIR_ENV, str(folder))
    return folder


def text_of(result):
    return "".join(block.text for block in result.content if block.type == "text")


def snapshot(folder):
    """Every file and folder under ``folder`` with its bytes (None for folders)."""
    if not folder.exists():
        return None
    return {
        path.relative_to(folder).as_posix(): (None if path.is_dir() else path.read_bytes())
        for path in sorted(folder.rglob("*"))
    }


async def build(entries, **options):
    async with Client(app) as client:
        return await client.call_tool(TOOL, {"entries": entries, **options})


async def tool_info(client):
    return next(tool for tool in (await client.list_tools()).tools if tool.name == TOOL)


def entries_of(raw):
    return [PlateEntryJSON.model_validate(entry) for entry in raw]


def piece_label(piece):
    return "-".join(str(value) for value in piece.values())


# --- Listing and schema -----------------------------------------------------


async def test_listed_with_a_description_and_the_six_piece_types():
    async with Client(app) as client:
        tool = await tool_info(client)
    assert tool.description.strip()
    assert "cad" in tool.description
    schema = tool.input_schema
    assert set(schema["properties"]) == {"entries", "bed_width", "bed_depth", "margin", "gap"}
    assert schema["required"] == ["entries"]
    entries = schema["properties"]["entries"]
    assert entries["description"]
    assert (entries["minItems"], entries["maxItems"]) == (1, 50)
    entry = schema["$defs"][entries["items"]["$ref"].split("/")[-1]]
    assert entry["additionalProperties"] is False
    assert sorted(entry["required"]) == ["color", "count", "piece"]
    union = entry["properties"]["piece"]
    arms = union.get("oneOf") or union.get("anyOf")
    shapes = [schema["$defs"][arm["$ref"].split("/")[-1]] for arm in arms]
    assert [shape["properties"]["type"]["const"] for shape in shapes] == TYPES
    count = entry["properties"]["count"]
    assert (count["type"], count["minimum"], count["maximum"]) == ("integer", 1, 500)
    color = entry["properties"]["color"]
    assert color["pattern"] == "^[a-z0-9][a-z0-9_-]{0,31}$"
    assert (color["minLength"], color["maxLength"]) == (1, 32)
    for name in ("piece", "count", "color"):
        assert entry["properties"][name].get("description") or name == "piece", name


async def test_bed_margin_and_gap_have_defaults_limits_and_units():
    async with Client(app) as client:
        props = (await tool_info(client)).input_schema["properties"]
    expected = {
        "bed_width": (256, "exclusiveMinimum", 0, 1000),
        "bed_depth": (256, "exclusiveMinimum", 0, 1000),
        "margin": (5, "minimum", 0, 50),
        "gap": (3, "minimum", 0, 20),
    }
    for name, (default, low_key, low, high) in expected.items():
        field = props[name]
        assert field["type"] == "number"
        assert field["default"] == default
        assert field[low_key] == low
        assert field["maximum"] == high
        assert "mm" in field["description"]


async def test_output_schema_is_published():
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
    assert set(schema["properties"]) == {"folder", "job", "plates", "summary"}


# --- Ids and the job hash (no CAD) ------------------------------------------


def test_ids_count_from_01_per_prefix_across_the_request():
    raw = [
        {"piece": TERRAIN, "count": 2, "color": "neutral"},
        {"piece": {"type": "canal", "kind": "straight"}, "count": 2, "color": "blue"},
        {"piece": {"type": "debt_token", "value": 5}, "count": 1, "color": "red"},
        {"piece": {**TERRAIN, "side": 18}, "count": 1, "color": "red"},
        {"piece": {"type": "canal", "kind": "straight"}, "count": 1, "color": "red"},
        {"piece": {"type": "debt_token", "value": 5}, "count": 1, "color": "red"},
        {"piece": {"type": "floodgate"}, "count": 1, "color": "red"},
        {"piece": {"type": "terrain", "terrain": "stone"}, "count": 1, "color": "red"},
    ]
    assert piece_ids(entries_of(raw)) == [
        ["terrain-river-01", "terrain-river-02"],
        ["canal-straight-01", "canal-straight-02"],
        ["debt_token-5-01"],
        ["terrain-river-03"],
        ["canal-straight-03"],
        ["debt_token-5-02"],
        ["floodgate-01"],
        ["terrain-stone-01"],
    ]
    assert piece_ids(entries_of(raw)) == piece_ids(entries_of(raw))


def test_ids_pad_to_at_least_two_digits():
    ids = piece_ids(entries_of([{"piece": TOKEN, "count": 120, "color": "red"}]))[0]
    assert ids[0] == "owner_token-01"
    assert ids[8:10] == ["owner_token-09", "owner_token-10"]
    assert ids[-1] == "owner_token-120"
    assert len(set(ids)) == 120


def test_job_hash_ignores_written_defaults_and_int_floats_but_not_any_value():
    def job(raw, bed=(256.0, 256.0), margin=5.0, gap=3.0):
        return job_id(entries_of(raw), bed[0], bed[1], margin, gap)

    base = job(KNOWN)
    assert len(base) == 12 and all(c in "0123456789abcdef" for c in base)
    assert job(KNOWN) == base
    explicit = [
        {"piece": {**TERRAIN, "side": 16, "height": 4.0, "clearance": 0}, "count": 10,
         "color": "neutral"},
        {"piece": {**TOKEN, "tolerance": 0.15, "cap_diameter": 7}, "count": 4, "color": "red"},
        KNOWN[2],
    ]
    assert job(explicit, bed=(256, 256), margin=5, gap=3) == base
    changed = [
        job(list(reversed(KNOWN))),
        job([KNOWN[0], {**KNOWN[1], "color": "green"}, KNOWN[2]]),
        job([{**KNOWN[0], "count": 11}, *KNOWN[1:]]),
        job([{**KNOWN[0], "piece": {**TERRAIN, "side": 16.5}}, *KNOWN[1:]]),
        job([{**KNOWN[0], "piece": {"type": "terrain", "terrain": "stone"}}, *KNOWN[1:]]),
        job(KNOWN, bed=(256.0, 255.0)),
        job(KNOWN, margin=4.0),
        job(KNOWN, gap=2.0),
    ]
    assert base not in changed
    assert len(set(changed)) == len(changed)


# --- Footprints -------------------------------------------------------------


def test_footprint_module_needs_no_cad():
    code = """
        import sys
        sys.modules["build123d"] = None
        sys.modules["trimesh"] = None
        from acequias.cad.footprints import piece_footprint
        print(piece_footprint("floodgate", tolerance=0.15, groove_width=6.0, groove_depth=1.5,
                              thickness=2.0))
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert "RectFootprint" in result.stdout


def test_footprint_formulas():
    from acequias.cad.footprints import piece_footprint

    hexes = piece_footprint("canal", None, side=16.0, clearance=0.2, height=4.0)
    assert hexes == HexFootprint(16.0 - 2 * 0.2 / math.sqrt(3))
    gate = piece_footprint("floodgate", tolerance=0.15, groove_width=6.0, thickness=2.0)
    assert gate.width == pytest.approx(5.70) and gate.depth == 2.0
    assert isinstance(gate, RectFootprint)
    assert piece_footprint("owner_token", cap_diameter=7.0) == CircleFootprint(7.0)
    assert piece_footprint("grape_cluster", base_diameter=14.0) == CircleFootprint(14.0)
    assert piece_footprint("debt_token", 5, diameter=12.0) == CircleFootprint(12.0)
    with pytest.raises(ValueError, match="clearance"):
        piece_footprint("terrain", side=16.0)
    with pytest.raises(ValueError, match="tile"):
        piece_footprint("tile")


@needs_cad
@pytest.mark.parametrize("piece", EVERY_PIECE, ids=piece_label)
def test_footprint_matches_the_solid(piece):
    from acequias.cad.footprints import piece_footprint
    from acequias.cad.pieces import build_piece
    from server.schemas import PIECE_MODELS, piece_params, piece_variant

    model = PIECE_MODELS[piece["type"]].model_validate(piece)
    variant, params = piece_variant(model), piece_params(model)
    footprint = piece_footprint(model.type, variant, **params)
    box = build_piece(model.type, variant, **params).bounding_box()
    assert box.size.X == pytest.approx(footprint.width, abs=0.05)
    assert box.size.Y == pytest.approx(footprint.depth, abs=0.05)
    # Centered on the origin, where export_plate puts the placement's x, y.
    assert box.center().X == pytest.approx(0, abs=0.05)
    assert box.center().Y == pytest.approx(0, abs=0.05)


# --- The known list ---------------------------------------------------------


@needs_cad
async def test_known_list_gives_three_plates_matching_layout_plates(out, monkeypatch):
    from build123d import Mesher

    import acequias.cad.pieces as pieces_module

    calls = []
    real_build = pieces_module.build_piece

    def counting_build(*args, **kwargs):
        calls.append(args)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(pieces_module, "build_piece", counting_build)
    result = await build(KNOWN)
    assert not result.is_error, text_of(result)
    data = result.structured_content
    assert len(calls) == 2  # one terrain hex and one owner token, shared by every id

    folder = out.resolve() / f"plates-{data['job']}"
    assert data["folder"] == str(folder)
    assert [(p["number"], p["color"]) for p in data["plates"]] == [
        (1, "neutral"), (2, "red"), (3, "blue")
    ]
    assert data["summary"] == {
        "pieces": 18, "plates": 3, "plates_per_color": {"neutral": 1, "red": 1, "blue": 1}
    }

    side = 16.0
    expected = layout_plates(
        [Piece(f"terrain-river-{n:02d}", HexFootprint(side), "neutral") for n in range(1, 11)]
        + [Piece(f"owner_token-{n:02d}", CircleFootprint(7.0), "red") for n in range(1, 5)]
        + [Piece(f"owner_token-{n:02d}", CircleFootprint(7.0), "blue") for n in range(5, 9)]
    )
    assert len(expected) == 3
    for plate, want in zip(data["plates"], expected):
        assert plate["number"] == want.number and plate["color"] == want.color_group
        assert [p["id"] for p in plate["placements"]] == [p.piece_id for p in want.placements]
        for got, placement in zip(plate["placements"], want.placements):
            assert got["x"] == round(placement.x, 2)
            assert got["y"] == round(placement.y, 2)
            assert got["rotation"] == 0
    first = data["plates"][0]["placements"][0]
    assert first["entry"] == 0
    assert first["piece"] == {**TERRAIN, "side": 16.0, "height": 4.0, "clearance": 0.0}
    assert [p["entry"] for p in data["plates"][2]["placements"]] == [2] * 4
    assert data["plates"][1]["placements"][0]["piece"] == {
        **TOKEN, "tolerance": 0.15, "cap_diameter": 7.0, "cap_height": 1.2
    }

    names = sorted(path.name for path in folder.iterdir())
    assert names == ["plate-1-neutral.3mf", "plate-2-red.3mf", "plate-3-blue.3mf"]
    assert sorted(path.name for path in out.iterdir()) == [folder.name]  # no temporary folder
    for plate in data["plates"]:
        path = plate["path"]
        assert os.path.isabs(path) and os.path.isfile(path)
        assert os.path.dirname(os.path.realpath(path)) == str(folder)
        shapes = Mesher().read(path)
        assert [shape.label for shape in shapes] == [p["id"] for p in plate["placements"]]


@needs_cad
async def test_same_color_plates_differ_by_number_and_stay_in_the_folder(out):
    result = await build(
        [{"piece": TERRAIN, "count": 1, "color": "red"},
         {"piece": TOKEN, "count": 1, "color": "red"}]
    )
    assert not result.is_error, text_of(result)
    plates = result.structured_content["plates"]
    assert [os.path.basename(p["path"]) for p in plates] == ["plate-1-red.3mf", "plate-2-red.3mf"]
    assert result.structured_content["summary"]["plates_per_color"] == {"red": 2}
    root = out.resolve()
    for path in (root / name for name in snapshot(out)):
        assert path.resolve().is_relative_to(root)


@needs_cad
async def test_same_request_overwrites_and_different_ones_get_their_own_folder(out):
    first = (await build(SMALL)).structured_content
    path = first["plates"][0]["path"]
    with open(path, "wb") as stale:
        stale.write(b"stale")
    explicit = [{**SMALL[0], "piece": {**SMALL[0]["piece"], "diameter": 12, "thickness": 2.0}}]
    again = (await build(explicit, bed_width=256, margin=5.0)).structured_content
    assert again == first
    assert os.path.getsize(path) > len(b"stale")  # overwritten

    other_color = (await build([{**SMALL[0], "color": "blue"}])).structured_content
    other_gap = (await build(SMALL, gap=4)).structured_content
    jobs = {first["job"], other_color["job"], other_gap["job"]}
    assert len(jobs) == 3
    assert sorted(path.name for path in out.iterdir()) == sorted(f"plates-{job}" for job in jobs)


# --- Errors -----------------------------------------------------------------


def many(count):
    return [{"piece": TOKEN, "count": 1, "color": "red"}] * count


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"entries": []}, ["entries"]),
        ({"entries": many(51)}, ["entries", "50"]),
        ({}, ["entries"]),
        ({"entries": [{"piece": TOKEN, "count": 0, "color": "red"}]}, ["count", "1"]),
        ({"entries": [{"piece": TOKEN, "count": 501, "color": "red"}]}, ["count", "500"]),
        ({"entries": [{"piece": TOKEN, "count": 1.5, "color": "red"}]}, ["count"]),
        ({"entries": [{"piece": TOKEN, "count": 2.0, "color": "red"}]}, ["count"]),
        ({"entries": [{"piece": TOKEN, "count": "2", "color": "red"}]}, ["count"]),
        ({"entries": [{"piece": TOKEN, "count": True, "color": "red"}]}, ["count"]),
        ({"entries": [{"piece": TOKEN, "count": 1}]}, ["color", "required"]),
        ({"entries": [{"piece": TOKEN, "count": 1, "color": "Red"}]}, ["color"]),
        ({"entries": [{"piece": TOKEN, "count": 1, "color": "red/blue"}]}, ["color"]),
        ({"entries": [{"piece": TOKEN, "count": 1, "color": ""}]}, ["color"]),
        ({"entries": [{"piece": TOKEN, "count": 1, "color": "_red"}]}, ["color"]),
        ({"entries": [{"piece": TOKEN, "count": 1, "color": "r" * 33}]}, ["color"]),
        ({"entries": [{"count": 1, "color": "red"}]}, ["piece", "required"]),
        ({"entries": [{"piece": TOKEN, "count": 1, "color": "red", "path": "x"}]}, ["path"]),
        ({"entries": SMALL, "bed_width": 0}, ["bed_width"]),
        ({"entries": SMALL, "bed_width": 1001}, ["bed_width"]),
        ({"entries": SMALL, "bed_depth": True}, ["bed_depth"]),
        ({"entries": SMALL, "bed_depth": "256"}, ["bed_depth"]),
        ({"entries": SMALL, "margin": -1}, ["margin"]),
        ({"entries": SMALL, "margin": 51}, ["margin"]),
        ({"entries": SMALL, "gap": 21}, ["gap"]),
        ({"entries": SMALL, "gap": False}, ["gap"]),
    ],
)
async def test_bad_input_is_a_tool_error_naming_the_problem(arguments, expected, out):
    async with Client(app) as client:
        result = await client.call_tool(TOOL, arguments)
    assert result.is_error
    text = text_of(result)
    for fragment in expected:
        assert fragment in text, (fragment, text)
    assert not out.exists()


def _without_location(text, prefix):
    """The validation messages without their header line and the entry's location."""
    return "\n".join(text.replace(prefix, "").splitlines()[1:])


@pytest.mark.parametrize(
    "piece",
    [
        {"type": "tile"},
        {"type": "terrain", "terrain": "forest"},
        {"type": "canal", "kind": "floodgate"},
        {"type": "canal"},
        {"type": "debt_token"},
        {"kind": "straight"},
        {"type": "terrain", "terrain": "river", "groove_width": 3},
        {"type": "terrain", "terrain": "river", "side": 500},
        {"type": "terrain", "terrain": "river", "side": True},
        {"type": "floodgate", "tolerance": 2.5},
        {"type": "debt_token", "value": 3},
    ],
    ids=piece_label,
)
async def test_a_bad_piece_gives_the_same_message_as_generate_piece_stl(piece, out):
    async with Client(app) as client:
        plate = await client.call_tool(
            TOOL, {"entries": [{"piece": piece, "count": 1, "color": "red"}]}
        )
        stl = await client.call_tool("generate_piece_stl", {"piece": piece})
    assert plate.is_error and stl.is_error
    assert _without_location(text_of(plate), "entries.0.") == _without_location(text_of(stl), "")
    assert not out.exists()


@needs_cad
async def test_a_total_above_500_names_the_total_and_the_limit(out):
    result = await build([{"piece": TOKEN, "count": 300, "color": "red"}] * 2)
    assert result.is_error
    assert "600" in text_of(result) and "500" in text_of(result)
    assert not out.exists()


@needs_cad
async def test_a_combination_the_cad_rejects_returns_its_message(out):
    piece = {"type": "canal", "kind": "straight", "side": 16, "groove_width": 20}
    async with Client(app) as client:
        plate = await client.call_tool(
            TOOL, {"entries": [{"piece": piece, "count": 1, "color": "red"}]}
        )
        stl = await client.call_tool("generate_piece_stl", {"piece": piece})
    assert plate.is_error and "groove_width" in text_of(plate)
    assert text_of(plate).split(": ", 1)[1] == text_of(stl).split(": ", 1)[1]
    assert not out.exists()


@needs_cad
async def test_layout_errors_return_the_layout_message(out):
    too_big = await build([{"piece": TERRAIN, "count": 1, "color": "red"}], bed_width=30)
    assert too_big.is_error
    assert "'terrain-river-01' is too big for the plate" in text_of(too_big)
    no_room = await build(SMALL, bed_width=100, margin=50)
    assert no_room.is_error
    assert "has no room inside a margin" in text_of(no_room)
    assert not out.exists()


@needs_cad
async def test_a_bad_output_folder_is_an_error_naming_it(tmp_path, monkeypatch):
    blocker = tmp_path / "taken.txt"
    blocker.write_text("keep me")
    monkeypatch.setenv(OUTPUT_DIR_ENV, str(blocker))
    result = await build(SMALL)
    assert result.is_error
    assert OUTPUT_DIR_ENV in text_of(result)
    assert str(blocker.resolve()) in text_of(result).replace("\\\\", "\\")
    assert blocker.read_text() == "keep me"


@needs_cad
async def test_failed_calls_leave_the_output_folder_as_it_was(out, monkeypatch):
    assert not (await build(SMALL)).is_error
    before = snapshot(out)
    failing = [
        ({"entries": [{"piece": TOKEN, "count": 300, "color": "red"}] * 2}, "500"),
        ({"entries": [{"piece": {"type": "debt_token", "value": 5, "diameter": 5},
                       "count": 1, "color": "red"}]}, "diameter"),
        ({"entries": [{"piece": TERRAIN, "count": 1, "color": "red"}], "bed_depth": 30},
         "too big"),
        ({"entries": SMALL, "bed_width": 100, "margin": 50}, "no room"),
        ({"entries": [{"piece": TOKEN, "count": 1, "color": "Red"}]}, "color"),
    ]
    async with Client(app) as client:
        for arguments, fragment in failing:
            result = await client.call_tool(TOOL, arguments)
            assert result.is_error and fragment in text_of(result), text_of(result)
            assert snapshot(out) == before

        # A failure while writing the second plate keeps the first one out too.
        import acequias.cad.plate_export as export_module

        real_export = export_module.export_plate

        def export_once(plate, *args, **kwargs):
            if plate.number > 1:
                raise ValueError("disk full")
            return real_export(plate, *args, **kwargs)

        monkeypatch.setattr(export_module, "export_plate", export_once)
        result = await client.call_tool(TOOL, {"entries": KNOWN[1:]})
    assert result.is_error and "disk full" in text_of(result)
    assert snapshot(out) == before


# --- Without the cad extra --------------------------------------------------


def test_without_the_cad_extra_the_tool_says_how_to_install(tmp_path):
    folder = tmp_path / "out"
    code = f"""
        import sys
        sys.modules["build123d"] = None
        sys.modules["trimesh"] = None
        import json
        import anyio
        from mcp import Client
        from server.app import app

        async def main():
            async with Client(app) as client:
                names = sorted(tool.name for tool in (await client.list_tools()).tools)
                plate = await client.call_tool("build_plate", {{"entries": {json.dumps(SMALL)}}})
                board = await client.call_tool(
                    "generate_board", {{"players": 2, "mode": "flash", "seed": 1}}
                )
                text = "".join(b.text for b in plate.content if b.type == "text")
                print(json.dumps({{
                    "names": names,
                    "error": plate.is_error,
                    "text": text,
                    "board_ok": not board.is_error,
                }}))

        anyio.run(main)
    """
    env = {**os.environ, OUTPUT_DIR_ENV: str(folder)}
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert TOOL in data["names"]
    assert {"ping", "generate_board", "generate_piece_stl"} <= set(data["names"])
    assert data["error"] is True
    assert CAD_EXTRA_MESSAGE in data["text"]
    assert "'cad' extra" in data["text"] and "uv sync --extra cad" in data["text"]
    assert data["board_ok"] is True
    assert not folder.exists()


def test_the_tool_module_does_not_import_cad_at_module_level():
    code = """
        import sys
        import server.app, server.tools.plate
        loaded = [name for name in sys.modules
                  if name.split(".")[0] in ("build123d", "trimesh", "OCP")
                  or name.startswith("acequias.cad.")]
        print(loaded)
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True, timeout=120
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
