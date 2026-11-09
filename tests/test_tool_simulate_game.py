"""The `simulate_game` MCP tool and the preset/overrides JSON in `server.schemas`."""

import dataclasses
import math

import jsonschema
import pytest
from mcp import Client

from acequias.bots import POLICIES
from acequias.config import Preset, preset
from acequias.model import Mode, PieceKind
from acequias.sim import SimRules, simulate_game
from server.app import app
from server.schemas import overrides_from_json
from server.tools.board import MAX_PICKED_SEED, MAX_SEED
from server.tools.simulate import DEFAULT_GAMES, MAX_GAMES

pytestmark = pytest.mark.anyio

MODES = {"normal": Mode.NORMAL, "flash": Mode.FLASH}
PRESET_FIELDS = [f.name for f in dataclasses.fields(Preset) if f.name != "mode"]
RESULT_KEYS = {
    "mode", "players", "policies", "n", "seed", "preset", "win_rate_by_position",
    "win_rate_by_seat", "win_rate_by_policy", "turn_order_advantage", "shared_win_rate",
    "score_terms", "mean_total_by_position", "winning_score", "turns_per_game",
    "actions_per_game", "games_with_bribe", "games_with_floodgate", "win_rate_bribers",
    "win_rate_non_bribers", "bodega_rate", "winner_varietal_rate",
}  # fmt: skip


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text_of(result):
    return "".join(block.text for block in result.content if block.type == "text")


async def tool_info(client):
    tools = (await client.list_tools()).tools
    return next(tool for tool in tools if tool.name == "simulate_game")


async def call(client, **arguments):
    return await client.call_tool("simulate_game", arguments)


def library_json(mode, players, games, seed, policies=None, overrides=None):
    rules = SimRules(
        MODES[mode],
        players,
        tuple(policies or ["greedy"] * players),
        overrides_from_json(overrides or {}),
    )
    return simulate_game(rules, games, seed).to_json()


# --- Listing and schemas ----------------------------------------------------


async def test_listed_next_to_the_other_tools_with_a_description():
    async with Client(app) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert {"ping", "generate_board", "calculate_score", "simulate_game"} <= set(tools)
    assert tools["simulate_game"].description.strip()


async def test_input_schema_describes_every_field():
    async with Client(app) as client:
        schema = (await tool_info(client)).input_schema
    jsonschema.Draft202012Validator.check_schema(schema)
    properties = schema["properties"]
    assert set(properties) == {"mode", "players", "games", "seed", "policies", "overrides"}
    assert all(properties[name].get("description") for name in properties)
    assert sorted(schema["required"]) == ["mode", "players"]

    assert properties["mode"]["enum"] == ["normal", "flash"]
    assert (properties["players"]["minimum"], properties["players"]["maximum"]) == (2, 5)
    games = properties["games"]
    assert (games["type"], games["minimum"], games["maximum"]) == ("integer", 1, MAX_GAMES)
    # Planned as 1,000 and 100; lowered so one call fits in 30 s (see MAX_GAMES).
    assert games["default"] == DEFAULT_GAMES == min(100, MAX_GAMES)
    assert MAX_GAMES == 10

    seed_int = next(arm for arm in properties["seed"]["anyOf"] if arm.get("type") == "integer")
    assert (seed_int["minimum"], seed_int["maximum"]) == (0, MAX_SEED)
    assert MAX_SEED == 2**53 - 1

    policy_list = next(arm for arm in properties["policies"]["anyOf"] if arm.get("type") == "array")
    assert policy_list["items"]["enum"] == list(POLICIES)

    assert properties["overrides"]["default"] == {}
    overrides = schema["$defs"]["PresetOverridesJSON"]
    assert overrides["additionalProperties"] is False
    assert list(overrides["properties"]) == PRESET_FIELDS
    assert all(item.get("description") for item in overrides["properties"].values())
    assert overrides["properties"]["rounds"]["propertyNames"]["enum"] == ["2", "3", "4", "5"]
    assert overrides["properties"]["bag_mix"]["propertyNames"]["enum"] == [
        kind.name.lower() for kind in PieceKind
    ]


async def test_output_schema_covers_every_key_of_to_json():
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
    assert schema is not None
    jsonschema.Draft202012Validator.check_schema(schema)
    assert set(schema["properties"]) == RESULT_KEYS
    assert set(schema["required"]) == RESULT_KEYS
    assert set(library_json("flash", 2, 1, 0)) == RESULT_KEYS


# --- Output -----------------------------------------------------------------


@pytest.mark.parametrize(("players", "mode"), [(2, "normal"), (3, "flash")])
async def test_five_games_match_the_schema_and_the_library(players, mode):
    async with Client(app) as client:
        schema = (await tool_info(client)).output_schema
        result = await call(client, mode=mode, players=players, games=5, seed=11)
    assert not result.is_error, text_of(result)
    data = result.structured_content
    jsonschema.validate(data, schema)
    assert data == library_json(mode, players, 5, 11)
    assert math.isclose(sum(data["win_rate_by_position"]), 1, abs_tol=1e-9)
    assert (data["mode"], data["players"], data["n"], data["seed"]) == (mode, players, 5, 11)
    assert data["policies"] == ["greedy"] * players


async def test_mixed_policies_give_one_win_rate_per_policy():
    policies = ["random", "greedy", "random"]
    async with Client(app) as client:
        result = await call(client, mode="flash", players=3, games=3, seed=5, policies=policies)
    assert not result.is_error, text_of(result)
    data = result.structured_content
    assert set(data["win_rate_by_policy"]) == {"random", "greedy"}
    assert data == library_json("flash", 3, 3, 5, policies=policies)


async def test_same_input_and_seed_give_identical_json():
    async with Client(app) as client:
        first = await call(client, mode="flash", players=4, games=2, seed=MAX_SEED)
        second = await call(client, mode="flash", players=4, games=2, seed=MAX_SEED)
    assert not first.is_error, text_of(first)
    assert first.structured_content == second.structured_content
    assert text_of(first) == text_of(second)


async def test_without_seed_the_server_picks_one_and_returns_it():
    async with Client(app) as client:
        picked = await call(client, mode="flash", players=2, games=2)
        assert not picked.is_error, text_of(picked)
        seed = picked.structured_content["seed"]
        assert isinstance(seed, int)
        assert 0 <= seed <= MAX_PICKED_SEED == 2**31 - 1
        again = await call(client, mode="flash", players=2, games=2, seed=seed)
    assert again.structured_content == picked.structured_content


async def test_games_has_a_default():
    async with Client(app) as client:
        # One round per game keeps the default run quick.
        one_round = {"rounds": {"2": 1, "3": 1, "4": 1, "5": 1}}
        result = await call(client, mode="flash", players=2, seed=1, overrides=one_round)
    assert not result.is_error, text_of(result)
    assert result.structured_content["n"] == DEFAULT_GAMES


async def test_overrides_change_only_the_given_fields():
    async with Client(app) as client:
        result = await call(
            client, mode="flash", players=2, games=1, seed=3, overrides={"market_size": 5}
        )
    assert not result.is_error, text_of(result)
    got = result.structured_content["preset"]
    shipped = library_json("flash", 2, 1, 3)["preset"]
    assert got["market_size"] == 5
    assert {k: v for k, v in got.items() if k != "market_size"} == {
        k: v for k, v in shipped.items() if k != "market_size"
    }
    assert shipped["market_size"] == preset(Mode.FLASH).market_size
    assert result.structured_content == library_json(
        "flash", 2, 1, 3, overrides={"market_size": 5}
    )


async def test_a_result_preset_can_be_passed_back_as_overrides():
    async with Client(app) as client:
        first = await call(client, mode="flash", players=2, games=1, seed=4)
        overrides = {k: v for k, v in first.structured_content["preset"].items() if k != "mode"}
        overrides["rounds"] = {"2": 4, "3": 4, "4": 4, "5": 4}
        second = await call(client, mode="flash", players=2, games=1, seed=4, overrides=overrides)
    assert not second.is_error, text_of(second)
    assert second.structured_content["preset"] == {"mode": "flash", **overrides}
    assert second.structured_content["turns_per_game"] == 8


def test_overrides_from_json_converts_keys_and_pairs():
    changes = overrides_from_json(
        {
            "rounds": {"2": 1, "3": 2, "4": 3, "5": 4},
            "bag_mix": {"floodgate": 10, "t_branch": 5},
            "vineyard_distance": [2, 3],
            "die_faces": 4,
        }
    )
    assert changes == {
        "rounds": {2: 1, 3: 2, 4: 3, 5: 4},
        "bag_mix": {PieceKind.FLOODGATE: 10, PieceKind.T_BRANCH: 5},
        "vineyard_distance": (2, 3),
        "die_faces": 4,
    }


# --- Errors -----------------------------------------------------------------

BASE = {"mode": "flash", "players": 2, "games": 1, "seed": 1}
FULL_BAG = {kind.name.lower(): share for kind, share in preset(Mode.FLASH).bag_mix.items()}


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        # games
        ({"games": 0}, "games"),
        ({"games": MAX_GAMES + 1}, "games"),
        ({"games": "5"}, "games"),
        ({"games": 5.0}, "games"),
        ({"games": True}, "games"),
        # players, mode, seed
        ({"players": 1}, "players"),
        ({"players": 6}, "players"),
        ({"players": "3"}, "players"),
        ({"mode": "Normal"}, "mode"),
        ({"mode": "fast"}, "mode"),
        ({"seed": -1}, "seed"),
        ({"seed": 2**53}, "seed"),
        ({"seed": 1.5}, "seed"),
        # policies
        ({"policies": ["greedy", "smart"]}, "policies"),
        ({"policies": ["greedy"]}, "policies"),
        ({"policies": ["greedy", "greedy", "random"]}, "policies"),
        # overrides keys
        ({"overrides": {"speed": 3}}, "speed"),
        ({"overrides": {"mode": "normal"}}, "mode"),
        # overrides types
        ({"overrides": {"rounds": 10}}, "rounds"),
        ({"overrides": {"hexes_per_player": "12"}}, "hexes_per_player"),
        ({"overrides": {"stone_share": 10.5}}, "stone_share"),
        ({"overrides": {"bag_mix": {**FULL_BAG, "pipe": 0}}}, "bag_mix"),
        ({"overrides": {"vineyard_distance": [3]}}, "vineyard_distance"),
    ],
)
async def test_bad_input_is_a_tool_error_naming_the_field(changes, expected):
    async with Client(app) as client:
        result = await client.call_tool("simulate_game", {**BASE, **changes})
    assert result.is_error
    assert expected in text_of(result)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"stone_share": 101}, "stone_share must be a percentage from 0 to 100, got 101"),
        (
            {"bag_mix": {**FULL_BAG, "straight": FULL_BAG["straight"] - 10}},
            "bag_mix shares must add up to exactly 100, got 90",
        ),
        ({"vineyard_distance": [1, 3]}, "vineyard_distance must start at 2 or more"),
        ({"rounds": {"2": 5, "3": 5, "4": 5}}, "rounds has no value for player counts [5]"),
    ],
)
async def test_values_preset_rejects_come_back_with_its_message(overrides, message):
    async with Client(app) as client:
        result = await call(client, **BASE, overrides=overrides)
    assert result.is_error
    assert message in text_of(result)


async def test_a_preset_the_board_cannot_meet_is_an_error_not_a_partial_result():
    overrides = {"vineyard_distance": [3, 3], "hexes_per_player": 7}
    with pytest.raises(ValueError) as raised:
        library_json("flash", 2, 3, 1, overrides=overrides)
    async with Client(app) as client:
        result = await call(client, mode="flash", players=2, games=3, seed=1, overrides=overrides)
    assert result.is_error
    assert result.structured_content is None
    text = text_of(result)
    assert str(raised.value) in text
    assert "game 0 (game seed" in text


async def test_session_survives_a_tool_error():
    async with Client(app) as client:
        assert (await call(client, **BASE, policies=["smart", "greedy"])).is_error
        assert (await call(client, **BASE, overrides={"stone_share": 101})).is_error
        result = await call(client, **BASE)
    assert not result.is_error, text_of(result)
    assert result.structured_content["n"] == 1
