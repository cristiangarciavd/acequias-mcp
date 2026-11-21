"""The score-aware bot (#67): full-score values, chance by expectation, the action die."""

import dataclasses
import random

import pytest
from mcp import Client

from acequias import sim
from acequias.bots import POLICIES, greedy_bot, policy, score_aware_bot
from acequias.config import (
    action_die_rules,
    preset,
    roulette_rules,
    scaled,
    with_overrides,
)
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
from acequias.sim import SimRules, simulate_game
from acequias.turn import (
    Bribe,
    DeclineFace,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    Release,
    Resow,
    RollActionDie,
    legal_actions,
)
from server.app import app

E, NE, NW, W, SW, SE = list(Direction)
STRAIGHT, GATE, T = PieceKind.STRAIGHT, PieceKind.FLOODGATE, PieceKind.T_BRANCH
MALBEC, BONARDA, TORRONTES = Varietal.MALBEC, Varietal.BONARDA, Varietal.TORRONTES
SEEDS = range(20)

R = Hex(0, 0)  # the river
EAST, WEST, SOUTH, NORTH = Hex(1, 0), Hex(-1, 0), Hex(0, 1), Hex(0, -1)
FAR_E, FAR_W, FAR_S, FAR_N = Hex(2, 0), Hex(-2, 0), Hex(0, 2), Hex(0, -2)

NORMAL = preset(Mode.NORMAL)
DIE = action_die_rules(roulette_rules(NORMAL))
# Roulette mean under DIE: (2 * 3 + 12 * 2) / 14 = 15/7.


# --- Helpers -----------------------------------------------------------------


def canal(hex, owner, *directions):
    """A canal on ``hex`` opening exactly ``directions``, whatever shape that takes."""
    wanted = frozenset(directions)
    for kind in PieceKind:
        if kind.is_canal:
            for rotation in range(6):
                if kind.edges(rotation) == wanted:
                    return PlacedCanal(hex, kind, rotation, owner)
    raise AssertionError(f"no canal shape opens {directions}")


def make_state(empties=(EAST, WEST), vineyards=(), canals=(), floodgates=(), claims=(),
               plantings=(), market=(STRAIGHT,), p=NORMAL, face=None):
    """A two-player state, a to play: a river at ``R``, ``empties``, ``(hex, varietal)`` vineyards.

    Under roulette rules pass varietal ``None`` and plant with ``plantings``.
    """
    tiles = [Tile(R, Terrain.RIVER)]
    tiles += [Tile(h, Terrain.EMPTY) for h in empties]
    tiles += [Tile(h, Terrain.VINEYARD, v) for h, v in vineyards]
    board = Board(tiles=tuple(tiles), canals=tuple(canals), floodgates=tuple(floodgates),
                  claims=tuple(claims), plantings=tuple(plantings))
    return GameState(board=board, players=(Player("a", 1), Player("b", 2)), mode=p.mode,
                     round=1, start_player="a", current_player="a", market=market, preset=p,
                     pending_face=face)


def picks(state, bot=score_aware_bot, seeds=SEEDS):
    """Every action ``bot`` picks for a over ``seeds``, checking it repeats per seed."""
    seen = set()
    for seed in seeds:
        first = bot(state, "a", random.Random(seed))
        assert first == bot(state, "a", random.Random(seed))
        assert first in legal_actions(state, "a")
        seen.add(first)
    return seen


class CountingRandom(random.Random):
    """A ``random.Random`` that records each ``choice`` and every other draw."""

    def __init__(self, seed):
        self.draws = []
        super().__init__(seed)

    def choice(self, seq):
        self.draws.append(("choice", tuple(seq)))
        twin = random.Random()
        twin.setstate(self.getstate())
        result = twin.choice(seq)
        self.setstate(twin.getstate())
        return result

    def random(self):
        self.draws.append("random")
        return super().random()

    def getrandbits(self, k):
        self.draws.append("getrandbits")
        return super().getrandbits(k)


def as_overrides(p):
    return {f.name: getattr(p, f.name) for f in dataclasses.fields(p) if f.name != "mode"}


# --- Interface ---------------------------------------------------------------


def test_policy_looks_up_the_score_aware_bot():
    assert policy("score_aware") is score_aware_bot
    assert POLICIES["score_aware"] is score_aware_bot


def test_simulate_game_accepts_score_aware_seats():
    rules = SimRules(Mode.FLASH, 2, ("score_aware", "greedy"))
    result = simulate_game(rules, 2, 3)
    assert set(result.win_rate_by_policy) == {"score_aware", "greedy"}


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_the_simulate_game_tool_accepts_score_aware_seats():
    policies = ["score_aware", "random"]
    async with Client(app) as client:
        result = await client.call_tool(
            "simulate_game",
            {"mode": "flash", "players": 2, "games": 1, "seed": 4, "policies": policies},
        )
    assert not result.is_error
    rules = SimRules(Mode.FLASH, 2, tuple(policies))
    assert result.structured_content == simulate_game(rules, 1, 4).to_json()


def test_unknown_player_is_a_value_error():
    with pytest.raises(ValueError):
        score_aware_bot(make_state(), "zed", random.Random(0))


def test_only_pass_legal_gives_pass_with_no_draw():
    state = make_state(empties=(), market=())
    rng = CountingRandom(0)
    assert score_aware_bot(state, "a", rng) == Pass()
    assert rng.draws == []


# --- Full games ---------------------------------------------------------------


def _clusters(p):
    return with_overrides(roulette_rules(p), grape_clusters_per_player=2,
                          vineyards_per_player=4, hexes_per_player=20)


COMBOS = {
    "shipped": lambda p: p,
    "roulette": roulette_rules,
    "clusters": _clusters,
    "die": lambda p: action_die_rules(roulette_rules(p)),
    "die_scaled": lambda p: scaled(action_die_rules(roulette_rules(p)), 3),
}
SEATS = ("score_aware", "random", "greedy", "random", "greedy")


def _checked(bot):
    def decide(state, player, rng):
        action = bot(state, player, rng)
        assert action in legal_actions(state, player)
        return action
    return decide


@pytest.mark.parametrize("combo", COMBOS)
def test_full_games_are_legal_and_deterministic(combo, monkeypatch):
    # Seed s plays 2 + s % 4 players, Normal for seeds 0-9 and Flash for 10-19.
    monkeypatch.setattr(sim, "policy", lambda name: _checked(POLICIES[name]))
    for seed in SEEDS:
        mode = Mode.NORMAL if seed < 10 else Mode.FLASH
        players = 2 + seed % 4
        p = COMBOS[combo](preset(mode))
        rules = SimRules(mode, players, SEATS[:players], as_overrides(p))
        assert simulate_game(rules, 1, seed) == simulate_game(rules, 1, seed)


# --- Water rights and the bodega ---------------------------------------------


def test_it_avoids_a_route_that_pays_water_rights_where_greedy_takes_it():
    # A straight on FAR_E extends b's canal to a Malbec (3, paying b 1: worth
    # 3 - 1 - 1 = 1); a straight on WEST reaches a Bonarda (2) on its own.
    state = make_state(empties=(EAST, FAR_E, WEST), canals=[canal(EAST, "b", W, E)],
                       vineyards=[(Hex(3, 0), MALBEC), (FAR_W, BONARDA)])
    via_b = PlaceCanal(STRAIGHT, FAR_E, 0)
    own = PlaceCanal(STRAIGHT, WEST, 0)
    assert {via_b, own} <= set(legal_actions(state, "a"))
    assert picks(state, greedy_bot) == {via_b}
    assert picks(state) == {own}


def test_it_completes_the_bodega_over_more_vineyard_points():
    # a holds a watered Malbec and Bonarda. A Torrontés (1) completes the
    # three varietals (+2 bodega); another Bonarda is worth 2 but no bonus.
    state = make_state(
        empties=(EAST, WEST, SOUTH, NORTH),
        canals=[canal(SOUTH, "a", NW, SE), canal(NORTH, "a", SE, NW)],
        vineyards=[(FAR_S, MALBEC), (FAR_N, BONARDA), (FAR_E, BONARDA), (FAR_W, TORRONTES)],
        claims=[(FAR_S, "a"), (FAR_N, "a")],
    )
    assert picks(state, greedy_bot) == {PlaceCanal(STRAIGHT, EAST, 0)}
    assert picks(state) == {PlaceCanal(STRAIGHT, WEST, 0)}


# --- Bribes ------------------------------------------------------------------


def test_it_skips_a_bribe_whose_expected_debt_exceeds_the_swing():
    # Removing the floodgate waters a's Malbec again: 3 < 3.5.
    state = make_state(empties=(EAST,), canals=[canal(EAST, "a", W, E)],
                       floodgates=[Floodgate(EAST, W)], vineyards=[(FAR_E, MALBEC)],
                       claims=[(FAR_E, "a")], market=())
    assert Bribe(EAST, W) in legal_actions(state, "a")
    assert picks(state) == {Pass()}


def test_it_takes_a_bribe_that_beats_the_expected_debt():
    # Removing the floodgate waters a's Malbec and Torrontés: 4 > 3.5.
    state = make_state(empties=(EAST,), canals=[canal(EAST, "a", W, E, NE)],
                       floodgates=[Floodgate(EAST, W)],
                       vineyards=[(FAR_E, MALBEC), (EAST.neighbor(NE), TORRONTES)],
                       claims=[(FAR_E, "a"), (EAST.neighbor(NE), "a")], market=())
    assert picks(state) == {Bribe(EAST, W)}


# --- Action die --------------------------------------------------------------


def _gated_own_bonarda(p, face=None):
    """a's canal on EAST, closed at the river, feeds a's Bonarda; nothing to place."""
    return make_state(empties=(EAST,), canals=[canal(EAST, "a", W, E)],
                      floodgates=[Floodgate(EAST, W)], vineyards=[(FAR_E, None)],
                      claims=[(FAR_E, "a")], plantings=[(FAR_E, BONARDA)], market=(),
                      p=p, face=face)


@pytest.mark.parametrize("cost, rolls", [(2, True), (4, False), (5, False)])
def test_it_rolls_only_when_the_faces_mean_best_use_beats_the_cost(cost, rolls):
    # Scaled x3: Release waters a's Bonarda (9) on 2 faces of 6, so the mean
    # best use is 3 (floodgate and resow faces have no use worth more than 0).
    p = with_overrides(scaled(DIE, 3), action_die_cost=cost)
    state = _gated_own_bonarda(p)
    assert legal_actions(state, "a") == (RollActionDie(), Pass())
    assert picks(state) == {RollActionDie() if rolls else Pass()}


def test_the_floodgate_face_dries_the_rival_canal_that_costs_the_rival_most():
    # b's Bonarda (3) is fed through EAST, b's Malbec (2) through WEST.
    state = make_state(canals=[canal(EAST, "b", W, E), canal(WEST, "b", E, W)],
                       vineyards=[(FAR_E, None), (FAR_W, None)],
                       claims=[(FAR_E, "b"), (FAR_W, "b")],
                       plantings=[(FAR_E, BONARDA), (FAR_W, MALBEC)],
                       market=(), p=DIE, face=DieFace.FLOODGATE)
    on_east = {a for a in legal_actions(state, "a") if isinstance(a, PlaceFloodgate)
               and EAST in (a.hex, a.hex.neighbor(a.direction))}
    assert len(on_east) == 2
    assert picks(state) == on_east


def test_the_release_face_frees_its_own_vineyard():
    state = _gated_own_bonarda(DIE, DieFace.RELEASE)
    assert picks(state) == {Release(EAST, W)}


def test_the_resow_face_resows_the_rivals_high_value_vineyard():
    # Resowing b's Bonarda (3) to the mean 15/7 gains 6/7; b's Malbec (2) would lose.
    state = make_state(canals=[canal(EAST, "b", W, E), canal(WEST, "b", E, W)],
                       vineyards=[(FAR_E, None), (FAR_W, None)],
                       claims=[(FAR_E, "b"), (FAR_W, "b")],
                       plantings=[(FAR_E, BONARDA), (FAR_W, MALBEC)],
                       market=(), p=DIE, face=DieFace.RESOW)
    assert picks(state) == {Resow(FAR_E)}


def test_it_declines_a_face_whose_every_use_is_worth_less_than_0():
    # The only resow is a's own Bonarda (3), worth the mean 15/7 after.
    state = make_state(empties=(EAST,), canals=[canal(EAST, "a", W, E)],
                       vineyards=[(FAR_E, None)], claims=[(FAR_E, "a")],
                       plantings=[(FAR_E, BONARDA)], market=(), p=DIE, face=DieFace.RESOW)
    assert legal_actions(state, "a") == (Resow(FAR_E), DeclineFace())
    assert picks(state) == {DeclineFace()}


def test_it_declines_an_unusable_face_with_no_draw():
    state = make_state(market=(), p=DIE, face=DieFace.RELEASE)
    assert legal_actions(state, "a") == (DeclineFace(),)
    rng = CountingRandom(0)
    assert score_aware_bot(state, "a", rng) == DeclineFace()
    assert rng.draws == []


# --- Cluster cap ---------------------------------------------------------------


@pytest.mark.parametrize("cap, expected", [(None, "canal"), (1, "floodgate")])
def test_with_no_clusters_left_it_does_not_count_a_vineyard_it_cannot_claim(cap, expected):
    # A straight on EAST waters an unclaimed Malbec (3); a floodgate on b's
    # canal on WEST dries b's Torrontés (1). a holds one claim already.
    p = with_overrides(NORMAL, grape_clusters_per_player=cap)
    state = make_state(
        empties=(EAST, WEST, SOUTH),
        canals=[canal(WEST, "b", E, W), canal(SOUTH, "a", NW, SE)],
        vineyards=[(FAR_E, MALBEC), (FAR_W, TORRONTES), (FAR_S, BONARDA)],
        claims=[(FAR_W, "b"), (FAR_S, "a")],
        market=(STRAIGHT, GATE), p=p,
    )
    chosen = picks(state)
    if expected == "canal":
        assert chosen == {PlaceCanal(STRAIGHT, EAST, 0)}
    else:
        assert chosen <= {PlaceFloodgate(WEST, E), PlaceFloodgate(WEST, W)}
        assert all(isinstance(a, PlaceFloodgate) for a in chosen)


# --- Randomness ----------------------------------------------------------------


def test_it_draws_nothing_when_one_action_is_best():
    state = make_state(empties=(EAST,), canals=[canal(EAST, "a", W, E, NE)],
                       floodgates=[Floodgate(EAST, W)],
                       vineyards=[(FAR_E, MALBEC), (EAST.neighbor(NE), TORRONTES)],
                       claims=[(FAR_E, "a"), (EAST.neighbor(NE), "a")], market=())
    rng = CountingRandom(0)
    global_before = random.getstate()
    assert score_aware_bot(state, "a", rng) == Bribe(EAST, W)
    assert rng.draws == []
    assert random.getstate() == global_before


def test_a_tie_is_one_rng_choice_over_the_tied_actions_in_legal_order():
    # Either floodgate on b's canal dries b's Malbec.
    state = make_state(empties=(EAST,), canals=[canal(EAST, "b", W, E)],
                       vineyards=[(FAR_E, MALBEC)], claims=[(FAR_E, "b")], market=(GATE,))
    tied = (PlaceFloodgate(EAST, E), PlaceFloodgate(EAST, W))
    assert legal_actions(state, "a") == tied
    for seed in SEEDS:
        rng = CountingRandom(seed)
        action = score_aware_bot(state, "a", rng)
        assert rng.draws == [("choice", tied)]
        assert action == random.Random(seed).choice(tied)
