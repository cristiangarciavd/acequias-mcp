"""The shipped Rules v2 presets (#126): Flash is for 2 or 3 players only, and
the library, the MCP tools, and ``scripts/tune.py`` say so with a clear error
(or skip those counts); a shipped game of each mode plays to the end."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from mcp import Client

from acequias.board import generate_board
from acequias.config import FLASH, NORMAL, BribeRules, VarietalRules, preset
from acequias.model import Mode, Terrain
from acequias.setup import new_game
from acequias.sim import SimRules, play_one, simulate_game
from server.app import app
from server.schemas import MODE_PLAYERS, board_to_hexes

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
tune = importlib.import_module("tune")

FLASH_ERROR = "flash mode is for 2 to 3 players, got {}"
APPROVED = {Mode.NORMAL: "constructive die, cost 1, season roll every 3",
            Mode.FLASH: "constructive die, cost 1, season roll every 2"}


# --- Library -------------------------------------------------------------------


@pytest.mark.parametrize("players", [4, 5])
def test_flash_board_and_game_reject_4_and_5_players(players):
    with pytest.raises(ValueError, match=FLASH_ERROR.format(players)):
        generate_board(players, 1, Mode.FLASH)
    with pytest.raises(ValueError, match=FLASH_ERROR.format(players)):
        new_game(players, 1, Mode.FLASH)
    with pytest.raises(ValueError, match=FLASH_ERROR.format(players)):
        play_one(SimRules(Mode.FLASH, players, ("greedy",) * players), 1)


@pytest.mark.parametrize(("mode", "players"), [(Mode.NORMAL, n) for n in (2, 3, 4, 5)] + [(Mode.FLASH, 2), (Mode.FLASH, 3)])
def test_every_supported_count_gets_a_game(mode, players):
    state = new_game(players, 7, mode)
    assert state.preset is preset(mode) and len(state.players) == players


def test_overrides_can_give_flash_4_players_back():
    rules = SimRules(Mode.FLASH, 4, ("greedy",) * 4, {"rounds": {2: 6, 3: 6, 4: 4}})
    assert len(play_one(rules, 1).log) >= 16


@pytest.mark.parametrize(("mode", "players"), [(Mode.NORMAL, 3), (Mode.FLASH, 2)])
def test_a_shipped_game_plays_rules_v2_to_the_end(mode, players):
    p = preset(mode)
    assert p.varietal_rules is VarietalRules.ROULETTE and p.bribe_rules is BribeRules.ACTION_DIE
    record = play_one(SimRules(mode, players, ("score_aware",) * players), 3)
    start = record.start
    assert all(t.varietal is None for t in start.board.tiles if t.terrain is Terrain.VINEYARD)
    assert "FLOODGATE" not in {k.name for k in start.market + start.bag}
    assert len(record.log) >= p.rounds_for(players) * players
    assert set(record.scores) == {player.id for player in start.players}


def test_simulate_game_rejects_before_playing():
    with pytest.raises(ValueError, match=FLASH_ERROR.format(5)):
        simulate_game(SimRules(Mode.FLASH, 5, ("greedy",) * 5), 1, 1)


# --- MCP tools -----------------------------------------------------------------

pytestmark_anyio = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def text_of(result):
    return "".join(block.text for block in result.content if block.type == "text")


def test_mode_players_text_follows_the_presets():
    assert MODE_PLAYERS == "normal 2 to 5; flash 2 to 3"


@pytestmark_anyio
async def test_tools_reject_flash_with_4_players_and_list_the_counts():
    hexes = board_to_hexes(generate_board(2, 1, Mode.FLASH))
    players = [{"id": f"p{k}", "debt": 0} for k in range(1, 5)]
    async with Client(app) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        for name in ("generate_board", "simulate_game"):
            assert "flash 2 to 3" in tools[name].input_schema["properties"]["players"]["description"]
        results = [
            await client.call_tool("generate_board", {"players": 4, "mode": "flash", "seed": 1}),
            await client.call_tool("simulate_game", {"players": 4, "mode": "flash", "games": 1, "seed": 1}),
            await client.call_tool("calculate_score", {"mode": "flash", "hexes": hexes, "players": players}),
        ]
    for result in results:
        assert result.is_error
        assert FLASH_ERROR.format(4) in text_of(result)


@pytestmark_anyio
async def test_simulate_game_rounds_override_sets_the_player_counts():
    async with Client(app) as client:
        result = await client.call_tool(
            "simulate_game",
            {"players": 5, "mode": "normal", "games": 1, "seed": 1, "overrides": {"rounds": {"2": 5, "3": 5}}}
        )
    assert result.is_error
    assert "normal mode is for 2 to 3 players, got 5" in text_of(result)


# --- tune.py -------------------------------------------------------------------


@pytest.mark.parametrize("mode", list(Mode))
def test_shipped_presets_are_the_approved_b5_candidate(mode):
    """The owner's approval on #103: ``--candidate b5 "constructive die, cost 1, season roll
    every 3|2" --scale 3 --rare-bonus 1 --multiple-bodegas --season-global-only``."""
    sweeps = tune.v2_sweeps(3, 1, multiple_bodegas=True, season_global_only=True)
    _, approved = tune.find_candidate(sweeps, "b5", APPROVED[mode], [mode])
    candidate = tune.with_overrides(tune.V1_PRESET[mode], **approved[mode])
    expected = {} if mode is Mode.NORMAL else {"rounds": {2: 6, 3: 6}}  # Flash: 2-3 players only
    assert {k: dict(v) if k == "rounds" else v for k, v in tune.diff_from(candidate, preset(mode)).items()} == expected


def test_shipped_sweep_line_and_jobs_skip_flash_4_and_5(capsys):
    sweep = {s.name: s for s in tune.v2_sweeps()}["shipped"]
    assert tune.describe(sweep.candidates[Mode.FLASH][0][1]).startswith("rounds=6/6, bag_mix=44/22/17/6/6/5/0")
    jobs = tune.sweep_jobs(sweep, list(Mode), 10)
    assert sorted((j.mode.value, j.players) for j in jobs) == sorted(
        [("normal", n) for n in (2, 3, 4, 5)] + [("flash", 2), ("flash", 3)])
    err = capsys.readouterr().err
    assert "skipped flash 4p score_aware shipped (Rules v2)" in err and "flash is for 2 to 3 players" in err
    for job in jobs:
        p = tune.with_overrides(preset(job.mode), **tune.rules_of(job).overrides)
        assert p == preset(job.mode)


def test_candidate_with_an_unsupported_player_count_is_an_argument_error(capsys):
    with pytest.raises(SystemExit):
        tune.main(["--candidate", "shipped", "shipped (Rules v2)", "--mode", "flash", "--players", "4", "--smoke"])
    assert "flash mode is for 2 to 3 players in candidate 'shipped (Rules v2)', got --players 4" in (
        capsys.readouterr().err)


def test_rules_v1_jobs_still_play_flash_with_5_players():
    sweep = {s.name: s for s in tune.v2_sweeps()}["b0"]
    jobs = tune.sweep_jobs(sweep, [Mode.FLASH], 10, [5])
    assert len(jobs) == 1
    assert tune.with_overrides(preset(Mode.FLASH), **tune.rules_of(jobs[0]).overrides) == tune.V1_PRESET[Mode.FLASH]


def test_flash_and_normal_constants_are_the_shipped_presets():
    assert preset(Mode.NORMAL) is NORMAL and preset(Mode.FLASH) is FLASH
