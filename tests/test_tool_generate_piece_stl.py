"""The `generate_piece_stl` MCP tool, its piece JSON, the output folder, and the dispatch.

Every test that writes a file points `ACEQUIAS_OUTPUT_DIR` at pytest's
temporary folder. Tests that build pieces need the optional `cad` extra and
skip without it; the schema, input-error, output-folder, and no-extra tests
run on a plain install too.
"""

import importlib.util
import inspect
import json
import os
import re
import subprocess
import sys
import textwrap

import pytest
from mcp import Client

from server.app import app
from server.output import OUTPUT_DIR_ENV, output_dir
from server.schemas import PIECE_MODELS
from server.tools.pieces import CAD_EXTRA_MESSAGE, format_number, piece_file_name

pytestmark = pytest.mark.anyio

CAD_REASON = "needs the optional 'cad' extra (build123d, trimesh): uv sync --extra cad"
HAS_CAD = all(importlib.util.find_spec(name) for name in ("build123d", "trimesh"))
needs_cad = pytest.mark.skipif(not HAS_CAD, reason=CAD_REASON)

TOOL = "generate_piece_stl"
TYPES = ["terrain", "canal", "floodgate", "owner_token", "grape_cluster", "debt_token"]
TERRAINS = ["river", "vineyard", "stone", "empty"]
KINDS = ["straight", "gentle_curve", "sharp_curve", "symmetric_y", "t_branch", "claw"]
EVERY_PIECE = (
    [{"type": "terrain", "terrain": terrain} for terrain in TERRAINS]
    + [{"type": "canal", "kind": kind} for kind in KINDS]
    + [
        {"type": "floodgate"},
        {"type": "owner_token"},
        {"type": "grape_cluster"},
        {"type": "debt_token", "value": 1},
        {"type": "debt_token", "value": 5},
    ]
)
LENGTHS = {"side", "height", "groove_width", "groove_depth", "thickness", "cap_diameter",
           "cap_height", "base_diameter", "diameter"}
FITS = {"clearance", "tolerance"}


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


def piece_id(piece):
    return "-".join(str(value) for value in piece.values())


def files_in(folder):
    return sorted(path.name for path in folder.iterdir()) if folder.exists() else []


async def call(client, piece):
    return await client.call_tool(TOOL, {"piece": piece})


async def generate(piece):
    async with Client(app) as client:
        return await call(client, piece)


async def tool_info(client):
    return next(tool for tool in (await client.list_tools()).tools if tool.name == TOOL)


def piece_schemas(schema):
    """The JSON schema of each piece type, keyed by type."""
    defs = schema["$defs"]
    union = schema["properties"]["piece"]
    arms = union.get("oneOf") or union.get("anyOf")
    shapes = [defs[arm["$ref"].split("/")[-1]] for arm in arms]
    return {shape["properties"]["type"]["const"]: shape for shape in shapes}


# --- Listing and schema -----------------------------------------------------


async def test_listed_with_a_description():
    async with Client(app) as client:
        tool = await tool_info(client)
    assert tool.description.strip()
    assert "cad" in tool.description


async def test_input_schema_has_the_six_types_and_only_piece():
    async with Client(app) as client:
        schema = (await tool_info(client)).input_schema
    assert set(schema["properties"]) == {"piece"}
    assert schema["required"] == ["piece"]
    assert list(piece_schemas(schema)) == TYPES


async def test_every_field_has_a_description_and_every_size_a_default_in_mm():
    async with Client(app) as client:
        shapes = piece_schemas((await tool_info(client)).input_schema)
    for piece_type, shape in shapes.items():
        assert shape["additionalProperties"] is False
        for name, field in shape["properties"].items():
            assert field.get("description"), (piece_type, name)
            if name in LENGTHS | FITS:
                assert "default" in field, (piece_type, name)
                assert "mm" in field["description"], (piece_type, name)
                assert field["type"] == "number"
                assert field["maximum"] == (100 if name in LENGTHS else 2)
                if name in LENGTHS:
                    assert field["exclusiveMinimum"] == 0
                else:
                    assert field["minimum"] == 0
            else:
                assert name in {"type", "terrain", "kind", "value"}, (piece_type, name)
    assert shapes["terrain"]["properties"]["terrain"]["enum"] == TERRAINS
    assert shapes["canal"]["properties"]["kind"]["enum"] == KINDS
    assert shapes["debt_token"]["properties"]["value"]["enum"] == [1, 5]
    assert sorted(shapes["canal"]["required"]) == ["kind", "type"]
    assert sorted(shapes["debt_token"]["required"]) == ["type", "value"]
    assert shapes["floodgate"]["required"] == ["type"]
    floodgate = shapes["floodgate"]["properties"]
    for name in ("groove_width", "groove_depth"):
        assert "must match the canal pieces" in floodgate[name]["description"]
    assert "hole_diameter" not in shapes["owner_token"]["properties"]


async def test_output_schema_is_published():
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
    assert set(schema["properties"]) == {
        "path", "piece", "size", "volume", "triangles", "watertight"
    }


@needs_cad
def test_defaults_are_the_cad_generators_defaults():
    from acequias.cad.pieces import GENERATORS, PIECE_TYPES
    from acequias.cad.channel import canal_piece
    from acequias.cad.hex_tile import hex_tile
    from acequias.cad.tokens import debt_token

    assert list(PIECE_TYPES) == TYPES == list(PIECE_MODELS)
    # The wrappers pass their sizes on to these generators.
    signatures = {"terrain": hex_tile, "canal": canal_piece, "debt_token": debt_token}
    for piece_type, model in PIECE_MODELS.items():
        generator = signatures.get(piece_type, GENERATORS[piece_type][0])
        parameters = inspect.signature(generator).parameters
        for name, field in model.model_fields.items():
            if name in LENGTHS | FITS:
                assert parameters[name].default == field.default, (piece_type, name)
                assert parameters[name].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD


# --- Every type and variant -------------------------------------------------


@needs_cad
@pytest.mark.parametrize("piece", EVERY_PIECE, ids=piece_id)
async def test_every_piece_is_written_watertight_and_measured(piece, out):
    import trimesh

    result = await generate(piece)
    assert not result.is_error, text_of(result)
    data = result.structured_content

    path = data["path"]
    assert os.path.isabs(path)
    written = out.resolve() / os.path.basename(path)
    assert os.path.realpath(path) == str(written)  # directly inside the output folder
    assert written.is_file()
    assert re.fullmatch(r"[a-z0-9_.-]+\.stl", written.name)
    assert files_in(out) == [written.name]  # no temporary file left behind

    assert data["piece"]["type"] == piece["type"]
    assert set(data["piece"]) == set(PIECE_MODELS[piece["type"]].model_fields)
    assert data["piece"] == {**data["piece"], **piece}

    mesh = trimesh.load_mesh(written, file_type="stl")
    assert data["watertight"] is True
    assert mesh.is_watertight
    assert data["triangles"] == len(mesh.faces)
    assert data["volume"] == pytest.approx(round(float(mesh.volume), 2), abs=1e-9)
    size = [round(float(extent), 2) for extent in mesh.extents]
    assert [data["size"][axis] for axis in "xyz"] == size


@needs_cad
async def test_default_terrain_is_27_71_by_32_by_4(out):
    result = await generate({"type": "terrain", "terrain": "vineyard"})
    assert result.structured_content["size"] == {"x": 27.71, "y": 32.0, "z": 4.0}
    assert result.structured_content["piece"] == {
        "type": "terrain", "terrain": "vineyard", "side": 16.0, "height": 4.0, "clearance": 0.0
    }


@needs_cad
async def test_the_four_terrains_are_the_same_tile_under_different_names(out):
    async with Client(app) as client:
        results = [await call(client, {"type": "terrain", "terrain": t}) for t in TERRAINS]
    paths = [result.structured_content["path"] for result in results]
    assert len(set(paths)) == 4
    contents = {open(path, "rb").read()[80:] for path in paths}  # skip the STL header
    assert len(contents) == 1


# --- File names -------------------------------------------------------------


@needs_cad
async def test_file_name_follows_type_variant_and_every_parameter(out):
    async with Client(app) as client:
        canal = await call(client, {"type": "canal", "kind": "symmetric_y"})
        debt = await call(client, {"type": "debt_token", "value": 5})
        gate = await call(client, {"type": "floodgate"})
        token = await call(client, {"type": "owner_token", "cap_height": 1})
    names = [os.path.basename(r.structured_content["path"]) for r in (canal, debt, gate, token)]
    assert names == [
        "canal-symmetric_y-side16-height4-clearance0-groove_width6-groove_depth1.5.stl",
        "debt_token-5-diameter12-thickness2.stl",
        "floodgate-tolerance0.15-groove_width6-groove_depth1.5-thickness2.stl",
        "owner_token-tolerance0.15-cap_diameter7-cap_height1.stl",
    ]


@needs_cad
async def test_omitting_a_parameter_or_passing_its_default_gives_the_same_file(out):
    async with Client(app) as client:
        omitted = await call(client, {"type": "terrain", "terrain": "stone"})
        explicit = await call(
            client, {"type": "terrain", "terrain": "stone", "side": 16, "height": 4.0, "clearance": 0}
        )
    assert omitted.structured_content == explicit.structured_content
    assert len(files_in(out)) == 1


@needs_cad
async def test_same_request_overwrites_and_a_different_one_writes_a_new_file(out):
    piece = {"type": "debt_token", "value": 1}
    async with Client(app) as client:
        first = await call(client, piece)
        path = first.structured_content["path"]
        with open(path, "wb") as stale:
            stale.write(b"stale")
        second = await call(client, piece)
        assert second.structured_content["path"] == path
        assert os.path.getsize(path) > len(b"stale")  # overwritten
        assert files_in(out) == [os.path.basename(path)]

        changed = await call(client, {**piece, "thickness": 2.5})
    assert changed.structured_content["path"] != path
    assert os.path.basename(changed.structured_content["path"]) == (
        "debt_token-1-diameter12-thickness2.5.stl"
    )
    assert len(files_in(out)) == 2


@pytest.mark.parametrize(
    ("value", "text"),
    [(16.0, "16"), (16, "16"), (1.5, "1.5"), (0.15, "0.15"), (0.0, "0"), (100.0, "100"),
     (1e-05, "0.00001"), (0.1 + 0.2, "0.30000000000000004")],
)
def test_numbers_are_written_in_their_shortest_exact_form(value, text):
    assert format_number(value) == text


def test_file_name_without_building_anything():
    piece = PIECE_MODELS["grape_cluster"].model_validate({"type": "grape_cluster", "height": 12})
    assert piece_file_name(piece) == "grape_cluster-base_diameter14-height12.stl"
    terrain = PIECE_MODELS["terrain"].model_validate({"type": "terrain", "terrain": "empty"})
    assert piece_file_name(terrain) == "terrain-empty-side16-height4-clearance0.stl"


# --- Errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("piece", "expected"),
    [
        ({"type": "tile"}, ["'terrain'", "'canal'", "'floodgate'", "'owner_token'",
                            "'grape_cluster'", "'debt_token'"]),
        ({"type": "terrain", "terrain": "forest"}, ["terrain", "'river'", "'empty'"]),
        ({"type": "canal", "kind": "floodgate"}, ["kind", "'straight'", "'claw'"]),
        ({"type": "canal", "kind": "y_junction"}, ["kind", "'symmetric_y'", "'t_branch'"]),
        ({"type": "canal"}, ["kind", "required"]),
        ({"type": "debt_token"}, ["value", "required"]),
        ({"kind": "straight"}, ["type"]),
        ({"type": "terrain", "terrain": "river", "groove_width": 3}, ["groove_width"]),
        ({"type": "owner_token", "hole_diameter": 4}, ["hole_diameter"]),
        ({"type": "terrain", "terrain": "river", "side": -16}, ["side"]),
        ({"type": "terrain", "terrain": "river", "side": 0}, ["side"]),
        ({"type": "terrain", "terrain": "river", "side": 500}, ["side"]),
        ({"type": "terrain", "terrain": "river", "side": True}, ["side"]),
        ({"type": "terrain", "terrain": "river", "side": "16"}, ["side"]),
        ({"type": "terrain", "terrain": "river", "clearance": -0.1}, ["clearance"]),
        ({"type": "floodgate", "tolerance": 2.5}, ["tolerance"]),
        ({"type": "grape_cluster", "height": 101}, ["height"]),
        ({"type": "debt_token", "value": 3}, ["value"]),
        ({"type": "debt_token", "value": True}, ["value"]),
        ({"type": "debt_token", "value": 1.0}, ["value"]),
        ({"type": "debt_token", "value": "5"}, ["value"]),
    ],
)
async def test_bad_input_is_a_tool_error_naming_the_problem(piece, expected, out):
    result = await generate(piece)
    assert result.is_error
    text = text_of(result)
    for fragment in expected:
        assert fragment in text, (fragment, text)
    assert not out.exists()


async def test_a_piece_that_is_not_an_object_is_a_tool_error(out):
    async with Client(app) as client:
        result = await client.call_tool(TOOL, {"piece": "terrain"})
        missing = await client.call_tool(TOOL, {})
    assert result.is_error and "piece" in text_of(result)
    assert missing.is_error and "piece" in text_of(missing)


@needs_cad
@pytest.mark.parametrize(
    ("piece", "parameter"),
    [
        ({"type": "canal", "kind": "straight", "side": 16, "groove_width": 20}, "groove_width"),
        ({"type": "canal", "kind": "claw", "groove_depth": 3.5}, "groove_depth"),
        ({"type": "grape_cluster", "base_diameter": 10, "height": 20}, "height"),
        ({"type": "debt_token", "value": 5, "diameter": 5}, "diameter"),
    ],
)
async def test_a_combination_the_cad_rejects_returns_its_message(piece, parameter, out):
    result = await generate(piece)
    assert result.is_error
    assert parameter in text_of(result)
    assert files_in(out) == []


@needs_cad
async def test_output_dir_on_an_existing_file_is_an_error_and_writes_nothing(tmp_path, monkeypatch):
    blocker = tmp_path / "taken.txt"
    blocker.write_text("keep me")
    for value in (blocker, blocker / "sub"):
        monkeypatch.setenv(OUTPUT_DIR_ENV, str(value))
        result = await generate({"type": "floodgate"})
        assert result.is_error
        text = text_of(result)
        assert OUTPUT_DIR_ENV in text
        assert str(value.resolve()) in text.replace("\\\\", "\\")
    assert blocker.read_text() == "keep me"
    assert sorted(path.name for path in tmp_path.iterdir()) == ["taken.txt"]


@needs_cad
async def test_a_failed_write_leaves_no_partial_or_temporary_file(out, monkeypatch):
    import acequias.cad.hex_tile as hex_tile_module

    async with Client(app) as client:
        kept = await call(client, {"type": "debt_token", "value": 5})
        before = {path.name: path.read_bytes() for path in out.iterdir()}

        def broken_export(shape, path):
            with open(path, "wb") as partial:
                partial.write(b"half an STL")
            raise ValueError("disk full")

        monkeypatch.setattr(hex_tile_module, "export_stl", broken_export)
        failed = await call(client, {"type": "debt_token", "value": 1})
        same_name = await call(client, {"type": "debt_token", "value": 5})
    assert not kept.is_error
    assert failed.is_error and "disk full" in text_of(failed)
    assert same_name.is_error
    assert {path.name: path.read_bytes() for path in out.iterdir()} == before


# --- The output folder ------------------------------------------------------


def test_output_dir_defaults_to_output_in_the_working_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for value in (None, ""):
        if value is None:
            monkeypatch.delenv(OUTPUT_DIR_ENV, raising=False)
        else:
            monkeypatch.setenv(OUTPUT_DIR_ENV, value)
        assert output_dir() == (tmp_path / "output").resolve()
        assert (tmp_path / "output").is_dir()


def test_output_dir_resolves_a_relative_value_and_creates_parents(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(OUTPUT_DIR_ENV, os.path.join("a", "b", "..", "c"))
    assert output_dir() == (tmp_path / "a" / "c").resolve()
    assert (tmp_path / "a" / "c").is_dir()


def test_output_dir_is_read_on_every_call(tmp_path, monkeypatch):
    monkeypatch.setenv(OUTPUT_DIR_ENV, str(tmp_path / "one"))
    first = output_dir()
    monkeypatch.setenv(OUTPUT_DIR_ENV, str(tmp_path / "two"))
    assert output_dir() != first
    assert output_dir() == (tmp_path / "two").resolve()


def test_output_dir_errors_name_the_variable_and_the_path(tmp_path, monkeypatch):
    blocker = tmp_path / "file"
    blocker.write_text("")
    for value in (blocker, blocker / "below"):
        monkeypatch.setenv(OUTPUT_DIR_ENV, str(value))
        with pytest.raises(ValueError, match=OUTPUT_DIR_ENV) as error:
            output_dir()
        assert str(value.resolve()) in str(error.value).replace("\\\\", "\\")


# --- The dispatch table -----------------------------------------------------


@needs_cad
def test_build_piece_rejects_bad_types_and_variants():
    from acequias.cad.pieces import build_piece
    from acequias.model import PieceKind

    with pytest.raises(ValueError, match="type must be one of"):
        build_piece("tile")
    with pytest.raises(ValueError, match="needs its variant"):
        build_piece("canal")
    with pytest.raises(ValueError, match="has no variant"):
        build_piece("floodgate", PieceKind.STRAIGHT)
    with pytest.raises(TypeError, match="Terrain"):
        build_piece("terrain", "river")
    with pytest.raises(ValueError, match="floodgate"):
        build_piece("canal", PieceKind.FLOODGATE)


# --- Without the cad extra --------------------------------------------------


def test_without_the_cad_extra_the_server_starts_and_the_tool_says_how_to_install(tmp_path):
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
                piece = await client.call_tool(
                    "generate_piece_stl", {{"piece": {{"type": "terrain", "terrain": "river"}}}}
                )
                board = await client.call_tool(
                    "generate_board", {{"players": 2, "mode": "flash", "seed": 1}}
                )
                text = "".join(b.text for b in piece.content if b.type == "text")
                print(json.dumps({{
                    "names": names,
                    "error": piece.is_error,
                    "text": text,
                    "board_ok": not board.is_error,
                    "cad_loaded": any(
                        name.startswith("acequias.cad.") for name in sys.modules
                    ),
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
    assert {"ping", "generate_board", "calculate_score", "simulate_game"} <= set(data["names"])
    assert data["error"] is True
    assert CAD_EXTRA_MESSAGE in data["text"]
    assert "'cad' extra" in data["text"] and "uv sync --extra cad" in data["text"]
    assert data["board_ok"] is True
    assert data["cad_loaded"] is False
    assert not folder.exists()


def test_the_server_does_not_import_cad_libraries_at_module_level():
    code = """
        import sys
        import server.app, server.schemas, server.output, server.tools.pieces
        loaded = [name for name in sys.modules
                  if name.split(".")[0] in ("build123d", "trimesh", "OCP")
                  or name.startswith("acequias.cad.")]
        print(loaded)
    """
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"
