"""The `calculate_score` MCP tool and its JSON shapes in `server.schemas`."""

import random

import jsonschema
import pytest
from mcp import Client

from acequias.hex import Direction, Hex
from acequias.model import PieceKind, Player
from server.app import app
from server.schemas import (
    canal_from_json,
    canal_to_json,
    direction_from_json,
    direction_to_json,
    kind_from_json,
    kind_to_json,
    players_from_json,
)

pytestmark = pytest.mark.anyio

KINDS = ["straight", "gentle_curve", "sharp_curve", "symmetric_y", "t_branch", "claw"]
DIRECTIONS = ["E", "NE", "NW", "W", "SW", "SE"]
SCORE_KEYS = {
    "player",
    "seat",
    "vineyards",
    "bodega",
    "rights_paid",
    "rights_collected",
    "debt",
    "total",
    "watered",
    "watered_vineyards",
}
TERMS = ("vineyards", "bodega", "rights_paid", "rights_collected", "debt", "total")


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text_of(result):
    return "".join(block.text for block in result.content if block.type == "text")


async def tool_info(client, name="calculate_score"):
    tools = (await client.list_tools()).tools
    return next(tool for tool in tools if tool.name == name)


async def call(client, **arguments):
    return await client.call_tool("calculate_score", arguments)


def resolve(schema, node):
    """`node` with a local `$ref` replaced by its definition."""
    ref = node.get("$ref")
    if ref is None:
        return node
    return schema["$defs"][ref.rsplit("/", 1)[-1]]


# --- The hand-worked game from tests/test_scoring.py ------------------------
#
# A lane is one board row: a river hex at q = 0, straight W-E canals at
# q = 1..n with the given owners, and a vineyard at q = n + 1. Lanes sit on
# even rows, so no two lanes touch and each vineyard has one path.


def hex_json(q, r, terrain, varietal=None):
    return {"q": q, "r": r, "terrain": terrain, "varietal": varietal}


def canal(q, r, owner, kind="straight", rotation=0):
    return {"q": q, "r": r, "kind": kind, "rotation": rotation, "owner": owner}


def game_json(lanes, debts, mode="normal"):
    hexes, canals, claims = [], [], []
    for row, owners, varietal, claimant in lanes:
        r = 2 * row
        if owners:
            hexes.append(hex_json(0, r, "river"))
        for q, owner in enumerate(owners, start=1):
            hexes.append(hex_json(q, r, "empty"))
            canals.append(canal(q, r, owner))
        hexes.append(hex_json(len(owners) + 1, r, "vineyard", varietal))
        if claimant is not None:
            claims.append({"q": len(owners) + 1, "r": r, "player": claimant})
    return {
        "mode": mode,
        "hexes": hexes,
        "canals": canals,
        "floodgates": [],
        "claims": claims,
        "players": [{"id": pid, "debt": debt} for pid, debt in debts.items()],
    }


def three_player_game():
    """The 3-player Normal game of `test_scoring.py`, "A full hand-worked game".

    a: 6 + bodega 2 - paid 3 + collected 1 - debt 1 = 5.
    b: 6 + 0 - paid 1 + collected 2 - debt 2 = 5.
    c: 2 + 0 - 0 + collected 1 - debt 1 = 2.
    a and b tie on 5; a has 3 watered vineyards to b's 2, so a wins.
    """
    lanes = [
        (0, ["a", "a"], "malbec", "a"),
        (1, ["b", "a"], "bonarda", "a"),
        (2, ["c", "b", "c"], "torrontes", "a"),
        (3, ["a", "b"], "malbec", "b"),
        (4, ["b"], "malbec", "b"),
        (5, ["c"], "bonarda", "c"),
        (6, [], "malbec", "c"),  # dry: no river, no canal
        (7, ["a"], "malbec", None),  # watered but unclaimed
    ]
    return game_json(lanes, {"a": 1, "b": 2, "c": 1})


def small_board(*extra_hexes):
    """River (0, 0), empty (1, 0) and (2, 0), a Malbec vineyard at (3, 0)."""
    return [
        hex_json(0, 0, "river"),
        hex_json(1, 0, "empty"),
        hex_json(2, 0, "empty"),
        hex_json(3, 0, "vineyard", "malbec"),
        hex_json(0, 1, "stone"),
        *extra_hexes,
    ]


def small_game(**overrides):
    arguments = {
        "mode": "normal",
        "hexes": small_board(),
        "canals": [canal(1, 0, "a"), canal(2, 0, "b")],
        "floodgates": [],
        "claims": [{"q": 3, "r": 0, "player": "a"}],
        "players": [{"id": "a", "debt": 0}, {"id": "b", "debt": 0}],
    }
    arguments.update(overrides)
    return arguments


# --- Listing and schemas ----------------------------------------------------


async def test_listed_next_to_ping_and_generate_board_with_a_description():
    async with Client(app) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert {"ping", "generate_board", "calculate_score"} <= set(tools)
    assert tools["calculate_score"].description.strip()


async def test_input_schema_describes_every_field_and_its_allowed_values():
    async with Client(app) as client:
        schema = (await tool_info(client)).input_schema
    properties = schema["properties"]
    assert set(properties) == {"mode", "hexes", "canals", "floodgates", "claims", "players"}
    assert all(properties[name].get("description") for name in properties)
    assert sorted(schema["required"]) == ["hexes", "mode", "players"]

    assert properties["mode"]["enum"] == ["normal", "flash"]
    assert properties["players"]["minItems"] == 2
    assert properties["players"]["maxItems"] == 5
    for name in ("canals", "floodgates", "claims"):
        assert properties[name]["default"] == []

    def item(name):
        return resolve(schema, properties[name]["items"])

    for name, keys in [
        ("hexes", {"q", "r", "terrain", "varietal"}),
        ("canals", {"q", "r", "kind", "rotation", "owner"}),
        ("floodgates", {"q", "r", "direction"}),
        ("claims", {"q", "r", "player"}),
        ("players", {"id", "debt"}),
    ]:
        shape = item(name)
        assert set(shape["properties"]) == keys
        assert sorted(shape["required"]) == sorted(keys)
        assert shape["additionalProperties"] is False
        assert all(field.get("description") for field in shape["properties"].values())

    canal_fields = item("canals")["properties"]
    assert canal_fields["kind"]["enum"] == KINDS
    assert canal_fields["rotation"]["type"] == "integer"
    assert (canal_fields["rotation"]["minimum"], canal_fields["rotation"]["maximum"]) == (0, 5)
    assert item("floodgates")["properties"]["direction"]["enum"] == DIRECTIONS
    player_fields = item("players")["properties"]
    assert player_fields["debt"]["type"] == "integer"
    assert player_fields["debt"]["minimum"] == 0
    assert player_fields["id"]["minLength"] == 1


async def test_output_schema_is_published():
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
    assert schema is not None
    assert set(schema["properties"]) == {"mode", "scores", "winners"}
    jsonschema.Draft202012Validator.check_schema(schema)
    score = resolve(schema, schema["properties"]["scores"]["items"])
    assert set(score["properties"]) == SCORE_KEYS


# --- Output -----------------------------------------------------------------


async def test_the_hand_worked_game_scores_every_term_exactly():
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
        result = await call(client, **three_player_game())
    assert not result.is_error, text_of(result)
    data = result.structured_content
    jsonschema.validate(data, schema)

    assert set(data) == {"mode", "scores", "winners"}
    assert data["mode"] == "normal"
    assert data["winners"] == ["a"]

    scores = data["scores"]
    assert [s["player"] for s in scores] == ["a", "b", "c"]
    assert [s["seat"] for s in scores] == [1, 2, 3]
    assert all(set(s) == SCORE_KEYS for s in scores)
    assert tuple(scores[0][t] for t in TERMS) == (6, 2, 3, 1, 1, 5)
    assert tuple(scores[1][t] for t in TERMS) == (6, 0, 1, 2, 2, 5)
    assert tuple(scores[2][t] for t in TERMS) == (2, 0, 0, 1, 1, 2)
    assert [s["watered"] for s in scores] == [3, 2, 1]
    for s in scores:
        assert s["total"] == (
            s["vineyards"] + s["bodega"] - s["rights_paid"] + s["rights_collected"] - s["debt"]
        )

    assert scores[0]["watered_vineyards"] == [
        {
            "q": 3, "r": 0, "varietal": "malbec",
            "path": [canal(1, 0, "a"), canal(2, 0, "a")],
            "pays": [],
        },
        {
            "q": 3, "r": 2, "varietal": "bonarda",
            "path": [canal(1, 2, "b"), canal(2, 2, "a")],
            "pays": ["b"],
        },
        {
            "q": 4, "r": 4, "varietal": "torrontes",
            "path": [canal(1, 4, "c"), canal(2, 4, "b"), canal(3, 4, "c")],
            "pays": ["b", "c"],
        },
    ]  # fmt: skip
    # b's vineyards in hex order: own Malbec (2, 8), then via a (3, 6).
    assert scores[1]["watered_vineyards"] == [
        {"q": 2, "r": 8, "varietal": "malbec", "path": [canal(1, 8, "b")], "pays": []},
        {
            "q": 3, "r": 6, "varietal": "malbec",
            "path": [canal(1, 6, "a"), canal(2, 6, "b")],
            "pays": ["a"],
        },
    ]  # fmt: skip
    assert scores[2]["watered_vineyards"] == [
        {"q": 2, "r": 10, "varietal": "bonarda", "path": [canal(1, 10, "c")], "pays": []},
    ]


async def test_flash_mode_uses_the_flash_bodega_bonus():
    arguments = three_player_game()
    arguments["mode"] = "flash"
    async with Client(app) as client:
        result = await call(client, **arguments)
    data = result.structured_content
    assert data["mode"] == "flash"
    assert data["scores"][0]["bodega"] == 1
    assert data["scores"][0]["total"] == 4


@pytest.mark.parametrize("seed", range(5))
async def test_the_order_of_the_lists_does_not_change_the_result(seed):
    arguments = three_player_game()
    # Two floodgates, so their order is shuffled too.
    arguments["floodgates"] = [{"q": 1, "r": 14, "direction": "E"}, {"q": 1, "r": 4, "direction": "W"}]
    shuffled = {key: list(value) if isinstance(value, list) else value for key, value in arguments.items()}
    rng = random.Random(seed)
    for key in ("hexes", "canals", "floodgates", "claims"):
        rng.shuffle(shuffled[key])
    assert shuffled != arguments
    async with Client(app) as client:
        first = await call(client, **arguments)
        second = await call(client, **shuffled)
    assert not first.is_error, text_of(first)
    assert first.structured_content == second.structured_content


async def test_a_floodgate_closes_the_path_it_sits_on():
    async with Client(app) as client:
        open_path = await call(client, **small_game())
        closed = await call(client, **small_game(floodgates=[{"q": 2, "r": 0, "direction": "E"}]))
    assert open_path.structured_content["scores"][0]["watered"] == 1
    a, b = closed.structured_content["scores"]
    assert (a["watered"], a["vineyards"], a["rights_paid"], b["rights_collected"]) == (0, 0, 0, 0)


async def test_a_fresh_generated_board_scores_zero_for_everyone():
    async with Client(app) as client:
        board = (await client.call_tool(
            "generate_board", {"players": 4, "mode": "flash", "seed": 21}
        )).structured_content
        players = [{"id": pid, "debt": 0} for pid in ["w", "x", "y", "z"]]
        result = await call(client, mode=board["mode"], hexes=board["hexes"], players=players)
    assert not result.is_error, text_of(result)
    data = result.structured_content
    assert data["mode"] == "flash"
    assert [s["player"] for s in data["scores"]] == ["w", "x", "y", "z"]
    for score in data["scores"]:
        assert all(score[term] == 0 for term in TERMS)
        assert score["watered"] == 0
        assert score["watered_vineyards"] == []
    assert data["winners"] == ["w", "x", "y", "z"]


# --- Errors -----------------------------------------------------------------


def players(*ids):
    return [{"id": pid, "debt": 0} for pid in ids]


ERROR_CASES = {
    "unknown terrain": (
        {"hexes": small_board(hex_json(4, 0, "lake"))}, "terrain"),
    "canal off the board": (
        {"canals": [canal(1, 0, "a"), canal(9, 9, "b")]}, "no tile"),
    "claim off the board": (
        {"claims": [{"q": 9, "r": 9, "player": "a"}]}, "not a vineyard"),
    "canal on a vineyard": (
        {"canals": [canal(3, 0, "a")], "claims": []}, "empty tiles"),
    "canal on the river": (
        {"canals": [canal(0, 0, "a")]}, "empty tiles"),
    "claim on an empty hex": (
        {"claims": [{"q": 2, "r": 0, "player": "a"}]}, "not a vineyard"),
    "two canals on one hex": (
        {"canals": [canal(1, 0, "a"), canal(1, 0, "b", kind="claw")]}, "two canals"),
    "two claims on one vineyard": (
        {"claims": [{"q": 3, "r": 0, "player": "a"}, {"q": 3, "r": 0, "player": "b"}]},
        "two claims"),
    "unknown owner": (
        {"canals": [canal(1, 0, "a"), canal(2, 0, "zed")]}, "unknown player"),
    "unknown claimant": (
        {"claims": [{"q": 3, "r": 0, "player": "zed"}]}, "unknown player"),
    "duplicate player ids": (
        {"players": players("a", "b", "a")}, "duplicate player ids"),
    "one player": (
        {"players": players("a"), "canals": [], "claims": []}, "players"),
    "six players": (
        {"players": players("a", "b", "c", "d", "e", "f")}, "players"),
    "players as an int": (
        {"players": 3}, "players"),
    "empty player id": (
        {"players": [{"id": "", "debt": 0}, {"id": "a", "debt": 0}]}, "id"),
    "negative debt": (
        {"players": [{"id": "a", "debt": -1}, {"id": "b", "debt": 0}]}, "debt"),
    "rotation 6": (
        {"canals": [canal(1, 0, "a", rotation=6)]}, "rotation"),
    "rotation -1": (
        {"canals": [canal(1, 0, "a", rotation=-1)]}, "rotation"),
    "kind floodgate": (
        {"canals": [canal(1, 0, "a", kind="floodgate")]}, "kind"),
    "kind with a space": (
        {"canals": [canal(1, 0, "a", kind="gentle curve")]}, "kind"),
    "lowercase direction": (
        {"floodgates": [{"q": 1, "r": 0, "direction": "e"}]}, "direction"),
    "direction N": (
        {"floodgates": [{"q": 1, "r": 0, "direction": "N"}]}, "direction"),
    "mode Normal": (
        {"mode": "Normal"}, "mode"),
    "floodgate with no canal": (
        {"canals": [canal(1, 0, "a")], "floodgates": [{"q": 2, "r": 0, "direction": "E"}]},
        "no canal"),
    "floodgate on an edge the canal does not open": (
        {"floodgates": [{"q": 1, "r": 0, "direction": "NE"}]}, "does not open"),
    "two floodgates on one edge": (
        {"floodgates": [{"q": 1, "r": 0, "direction": "E"}, {"q": 1, "r": 0, "direction": "E"}]},
        "two floodgates"),
    "one edge from both sides": (
        {"floodgates": [{"q": 1, "r": 0, "direction": "E"}, {"q": 2, "r": 0, "direction": "W"}]},
        "two floodgates"),
    "q as a string": (
        {"claims": [{"q": "3", "r": 0, "player": "a"}]}, "q"),
    "r as a float": (
        {"canals": [canal(1, 0.0, "a")]}, "r"),
    "q as a boolean": (
        {"canals": [canal(True, 0, "a")]}, "q"),
    "rotation as a string": (
        {"canals": [canal(1, 0, "a", rotation="0")]}, "rotation"),
    "debt as a float": (
        {"players": [{"id": "a", "debt": 1.0}, {"id": "b", "debt": 0}]}, "debt"),
    "debt as a boolean": (
        {"players": [{"id": "a", "debt": False}, {"id": "b", "debt": 0}]}, "debt"),
    "an extra key on a canal": (
        {"canals": [{**canal(1, 0, "a"), "player": "a"}]}, "player"),
}  # fmt: skip


@pytest.mark.parametrize(("overrides", "message"), ERROR_CASES.values(), ids=ERROR_CASES.keys())
async def test_bad_input_is_a_tool_error_saying_what_is_wrong(overrides, message):
    async with Client(app) as client:
        result = await call(client, **small_game(**overrides))
    assert result.is_error
    assert message in text_of(result)


async def test_the_small_game_itself_is_valid():
    async with Client(app) as client:
        result = await call(client, **small_game())
    assert not result.is_error, text_of(result)
    a, b = result.structured_content["scores"]
    assert (a["vineyards"], a["rights_paid"], b["rights_collected"]) == (3, 1, 1)


async def test_session_survives_a_tool_error():
    async with Client(app) as client:
        assert (await call(client, **small_game(mode="Normal"))).is_error
        assert (await call(client, **small_game(claims=[{"q": 2, "r": 0, "player": "a"}]))).is_error
        result = await call(client, **small_game())
    assert not result.is_error
    assert result.structured_content["winners"] == ["a"]


# --- server.schemas ---------------------------------------------------------


def test_kind_and_direction_strings_round_trip():
    canal_kinds = [kind for kind in PieceKind if kind.is_canal]
    assert [kind_to_json(kind) for kind in canal_kinds] == KINDS
    assert [direction_to_json(d) for d in Direction] == DIRECTIONS
    for kind in canal_kinds:
        assert kind_from_json(kind_to_json(kind)) is kind
    for direction in Direction:
        assert direction_from_json(direction_to_json(direction)) is direction
    assert all(name.isascii() for name in KINDS)


@pytest.mark.parametrize(
    ("convert", "value"),
    [
        (kind_from_json, "floodgate"),
        (kind_from_json, "gentle curve"),
        (kind_from_json, "T branch"),
        (kind_from_json, "Straight"),
        (direction_from_json, "e"),
        (direction_from_json, "N"),
        (direction_from_json, 0),
    ],
)
def test_unknown_kind_and_direction_strings_raise_value_error(convert, value):
    with pytest.raises(ValueError):
        convert(value)


def test_the_floodgate_has_no_canal_kind_string():
    with pytest.raises(ValueError):
        kind_to_json(PieceKind.FLOODGATE)


def test_canal_json_round_trips():
    item = canal(2, -1, "a", kind="t_branch", rotation=4)
    placed = canal_from_json(item)
    assert (placed.hex, placed.kind, placed.rotation, placed.owner) == (
        Hex(2, -1), PieceKind.T_BRANCH, 4, "a"
    )
    assert canal_to_json(placed) == item


def test_players_get_seats_in_list_order():
    assert players_from_json([{"id": "z", "debt": 2}, {"id": "a", "debt": 0}]) == (
        Player("z", 1, 2),
        Player("a", 2, 0),
    )
