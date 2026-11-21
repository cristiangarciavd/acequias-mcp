"""The action die (#112): an opt-in preset option that replaces the bribe.

Covers the pending face in the model, the die actions in ``turn.apply`` and
``legal_actions`` (with their rng draws), the round loop, the bots, the
simulation statistics, and the ``simulate_game`` JSON.
"""

import random
from dataclasses import replace

import pytest
from mcp import Client

from acequias.bots import greedy_bot, saboteur_bot
from acequias.config import (
    ROULETTE_SECTORS,
    BribeRules,
    action_die_rules,
    preset,
    roulette_rules,
    with_overrides,
)
from acequias.game import act, game_rngs, replay
from acequias.hex import Direction, Hex
from acequias.model import (
    Board,
    DieFace,
    Floodgate,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    Player,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import calculate_score
from acequias.setup import new_game
from acequias.sim import SimRules, play_one, simulate_game
from acequias.turn import (
    Bribe,
    DeclineFace,
    IllegalAction,
    Pass,
    PlaceFloodgate,
    Release,
    Resow,
    RollActionDie,
    apply,
    legal_actions,
)
from server.app import app

V = Varietal
DIE = {m: action_die_rules(roulette_rules(preset(m))) for m in Mode}
P = DIE[Mode.NORMAL]

R, H1 = Hex(0, 0), Hex(1, 0)
VA, VB = Hex(2, -1), Hex(2, 0)  # NE and E of H1
STRAIGHT = PlacedCanal(H1, PieceKind.STRAIGHT, 0, "b")  # opens W (river) and E (VB)
GATE = Floodgate(H1, Direction.E)


def board(**kw):
    tiles = (
        Tile(R, Terrain.RIVER),
        Tile(H1, Terrain.EMPTY),
        Tile(VA, Terrain.VINEYARD),
        Tile(VB, Terrain.VINEYARD),
    )
    return Board(tiles=tiles, **kw)


def state(b, face=None, market=(PieceKind.STRAIGHT,), bag=(PieceKind.CLAW,), p=P, debt=0):
    return GameState(
        board=b,
        players=(Player("a", 1, debt), Player("b", 2)),
        mode=p.mode,
        round=1,
        start_player="a",
        current_player="a",
        market=market,
        bag=bag,
        preset=p,
        pending_face=face,
    )


def rng_pair(seed=5):
    return random.Random(seed), random.Random(seed)


# --- Model -----------------------------------------------------------------------


def test_pending_face_needs_action_die_rules_and_a_face_on_the_die():
    with pytest.raises(ValueError, match="action_die"):
        state(board(), DieFace.RELEASE, p=roulette_rules(preset(Mode.NORMAL)))
    with pytest.raises(ValueError, match="not on the preset"):
        state(board(), DieFace.RESOW, p=replace(P, action_die=(DieFace.RELEASE,)))
    with pytest.raises(TypeError):
        state(board(), "release")
    assert state(board(), DieFace.RELEASE).pending_face is DieFace.RELEASE


@pytest.mark.parametrize("mode", list(Mode), ids=lambda m: m.name)
@pytest.mark.parametrize("players", [2, 5])
def test_a_die_game_has_no_floodgate_in_market_or_bag(mode, players):
    for seed in range(5):
        s = new_game(players, seed, mode, preset=DIE[mode])
        assert PieceKind.FLOODGATE not in s.market + s.bag


# --- Roll ------------------------------------------------------------------------


def test_roll_adds_the_cost_and_sets_the_face_with_one_draw():
    for seed in range(20):
        rng, ref = rng_pair(seed)
        face = ref.choice(P.action_die)
        before = state(board(), debt=3)
        after = apply(before, "a", RollActionDie(), rng)
        assert after.player("a").debt == 3 + P.action_die_cost
        assert after.player("b").debt == 0
        assert after.pending_face is face
        assert after.board == before.board and after.market == before.market
        assert rng.getstate() == ref.getstate()


def test_a_roll_at_cost_zero_keeps_the_debt_and_sets_the_face():
    p = with_overrides(P, action_die_cost=0)
    for seed in range(5):
        rng, ref = rng_pair(seed)
        face = ref.choice(p.action_die)
        after = apply(state(board(), p=p, debt=3), "a", RollActionDie(), rng)
        assert after.player("a").debt == 3
        assert after.pending_face is face
        assert legal_actions(after, "a")[-1] == DeclineFace()
        assert apply(after, "a", DeclineFace(), rng).pending_face is None


def test_legal_actions_without_a_pending_face():
    no_place = state(board(canals=(STRAIGHT,), floodgates=(GATE,)), market=())
    assert legal_actions(no_place, "a") == (RollActionDie(), Pass())
    actions = legal_actions(state(board()), "a")
    assert actions[-1] == RollActionDie()
    assert not any(isinstance(a, (Bribe, Pass)) for a in actions)


def test_bribe_under_action_die_and_roll_under_d6_are_illegal():
    rng = random.Random(1)
    before = rng.getstate()
    with pytest.raises(IllegalAction, match="no bribe"):
        apply(state(board(canals=(STRAIGHT,), floodgates=(GATE,))), "a", Bribe(H1, Direction.E), rng)
    d6 = state(board(), p=roulette_rules(preset(Mode.NORMAL)))
    with pytest.raises(IllegalAction, match="action_die"):
        apply(d6, "a", RollActionDie(), rng)
    assert RollActionDie() not in legal_actions(d6, "a")
    assert rng.getstate() == before


@pytest.mark.parametrize("action", [Release(H1, Direction.E), Resow(VB), DeclineFace()])
def test_face_actions_need_a_pending_face(action):
    rng = random.Random(1)
    before = rng.getstate()
    s = state(board(canals=(STRAIGHT,), floodgates=(GATE,), claims=((VB, "b"),),
                    plantings=((VB, V.SYRAH),)))
    with pytest.raises(IllegalAction, match="needs a rolled"):
        apply(s, "a", action, rng)
    assert rng.getstate() == before


# --- Pending face ------------------------------------------------------------------


def test_a_pending_face_allows_only_its_uses_and_decline():
    b = board(canals=(STRAIGHT,), floodgates=(GATE,), claims=((VB, "b"),),
              plantings=((VB, V.SYRAH),))
    assert legal_actions(state(b, DieFace.RELEASE), "a") == (Release(H1, Direction.E), DeclineFace())
    assert legal_actions(state(b, DieFace.RESOW), "a") == (Resow(VB), DeclineFace())
    assert legal_actions(state(b, DieFace.FLOODGATE), "a") == (
        PlaceFloodgate(H1, Direction.W), DeclineFace()
    )
    assert legal_actions(state(b, DieFace.RELEASE), "b") == ()
    rng = random.Random(1)
    before = rng.getstate()
    for action in (Resow(VB), Pass(), RollActionDie(), PlaceFloodgate(H1, Direction.W)):
        with pytest.raises(IllegalAction, match="allows only"):
            apply(state(b, DieFace.RELEASE), "a", action, rng)
    with pytest.raises(IllegalAction, match="cannot act"):
        apply(state(b, DieFace.RELEASE), "b", DeclineFace(), rng)
    with pytest.raises(IllegalAction, match="no floodgate to release"):
        apply(state(b, DieFace.RELEASE), "a", Release(H1, Direction.W), rng)
    with pytest.raises(IllegalAction, match="not a claimed vineyard"):
        apply(state(b, DieFace.RESOW), "a", Resow(VA), rng)
    assert rng.getstate() == before


def test_floodgate_face_comes_from_the_die_not_the_market():
    b = board(canals=(STRAIGHT,), claims=((VB, "b"),), plantings=((VB, V.SYRAH),))
    before = state(b, DieFace.FLOODGATE)
    rng = random.Random(2)
    start = rng.getstate()
    after = apply(before, "a", PlaceFloodgate(H1, Direction.E), rng)
    assert after.board.floodgates == (GATE,)
    assert after.market == before.market and after.bag == before.bag
    assert after.pending_face is None
    assert rng.getstate() == start


def test_release_face_removes_the_floodgate_and_the_roller_claims_and_spins():
    b = board(canals=(STRAIGHT,), floodgates=(GATE,))
    rng, ref = rng_pair(4)
    spin = ref.choice(ROULETTE_SECTORS)
    after = apply(state(b, DieFace.RELEASE, debt=2), "a", Release(H1, Direction.E), rng)
    assert after.board.floodgates == ()
    assert after.board.claims == ((VB, "a"),)
    assert after.board.plantings == ((VB, spin),)
    assert after.player("a").debt == 2
    assert after.pending_face is None
    assert rng.getstate() == ref.getstate()


def test_release_can_be_named_from_the_other_side_of_the_edge():
    b = board(canals=(STRAIGHT,), floodgates=(GATE,))
    after = apply(state(b, DieFace.RELEASE), "a", Release(VB, Direction.W), random.Random(0))
    assert after.board.floodgates == ()


def test_resow_on_a_rival_vineyard_spins_once_and_keeps_the_claim():
    b = board(canals=(STRAIGHT,), claims=((VB, "b"),), plantings=((VB, V.SYRAH),))
    for seed in range(30):
        rng, ref = rng_pair(seed)
        spin = ref.choice(ROULETTE_SECTORS)
        after = apply(state(b, DieFace.RESOW), "a", Resow(VB), rng)
        assert after.board.claims == ((VB, "b"),)
        assert after.board.plantings == ((VB, spin),)
        assert after.pending_face is None
        assert rng.getstate() == ref.getstate()


def test_resow_can_give_the_same_varietal_again():
    b = board(canals=(STRAIGHT,), claims=((VB, "b"),), plantings=((VB, V.SYRAH),))
    seed = next(s for s in range(200) if random.Random(s).choice(ROULETTE_SECTORS) is V.SYRAH)
    rng, ref = rng_pair(seed)
    ref.choice(ROULETTE_SECTORS)
    after = apply(state(b, DieFace.RESOW), "a", Resow(VB), rng)
    assert after.board.plantings == ((VB, V.SYRAH),)
    assert rng.getstate() == ref.getstate()  # it was spun, not skipped


def test_an_unusable_face_can_only_be_declined_and_the_cost_stays_paid():
    s = state(board(canals=(STRAIGHT,)), DieFace.RELEASE, debt=2)
    assert legal_actions(s, "a") == (DeclineFace(),)
    rng = random.Random(3)
    before = rng.getstate()
    after = apply(s, "a", DeclineFace(), rng)
    assert after == replace(s, pending_face=None)
    assert after.player("a").debt == 2
    assert rng.getstate() == before


def test_an_unwanted_face_declined_changes_nothing_else():
    s = state(board(canals=(STRAIGHT,), floodgates=(GATE,)), DieFace.RELEASE, debt=2)
    rng = random.Random(3)
    before = rng.getstate()
    assert apply(s, "a", DeclineFace(), rng) == replace(s, pending_face=None)
    assert rng.getstate() == before


# --- Round loop ------------------------------------------------------------------


def test_a_die_turn_keeps_the_player_then_moves_on():
    s = state(board(canals=(STRAIGHT,), floodgates=(GATE,)), market=())
    rolled = act(s, "a", RollActionDie(), random.Random(0))
    assert rolled.current_player == "a" and rolled.round == 1
    assert rolled.pending_face is not None
    with pytest.raises(ValueError):
        act(rolled, "b", DeclineFace(), random.Random(0))
    done = act(rolled, "a", DeclineFace(), random.Random(0))
    assert done.current_player == "b" and done.round == 1
    assert done.pending_face is None


def die_record(policies=("random", "random", "random"), mode=Mode.FLASH):
    rules = SimRules(mode, len(policies), policies, {
        "varietal_rules": DIE[mode].varietal_rules,
        "varietal_points": DIE[mode].varietal_points,
        "bribe_rules": BribeRules.ACTION_DIE,
        "bag_mix": DIE[mode].bag_mix,
    })
    for seed in range(50):
        record = play_one(rules, seed)
        if any(isinstance(r.action, RollActionDie) for r in record.log):
            return record
    raise AssertionError("no game rolled the die")


def test_a_die_game_logs_two_records_per_die_turn_and_replays():
    record = die_record()
    log = record.log
    for i, r in enumerate(log):
        if isinstance(r.action, RollActionDie):
            assert r.face is not None
            nxt = log[i + 1]
            assert (nxt.round, nxt.player) == (r.round, r.player)
            assert isinstance(nxt.action, (PlaceFloodgate, Release, Resow, DeclineFace))
        else:
            assert r.face is None
    dice, _ = game_rngs(record.game_seed)
    assert replay(record.start, log, dice) == record.final
    rolls = sum(isinstance(r.action, RollActionDie) for r in log)
    players = len(record.start.players)
    assert len(log) == record.start.preset.rounds_for(players) * players + rolls


def test_scoring_subtracts_the_die_debt():
    record = die_record()
    for p in record.final.players:
        assert record.scores[p.id].debt == p.debt
    roller = next(r.player for r in record.log if isinstance(r.action, RollActionDie))
    assert record.final.player(roller).debt >= P.action_die_cost


# --- Bots ------------------------------------------------------------------------


@pytest.mark.parametrize("bot", [greedy_bot, saboteur_bot])
def test_greedy_and_saboteur_resow_a_rivals_best_vineyard(bot):
    # Bonarda is worth 3, above the roulette's mean (30/14): resowing a rival's helps.
    b = board(canals=(STRAIGHT,), claims=((VB, "b"),), plantings=((VB, V.BONARDA),))
    assert bot(state(b, DieFace.RESOW), "a", random.Random(0)) == Resow(VB)


@pytest.mark.parametrize("bot", [greedy_bot, saboteur_bot])
def test_greedy_and_saboteur_decline_a_face_with_no_gain(bot):
    own = board(canals=(STRAIGHT,), claims=((VB, "a"),), plantings=((VB, V.BONARDA),))
    assert bot(state(own, DieFace.RESOW), "a", random.Random(0)) == DeclineFace()
    assert bot(state(board(canals=(STRAIGHT,)), DieFace.RELEASE), "a", random.Random(0)) == DeclineFace()


@pytest.mark.parametrize("bot", [greedy_bot, saboteur_bot])
def test_greedy_and_saboteur_release_a_floodgate_that_waters_their_claim(bot):
    b = board(canals=(STRAIGHT,), floodgates=(GATE,))
    assert bot(state(b, DieFace.RELEASE), "a", random.Random(0)) == Release(H1, Direction.E)


@pytest.mark.parametrize("policy", ["greedy", "saboteur"])
def test_greedy_and_saboteur_finish_die_games_without_rolling(policy):
    rules = SimRules(Mode.FLASH, 3, (policy,) * 3, {
        "varietal_rules": P.varietal_rules,
        "varietal_points": P.varietal_points,
        "bribe_rules": BribeRules.ACTION_DIE,
        "bag_mix": P.bag_mix,
    })
    for seed in range(3):
        record = play_one(rules, seed)
        assert not any(isinstance(r.action, RollActionDie) for r in record.log)
        assert calculate_score(record.final) == record.scores


@pytest.mark.parametrize("policy", ["score_aware", "lookahead"])
def test_smart_bots_finish_a_cost_zero_die_game(policy):
    rules = SimRules(Mode.FLASH, 3, (policy,) * 3, {
        "varietal_rules": P.varietal_rules,
        "varietal_points": P.varietal_points,
        "bribe_rules": BribeRules.ACTION_DIE,
        "bag_mix": P.bag_mix,
        "action_die_cost": 0,
    })
    record = play_one(rules, 1)
    assert calculate_score(record.final) == record.scores
    assert all(p.debt == 0 for p in record.final.players)


# --- Simulation and JSON ------------------------------------------------------------

DIE_JSON = {
    "varietal_rules": "roulette",
    "varietal_points": {
        "malbec": 2, "cabernet_sauvignon": 2, "cabernet_franc": 3, "syrah": 2,
        "merlot": 2, "bonarda": 3, "torrontes": 2, "chardonnay": 2,
    },
    "bribe_rules": "action_die",
    "action_die": ["floodgate", "release", "release", "resow"],
    "action_die_cost": 3,
    "bag_mix": {
        "straight": 44, "gentle_curve": 22, "sharp_curve": 17, "symmetric_y": 6,
        "t_branch": 6, "claw": 5, "floodgate": 0,
    },
}


def test_die_simulation_is_repeatable_and_counts_the_die():
    from server.schemas import overrides_from_json

    rules = SimRules(Mode.FLASH, 3, ("random",) * 3, overrides_from_json(DIE_JSON))
    first = simulate_game(rules, 6, 11)
    assert first == simulate_game(rules, 6, 11)
    assert first.games_with_die > 0
    actions = first.actions_per_game
    assert sum(actions.values()) == pytest.approx(first.turns_per_game)
    assert actions["die"] == pytest.approx(sum(first.die_faces_per_game.values()))
    # Every roll is resolved once; all floodgates come from the die.
    assert actions["die"] == pytest.approx(
        actions["floodgate"] + actions["release"] + actions["resow"] + actions["decline"]
    )
    assert actions["bribe"] == 0
    assert 0 <= first.die_use_rate <= 1
    assert first.die_use_rate == pytest.approx(1 - actions["decline"] / actions["die"])


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_simulate_game_tool_accepts_and_echoes_the_die_overrides():
    async with Client(app) as client:
        result = await client.call_tool("simulate_game", {
            "mode": "flash", "players": 3, "games": 2, "seed": 4,
            "policies": ["random", "random", "random"], "overrides": DIE_JSON,
        })
    assert not result.is_error
    data = result.structured_content
    for key in ("bribe_rules", "action_die", "action_die_cost", "bag_mix"):
        assert data["preset"][key] == DIE_JSON[key]
    assert set(data["die_faces_per_game"]) == {"floodgate", "release", "resow"}


@pytest.mark.anyio
async def test_simulate_game_tool_takes_a_cost_of_zero_and_rejects_minus_one():
    async with Client(app) as client:
        ok = await client.call_tool("simulate_game", {
            "mode": "flash", "players": 2, "games": 1, "seed": 4,
            "overrides": {**DIE_JSON, "action_die_cost": 0},
        })
        bad = await client.call_tool("simulate_game", {
            "mode": "flash", "players": 2, "games": 1, "seed": 4,
            "overrides": {**DIE_JSON, "action_die_cost": -1},
        })
    assert not ok.is_error
    assert ok.structured_content["preset"]["action_die_cost"] == 0
    assert bad.is_error
    assert "action_die_cost" in str(bad.content)


@pytest.mark.anyio
@pytest.mark.parametrize("overrides", [
    {**DIE_JSON, "action_die": ["floodgate", "teleport"]},
    {**DIE_JSON, "bribe_rules": "d20"},
])
async def test_simulate_game_tool_rejects_unknown_die_names(overrides):
    async with Client(app) as client:
        result = await client.call_tool("simulate_game", {
            "mode": "flash", "players": 2, "games": 1, "seed": 4, "overrides": overrides,
        })
    assert result.is_error
