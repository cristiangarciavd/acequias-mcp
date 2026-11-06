"""The `generate_board` MCP tool and the shared board JSON in `server.schemas`."""

import itertools

import jsonschema
import pytest
from mcp import Client

from acequias.assembly import assembly_instructions
from acequias.board import generate_board
from acequias.hex import Hex
from acequias.model import Board, Mode, Terrain, Tile, Varietal
from server.app import app
from server.schemas import (
    board_to_hexes,
    hexes_to_board,
    mode_from_json,
    mode_to_json,
    terrain_from_json,
    terrain_to_json,
    varietal_from_json,
    varietal_to_json,
)
from server.tools.board import MAX_PICKED_SEED, MAX_SEED

pytestmark = pytest.mark.anyio

CASES = list(itertools.product([2, 5], ["normal", "flash"]))
MODES = {"normal": Mode.NORMAL, "flash": Mode.FLASH}


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text_of(result):
    return "".join(block.text for block in result.content if block.type == "text")


async def tool_info(client):
    tools = (await client.list_tools()).tools
    return next(tool for tool in tools if tool.name == "generate_board")


async def call(client, **arguments):
    return await client.call_tool("generate_board", arguments)


# --- Listing and schemas ----------------------------------------------------


async def test_listed_next_to_ping_with_a_description():
    async with Client(app) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert {"ping", "generate_board"} <= set(tools)
        assert tools["generate_board"].description.strip()


async def test_input_schema_lists_the_three_fields():
    async with Client(app) as client:
        schema = (await tool_info(client)).input_schema
    properties = schema["properties"]
    assert set(properties) == {"players", "mode", "seed"}
    assert all(properties[name].get("description") for name in properties)
    assert sorted(schema["required"]) == ["mode", "players"]

    assert properties["players"]["type"] == "integer"
    assert properties["players"]["minimum"] == 2
    assert properties["players"]["maximum"] == 5
    assert properties["mode"]["enum"] == ["normal", "flash"]

    seed_int = next(arm for arm in properties["seed"]["anyOf"] if arm.get("type") == "integer")
    assert seed_int["minimum"] == 0
    assert seed_int["maximum"] == MAX_SEED == 2**53 - 1


async def test_output_schema_is_published():
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
    assert schema is not None
    assert set(schema["properties"]) == {"players", "mode", "seed", "hexes", "assembly"}
    jsonschema.Draft202012Validator.check_schema(schema)


# --- Output -----------------------------------------------------------------


@pytest.mark.parametrize(("players", "mode"), CASES)
async def test_response_matches_the_output_schema_and_the_library(players, mode):
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
        result = await call(client, players=players, mode=mode, seed=7)
    assert not result.is_error
    data = result.structured_content
    jsonschema.validate(data, schema)

    assert set(data) == {"players", "mode", "seed", "hexes", "assembly"}
    assert (data["players"], data["mode"], data["seed"]) == (players, mode, 7)

    board = generate_board(players, 7, MODES[mode])
    assert len(data["hexes"]) == len(board.tiles)
    for item, tile in zip(data["hexes"], board.tiles):
        assert set(item) == {"q", "r", "terrain", "varietal"}
        assert (item["q"], item["r"]) == (tile.hex.q, tile.hex.r)
        assert item["terrain"] == tile.terrain.value
        if tile.terrain is Terrain.VINEYARD:
            assert item["varietal"] in {"malbec", "bonarda", "torrontes"}
        else:
            assert item["varietal"] is None
    assert [(h["q"], h["r"]) for h in data["hexes"]] == sorted((h["q"], h["r"]) for h in data["hexes"])

    steps = assembly_instructions(board)
    assert len(data["assembly"]) == len(steps)
    for item, step in zip(data["assembly"], steps):
        assert set(item) == {"row", "position", "q", "r", "terrain", "varietal", "text"}
        assert (item["row"], item["position"]) == (step.row, step.position)
        assert (item["q"], item["r"]) == (step.hex.q, step.hex.r)
        assert item["terrain"] == step.terrain.value
        assert item["varietal"] == varietal_to_json(step.varietal)
        assert item["text"] == step.text


async def test_varietals_are_lowercase_ascii():
    async with Client(app) as client:
        result = await call(client, players=5, mode="normal", seed=3)
    varietals = {h["varietal"] for h in result.structured_content["hexes"]} - {None}
    assert varietals
    assert varietals <= {"malbec", "bonarda", "torrontes"}
    assert all(name.isascii() for name in varietals)
    texts = [s["text"] for s in result.structured_content["assembly"]]
    assert any("vineyard, " in text for text in texts)  # display names stay in the text


@pytest.mark.parametrize(("players", "mode"), CASES)
async def test_hexes_convert_back_to_the_library_board(players, mode):
    async with Client(app) as client:
        result = await call(client, players=players, mode=mode, seed=12345)
    board = hexes_to_board(result.structured_content["hexes"])
    assert board == generate_board(players, 12345, MODES[mode])


async def test_same_arguments_give_identical_json():
    async with Client(app) as client:
        first = await call(client, players=4, mode="flash", seed=99)
        second = await call(client, players=4, mode="flash", seed=99)
    assert first.structured_content == second.structured_content
    assert text_of(first) == text_of(second)


async def test_a_large_seed_is_accepted():
    async with Client(app) as client:
        result = await call(client, players=3, mode="normal", seed=MAX_SEED)
    assert not result.is_error
    assert result.structured_content["seed"] == MAX_SEED


async def test_without_seed_the_server_picks_one_and_returns_it():
    async with Client(app) as client:
        picked = await call(client, players=3, mode="normal")
        assert not picked.is_error
        seed = picked.structured_content["seed"]
        assert isinstance(seed, int)
        assert 0 <= seed <= MAX_PICKED_SEED == 2**31 - 1

        again = await call(client, players=3, mode="normal", seed=seed)
    assert again.structured_content["hexes"] == picked.structured_content["hexes"]
    assert again.structured_content["assembly"] == picked.structured_content["assembly"]


# --- Errors -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("arguments", "field"),
    [
        ({"players": 1, "mode": "normal"}, "players"),
        ({"players": 6, "mode": "normal"}, "players"),
        ({"players": 3, "mode": "Normal"}, "mode"),
        ({"players": 3, "mode": "fast"}, "mode"),
        ({"players": 3, "mode": "normal", "seed": -1}, "seed"),
        ({"players": 3, "mode": "normal", "seed": 1.5}, "seed"),
        ({"players": 3, "mode": "normal", "seed": "7"}, "seed"),
        ({"players": 3, "mode": "normal", "seed": MAX_SEED + 1}, "seed"),
        ({"players": "3", "mode": "normal"}, "players"),
        ({"players": True, "mode": "normal"}, "players"),
        ({"players": 3.0, "mode": "normal"}, "players"),
        ({"players": 3.5, "mode": "normal"}, "players"),
        ({"players": 3, "mode": "normal", "seed": True}, "seed"),
    ],
)
async def test_bad_input_is_a_tool_error_naming_the_field(arguments, field):
    async with Client(app) as client:
        result = await client.call_tool("generate_board", arguments)
    assert result.is_error
    assert field in text_of(result)


async def test_session_survives_a_tool_error():
    async with Client(app) as client:
        assert (await call(client, players=6, mode="normal")).is_error
        assert (await call(client, players=3, mode="fast")).is_error
        result = await call(client, players=3, mode="normal", seed=1)
    assert not result.is_error
    assert result.structured_content["players"] == 3


# --- server.schemas ---------------------------------------------------------


def test_string_mappings_round_trip():
    assert [terrain_to_json(t) for t in Terrain] == ["river", "vineyard", "stone", "empty"]
    assert [varietal_to_json(v) for v in Varietal] == ["malbec", "bonarda", "torrontes"]
    assert [mode_to_json(m) for m in Mode] == ["normal", "flash"]
    assert varietal_to_json(None) is None
    for terrain in Terrain:
        assert terrain_from_json(terrain_to_json(terrain)) is terrain
    for varietal in Varietal:
        assert varietal_from_json(varietal_to_json(varietal)) is varietal
    for mode in Mode:
        assert mode_from_json(mode_to_json(mode)) is mode
    assert varietal_from_json(None) is None


@pytest.mark.parametrize(
    ("convert", "value"),
    [
        (terrain_from_json, "lake"),
        (terrain_from_json, "River"),
        (varietal_from_json, "Malbec"),
        (varietal_from_json, "Torrontés"),
        (varietal_from_json, "syrah"),
        (mode_from_json, "Normal"),
        (mode_from_json, 1),
    ],
)
def test_unknown_strings_raise_value_error(convert, value):
    with pytest.raises(ValueError):
        convert(value)


def test_board_to_hexes_and_back():
    board = generate_board(3, 5, Mode.NORMAL)
    hexes = board_to_hexes(board)
    assert len(hexes) == len(board.tiles)
    assert hexes_to_board(hexes) == board


def hexes(*items):
    base = [
        {"q": 0, "r": 0, "terrain": "river", "varietal": None},
        {"q": 1, "r": 0, "terrain": "empty", "varietal": None},
    ]
    return base + list(items)


def test_valid_hexes_build_the_tiles():
    board = hexes_to_board(hexes({"q": 2, "r": 0, "terrain": "vineyard", "varietal": "torrontes"}))
    assert board.tile_at(Hex(2, 0)) == Tile(Hex(2, 0), Terrain.VINEYARD, Varietal.TORRONTES)
    assert board == Board(tiles=board.tiles)


def test_unknown_terrain_raises():
    with pytest.raises(ValueError, match="terrain"):
        hexes_to_board(hexes({"q": 2, "r": 0, "terrain": "lake", "varietal": None}))


def test_unknown_varietal_raises():
    with pytest.raises(ValueError, match="varietal"):
        hexes_to_board(hexes({"q": 2, "r": 0, "terrain": "vineyard", "varietal": "syrah"}))


def test_vineyard_without_varietal_raises():
    with pytest.raises(ValueError, match="varietal"):
        hexes_to_board(hexes({"q": 2, "r": 0, "terrain": "vineyard", "varietal": None}))


def test_varietal_on_a_non_vineyard_raises():
    with pytest.raises(ValueError, match="varietal"):
        hexes_to_board(hexes({"q": 2, "r": 0, "terrain": "stone", "varietal": "malbec"}))


def test_two_hexes_on_the_same_coordinate_raise():
    with pytest.raises(ValueError, match="two tiles"):
        hexes_to_board(hexes({"q": 1, "r": 0, "terrain": "stone", "varietal": None}))


@pytest.mark.parametrize(
    "item",
    [
        {"q": 2, "r": 0, "terrain": "empty"},
        {"q": 2, "r": 0, "terrain": "empty", "varietal": None, "owner": "a"},
        {"q": "2", "r": 0, "terrain": "empty", "varietal": None},
        {"q": True, "r": 0, "terrain": "empty", "varietal": None},
        ["q", "r"],
    ],
)
def test_malformed_hex_objects_raise(item):
    with pytest.raises((ValueError, TypeError)):
        hexes_to_board(hexes(item))


def test_hexes_must_be_a_list():
    with pytest.raises(TypeError):
        hexes_to_board({"q": 0, "r": 0, "terrain": "river", "varietal": None})
