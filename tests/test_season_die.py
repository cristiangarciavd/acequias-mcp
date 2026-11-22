"""The constructive action die and the season roll (#130): opt-in Rules v2 options.

Covers the new faces in the preset and the model, the season faces in
``turn.apply`` (with their rng draws), the drought clamp in scoring, the
season roll in the round loop (timing and who rolls), the bots, the
simulation statistics, and the MCP JSON.
"""

import random
from dataclasses import replace

import pytest
from mcp import Client

from acequias.config import (
    ACTION_DIE_FACES,
    CONSTRUCTIVE_DIE_FACES,
    action_die_rules,
    common_vineyard_points,
    preset,
    roulette_rules,
    scaled,
    with_overrides,
)
from acequias.game import act, game_rngs, play_game, replay, turn_order
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
    SeasonRoll,
    Terrain,
    Tile,
    Varietal,
)
from acequias.bots import POLICIES
from acequias.scoring import calculate_score
from acequias.setup import new_game
from acequias.sim import SimRules, play_one, simulate_game
from acequias.turn import (
    DeclineFace,
    IllegalAction,
    PlaceCanal,
    Release,
    RollActionDie,
    apply,
    legal_actions,
)
from server.app import app

V = Varietal
DIE = action_die_rules(roulette_rules(preset(Mode.NORMAL)))
P = with_overrides(DIE, action_die=CONSTRUCTIVE_DIE_FACES)
GOOD = with_overrides(P, action_die=(DieFace.GOOD_SEASON,))
DRY = with_overrides(P, action_die=(DieFace.DROUGHT,))

R, H1 = Hex(0, 0), Hex(1, 0)
VA, VB = Hex(2, -1), Hex(2, 0)  # NE and E of H1
STRAIGHT = PlacedCanal(H1, PieceKind.STRAIGHT, 0, "b")  # opens W (river) and E (VB)


def board(**kw):
    tiles = (
        Tile(R, Terrain.RIVER),
        Tile(H1, Terrain.EMPTY),
        Tile(VA, Terrain.VINEYARD),
        Tile(VB, Terrain.VINEYARD),
    )
    return Board(tiles=tiles, **kw)


def state(b=None, p=P, players=None, **kw):
    return GameState(
        board=b if b is not None else board(),
        players=players or (Player("a", 1), Player("b", 2)),
        mode=p.mode,
        round=1,
        start_player="a",
        current_player="a",
        market=(PieceKind.STRAIGHT,),
        bag=(PieceKind.CLAW,),
        preset=p,
        **kw,
    )


# --- Preset --------------------------------------------------------------------


def test_constructive_die_faces_and_the_default_die_is_unchanged():
    assert CONSTRUCTIVE_DIE_FACES == (
        DieFace.FLOODGATE, DieFace.RELEASE, DieFace.RESOW, DieFace.RESOW,
        DieFace.GOOD_SEASON, DieFace.DROUGHT,
    )
    for mode in Mode:
        assert preset(mode).action_die == ACTION_DIE_FACES
        assert action_die_rules(roulette_rules(preset(mode))).action_die == ACTION_DIE_FACES
        p = preset(mode)
        assert (p.season_points, p.drought_points, p.season_roll_every) == (None, None, None)
    assert [f.is_season for f in DieFace] == [False, False, False, True, True]


def test_season_points_default_to_a_common_plot_and_scale():
    assert common_vineyard_points(P) == 2  # 12 of the 14 sectors score 2
    assert (P.season_gain, P.drought_loss) == (2, 1)
    assert (scaled(P, 3).season_gain, scaled(P, 3).drought_loss) == (6, 3)
    # Fixed rules: Malbec 3, Bonarda 2, Torrontes 1 tie once each, so the lowest.
    assert common_vineyard_points(preset(Mode.NORMAL)) == 1
    assert preset(Mode.NORMAL).drought_loss == 1  # half of 1 rounds to 0: at least 1


def test_explicit_season_points_are_used_and_scaled():
    p = with_overrides(P, season_points=5, drought_points=4)
    assert (p.season_gain, p.drought_loss) == (5, 4)
    assert (scaled(p, 2).season_gain, scaled(p, 2).drought_loss) == (10, 8)
    assert with_overrides(P, season_points=5).drought_loss == 2


@pytest.mark.parametrize("name", ["season_points", "drought_points", "season_roll_every"])
def test_season_values_are_ints_of_at_least_1(name):
    with pytest.raises(ValueError):
        with_overrides(P, **{name: 0})
    with pytest.raises(TypeError):
        with_overrides(P, **{name: 1.5})


def test_season_roll_needs_action_die_rules():
    with pytest.raises(ValueError, match="action_die"):
        with_overrides(preset(Mode.NORMAL), season_roll_every=2)
    assert with_overrides(P, season_roll_every=2).is_season_round(4)
    assert not with_overrides(P, season_roll_every=2).is_season_round(3)
    assert not P.is_season_round(2)


# --- Model ---------------------------------------------------------------------


def test_a_season_face_is_never_pending():
    with pytest.raises(ValueError, match="never pending"):
        state(pending_face=DieFace.DROUGHT)


def test_season_roll_state_is_checked():
    every = with_overrides(P, season_roll_every=2)
    with pytest.raises(ValueError, match="season_roll_every"):
        state(season_roll=SeasonRoll.DUE)
    with pytest.raises(ValueError, match="ROLLED"):
        state(p=every, season_roll=SeasonRoll.ROLLED)
    with pytest.raises(ValueError, match="ROLLED"):
        state(p=every, season_roll=SeasonRoll.DUE, pending_face=DieFace.RELEASE)
    assert state(p=every, season_roll=SeasonRoll.ROLLED, pending_face=DieFace.RELEASE)


def test_player_season_and_drought_are_not_negative():
    with pytest.raises(ValueError):
        Player("a", 1, season=-1)
    with pytest.raises(ValueError):
        Player("a", 1, drought=-1)


# --- Faces -----------------------------------------------------------------------


def test_good_season_gives_every_player_the_gain_with_one_draw():
    rng, ref = random.Random(3), random.Random(3)
    ref.choice(GOOD.action_die)
    after = apply(state(p=GOOD), "a", RollActionDie(), rng)
    assert rng.getstate() == ref.getstate()
    assert after.pending_face is None
    assert [(p.season, p.drought) for p in after.players] == [(2, 0), (2, 0)]
    assert after.player("a").debt == GOOD.action_die_cost
    assert after.player("b").debt == 0
    assert legal_actions(after, "a")[-1] == RollActionDie()  # no face to resolve


def test_drought_adds_the_loss_to_every_player():
    after = apply(state(p=DRY), "b", RollActionDie(), random.Random(1))
    assert [(p.season, p.drought) for p in after.players] == [(0, 1), (0, 1)]
    assert after.player("b").debt == DRY.action_die_cost


@pytest.mark.parametrize("face", [DieFace.GOOD_SEASON, DieFace.DROUGHT])
def test_a_voluntary_season_face_ends_the_turn(face):
    p = with_overrides(P, action_die=(face,))
    after = act(state(p=p), "a", RollActionDie(), random.Random(1))
    assert after.current_player == "b"
    assert after.pending_face is None


def test_personal_faces_can_be_declined_and_an_unusable_one_does_nothing():
    rolled = state(pending_face=DieFace.RELEASE)  # no floodgate on the board
    assert legal_actions(rolled, "a") == (DeclineFace(),)
    after = act(rolled, "a", DeclineFace(), random.Random(1))
    assert after.board == rolled.board and after.players == rolled.players
    assert after.current_player == "b"
    gated = state(board(canals=(STRAIGHT,), floodgates=(Floodgate(H1, Direction.E),)),
                  pending_face=DieFace.RELEASE)
    assert Release(H1, Direction.E) in legal_actions(gated, "a")
    assert apply(gated, "a", DeclineFace(), random.Random(1)).board == gated.board


def test_constructive_die_rolls_every_face():
    rng = random.Random(0)
    seen = set()
    for _ in range(200):
        after = apply(state(), "a", RollActionDie(), rng)
        if after.pending_face is not None:
            seen.add(after.pending_face)
        elif after.player("a").season:
            seen.add(DieFace.GOOD_SEASON)
        else:
            assert after.player("a").drought
            seen.add(DieFace.DROUGHT)
    assert seen == set(DieFace)


# --- Scoring ---------------------------------------------------------------------


def _claimed_watered(p=P):
    """b owns the canal to VB, a claimed VB with Malbec: a scores 2 - 1 right = 1."""
    return board(canals=(STRAIGHT,), claims=((VB, "a"),), plantings=((VB, V.MALBEC),))


def test_score_adds_season_and_takes_drought():
    players = (Player("a", 1, season=4, drought=2), Player("b", 2, season=4, drought=2))
    scores = calculate_score(state(_claimed_watered(), players=players))
    a, b = scores["a"], scores["b"]
    assert (a.vineyards, a.rights_paid, a.season, a.drought, a.total) == (2, 1, 4, 2, 3)
    assert (b.rights_collected, b.season, b.drought, b.total) == (1, 4, 2, 3)


def test_drought_never_takes_a_score_below_zero():
    players = (Player("a", 1, drought=5), Player("b", 2, drought=1))
    scores = calculate_score(state(_claimed_watered(), players=players))
    assert (scores["a"].drought, scores["a"].total) == (1, 0)  # had 1 point, loses 1
    assert (scores["b"].drought, scores["b"].total) == (1, 0)  # had exactly 1
    nothing = (Player("a", 1, drought=3), Player("b", 2, debt=2, drought=3))
    scores = calculate_score(state(players=nothing))
    assert (scores["a"].drought, scores["a"].total) == (0, 0)  # at 0: loses nothing
    assert (scores["b"].drought, scores["b"].total) == (0, -2)  # debt below 0: loses nothing


# --- Season roll -------------------------------------------------------------------


EVERY2 = with_overrides(P, season_roll_every=2)


def _advance_to(s, round, rng):
    """Play first legal actions (declining faces) until ``round`` starts."""
    while s.round < round:
        player = s.current_player
        s = act(s, player, legal_actions(s, player)[0], rng)
    return s


def test_season_roll_comes_at_the_start_of_every_xth_round():
    rng = random.Random(0)
    s = new_game(2, 1, Mode.NORMAL, preset=EVERY2)
    assert s.season_roll is None
    s = _advance_to(s, 2, rng)
    assert s.season_roll is SeasonRoll.DUE
    assert s.current_player == s.start_player
    s = _advance_to(s, 3, rng)
    assert s.season_roll is None
    s = _advance_to(s, 4, rng)
    assert s.season_roll is SeasonRoll.DUE
    assert new_game(2, 1, Mode.NORMAL, preset=with_overrides(P, season_roll_every=1)).season_roll \
        is SeasonRoll.DUE


def test_the_season_roll_is_the_only_action_and_is_free():
    s = state(p=EVERY2, season_roll=SeasonRoll.DUE, players=(Player("a", 1, 3), Player("b", 2)))
    assert legal_actions(s, "a") == (RollActionDie(),)
    assert legal_actions(s, "b") == ()
    with pytest.raises(IllegalAction, match="season roll"):
        apply(s, "a", PlaceCanal(PieceKind.STRAIGHT, H1, 0), random.Random(1))
    with pytest.raises(IllegalAction, match="season roll"):
        apply(s, "b", RollActionDie(), random.Random(1))
    for seed in range(10):
        rng, ref = random.Random(seed), random.Random(seed)
        face = ref.choice(EVERY2.action_die)
        after = act(s, "a", RollActionDie(), rng)
        assert rng.getstate() == ref.getstate()
        assert after.player("a").debt == 3
        assert after.current_player == "a"  # the roll spends no turn
        if face.is_season:
            assert after.pending_face is None and after.season_roll is None
        else:
            assert after.pending_face is face and after.season_roll is SeasonRoll.ROLLED


@pytest.mark.parametrize("face", [DieFace.GOOD_SEASON, DieFace.DROUGHT])
def test_a_season_face_on_the_season_roll_keeps_the_turn(face):
    p = with_overrides(P, action_die=(face,), season_roll_every=2)
    s = state(p=p, season_roll=SeasonRoll.DUE)
    after = act(s, "a", RollActionDie(), random.Random(1))
    assert after.current_player == "a" and after.season_roll is None
    assert all(pl.debt == 0 for pl in after.players)
    assert all((pl.season, pl.drought) != (0, 0) for pl in after.players)
    assert RollActionDie() in legal_actions(after, "a")  # their own turn now


def test_a_declined_or_unusable_season_roll_face_keeps_the_turn():
    p = with_overrides(P, action_die=(DieFace.RELEASE,), season_roll_every=2)
    s = state(p=p, season_roll=SeasonRoll.DUE)
    rolled = act(s, "a", RollActionDie(), random.Random(1))
    assert legal_actions(rolled, "a") == (DeclineFace(),)  # no floodgate: unusable
    after = act(rolled, "a", DeclineFace(), random.Random(1))
    assert after.current_player == "a" and after.season_roll is None
    assert after.board == s.board and after.players == s.players
    moved = act(after, "a", PlaceCanal(PieceKind.STRAIGHT, H1, 0), random.Random(1))
    assert moved.current_player == "b"


@pytest.mark.parametrize("players", [2, 3])
def test_the_start_player_rotates_who_makes_the_season_roll(players):
    p = with_overrides(P, season_roll_every=1)
    start = new_game(players, 7, Mode.NORMAL, preset=p)
    dice, bots = game_rngs(7)
    final, log = play_game(start, {pl.id: POLICIES["random"] for pl in start.players}, dice, bots)
    rounds = p.rounds_for(players)
    rollers = []
    for r in range(1, rounds + 1):
        first = next(rec for rec in log if rec.round == r)
        assert isinstance(first.action, RollActionDie)
        assert first.player == turn_order(start, r)[0]
        assert first.face is not None
        rollers.append(first.player)
    seats = [pl.id for pl in start.players]
    k = seats.index(rollers[0])
    assert rollers == [seats[(k + i) % players] for i in range(rounds)]
    assert replay(start, log, game_rngs(7)[0]) == final


def test_season_faces_are_logged():
    p = with_overrides(P, action_die=(DieFace.GOOD_SEASON, DieFace.DROUGHT), season_roll_every=1)
    record = play_one(SimRules(Mode.FLASH, 2, ("greedy", "greedy"), _overrides(p)), 3)
    faces = {r.face for r in record.log if isinstance(r.action, RollActionDie)}
    assert faces == {DieFace.GOOD_SEASON, DieFace.DROUGHT}


# --- Bots and simulation ---------------------------------------------------------------


def _overrides(p, **kw):
    return {
        "varietal_rules": p.varietal_rules,
        "varietal_points": p.varietal_points,
        "bribe_rules": p.bribe_rules,
        "bag_mix": p.bag_mix,
        "action_die": p.action_die,
        "season_roll_every": p.season_roll_every,
        **kw,
    }


@pytest.mark.parametrize("policy", ["random", "greedy", "saboteur", "score_aware", "lookahead"])
def test_bots_finish_constructive_die_games_with_season_rolls(policy):
    rules = SimRules(Mode.FLASH, 3, (policy,) * 3, _overrides(EVERY2, action_die_cost=1))
    record = play_one(rules, 2)
    assert calculate_score(record.final) == record.scores
    rolls = [r for r in record.log if isinstance(r.action, RollActionDie)]
    assert len(rolls) >= preset(Mode.FLASH).rounds_for(3) // 2  # every season roll was made


def test_score_aware_values_a_season_face_at_zero():
    from acequias.bots import _Evaluator

    only_seasons = with_overrides(P, action_die=(DieFace.GOOD_SEASON, DieFace.DROUGHT),
                                  action_die_cost=0)
    assert _Evaluator(state(p=only_seasons), "a").roll_value() == 0
    due = state(p=with_overrides(only_seasons, action_die_cost=3, season_roll_every=2),
                season_roll=SeasonRoll.DUE)
    assert _Evaluator(due, "a").roll_value() == 0  # the season roll is free


def test_simulation_counts_season_faces_and_rolls():
    rules = SimRules(Mode.FLASH, 2, ("random", "random"), _overrides(EVERY2))
    result = simulate_game(rules, 6, 5)
    faces = result.die_faces_per_game
    assert set(faces) == {f.value for f in DieFace}
    assert result.actions_per_game["die"] == pytest.approx(sum(faces.values()))
    assert faces["good_season"] + faces["drought"] > 0
    assert set(result.score_terms) >= {"season", "drought"}
    assert sum(result.actions_per_game.values()) == pytest.approx(result.turns_per_game)


# --- MCP ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _hex(q, r, terrain, varietal=None):
    return {"q": q, "r": r, "terrain": terrain, "varietal": varietal}


@pytest.mark.anyio
async def test_calculate_score_reads_and_shows_season_and_drought():
    arguments = {
        "mode": "normal",
        "hexes": [_hex(0, 0, "river"), _hex(1, 0, "empty"), _hex(2, 0, "vineyard", "malbec")],
        "canals": [{"q": 1, "r": 0, "kind": "straight", "rotation": 0, "owner": "a"}],
        "floodgates": [],
        "claims": [{"q": 2, "r": 0, "player": "a"}],
        "players": [{"id": "a", "debt": 0, "season": 2, "drought": 1},
                    {"id": "b", "debt": 0, "drought": 4}],
    }
    async with Client(app) as client:
        result = await client.call_tool("calculate_score", arguments)
    assert not result.is_error
    a, b = result.structured_content["scores"]
    assert (a["vineyards"], a["season"], a["drought"], a["total"]) == (3, 2, 1, 4)
    assert (b["season"], b["drought"], b["total"]) == (0, 0, 0)


@pytest.mark.anyio
async def test_simulate_game_takes_the_season_overrides():
    overrides = {
        "varietal_rules": "roulette",
        "varietal_points": {
            "malbec": 2, "cabernet_sauvignon": 2, "cabernet_franc": 3, "syrah": 2,
            "merlot": 2, "bonarda": 3, "torrontes": 2, "chardonnay": 2,
        },
        "bribe_rules": "action_die",
        "action_die": ["floodgate", "release", "resow", "resow", "good_season", "drought"],
        "action_die_cost": 1,
        "season_points": 3,
        "drought_points": 2,
        "season_roll_every": 2,
        "bag_mix": {
            "straight": 44, "gentle_curve": 22, "sharp_curve": 17, "symmetric_y": 6,
            "t_branch": 6, "claw": 5, "floodgate": 0,
        },
    }
    async with Client(app) as client:
        result = await client.call_tool("simulate_game", {
            "mode": "flash", "players": 2, "games": 2, "seed": 4,
            "policies": ["random", "random"], "overrides": overrides,
        })
    assert not result.is_error
    data = result.structured_content
    for key in ("action_die", "season_points", "drought_points", "season_roll_every"):
        assert data["preset"][key] == overrides[key]
    assert {"season", "drought"} <= set(data["score_terms"])
