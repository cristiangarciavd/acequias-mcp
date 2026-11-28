"""Rules v3 split vineyard scoring, the three-canal planting option, and the move face (#160)."""

from __future__ import annotations

import dataclasses
import importlib.util
import random
import sys
from pathlib import Path

import pytest
from mcp import Client

from acequias.bots import greedy_bot, lookahead_bot, score_aware_bot
from acequias.config import (
    CONSTRUCTIVE_DIE_FACES,
    NORMAL_V2,
    RULES_V2,
    V3_DIE_FACES,
    V3_POINTS,
    BoardShape,
    PlantingRules,
    Preset,
    with_overrides,
)
from acequias.flow import can_plant, plantable_spots, vertex_thirds
from acequias.hex import Direction, Hex, Vertex
from acequias.model import (
    ActionsLeft,
    Board,
    DieFace,
    Floodgate,
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
from acequias.scoring import calculate_score, split_points
from acequias.sim import SimRules, simulate_game
from acequias.turn import DeclineFace, IllegalAction, MoveVineyard, Plant, apply, legal_actions
from server.app import app
from server.schemas import watered_vineyard_to_json

pytestmark = pytest.mark.anyio

V3 = with_overrides(NORMAL_V2, planting=PlantingRules.VERTICES, varietal_points=V3_POINTS)


def v2_overrides(mode: Mode) -> dict:
    """Every Rules v2 value of ``mode`` (``RULES_V2``) as ``SimRules`` overrides (#192)."""
    return {f.name: getattr(RULES_V2[mode], f.name) for f in dataclasses.fields(Preset) if f.name != "mode"}

THREE = with_overrides(V3, vertex_needs_three_canals=True)

# River on (0, -1) and (0, 0). Canals on L = (1, -1), M = (1, 0), N = (2, 0) and
# R = (2, -1), all straight E-W: L and M take water from the river, N from M,
# R from L. The vertex V is where M, N and R meet.
RIVER = (Hex(0, -1), Hex(0, 0))
L, M, N, R = Hex(1, -1), Hex(1, 0), Hex(2, 0), Hex(2, -1)
V = Vertex((M, N, R))
AT_RIVER = Vertex((Hex(0, 0), L, M))  # a river hex, L and M
TILES = tuple(Tile(h, Terrain.RIVER) for h in RIVER) + tuple(
    Tile(Hex(q, r), Terrain.EMPTY) for q in range(1, 5) for r in (-2, -1, 0, 1)
)


def canal(hex, owner) -> PlacedCanal:
    return PlacedCanal(hex, PieceKind.STRAIGHT, 0, owner)


def board(owners, planted=(), floodgates=()) -> Board:
    """``owners`` maps canal hexes to their owner; hexes left out are empty."""
    return Board(
        tiles=TILES,
        canals=tuple(canal(h, o) for h, o in owners.items()),
        planted=planted,
        floodgates=floodgates,
    )


def state(b, preset=V3, face=None, left=ActionsLeft(1, 1)) -> GameState:
    return GameState(
        board=b,
        players=(Player("p1", 1), Player("p2", 2)),
        mode=Mode.NORMAL,
        round=1,
        start_player="p1",
        current_player="p1",
        market=(PieceKind.STRAIGHT,) * 4,
        preset=preset,
        actions_left=left,
        pending_face=face,
    )


def scores(b, preset=V3):
    return calculate_score(state(b, preset))


def bonarda(vertex=V, owner="p1") -> PlantedVineyard:
    return PlantedVineyard(vertex, owner, Varietal.BONARDA)


ALL = {L: "p1", M: "p1", N: "p1", R: "p1"}
TWO_ONE = {L: "p2", M: "p1", N: "p1", R: "p2"}  # V: M and N are p1's, R is p2's


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- Values -----------------------------------------------------------------------


def test_v3_values_are_6_and_rare_9_and_split_in_whole_thirds():
    assert V3_POINTS[Varietal.BONARDA] == V3_POINTS[Varietal.CABERNET_FRANC] == 9
    assert {p for v, p in V3_POINTS.items() if v not in (Varietal.BONARDA, Varietal.CABERNET_FRANC)} == {6}
    assert set(V3_POINTS) == set(NORMAL_V2.varietal_points)
    assert [split_points(9, k) for k in range(4)] == [0, 3, 6, 9]
    assert [split_points(7, k) for k in range(4)] == [0, 2, 4, 7]  # other values round down


# --- Split scoring ----------------------------------------------------------------------


def test_all_three_thirds_mine():
    s = scores(board(ALL, (bonarda(),)))
    assert s["p1"].vineyards == 9 and s["p2"].vineyards == 0
    (w,) = s["p1"].watered_vineyards
    assert (w.vertex, w.thirds, w.points, w.planter, w.pays) == (V, 3, 9, "p1", ())
    assert [c.hex for c in w.path.canals] == list(V.hexes)


def test_two_thirds_mine_one_a_rivals():
    s = scores(board(TWO_ONE, (bonarda(),)))
    assert s["p1"].vineyards == 6 and s["p2"].vineyards == 3
    assert s["p2"].watered_vineyards[0].planter == "p1"
    assert s["p1"].rights_paid == s["p1"].rights_collected == 0
    assert s["p2"].rights_paid == s["p2"].rights_collected == 0
    assert s["p1"].total == 6 and s["p2"].total == 3


def test_a_floodgate_dries_my_thirds_and_the_rival_keeps_theirs():
    gate = Floodgate(M, Direction.W)  # M no longer takes water from the river; N dries too
    b = board(TWO_ONE, (bonarda(),), (gate,))
    assert vertex_thirds(b)[V] == {"p2": 1}
    s = scores(b)
    assert s["p1"].vineyards == 0 and s["p1"].watered == 0
    assert s["p2"].vineyards == 3 and s["p2"].watered == 1


def test_an_empty_hex_third_and_a_river_third_score_for_nobody():
    s = scores(board({M: "p1", N: "p1"}, (bonarda(),)))  # R is empty
    assert s["p1"].vineyards == 6 and s["p2"].vineyards == 0
    s = scores(board({L: "p2", M: "p1"}, (bonarda(AT_RIVER),)))
    assert s["p1"].vineyards == 3 and s["p2"].vineyards == 3


def test_an_unwatered_canal_third_scores_for_nobody():
    dry = {M: "p1", N: "p1", R: "p2"}  # R takes no water: L is missing
    assert vertex_thirds(board(dry, (bonarda(),)))[V] == {"p1": 2}
    s = scores(board(dry, (bonarda(),)))
    assert s["p1"].vineyards == 6 and s["p2"].vineyards == 0


def test_bodega_counts_rivals_plantings_with_one_of_my_watered_thirds():
    spots = [v for v in M.vertices() if v not in (V, AT_RIVER)][:3]
    planted = tuple(
        PlantedVineyard(v, "p2", varietal)
        for v, varietal in zip(spots, (Varietal.MALBEC, Varietal.SYRAH, Varietal.MERLOT))
    )
    s = scores(board({M: "p1"}, planted))
    assert s["p1"].bodegas == 1 and s["p1"].bodega == V3.bodega_points
    assert s["p2"].bodegas == 0 and s["p2"].vineyards == 0  # p2 has no canal there
    assert s["p1"].watered == 3


def test_a_dried_vineyard_leaves_the_bodega():
    spots = [v for v in M.vertices() if v not in (V, AT_RIVER)][:3]
    planted = tuple(
        PlantedVineyard(v, "p1", varietal)
        for v, varietal in zip(spots, (Varietal.MALBEC, Varietal.SYRAH, Varietal.MERLOT))
    )
    assert scores(board({M: "p1"}, planted))["p1"].bodegas == 1
    gated = board({M: "p1"}, planted, (Floodgate(M, Direction.W),))
    assert scores(gated)["p1"].bodegas == 0


def test_hex_vineyards_keep_their_scoring():
    assert split_points(V3_POINTS[Varietal.MALBEC], 3) == V3_POINTS[Varietal.MALBEC]
    # Rules v1/v2 are covered by the golden games; a hex vineyard lists no split.
    s = scores(board(ALL, (bonarda(),)))
    assert all(w.hex is None for w in s["p1"].watered_vineyards)


# --- Planting rule -------------------------------------------------------------------


def test_vertex_needs_three_canals_off_allows_an_empty_or_river_third():
    b = board({M: "p1", N: "p1"})
    assert can_plant(b, "p1", V) and V in plantable_spots(b, "p1")
    assert can_plant(b, "p1", AT_RIVER)
    assert Plant(V) in legal_actions(state(b), "p1")


def test_vertex_needs_three_canals_on_needs_a_canal_on_each_hex():
    b = board({M: "p1", N: "p1"})
    assert not can_plant(b, "p1", V, three_canals=True)
    assert V not in plantable_spots(b, "p1", three_canals=True)
    assert Plant(V) not in legal_actions(state(b, THREE), "p1")
    with pytest.raises(IllegalAction, match="3 hexes"):
        apply(state(b, THREE), "p1", Plant(V), random.Random(0))
    assert not can_plant(b, "p1", AT_RIVER, three_canals=True)  # a river hex is never a canal
    full = board(TWO_ONE)  # R is a rival's canal: allowed
    assert can_plant(full, "p1", V, three_canals=True)
    assert Plant(V) in legal_actions(state(full, THREE), "p1")


def test_planting_still_needs_an_own_watered_canal():
    b = board({L: "p2", R: "p2", M: "p1"}, floodgates=(Floodgate(M, Direction.W),))
    assert not can_plant(b, "p1", Vertex((M, N, R)))
    assert can_plant(b, "p2", Vertex((M, N, R)))  # next to a rival's canal is allowed


def test_three_canals_needs_vertex_planting():
    with pytest.raises(ValueError, match="needs vertex planting"):
        with_overrides(NORMAL_V2, vertex_needs_three_canals=True)


# --- Move face ----------------------------------------------------------------------


def test_the_v3_die_has_six_distinct_faces_with_move():
    assert len(set(V3_DIE_FACES)) == 6 and DieFace.MOVE in V3_DIE_FACES
    assert DieFace.MOVE not in CONSTRUCTIVE_DIE_FACES


def test_move_follows_the_three_canal_rule():
    b = board({M: "p1", N: "p1"}, (PlantedVineyard(AT_RIVER, "p1", Varietal.MALBEC),))
    loose = state(b, with_overrides(V3, action_die=V3_DIE_FACES), face=DieFace.MOVE)
    assert MoveVineyard(AT_RIVER, V) in legal_actions(loose, "p1")
    strict = state(b, with_overrides(THREE, action_die=V3_DIE_FACES), face=DieFace.MOVE)
    assert legal_actions(strict, "p1") == (DeclineFace(),)
    with pytest.raises(IllegalAction):
        apply(strict, "p1", MoveVineyard(AT_RIVER, V), random.Random(0))


@pytest.mark.parametrize("bot", [greedy_bot, score_aware_bot, lookahead_bot])
def test_bots_move_a_dry_vineyard_onto_their_watered_thirds(bot):
    # p1's Bonarda at the river vertex has one watered third (M); V gives it three.
    gate = Floodgate(L, Direction.W)  # L is dry: AT_RIVER keeps only M's third
    b = board(ALL, (bonarda(AT_RIVER),), (gate,))
    s = state(b, with_overrides(V3, action_die=V3_DIE_FACES), face=DieFace.MOVE)
    assert bot(s, "p1", random.Random(0)) == MoveVineyard(AT_RIVER, V)


def test_sim_counts_move_rolls_only_under_v3():
    v3 = SimRules(Mode.FLASH, 2, ("greedy",) * 2, {
        "planting": PlantingRules.VERTICES, "board_shape": BoardShape.RIVER_STRIP,
        "bag_size": {2: 24, 3: 36}, "action_die": V3_DIE_FACES, "varietal_points": V3_POINTS,
    })
    result = simulate_game(v3, 3, 1)
    assert "move" in result.die_faces_per_game and result.die_faces_per_game["move"] > 0
    assert "move" in result.actions_per_game
    v2 = simulate_game(SimRules(Mode.FLASH, 2, ("greedy",) * 2, v2_overrides(Mode.FLASH)), 1, 1)
    assert "move" not in v2.die_faces_per_game


# --- MCP ------------------------------------------------------------------------------


def test_watered_vineyard_json_lists_the_split():
    (w,) = scores(board(TWO_ONE, (bonarda(),)))["p2"].watered_vineyards
    data = watered_vineyard_to_json(w)
    assert (data["planter"], data["thirds"], data["points"], data["pays"]) == ("p1", 1, 3, [])
    assert [[c["q"], c["r"]] for c in data["path"]] == [[R.q, R.r]]


async def test_calculate_score_splits_vertex_vineyards():
    async with Client(app) as client:
        result = await client.call_tool("calculate_score", {
            "mode": "normal",
            "hexes": [{"q": t.hex.q, "r": t.hex.r, "terrain": t.terrain.value, "varietal": None}
                      for t in TILES],
            "players": [{"id": "p1", "debt": 0}, {"id": "p2", "debt": 0}],
            "canals": [{"q": h.q, "r": h.r, "kind": "straight", "rotation": 0, "owner": o}
                       for h, o in TWO_ONE.items()],
            "planted": [{"hexes": [[h.q, h.r] for h in V.hexes], "player": "p1",
                         "varietal": "bonarda"}],
            "overrides": {"planting": "vertices",
                          "varietal_points": {v.name.lower(): p for v, p in V3_POINTS.items()}},
        })
    assert not result.is_error, result.content
    by_player = {s["player"]: s for s in result.structured_content["scores"]}
    assert by_player["p1"]["vineyards"] == 6 and by_player["p2"]["vineyards"] == 3
    (w,) = by_player["p2"]["watered_vineyards"]
    assert (w["planter"], w["thirds"], w["points"]) == ("p1", 1, 3)


# --- tune.py -----------------------------------------------------------------------------


def _tune():
    if "tune" in sys.modules:
        return sys.modules["tune"]
    path = Path(__file__).resolve().parent.parent / "scripts" / "tune.py"
    spec = importlib.util.spec_from_file_location("tune", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["tune"] = module
    spec.loader.exec_module(module)
    return module


def test_tune_v3split_sweep_covers_the_options():
    tune = _tune()
    (sweep,) = tune.v3split_sweeps()
    assert sweep.name == "v3split" and "v3split" in tune.SWEEP_NAMES
    assert sweep.seatings == ("score_aware",)
    for mode in Mode:
        overrides = [{**sweep.base[mode], **changes} for _, changes in sweep.candidates[mode]]
        assert {o["vertex_needs_three_canals"] for o in overrides} == {False, True}
        assert {o["action_die"] for o in overrides} == {V3_DIE_FACES, CONSTRUCTIVE_DIE_FACES}
        assert {o["bag_size"][2] // 2 for o in overrides} == {16, 20, 24}
        assert {o["river_hexes_per_segment"] for o in overrides} == {5, 6}
        assert {o.get("bodega_points", NORMAL_V2.bodega_points if mode is Mode.NORMAL else 3)
                for o in overrides} == {3, 6, 9}
        shipped = tune.RULES_V2[mode].rounds
        steps = {o["rounds"][2] - shipped[2] if "rounds" in o else 0 for o in overrides}
        assert steps == {-2, 0, 2}
        assert all(o["varietal_points"] == V3_POINTS for o in overrides)
        for label, changes in sweep.candidates[mode]:
            job = tune.Job(label, mode, 2, "score_aware", {**sweep.base[mode], **changes}, 1, 1)
            p = with_overrides(tune.default_preset(mode), **dict(tune.rules_of(job).overrides))
            assert p.planting is PlantingRules.VERTICES and tune.is_v3(job.overrides)


def test_tune_reports_floodgates_per_game():
    tune = _tune()
    (sweep,) = tune.v3split_sweeps()
    label, changes = sweep.candidates[Mode.FLASH][0]
    job = tune.Job(label, Mode.FLASH, 2, "greedy", {**sweep.base[Mode.FLASH], **changes}, 4, 1)
    outcome = tune.run_chunk(job, 0, 4)
    assert outcome.status == "ok", outcome.error
    stats = tune.floodgate_stats(outcome.records)
    placed = [sum(isinstance(r.action, tune.PlaceFloodgate) for r in g.log) for g in outcome.records]
    assert stats["placed"] == sum(placed) / len(placed)
    assert stats["peak"] <= stats["peak_max"] <= max(placed)
    data = tune.summarize(tune.rules_of(job), job.seed, outcome.records).to_json()
    data["floodgates"] = stats
    row = tune.v3_sweep_row(job, tune.Outcome("ok", data))
    assert row.count("|") == tune.V3_SWEEP_COLUMNS + 1
    assert f"{stats['placed']:.2f} / {stats['peak']:.2f} / {stats['peak_max']:.0f}" in row
