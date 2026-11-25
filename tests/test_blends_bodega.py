"""Rules v3 scoring options: blend (corte) bonuses and bodega buildings (#166)."""

from __future__ import annotations

import random
from dataclasses import replace
from fractions import Fraction

import pytest
from mcp import Client

from acequias import bots
from acequias.bots import _Evaluator, greedy_bot, lookahead_bot, score_aware_bot
from acequias.config import (
    FLASH,
    NORMAL,
    DEFAULT_BLENDS,
    V3_DIE_FACES,
    V3_POINTS,
    Blend,
    BlendRule,
    BodegaPlacement,
    BoardShape,
    PlantingRules,
    preset,
    with_overrides,
)
from acequias.flow import plantable_spots
from acequias.game import act, game_over, game_rngs
from acequias.hex import Hex, Vertex
from acequias.model import (
    ActionsLeft,
    Board,
    BodegaBuilding,
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
from acequias.scoring import blend_points, calculate_score
from acequias.setup import new_game
from acequias.sim import SimRules, simulate_game
from acequias.turn import (
    BuildBodega,
    IllegalAction,
    MoveVineyard,
    Pass,
    PlaceCanal,
    Plant,
    ResowVineyard,
    apply,
    can_build_bodega,
    legal_actions,
)
from server.app import app
from test_split_scoring import _tune

pytestmark = pytest.mark.anyio

MA, CS, CF, ME, BO = (
    Varietal.MALBEC, Varietal.CABERNET_SAUVIGNON, Varietal.CABERNET_FRANC, Varietal.MERLOT,
    Varietal.BONARDA,
)
TO, CH, SY = Varietal.TORRONTES, Varietal.CHARDONNAY, Varietal.SYRAH

# The issue's first table: small enough to check the rules by hand.
TABLE = (
    Blend(frozenset({Varietal.CABERNET_FRANC, Varietal.MALBEC}), 3),
    Blend(frozenset({Varietal.CABERNET_SAUVIGNON, Varietal.MALBEC}), 2),
    Blend(frozenset({Varietal.MALBEC, Varietal.CABERNET_SAUVIGNON, Varietal.MERLOT,
                     Varietal.CABERNET_FRANC}), 5),
    Blend(frozenset({Varietal.MALBEC, Varietal.CABERNET_SAUVIGNON, Varietal.BONARDA}), 4),
)
V3 = with_overrides(NORMAL, planting=PlantingRules.VERTICES, varietal_points=V3_POINTS)
BLENDS = with_overrides(V3, varietal_bodega=False, blends=DEFAULT_BLENDS)
BUILD = with_overrides(V3, bodega_building=True, action_die=V3_DIE_FACES)

# The geometry of tests/test_split_scoring.py: river on (0, -1) and (0, 0); straight E-W
# canals on L, M, N, R; V is where M, N and R meet.
RIVER = (Hex(0, -1), Hex(0, 0))
L, M, N, R = Hex(1, -1), Hex(1, 0), Hex(2, 0), Hex(2, -1)
V = Vertex((M, N, R))
TILES = tuple(Tile(h, Terrain.RIVER) for h in RIVER) + tuple(
    Tile(Hex(q, r), Terrain.EMPTY) for q in range(1, 5) for r in (-2, -1, 0, 1)
)
ALL = {L: "p1", M: "p1", N: "p1", R: "p1"}
TWO_ONE = {L: "p2", M: "p1", N: "p1", R: "p2"}  # V: M and N are p1's, R is p2's


def board(owners, planted=(), bodegas=()) -> Board:
    return Board(
        tiles=TILES,
        canals=tuple(PlacedCanal(h, PieceKind.STRAIGHT, 0, o) for h, o in owners.items()),
        planted=planted,
        bodegas=bodegas,
    )


def state(b, p=V3, face=None, left=ActionsLeft(1, 1)) -> GameState:
    return GameState(
        board=b,
        players=(Player("p1", 1), Player("p2", 2)),
        mode=Mode.NORMAL,
        round=1,
        start_player="p1",
        current_player="p1",
        market=(PieceKind.STRAIGHT,) * 4,
        preset=p,
        actions_left=left,
        pending_face=face,
    )


SPOTS = plantable_spots(board(ALL), "p1")  # 16 spots, all touching p1's wet canals
FREE = [s for s in SPOTS if s != V]


def planted(*varietals, owner="p1", spots=FREE) -> tuple[PlantedVineyard, ...]:
    return tuple(PlantedVineyard(s, owner, v) for s, v in zip(spots, varietals))


@pytest.fixture
def anyio_backend():
    return "asyncio"


# --- Config ----------------------------------------------------------------------


def test_shipped_presets_keep_the_options_off():
    for p in (NORMAL, FLASH):
        assert p.varietal_bodega and p.blends == () and not p.bodega_building
    assert (V3.bodega_min_reds, V3.bodega_min_whites, V3.bodega_building_points) == (2, 2, 12)
    assert V3.bodegas_per_player == 1 and V3.bodega_placement is BodegaPlacement.NEW_SPOT


def test_default_blends_are_the_cortes_of_docs_blends_md():
    assert [(b.name, b.points) for b in DEFAULT_BLENDS] == [
        ("Malbec + Cabernet Sauvignon", 2),
        ("Malbec + Bonarda", 2),
        ("Malbec + Syrah", 2),
        ("Malbec + Cabernet Franc", 3),
        ("Torrontés + Chardonnay", 3),
        ("Malbec + Torrontés", 3),
        ("Malbec + Cabernet Sauvignon + Merlot", 4),
        ("Malbec + Cabernet Sauvignon + Cabernet Franc", 4),
        ("Malbec + Cabernet Sauvignon + Bonarda", 4),
        ("Malbec + Cabernet Sauvignon + Cabernet Franc + Merlot", 5),
    ]


def test_blends_accept_white_and_mixed_sets_and_pairs():
    p = with_overrides(V3, blends=[({TO, CH}, 3), (frozenset({MA, TO}), 2)])
    assert p.blends == (Blend(frozenset({TO, CH}), 3), Blend(frozenset({MA, TO}), 2))
    assert p.blends[0].name == "Torrontés + Chardonnay"
    assert repr(p.blends[1]) == "Blend(frozenset({Varietal.MALBEC, Varietal.TORRONTES}), 2)"


@pytest.mark.parametrize("changes, error", [
    ({"blends": [({MA}, 3)]}, ValueError),
    ({"blends": [((MA, MA), 3)]}, ValueError),
    ({"blends": [({MA, CS}, 0)]}, ValueError),
    ({"blends": [({MA, CS}, 2), ({CS, MA}, 3)]}, ValueError),
    ({"blends": [("malbec", 3)]}, TypeError),
    ({"bodega_min_whites": 3, "bodega_building": True}, ValueError),
    ({"bodega_min_reds": -1}, ValueError),
    ({"bodega_building_points": 0}, ValueError),
    ({"bodegas_per_player": 0}, ValueError),
    ({"blend_rule": "disjoint"}, TypeError),
])
def test_bad_options_are_rejected(changes, error):
    with pytest.raises(error):
        with_overrides(V3, **changes)


def test_blends_and_buildings_need_vertex_planting():
    with pytest.raises(ValueError, match="vertex planting"):
        with_overrides(NORMAL, blends=DEFAULT_BLENDS)
    with pytest.raises(ValueError, match="vertex planting"):
        with_overrides(NORMAL, bodega_building=True)


# --- Blend scoring ----------------------------------------------------------------


def test_each_once_scores_every_held_blend_once():
    points, scored = blend_points([MA, CS, CF, ME, BO], TABLE, BlendRule.EACH_ONCE)
    assert points == 3 + 2 + 5 + 4 and scored == TABLE
    assert blend_points([MA, MA, CS], TABLE, BlendRule.EACH_ONCE)[0] == 2


def test_disjoint_scores_the_best_set_that_uses_no_vineyard_twice():
    points, scored = blend_points([MA, CS, CF, ME, BO], TABLE, BlendRule.DISJOINT)
    assert points == 5 and [b.points for b in scored] == [5]  # one Malbec: one blend
    points, scored = blend_points([MA, MA, CS, CS, CF, ME, BO], TABLE, BlendRule.DISJOINT)
    assert points == 9 and sorted(b.points for b in scored) == [4, 5]
    assert blend_points([MA, MA, CF, CS], TABLE, BlendRule.DISJOINT)[0] == 5  # 3 + 2


def test_white_blends_score():
    blends = (Blend(frozenset({TO, CH}), 4), Blend(frozenset({MA, TO}), 2))
    assert blend_points([TO, CH, MA], blends, BlendRule.DISJOINT) == (4, blends[:1])
    assert blend_points([TO, CH, MA], blends, BlendRule.EACH_ONCE) == (6, blends)


def test_calculate_score_adds_blends_for_every_watered_third_holder():
    b = board(TWO_ONE, (PlantedVineyard(V, "p1", MA),) + planted(CF, spots=[Vertex((M, N, Hex(1, 1)))]))
    s = calculate_score(state(b, BLENDS))
    assert (s["p1"].blend, s["p1"].blends, s["p1"].bodega) == (3, ("Malbec + Cabernet Franc",), 0)
    assert s["p1"].total == s["p1"].vineyards + 3
    assert s["p2"].blend == 0  # p2 holds Malbec (a third of V) but no Cabernet Franc


def test_the_bodega_bonus_can_be_turned_off():
    b = board(ALL, planted(MA, CS, SY))
    assert calculate_score(state(b))["p1"].bodega == V3.bodega_points
    off = calculate_score(state(b, with_overrides(V3, varietal_bodega=False)))["p1"]
    assert (off.bodega, off.bodegas) == (0, 0)


# --- Bodega buildings: scoring -------------------------------------------------------


def test_a_bodega_building_scores_split_in_thirds_and_counts_no_varietal():
    s = calculate_score(state(board(TWO_ONE, bodegas=(BodegaBuilding(V, "p1"),)), BLENDS))
    assert (s["p1"].buildings, s["p2"].buildings) == (8, 4)
    (w,) = s["p2"].watered_bodegas
    assert (w.vertex, w.builder, w.thirds, w.points) == (V, "p1", 1, 4)
    assert s["p1"].total == 8 and s["p1"].watered == 0 and s["p1"].vineyards == 0
    dry = calculate_score(state(board({M: "p1"}, bodegas=(BodegaBuilding(V, "p1"),))))
    assert dry["p1"].buildings == 4  # only M carries water


def test_a_bodega_and_a_vineyard_cannot_share_a_vertex():
    with pytest.raises(ValueError, match="both on"):
        board(ALL, (PlantedVineyard(V, "p1", MA),), (BodegaBuilding(V, "p1"),))
    with pytest.raises(ValueError, match="hex planting"):
        GameState(board=board(ALL, bodegas=(BodegaBuilding(V, "p1"),)),
                  players=(Player("p1", 1), Player("p2", 2)), mode=Mode.NORMAL, round=1,
                  start_player="p1", current_player="p1", market=(), preset=NORMAL)


# --- Bodega buildings: the action ---------------------------------------------------


READY = planted(MA, CS, TO, CH)  # 2 distinct reds and 2 distinct whites


def test_build_needs_two_distinct_reds_and_whites_of_own_planted_vineyards():
    assert can_build_bodega(board(ALL, READY), "p1", BUILD)
    assert not can_build_bodega(board(ALL, READY), "p1", V3)  # option off
    assert not can_build_bodega(board(ALL, planted(MA, MA, TO, CH)), "p1", BUILD)
    assert not can_build_bodega(board(ALL, planted(MA, CS, TO, TO)), "p1", BUILD)
    rival = planted(MA, CS, TO, CH, owner="p2")  # watered by p1's canals, planted by p2
    assert not can_build_bodega(board(ALL, rival), "p1", BUILD)
    assert can_build_bodega(board(ALL, planted(MA, TO)), "p1",
                            with_overrides(BUILD, bodega_min_reds=1, bodega_min_whites=1))
    assert not can_build_bodega(board(ALL, planted(MA, TO)), "p1",
                                with_overrides(BUILD, bodega_min_reds=0, bodega_min_whites=0,
                                               bodega_min_vineyards=3))


def test_build_on_a_new_spot_is_one_action_and_capped():
    s = state(board(ALL, READY), BUILD, left=ActionsLeft(2, 1))
    builds = [a for a in legal_actions(s, "p1") if isinstance(a, BuildBodega)]
    spots = plantable_spots(s.board, "p1")
    assert [a.vertex for a in builds] == list(spots)
    plants = [a for a in legal_actions(s, "p1") if isinstance(a, Plant)]
    assert legal_actions(s, "p1").index(builds[0]) > legal_actions(s, "p1").index(plants[-1])
    after = apply(s, "p1", BuildBodega(V), random.Random(0))
    assert after.board.bodega_at(V) == BodegaBuilding(V, "p1")
    assert after.board.planted == s.board.planted and after.actions_left == ActionsLeft(1, 1)
    assert not any(isinstance(a, BuildBodega) for a in legal_actions(after, "p1"))  # 1 per player
    assert Plant(V) not in legal_actions(after, "p1")
    with pytest.raises(IllegalAction):
        apply(after, "p1", BuildBodega(spots[0]), random.Random(0))
    with pytest.raises(IllegalAction):
        apply(after, "p1", Plant(V), random.Random(0))
    two = with_overrides(BUILD, bodegas_per_player=2)
    assert any(isinstance(a, BuildBodega) for a in legal_actions(replace(after, preset=two), "p1"))


def test_build_is_illegal_without_the_requirement_or_on_a_bad_spot():
    s = state(board(ALL, planted(MA, CS, TO)), BUILD)
    assert not any(isinstance(a, BuildBodega) for a in legal_actions(s, "p1"))
    with pytest.raises(IllegalAction, match="may not build"):
        apply(s, "p1", BuildBodega(V), random.Random(0))
    ready = state(board(ALL, READY), BUILD)
    with pytest.raises(IllegalAction, match="plant on"):
        apply(ready, "p1", BuildBodega(READY[0].vertex), random.Random(0))
    with pytest.raises(IllegalAction):
        apply(state(board(ALL, READY), V3), "p1", BuildBodega(V), random.Random(0))


def test_replace_placement_swaps_one_own_vineyard_for_the_bodega():
    p = with_overrides(BUILD, bodega_placement=BodegaPlacement.REPLACE)
    s = state(board(ALL, READY), p)
    builds = [a for a in legal_actions(s, "p1") if isinstance(a, BuildBodega)]
    assert {a.vertex for a in builds} == {v.vertex for v in READY}
    after = apply(s, "p1", BuildBodega(READY[0].vertex), random.Random(0))
    assert after.board.planted_at(READY[0].vertex) is None
    assert after.board.bodega_at(READY[0].vertex).owner == "p1"
    with pytest.raises(IllegalAction, match="no vineyard"):
        apply(s, "p1", BuildBodega(V), random.Random(0))


def test_a_bodega_is_never_moved_or_resown():
    b = board(ALL, READY[:1], (BodegaBuilding(V, "p1"),))
    moves = legal_actions(state(b, BUILD, face=DieFace.MOVE), "p1")
    assert all(m.vertex != V and m.to != V for m in moves if isinstance(m, MoveVineyard))
    resows = legal_actions(state(b, BUILD, face=DieFace.RESOW), "p1")
    assert ResowVineyard(V) not in resows
    with pytest.raises(IllegalAction):
        apply(state(b, BUILD, face=DieFace.MOVE), "p1", MoveVineyard(V, FREE[5]), random.Random(0))


# --- Bots ------------------------------------------------------------------------


@pytest.mark.parametrize("bot", [greedy_bot, score_aware_bot])
def test_bots_build_a_bodega_when_they_may(bot):
    s = replace(state(board(TWO_ONE, READY), BUILD), market=())  # no canal to weigh against
    assert isinstance(bot(s, "p1", random.Random(0)), BuildBodega)


def test_lookahead_values_a_bodega_build():
    s = replace(state(board(TWO_ONE, READY), BUILD), market=())
    assert isinstance(lookahead_bot(s, "p1", random.Random(0), depth=1), BuildBodega)
    options = dict(bots._Lookahead(s, "p1", 3).options(s, {}, 2))
    builds = [v for a, v in options.items() if isinstance(a, BuildBodega)]
    assert builds  # a build is among the beam's best one-move values


def test_score_aware_values_blends_and_the_turned_off_bodega():
    # A resow face: p1 can respin its Merlot next to its Malbec (no blend). A blank
    # counts for no blend, so blends change nothing here.
    b = board(ALL, planted(MA, ME))
    face = DieFace.RESOW
    with_blends = _Evaluator(state(b, BLENDS, face=face), "p1")
    no_blends = _Evaluator(state(b, with_overrides(V3, varietal_bodega=False), face=face), "p1")
    s = state(b, BLENDS, face=face)
    action = ResowVineyard(FREE[1])
    assert with_blends.value(s, action) == no_blends.value(replace(s, preset=no_blends.preset), action)
    # A blend already held is lost by respinning one of its vineyards.
    held = board(ALL, planted(MA, CF))
    s = state(held, BLENDS, face=face)
    assert _Evaluator(s, "p1").value(s, ResowVineyard(FREE[1])) < _Evaluator(
        replace(s, preset=with_overrides(V3, varietal_bodega=False)), "p1"
    ).value(replace(s, preset=with_overrides(V3, varietal_bodega=False)), ResowVineyard(FREE[1]))


STRIP = {
    "planting": PlantingRules.VERTICES,
    "board_shape": BoardShape.RIVER_STRIP,
    "bag_size": {2: 32, 3: 48},
    "varietal_points": V3_POINTS,
    "action_die": V3_DIE_FACES,
}


def _states(policy, extra, seed):
    s = new_game(2, seed, Mode.FLASH, preset=with_overrides(preset(Mode.FLASH), **extra))
    dice, bot_rng = game_rngs(seed)
    while not game_over(s):
        if s.pending_face is None and s.actions_left is not None:
            yield s
        player = s.current_player
        s = act(s, player, bots.policy(policy)(s, player, bot_rng), dice)


@pytest.mark.parametrize("extra", [
    {**STRIP, "varietal_bodega": False, "blends": DEFAULT_BLENDS},
    {**STRIP, "blends": DEFAULT_BLENDS, "blend_rule": BlendRule.DISJOINT, "bodega_building": True,
     "bodega_min_reds": 1, "bodega_min_whites": 0},
])
def test_fast_canal_and_plant_values_equal_a_full_scoring(monkeypatch, extra):
    checked = built = 0
    for s in _states("score_aware", extra, 3):
        player = s.current_player
        built += len(s.board.bodegas)
        fast = _Evaluator(s, player, {"p2": Fraction(1, 2)}, {})
        monkeypatch.setattr(_Evaluator, "fast", False)
        full = _Evaluator(s, player, {"p2": Fraction(1, 2)}, {})
        for action in legal_actions(s, player):
            if isinstance(action, (PlaceCanal, Plant)):
                monkeypatch.setattr(_Evaluator, "fast", True)
                a = fast.value(s, action)
                monkeypatch.setattr(_Evaluator, "fast", False)
                b = full.value(s, action)
                assert a == b, (action, s.board)
                checked += 1
        monkeypatch.setattr(_Evaluator, "fast", True)
    assert checked > 50
    if extra.get("bodega_building"):
        assert built > 0


def test_bots_resow_to_complete_a_close_requirement():
    # Malbec, Cabernet Sauvignon, Torrontés and a second Torrontés: one white short.
    b = board(ALL, planted(MA, CS, TO, TO))
    dup = ResowVineyard(FREE[3])
    with_req = state(b, BUILD, face=DieFace.RESOW)
    without = replace(with_req, preset=with_overrides(V3, action_die=V3_DIE_FACES))
    gain = _Evaluator(with_req, "p1").value(with_req, dup) - _Evaluator(without, "p1").value(without, dup)
    assert gain == bots.REQUIREMENT_SHARE * 12 * Fraction(2, 14)  # a Chardonnay spin
    # A met requirement is not risked: resowing a needed white loses.
    met = state(board(ALL, planted(MA, CS, TO, CH)), BUILD, face=DieFace.RESOW)
    plain = replace(met, preset=with_overrides(V3, action_die=V3_DIE_FACES))
    needed = ResowVineyard(FREE[2])
    assert _Evaluator(met, "p1").value(met, needed) < _Evaluator(plain, "p1").value(plain, needed)
    # Greedy weighs the same potential (_requirement) in its face swing.
    assert bots._requirement(BUILD, b, "p1", ()) == 0
    assert bots._requirement(BUILD, b, "p1", (FREE[3],)) == bots.REQUIREMENT_SHARE * 12 * Fraction(2, 14)
    built = board(ALL, READY[:1], (BodegaBuilding(V, "p1"),))  # kept once built
    assert bots._requirement(BUILD, built, "p1", ()) == bots.REQUIREMENT_SHARE * 12


# --- Sim and MCP ------------------------------------------------------------------


def test_simulate_game_counts_bodegas_and_writes_the_options():
    overrides = {**STRIP, "varietal_bodega": False, "blends": DEFAULT_BLENDS[:2],
                 "bodega_building": True, "bodega_min_reds": 1, "bodega_min_whites": 0}
    result = simulate_game(SimRules(Mode.FLASH, 2, ("greedy", "greedy"), overrides), 2, 1)
    assert result.actions_per_game["bodega"] > 0
    values = result.to_json()["preset"]
    assert values["varietal_bodega"] is False and values["bodega_building"] is True
    assert values["blends"][0] == {"varietals": ["malbec", "cabernet_sauvignon"], "points": 2}
    assert "bodega_placement" not in values and "bodegas_per_player" not in values
    plain = simulate_game(SimRules(Mode.FLASH, 2, ("greedy", "greedy"), STRIP), 1, 1).to_json()
    assert "bodega" not in plain["actions_per_game"] and "blends" not in plain["preset"]


async def test_mcp_tools_take_blends_and_bodegas():
    overrides = {
        "planting": "vertices",
        "varietal_points": {v.name.lower(): p for v, p in V3_POINTS.items()},
        "varietal_bodega": False,
        "blends": [{"varietals": ["malbec", "torrontes"], "points": 2},
                   {"varietals": ["torrontes", "chardonnay"], "points": 3}],
        "blend_rule": "disjoint",
        "bodega_building": True,
        "bodega_placement": "replace",
        "bodegas_per_player": None,
    }
    tiles = [{"q": t.hex.q, "r": t.hex.r, "terrain": t.terrain.value, "varietal": None} for t in TILES]
    async with Client(app) as client:
        result = await client.call_tool("calculate_score", {
            "mode": "normal",
            "hexes": tiles,
            "players": [{"id": "p1", "debt": 0}, {"id": "p2", "debt": 0}],
            "canals": [{"q": h.q, "r": h.r, "kind": "straight", "rotation": 0, "owner": o}
                       for h, o in TWO_ONE.items()],
            "planted": [{"hexes": [[h.q, h.r] for h in s.hexes], "player": "p1", "varietal": v}
                        for s, v in zip(FREE[2:5], ("malbec", "torrontes", "chardonnay"))],
            "bodegas": [{"hexes": [[h.q, h.r] for h in V.hexes], "player": "p1"}],
            "overrides": overrides,
        })
        assert not result.is_error, result.content
        p1 = {s["player"]: s for s in result.structured_content["scores"]}["p1"]
        assert p1["buildings"] == 8 and p1["watered_bodegas"][0]["points"] == 8
        sim = await client.call_tool("simulate_game", {
            "mode": "flash", "players": 2, "n": 1, "seed": 1,
            "overrides": {**overrides, "board_shape": "river_strip", "bag_size": {"2": 32, "3": 48}},
        })
        assert not sim.is_error, sim.content
        echoed = sim.structured_content["preset"]
        assert echoed["blend_rule"] == "disjoint" and echoed["bodegas_per_player"] is None
        assert echoed["blends"][1] == {"varietals": ["torrontes", "chardonnay"], "points": 3}
        plain = await client.call_tool("calculate_score", {
            "mode": "normal", "hexes": tiles, "players": [{"id": "p1", "debt": 0}, {"id": "p2", "debt": 0}],
        })
        assert "blend" not in plain.structured_content["scores"][0]


# --- tune.py ----------------------------------------------------------------------


def test_tune_v3blends_sweep_covers_the_options():
    tune = _tune()
    (sweep,) = tune.v3blends_sweeps()
    assert sweep.name == "v3blends" and "v3blends" in tune.SWEEP_NAMES
    for mode in Mode:
        labels = [label for label, _ in sweep.candidates[mode]]
        assert len(labels) == 17
        assert any("disjoint x0.5" in x for x in labels) and any("building 15 x1," in x for x in labels)
        assert sum("2 reds + 1 whites" in x for x in labels) == sum("2 reds + 2 whites" in x for x in labels) == 4
        for label, changes in sweep.candidates[mode]:
            job = tune.Job(label, mode, 2, "score_aware", {**sweep.base[mode], **changes}, 1, 1)
            p = with_overrides(tune.shipped_preset(mode), **dict(tune.rules_of(job).overrides))
            assert p.planting is PlantingRules.VERTICES and p.action_die == V3_DIE_FACES
    x15 = dict(sweep.candidates[Mode.NORMAL])["blends each_once x1.5"]
    assert [b.points for b in x15["blends"]] == [3, 3, 3, 5, 5, 5, 6, 6, 6, 8]


def test_tune_blend_stats_and_row():
    tune = _tune()
    (sweep,) = tune.v3blends_sweeps()
    label, changes = next(
        (x, c) for x, c in sweep.candidates[Mode.FLASH] if "building 12 x1, 2 reds + 1" in x)
    changes = {**changes, "bodega_min_reds": 1, "bodega_min_whites": 0}
    job = tune.Job(label, Mode.FLASH, 2, "greedy", {**sweep.base[Mode.FLASH], **changes}, 2, 1)
    outcome = tune.run_chunk(job, 0, 2)
    stats = tune.blend_stats(outcome.records)
    assert stats["built"] > 0 and set(stats["rates"]) <= {b.name for b in DEFAULT_BLENDS}
    req = stats["requirement"]
    assert 0 < req["builders"] <= req["met"] <= 1 and 1 <= req["first_round"]
    data = tune.summarize(tune.rules_of(job), job.seed, outcome.records).to_json()
    data["blend_stats"] = stats
    assert tune.is_v3blends(job.overrides)
    row = tune.v3_sweep_row(job, tune.Outcome("ok", data)) + tune._blend_columns(data)
    assert row.count("|") == tune.V3_SWEEP_COLUMNS + tune.BLEND_COLUMNS + 1
