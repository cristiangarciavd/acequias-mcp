"""The lookahead bot (#42): own moves planned ahead, score_aware rivals, chance by expectation."""

import random
from dataclasses import replace

import pytest
from mcp import Client
from test_score_aware import (
    COMBOS,
    EAST,
    FAR_E,
    FAR_W,
    GATE,
    MALBEC,
    NE,
    NORMAL,
    STRAIGHT,
    TORRONTES,
    WEST,
    CountingRandom,
    E,
    W,
    as_overrides,
    canal,
    make_state,
    picks,
)

from acequias import sim
from acequias.bots import POLICIES, greedy_bot, lookahead_bot, policy, score_aware_bot
from acequias.config import RULES_V1, action_die_rules, preset, scaled, with_overrides
from acequias.hex import Hex
from acequias.model import DieFace, Mode
from acequias.sim import SimRules, simulate_game
from acequias.turn import PlaceCanal, PlaceFloodgate, RollActionDie, legal_actions
from server.app import app

PIN_RULES_V1 = True
"""``conftest.py``: these tests check the engine under the Rules v1 presets."""
NORMAL, FLASH = RULES_V1[Mode.NORMAL], RULES_V1[Mode.FLASH]

FAR_FAR_E = Hex(3, 0)


# --- Interface ---------------------------------------------------------------


def test_policy_looks_up_the_lookahead_bot_with_its_defaults():
    bot = policy("lookahead")
    assert bot is POLICIES["lookahead"]
    assert bot.func is lookahead_bot
    assert bot.keywords == {"depth": 2, "beam": 3}


def test_simulate_game_accepts_lookahead_seats():
    rules = SimRules(Mode.FLASH, 2, ("lookahead", "greedy"))
    result = simulate_game(rules, 1, 3)
    assert set(result.win_rate_by_policy) == {"lookahead", "greedy"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_the_simulate_game_tool_accepts_lookahead_seats():
    policies = ["lookahead", "random"]
    async with Client(app) as client:
        result = await client.call_tool(
            "simulate_game",
            {"mode": "flash", "players": 2, "games": 1, "seed": 4, "policies": policies},
        )
    assert not result.is_error
    rules = SimRules(Mode.FLASH, 2, tuple(policies))
    assert result.structured_content == simulate_game(rules, 1, 4).to_json()


@pytest.mark.parametrize("option", ["depth", "beam"])
@pytest.mark.parametrize("value, error", [(0, ValueError), (True, TypeError), (1.0, TypeError)])
def test_depth_and_beam_must_be_ints_of_at_least_1(option, value, error):
    with pytest.raises(error):
        lookahead_bot(make_state(), "a", random.Random(0), **{option: value})


def test_unknown_player_is_a_value_error():
    with pytest.raises(ValueError):
        lookahead_bot(make_state(), "zed", random.Random(0))


# --- Depth 1 is score_aware -------------------------------------------------------


@pytest.mark.parametrize("combo", COMBOS)
def test_with_depth_1_it_picks_score_awares_move(combo, monkeypatch):
    # The generated states are those of score_aware games, every seat checked.
    def both(state, player, rng):
        twin = random.Random()
        twin.setstate(rng.getstate())
        expected = score_aware_bot(state, player, twin)
        assert lookahead_bot(state, player, rng, depth=1) == expected
        assert rng.getstate() == twin.getstate()
        return expected

    monkeypatch.setattr(sim, "policy", lambda name: both)
    players = 3 + list(COMBOS).index(combo) % 2
    p = COMBOS[combo](preset(Mode.FLASH))
    simulate_game(SimRules(Mode.FLASH, players, ("score_aware",) * players, as_overrides(p)), 1, 0)


# --- Full games ---------------------------------------------------------------


def _checked(bot):
    def decide(state, player, rng):
        action = bot(state, player, rng)
        assert action in legal_actions(state, player)
        return action
    return decide


SEATS = ("lookahead", "random", "greedy", "random", "greedy")


@pytest.mark.parametrize("seed", range(10))
def test_full_games_are_legal_and_deterministic(seed, monkeypatch):
    # Seed s: rule combination s % 5 (each twice), 2 + s % 4 players,
    # Normal at 2 players and Flash at 3-5, to keep the suite fast (B4 and
    # the sample in #42's PR play longer Normal games).
    monkeypatch.setattr(sim, "policy", lambda name: _checked(POLICIES[name]))
    players = 2 + seed % 4
    mode = Mode.NORMAL if players == 2 else Mode.FLASH
    p = list(COMBOS.values())[seed % 5](preset(mode))
    rules = SimRules(mode, players, SEATS[:players], as_overrides(p))
    assert simulate_game(rules, 1, seed) == simulate_game(rules, 1, seed)


# --- Planning ahead ---------------------------------------------------------------


def _setup_state(**kwargs):
    """a acts last in round 1 and first in round 2: two moves in a row.

    A straight on WEST claims a Torrontés (1) now; one on EAST claims
    nothing, but sets up a straight on FAR_E to a Malbec (3).
    """
    state = make_state(empties=(EAST, FAR_E, WEST),
                       vineyards=[(FAR_FAR_E, MALBEC), (FAR_W, TORRONTES)], **kwargs)
    return replace(state, start_player="b")


SET_UP = PlaceCanal(STRAIGHT, EAST, 0)
CLAIM_NOW = PlaceCanal(STRAIGHT, WEST, 0)


def test_it_plays_a_canal_that_sets_up_a_bigger_claim_next_move():
    state = _setup_state(market=(STRAIGHT, STRAIGHT))
    assert set(legal_actions(state, "a")) == {SET_UP, CLAIM_NOW}
    assert picks(state, greedy_bot) == {CLAIM_NOW}
    assert picks(state) == {CLAIM_NOW}
    assert picks(state, lookahead_bot) == {SET_UP}


def test_in_the_last_round_it_does_not_plan_past_the_end():
    state = _setup_state(market=(STRAIGHT, STRAIGHT))
    last = replace(state, round=NORMAL.rounds_for(2))
    assert picks(last, lookahead_bot) == {CLAIM_NOW}


@pytest.mark.parametrize("bag", [(), (STRAIGHT,), (GATE, STRAIGHT), (STRAIGHT, GATE)])
def test_it_plans_with_the_visible_market_only(bag):
    # One straight in the market: the set-up needs a second, which only the
    # bag could give. However the bag is ordered, it claims now.
    state = replace(_setup_state(market=(STRAIGHT,)), bag=bag)
    assert picks(state, lookahead_bot) == {CLAIM_NOW}


# --- Action die --------------------------------------------------------------------

L, V = Hex(3, -1), FAR_FAR_E
FACES = (DieFace.FLOODGATE,) * 2 + (DieFace.RELEASE,) * 4
DIE_FIXED = with_overrides(
    scaled(action_die_rules(with_overrides(NORMAL, action_die=FACES)), 3),
    action_die_cost=1, grape_clusters_per_player=1,
)
"""Fixed varietals (no resow face), x3, cost 1, one grape cluster each."""


def _die_state(face=None):
    """a's dry canal on FAR_E leads to a Torrontés L (3) and a Malbec V (9).

    A straight on EAST waters both, but a claims only one: L, the lower
    hex. A floodgate on the canal's NE edge first leaves V for that claim.
    a acts twice in a row.
    """
    state = make_state(empties=(EAST, FAR_E), canals=[canal(FAR_E, "a", W, E, NE)],
                       vineyards=[(L, TORRONTES), (V, MALBEC)], market=(STRAIGHT,),
                       p=DIE_FIXED, face=face)
    return replace(state, start_player="b")


def test_it_rolls_the_die_when_a_face_sets_up_its_next_move():
    # Rolling: -1 + (2/6 * 9 + 4/6 * 3) = 4; placing now: 3. score_aware
    # sees the roll at -1 (a floodgate now changes no score).
    state = _die_state()
    assert legal_actions(state, "a") == (SET_UP, RollActionDie())
    assert picks(state) == {SET_UP}
    assert picks(state, lookahead_bot) == {RollActionDie()}


def test_handed_the_floodgate_face_it_closes_the_branch_to_the_cheap_vineyard():
    state = _die_state(DieFace.FLOODGATE)
    assert picks(state, lookahead_bot) == {PlaceFloodgate(FAR_E, NE)}


# --- Randomness ---------------------------------------------------------------------


def test_it_draws_nothing_when_one_action_is_best():
    state = _setup_state(market=(STRAIGHT, STRAIGHT))
    rng = CountingRandom(0)
    global_before = random.getstate()
    assert lookahead_bot(state, "a", rng) == SET_UP
    assert rng.draws == []
    assert random.getstate() == global_before


def test_a_root_tie_is_one_rng_choice_over_the_tied_actions_in_legal_order():
    # Either floodgate on b's canal dries b's Malbec, now and next move.
    state = make_state(empties=(EAST,), canals=[canal(EAST, "b", W, E)],
                       vineyards=[(FAR_E, MALBEC)], claims=[(FAR_E, "b")], market=(GATE,))
    tied = (PlaceFloodgate(EAST, E), PlaceFloodgate(EAST, W))
    assert legal_actions(state, "a") == tied
    for seed in range(10):
        rng = CountingRandom(seed)
        action = lookahead_bot(state, "a", rng)
        assert rng.draws == [("choice", tied)]
        assert action == random.Random(seed).choice(tied)
