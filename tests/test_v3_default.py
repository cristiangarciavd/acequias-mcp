"""Rules v3 is the default (#192): with no overrides the library and the MCP
tools play, generate and score the shipped Rules v3 game; Rules v2 is kept
under ``NORMAL_V2`` / ``FLASH_V2`` (``RULES_V2``)."""

from __future__ import annotations

import json

import pytest
from mcp import Client

from acequias.board import generate_board
from acequias.config import (
    FLASH,
    FLASH_V3,
    NORMAL,
    NORMAL_V3,
    RULES_V2,
    BoardShape,
    PlantingRules,
    preset,
    with_overrides,
)
from acequias.model import Mode
from acequias.setup import new_game
from acequias.sim import SimRules, play_one, simulate_game
from server.app import app
from server.schemas import overrides_from_json
from test_split_scoring import TILES, TWO_ONE, V, v2_overrides

pytestmark = pytest.mark.anyio

V2_DEFAULTS_JSON = {
    "planting": "hexes", "board_shape": "field", "bag_size": {}, "blends": [], "varietal_bodega": True,
    "bodega_building": False, "bodega_min_whites": 2, "bribe_optional": False, "end_conditions": [],
    "vineyard_supply": {}, "score_target": {}, "max_spins": 1,
}
"""The Rules v2 values a ``simulate_game`` preset leaves out (they are the engine defaults)."""


@pytest.fixture
def anyio_backend():
    return "asyncio"


def v2_json(mode: Mode) -> dict:
    """Rules v2 as MCP overrides: a Rules v2 result's preset plus the values it leaves out."""
    result = simulate_game(SimRules(mode, 2, ("greedy",) * 2, v2_overrides(mode)), 1, 1).to_json()
    values = json.loads(json.dumps(result["preset"]))
    del values["mode"]
    return {**values, **V2_DEFAULTS_JSON}


# --- Library -------------------------------------------------------------------


def test_preset_and_constants_are_rules_v3():
    assert preset(Mode.NORMAL) is NORMAL is NORMAL_V3 and preset(Mode.FLASH) is FLASH is FLASH_V3
    for p in (NORMAL, FLASH):
        assert p.planting is PlantingRules.VERTICES and p.board_shape is BoardShape.RIVER_STRIP


@pytest.mark.parametrize(("mode", "players"), [(Mode.NORMAL, 3), (Mode.FLASH, 2)])
def test_new_game_and_simulate_game_play_the_river_strip_with_vertex_planting(mode, players):
    state = new_game(players, 1, mode)
    assert state.preset is preset(mode) and state.board.strip is not None
    assert generate_board(players, 1, mode).strip is not None
    record = play_one(SimRules(mode, players, ("score_aware",) * players), 192)
    assert record.start.board.strip is not None and record.final.board.planted
    assert record.final.end_trigger in preset(mode).end_conditions
    result = simulate_game(SimRules(mode, players, ("score_aware",) * players), 2, 192).to_json()
    assert result["preset"]["planting"] == "vertices" and result["preset"]["board_shape"] == "river_strip"
    assert result["actions_per_game"]["plant"] > 0


@pytest.mark.parametrize("mode", list(Mode))
def test_rules_v2_is_kept_and_reachable_by_overrides(mode):
    assert with_overrides(preset(mode), **v2_overrides(mode)) == RULES_V2[mode]
    assert with_overrides(preset(mode), **overrides_from_json(v2_json(mode))) == RULES_V2[mode]
    record = play_one(SimRules(mode, 2, ("greedy",) * 2, v2_overrides(mode)), 1)
    assert record.start.board.strip is None and not record.final.board.planted


# --- MCP tools -----------------------------------------------------------------


def score_args(**changes) -> dict:
    return {
        "mode": "normal",
        "hexes": [{"q": t.hex.q, "r": t.hex.r, "terrain": t.terrain.value, "varietal": None} for t in TILES],
        "players": [{"id": "p1", "debt": 0}, {"id": "p2", "debt": 0}],
        "canals": [{"q": h.q, "r": h.r, "kind": "straight", "rotation": 0, "owner": o} for h, o in TWO_ONE.items()],
        **changes,
    }


async def test_generate_board_default_returns_the_strip():
    async with Client(app) as client:
        result = await client.call_tool("generate_board", {"players": 3, "mode": "normal", "seed": 1})
    assert not result.is_error, result.content
    data = result.structured_content
    assert len(data["strip"]["segments"]) == 2 and "spots" not in data
    assert all(h["terrain"] == "river" for h in data["hexes"])


async def test_calculate_score_default_scores_planted_vertex_vineyards():
    planted = [{"hexes": [[h.q, h.r] for h in V.hexes], "player": "p1", "varietal": "bonarda"}]
    async with Client(app) as client:
        result = await client.call_tool("calculate_score", score_args(planted=planted))
    assert not result.is_error, result.content
    by_player = {s["player"]: s for s in result.structured_content["scores"]}
    # Bonarda is 9 under Rules v3: p1 owns 2 thirds (6), p2 one (3).
    assert by_player["p1"]["vineyards"] == 6 and by_player["p2"]["vineyards"] == 3


async def test_calculate_score_claims_need_rules_v2_overrides():
    hexes = [
        {"q": 0, "r": 0, "terrain": "river", "varietal": None},
        {"q": 1, "r": 0, "terrain": "empty", "varietal": None},
        {"q": 2, "r": 0, "terrain": "vineyard", "varietal": None},
    ]
    args = {
        "mode": "normal", "hexes": hexes,
        "players": [{"id": "a", "debt": 0}, {"id": "b", "debt": 0}],
        "canals": [{"q": 1, "r": 0, "kind": "straight", "rotation": 0, "owner": "a"}],
        "claims": [{"q": 2, "r": 0, "player": "a", "varietal": "bonarda"}],
    }
    async with Client(app) as client:
        refused = await client.call_tool("calculate_score", args)
        scored = await client.call_tool("calculate_score", {**args, "overrides": v2_json(Mode.NORMAL)})
    assert refused.is_error
    text = "".join(block.text for block in refused.content if block.type == "text")
    assert "claims are Rules v2 hex vineyards" in text and "planted" in text
    assert not scored.is_error, scored.content
    by_player = {s["player"]: s for s in scored.structured_content["scores"]}
    assert by_player["a"]["vineyards"] == RULES_V2[Mode.NORMAL].varietal_points[
        next(v for v in RULES_V2[Mode.NORMAL].varietal_points if v.name == "BONARDA")]


async def test_simulate_game_default_echoes_rules_v3():
    async with Client(app) as client:
        result = await client.call_tool("simulate_game", {"players": 2, "mode": "normal", "games": 1, "seed": 1})
    assert not result.is_error, result.content
    values = result.structured_content["preset"]
    assert values["planting"] == "vertices" and values["board_shape"] == "river_strip"
    assert values["end_conditions"] == ["supply_empty", "score_target", "dead_turns"]
