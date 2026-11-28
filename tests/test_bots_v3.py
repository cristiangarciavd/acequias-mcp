"""Rules v3 bots, MCP tools and tune.py sweep (#153).

greedy, score_aware and lookahead play the v3 turn (the mandatory die,
planting, good season's two actions, resow and resow-move) on both v3
boards; score_aware's fast paths equal a full scoring; the MCP tools accept
and return v3 state; tune.py has a v3 sweep and v3 report columns.
"""

from __future__ import annotations

import importlib.util
import pickle
import random
import sys
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import jsonschema
import pytest
from mcp import Client

from acequias import bots
from acequias.bots import _Evaluator, greedy_bot, lookahead_bot, score_aware_bot
from acequias.config import (
    NORMAL_V2,
    V3_DIE_FACES,
    V3_POINTS,
    BoardShape,
    PlantingRules,
    with_overrides,
)
from acequias.config import preset as shipped_preset
from acequias.game import act, game_over, game_rngs
from acequias.hex import Direction, Hex
from acequias.model import (
    ActionsLeft,
    Board,
    DieFace,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    PlantedVineyard,
    Player,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import calculate_score
from acequias.setup import new_game
from acequias.sim import SimRules, play_one, simulate_game
from acequias.turn import (
    DeclineFace,
    MoveVineyard,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    Plant,
    ResowVineyard,
    RollActionDie,
    legal_actions,
)
from server.app import app
from server.schemas import WateredVineyardJSON, overrides_from_json
from test_split_scoring import v2_overrides

pytestmark = pytest.mark.anyio

V3 = with_overrides(NORMAL_V2, planting=PlantingRules.VERTICES, varietal_points=V3_POINTS)
V3_MOVE = with_overrides(V3, action_die=V3_DIE_FACES)
STRIP = {
    "planting": PlantingRules.VERTICES,
    "board_shape": BoardShape.RIVER_STRIP,
    "bag_size": {2: 24, 3: 36},
}
FIELD = {"planting": PlantingRules.VERTICES}

# River on (0, 0); a row of empty hexes east of it. Canals A (p1) and B (p2)
# carry water east from the river; C and D are free.
RIVER = Hex(0, 0)
A, B, C, D = Hex(1, 0), Hex(2, 0), Hex(3, 0), Hex(4, 0)
TILES = (Tile(RIVER, Terrain.RIVER),) + tuple(
    Tile(Hex(q, r), Terrain.EMPTY) for q in range(1, 6) for r in (-1, 0, 1)
)
CANALS = (
    PlacedCanal(A, PieceKind.STRAIGHT, 0, "p1"),
    PlacedCanal(B, PieceKind.STRAIGHT, 0, "p2"),
)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def board(canals=CANALS, planted=(), floodgates=()) -> Board:
    return Board(tiles=TILES, canals=canals, floodgates=floodgates, planted=planted)


def state(b=None, preset=V3, left=ActionsLeft(1, 1), face=None, market=(PieceKind.STRAIGHT,) * 4):
    return GameState(
        board=board() if b is None else b,
        players=(Player("p1", 1), Player("p2", 2)),
        mode=Mode.NORMAL,
        round=1,
        start_player="p1",
        current_player="p1",
        market=market,
        preset=preset,
        actions_left=left,
        pending_face=face,
    )


def rules(policy, players=2, mode=Mode.FLASH, **extra):
    return SimRules(mode, players, (policy,) * players, {**STRIP, **extra})


# --- Whole games --------------------------------------------------------------


@pytest.mark.parametrize("policy", ["greedy", "saboteur", "score_aware", "random"])
@pytest.mark.parametrize("shape", [STRIP, FIELD])
def test_bots_play_whole_v3_games_on_both_boards(policy, shape):
    extra = {} if shape is FIELD else {"bag_size": STRIP["bag_size"]}
    record = play_one(SimRules(Mode.FLASH, 2, (policy,) * 2, {**shape, **extra}), 5)
    kinds = {type(r.action) for r in record.log}
    assert RollActionDie in kinds
    if policy != "random":
        assert Plant in kinds and PlaceCanal in kinds
    assert record.final.board.planted


def test_lookahead_plays_a_v3_strip_game_and_is_deterministic():
    first = play_one(rules("lookahead"), 3)
    again = play_one(rules("lookahead"), 3)
    assert first.log == again.log and first.scores == again.scores
    assert any(isinstance(r.action, Plant) for r in first.log)


def test_the_move_face_is_handled_by_every_bot():
    for policy in ("greedy", "score_aware", "lookahead"):
        record = play_one(rules(policy, action_die=V3_DIE_FACES), 11)
        assert any(r.face is DieFace.MOVE for r in record.log)
        assert any(isinstance(r.action, (MoveVineyard, DeclineFace)) for r in record.log)


def test_score_aware_beats_greedy_on_the_strip():
    mixed = SimRules(Mode.FLASH, 2, ("score_aware", "greedy"), STRIP)
    result = simulate_game(mixed, 20, 153)
    assert result.win_rate_by_policy["score_aware"] > result.win_rate_by_policy["greedy"]


# --- Decisions ------------------------------------------------------------------


def test_bots_roll_first():
    s = state(left=None)
    for bot in (greedy_bot, score_aware_bot, lookahead_bot):
        assert bot(s, "p1", random.Random(0)) == RollActionDie()


def test_bots_plant_when_they_can():
    s = state()
    for bot in (greedy_bot, score_aware_bot, lookahead_bot):
        assert isinstance(bot(s, "p1", random.Random(0)), Plant)


def test_with_no_spot_a_canal_beats_a_pass():
    s = state(board(canals=()))  # nothing to plant on: open spots first
    for bot in (greedy_bot, score_aware_bot, lookahead_bot):
        action = bot(s, "p1", random.Random(0))
        assert isinstance(action, PlaceCanal), bot


def test_score_aware_plants_where_it_pays_no_rights():
    s = state()
    action = score_aware_bot(s, "p1", random.Random(0))
    # A's vertices touching B are watered through p2's canal only if A is gated; here
    # every plantable spot of p1 is fed by A from the river: no rights.
    scores = calculate_score(
        replace(s, board=s.board._derive(planted=(PlantedVineyard(action.vertex, "p1", Varietal.MALBEC),)))
    )
    assert scores["p1"].rights_paid == 0


def test_a_mandatory_face_is_used_even_when_it_hurts():
    # p1's only floodgate edges are on its own canal A or on B: some use must be played.
    s = state(face=DieFace.FLOODGATE)
    assert DeclineFace() not in legal_actions(s, "p1")
    for bot in (greedy_bot, score_aware_bot, lookahead_bot):
        assert isinstance(bot(s, "p1", random.Random(0)), PlaceFloodgate)


def test_a_floodgate_face_dries_the_rival():
    planted = (PlantedVineyard(B.vertex(5), "p2", Varietal.MALBEC),)  # SE corner: touches B only
    s = state(board(planted=planted), face=DieFace.FLOODGATE)
    for bot in (score_aware_bot, greedy_bot):
        gate = bot(s, "p1", random.Random(0))
        after = s.board._derive(floodgates=(bots._v3_board_after(s, "p1", gate)[0].floodgates))
        assert calculate_score(replace(s, board=after, pending_face=None))["p2"].vineyards == 0


def test_resow_is_declined_when_worthless_and_used_on_a_poor_own_vineyard():
    points = dict(V3.varietal_points)
    worst = min(points, key=points.get)
    best = max(points, key=points.get)
    s = state(board(planted=(PlantedVineyard(A.vertex(2), "p1", best),)), face=DieFace.RESOW)
    assert score_aware_bot(s, "p1", random.Random(0)) == DeclineFace()
    s = state(board(planted=(PlantedVineyard(A.vertex(2), "p1", worst),)), face=DieFace.RESOW)
    assert score_aware_bot(s, "p1", random.Random(0)) == ResowVineyard(A.vertex(2))


# --- Fast paths equal a full scoring ---------------------------------------------


def _states(policy, extra, seed, every=1):
    s = new_game(2, seed, Mode.FLASH, preset=with_overrides(shipped_preset(Mode.FLASH), **extra))
    dice, bot_rng = game_rngs(seed)
    i = 0
    while not game_over(s):
        if s.pending_face is None and s.actions_left is not None and i % every == 0:
            yield s
        i += 1
        player = s.current_player
        s = act(s, player, bots.policy(policy)(s, player, bot_rng), dice)


@pytest.mark.parametrize("policy", ["random", "score_aware"])
@pytest.mark.parametrize("extra", [
    STRIP,
    {**FIELD, "grape_clusters_per_player": 4},
    {**STRIP, "vertex_needs_three_canals": True, "varietal_points": V3_POINTS},
    {**STRIP, "varietal_points": V3_POINTS, "action_die": V3_DIE_FACES},
])
def test_fast_canal_and_plant_values_equal_a_full_scoring(monkeypatch, extra, policy):
    checked = 0
    for s in _states(policy, extra, 2):
        player = s.current_player
        planted = [v.vertex for v in s.board.planted]
        for blanks in (frozenset(), frozenset(planted[::2])):
            fast = _Evaluator(s, player, {"p2": Fraction(1, 2)}, {}, blanks)
            monkeypatch.setattr(_Evaluator, "fast", False)
            full = _Evaluator(s, player, {"p2": Fraction(1, 2)}, {}, blanks)
            monkeypatch.setattr(_Evaluator, "fast", True)
            for action in legal_actions(s, player):
                if isinstance(action, (PlaceCanal, Plant)):
                    monkeypatch.setattr(_Evaluator, "fast", True)
                    a = fast.value(s, action)
                    monkeypatch.setattr(_Evaluator, "fast", False)
                    b = full.value(s, action)
                    monkeypatch.setattr(_Evaluator, "fast", True)
                    assert a == b, (action, s.board)
                    checked += 1
    assert checked > 50


# --- Pickling (tune.py sends records between processes) ------------------------------


def test_a_v3_strip_game_record_pickles():
    _tune()  # registers the pickling of read-only mappings, as tune.py's workers use it
    record = play_one(rules("greedy"), 1)
    again = pickle.loads(pickle.dumps(record))
    assert again == record
    assert again.final.board._static().river_dirs[Hex(1, 0)] is not None


# --- MCP tools --------------------------------------------------------------------



STRIP_JSON = {"planting": "vertices", "board_shape": "river_strip", "bag_size": {"2": 24, "3": 36}}


async def test_simulate_game_returns_v3_results_equal_to_the_library():
    async with Client(app) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
        result = await client.call_tool(
            "simulate_game",
            {"mode": "flash", "players": 2, "games": 2, "seed": 4,
             "policies": ["score_aware", "greedy"], "overrides": STRIP_JSON},
        )
    assert not result.is_error, result.content
    data = result.structured_content
    jsonschema.validate(data, tools["simulate_game"].output_schema)
    rules_ = SimRules(Mode.FLASH, 2, ("score_aware", "greedy"), overrides_from_json(STRIP_JSON))
    assert data == simulate_game(rules_, 2, 4).to_json()
    assert data["preset"]["planting"] == "vertices"
    assert data["preset"]["board_shape"] == "river_strip"
    assert data["actions_per_game"]["plant"] > 0


async def test_simulate_game_default_is_v3_and_v2_preset_json_has_no_v3_keys():
    async with Client(app) as client:
        result = await client.call_tool("simulate_game", {"mode": "flash", "players": 2, "games": 1, "seed": 1})
    values = result.structured_content["preset"]
    assert values["planting"] == "vertices" and values["board_shape"] == "river_strip"
    assert values["bribe_optional"] is True and values["end_conditions"]
    v2 = simulate_game(SimRules(Mode.FLASH, 2, ("greedy",) * 2, v2_overrides(Mode.FLASH)), 1, 1).to_json()
    assert not {"planting", "board_shape", "bag_size", "vertex_needs_three_canals", "river_hexes_per_segment"} & set(
        v2["preset"]
    )


async def test_generate_board_returns_spots_or_the_strip():
    async with Client(app) as client:
        plain = await client.call_tool("generate_board", {"players": 2, "mode": "flash", "seed": 3})
        field = await client.call_tool(
            "generate_board", {"players": 2, "mode": "flash", "seed": 3, "overrides": {"board_shape": "field"}}
        )
        strip = await client.call_tool(
            "generate_board", {"players": 2, "mode": "flash", "seed": 3, "overrides": STRIP_JSON}
        )
    assert not (plain.is_error or field.is_error or strip.is_error), (field.content, strip.content)
    # The shipped Rules v3 preset gives the open river strip, which has no fixed spots (#192).
    assert "spots" not in plain.structured_content and len(plain.structured_content["strip"]["segments"]) == 1
    assert all(h["terrain"] == "river" for h in plain.structured_content["hexes"])
    assert "strip" not in field.structured_content
    assert field.structured_content["spots"] and all(len(v) == 3 for v in field.structured_content["spots"])
    assert len(strip.structured_content["strip"]["segments"]) == 1
    assert all(h["terrain"] == "river" for h in strip.structured_content["hexes"])


async def test_calculate_score_scores_planted_vertex_vineyards_on_a_strip():
    record = play_one(rules("score_aware"), 2)
    final = record.final
    async with Client(app) as client:
        board = (await client.call_tool(
            "generate_board", {"players": 2, "mode": "flash", "seed": 0, "overrides": STRIP_JSON}
        )).structured_content
        result = await client.call_tool("calculate_score", {
            "mode": "flash",
            "hexes": [],
            "strip": board["strip"],
            "players": [{"id": p.id, "debt": p.debt} for p in final.players],
            "canals": [{"q": c.hex.q, "r": c.hex.r, "kind": c.kind.name.lower(),
                        "rotation": c.rotation, "owner": c.owner} for c in final.board.canals],
            "floodgates": [{"q": g.hex.q, "r": g.hex.r, "direction": g.direction.name}
                           for g in final.board.floodgates],
            "planted": [{"hexes": [[h.q, h.r] for h in v.vertex.hexes], "player": v.owner,
                         "varietal": v.varietal.name.lower()} for v in final.board.planted],
            "overrides": STRIP_JSON,
        })
    assert not result.is_error, result.content
    scores = {s["player"]: s for s in result.structured_content["scores"]}
    for pid, score in record.scores.items():
        assert scores[pid]["total"] == score.total
        watered = scores[pid]["watered_vineyards"]
        assert all("hexes" in w and "q" not in w for w in watered)
        assert len(watered) == score.watered


def test_watered_vineyard_json_takes_a_hex_or_a_vertex():
    base = {"varietal": "malbec", "path": [], "pays": []}
    assert WateredVineyardJSON.model_validate({**base, "q": 1, "r": 0}).hexes is None
    vertex = WateredVineyardJSON.model_validate({**base, "hexes": [[0, 0], [0, 1], [1, 0]]})
    assert "q" not in vertex.model_dump()
    for bad in ({}, {"q": 1}, {"q": 1, "r": 0, "hexes": [[0, 0], [0, 1], [1, 0]]}):
        with pytest.raises(ValueError):
            WateredVineyardJSON.model_validate({**base, **bad})


# --- tune.py -----------------------------------------------------------------------


def _tune():
    path = Path(__file__).resolve().parent.parent / "scripts" / "tune.py"
    spec = importlib.util.spec_from_file_location("tune_v3", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["tune_v3"] = module
    spec.loader.exec_module(module)
    return module


def test_tune_v3_sweep_builds_valid_v3_presets():
    tune = _tune()
    (sweep,) = tune.v3_sweeps()
    assert sweep.name == "v3" and "v3" in tune.SWEEP_NAMES
    assert sweep.seatings == ("score_aware",)
    for mode in Mode:
        labels = [label for label, _ in sweep.candidates[mode]]
        assert labels[0] == "base" and "move face" in labels
        for label, changes in sweep.candidates[mode]:
            job = tune.Job(label, mode, 2, "score_aware", {**sweep.base[mode], **changes}, 1, 1)
            p = with_overrides(shipped_preset(mode), **dict(tune.rules_of(job).overrides))
            assert p.planting is PlantingRules.VERTICES
            assert p.board_shape is BoardShape.RIVER_STRIP
            assert tune.is_v3(job.overrides)
    (custom,) = tune.v3_sweeps(6, 12)
    base = custom.base[Mode.NORMAL]
    assert base["river_hexes_per_segment"] == 6 and base["bag_size"][4] == 48
    labels = [label for label, _ in custom.candidates[Mode.NORMAL]]
    assert "6 river hexes/segment" not in labels and "bag 12/player" not in labels


def test_tune_v3_rows_report_planting_and_the_bodega(capsys):
    tune = _tune()
    job = tune.Job("base", Mode.FLASH, 2, "score_aware",
                   {**tune.v3_sweeps()[0].base[Mode.FLASH]}, 3, 1)
    outcome = tune.run_chunk(job, 0, 3)
    assert outcome.status == "ok", outcome.error
    data = tune.summarize(tune.rules_of(job), job.seed, outcome.records).to_json()
    row = tune.v3_sweep_row(job, tune.Outcome("ok", data))
    assert row.count("|") == tune.V3_SWEEP_COLUMNS + 1
    planted = data["actions_per_game"]["plant"] / 2
    assert f"| {planted:.2f} |" in row
    assert f"{data['bodega_rate']:.3f}" in row
