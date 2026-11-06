import random

import pytest

from acequias.bots import POLICIES, greedy_bot, policy, random_bot
from acequias.game import game_over, game_rngs, play_game
from acequias.hex import Direction, Hex
from acequias.model import (
    Board,
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
from acequias.config import preset as shipped_preset
from acequias.setup import new_game
from acequias.turn import Bribe, Pass, PlaceCanal, PlaceFloodgate, legal_actions

E, NE, NW, W, SW, SE = list(Direction)
STRAIGHT, GENTLE, SHARP, Y, T, CLAW, GATE = list(PieceKind)
MALBEC, BONARDA, TORRONTES = Varietal.MALBEC, Varietal.BONARDA, Varietal.TORRONTES
BOTS = (random_bot, greedy_bot)
SEEDS = range(40)

R = Hex(0, 0)  # the river
EAST, WEST = Hex(1, 0), Hex(-1, 0)  # empty hexes on either side of the river


# --- Helpers -----------------------------------------------------------------


def make_state(empties=(EAST,), vineyards=(), canals=(), floodgates=(), claims=(),
               market=(STRAIGHT,)):
    """A two-player state: a river at ``R``, ``empties``, and ``(hex, varietal)`` vineyards."""
    tiles = [Tile(R, Terrain.RIVER)]
    tiles += [Tile(h, Terrain.EMPTY) for h in empties]
    tiles += [Tile(h, Terrain.VINEYARD, v) for h, v in vineyards]
    board = Board(tiles=tuple(tiles), canals=tuple(canals),
                  floodgates=tuple(floodgates), claims=tuple(claims))
    return GameState(board=board, players=(Player("a", 1), Player("b", 2)),
                     mode=Mode.NORMAL, round=1, start_player="a", current_player="a",
                     market=market)


def straight(hex, owner):
    return PlacedCanal(hex, STRAIGHT, 0, owner)


def decide_quietly(bot, state, player="a", seed=0):
    """The bot's action, checking that a lone candidate made no draw."""
    rng = random.Random(seed)
    return bot(state, player, rng), rng


def seeded_states(players=3, seed=7, mode=Mode.FLASH):
    """Every state reached in a seeded mixed game, with its current player."""
    state = new_game(players, seed, mode)
    bots = seating(state, "mixed")
    states = []
    recorder = {pid: _recording(bot, states) for pid, bot in bots.items()}
    play_game(state, recorder, *game_rngs(seed))
    return states


def _recording(bot, states):
    def decide(state, player, rng):
        states.append((state, player))
        return bot(state, player, rng)
    return decide


def seating(state, name):
    seats = sorted(state.players, key=lambda p: p.seat)
    if name == "mixed":
        return {p.id: (random_bot, greedy_bot)[i % 2] for i, p in enumerate(seats)}
    return {p.id: POLICIES[name] for p in seats}


# --- Interface ---------------------------------------------------------------


def test_policies_maps_names_to_bots_and_is_read_only():
    assert dict(POLICIES) == {"random": random_bot, "greedy": greedy_bot}
    with pytest.raises(TypeError):
        POLICIES["other"] = random_bot
    with pytest.raises(TypeError):
        del POLICIES["random"]


def test_policy_looks_up_a_name():
    assert policy("random") is random_bot
    assert policy("greedy") is greedy_bot


def test_unknown_policy_lists_the_valid_names():
    with pytest.raises(ValueError) as error:
        policy("smart")
    for name in POLICIES:
        assert repr(name) in str(error.value)


@pytest.mark.parametrize("name", [None, 1, b"random", random_bot])
def test_non_str_policy_name_is_a_type_error(name):
    with pytest.raises(TypeError):
        policy(name)


@pytest.mark.parametrize("bot", BOTS)
@pytest.mark.parametrize("player", ["z", "", None])
def test_unknown_player_is_a_value_error(bot, player):
    with pytest.raises(ValueError):
        bot(make_state(), player, random.Random(0))


@pytest.mark.parametrize("bot", BOTS)
def test_bots_return_a_legal_action_and_leave_the_state_and_global_random_alone(bot):
    for i, (state, player) in enumerate(seeded_states()):
        snapshot = repr(state)
        global_before = random.getstate()
        action = bot(state, player, random.Random(i))
        assert random.getstate() == global_before
        assert repr(state) == snapshot
        assert action in legal_actions(state, player)


@pytest.mark.parametrize("bot", BOTS)
def test_only_pass_legal_gives_pass(bot):
    state = make_state(market=())
    assert legal_actions(state, "a") == (Pass(),)
    assert bot(state, "a", random.Random(0)) == Pass()


# --- Random ------------------------------------------------------------------


def test_random_bot_is_one_rng_choice_over_the_legal_actions():
    for i, (state, player) in enumerate(seeded_states()):
        rng, twin = random.Random(i), random.Random(i)
        assert random_bot(state, player, rng) == twin.choice(legal_actions(state, player))
        assert rng.getstate() == twin.getstate()


def test_random_bot_picks_floodgates_bribes_and_moves():
    # One canal with a floodgate on its west edge: open edges and bribes are legal.
    state = make_state(canals=[straight(EAST, "b")], floodgates=[Floodgate(EAST, W)],
                       market=(GATE,))
    legal = legal_actions(state, "a")
    picks = {random_bot(state, "a", random.Random(s)) for s in range(200)}
    assert picks == set(legal)
    assert any(isinstance(a, Bribe) and a.to is None for a in picks)
    assert any(isinstance(a, Bribe) and a.to is not None for a in picks)
    assert any(isinstance(a, PlaceFloodgate) for a in picks)


# --- Greedy: canal placements ------------------------------------------------


def test_greedy_takes_a_malbec_over_a_bonarda():
    # A straight on EAST waters the Malbec east; a gentle curve waters the Bonarda south-east.
    state = make_state(vineyards=[(Hex(2, 0), MALBEC), (EAST.neighbor(SE), BONARDA)],
                       market=(GENTLE, STRAIGHT))
    assert PlaceCanal(GENTLE, EAST, 3) in legal_actions(state, "a")
    action, rng = decide_quietly(greedy_bot, state)
    assert action == PlaceCanal(STRAIGHT, EAST, 0)
    assert rng.getstate() == random.Random(0).getstate()


def test_greedy_sums_the_points_a_placement_claims():
    # A T branch opening W, E, NE claims the Bonarda (E) and the Torrontés (NE): 3 points.
    # A straight claims only the Bonarda: 2 points.
    state = make_state(vineyards=[(EAST.neighbor(E), BONARDA), (EAST.neighbor(NE), TORRONTES)],
                       market=(STRAIGHT, T))
    action, _ = decide_quietly(greedy_bot, state)
    assert action == PlaceCanal(T, EAST, 0)


def test_greedy_ignores_vineyards_already_claimed():
    # The Malbec east is already claimed by b, so the Bonarda south-east is the only gain.
    state = make_state(vineyards=[(Hex(2, 0), MALBEC), (EAST.neighbor(SE), BONARDA)],
                       claims=[(Hex(2, 0), "b")], market=(GENTLE, STRAIGHT))
    action, _ = decide_quietly(greedy_bot, state)
    assert action == PlaceCanal(GENTLE, EAST, 3)


def test_greedy_with_no_claim_goes_nearest_an_unclaimed_vineyard():
    # Only straights E-W on EAST and WEST are legal; the Malbec is 3 from EAST, 5 from WEST.
    state = make_state(empties=(EAST, WEST), vineyards=[(Hex(4, 0), MALBEC)])
    assert len(legal_actions(state, "a")) == 2
    for seed in SEEDS:
        action, rng = decide_quietly(greedy_bot, state, seed=seed)
        assert action == PlaceCanal(STRAIGHT, EAST, 0)
        assert rng.getstate() == random.Random(seed).getstate()


@pytest.mark.parametrize("east, west, expected", [
    (MALBEC, TORRONTES, EAST),
    (TORRONTES, MALBEC, WEST),
])
def test_greedy_at_equal_distance_prefers_the_more_valuable_vineyard(east, west, expected):
    state = make_state(empties=(EAST, WEST),
                       vineyards=[(Hex(4, 0), east), (Hex(-4, 0), west)])
    for seed in SEEDS:
        action, _ = decide_quietly(greedy_bot, state, seed=seed)
        assert action == PlaceCanal(STRAIGHT, expected, 0)


def test_greedy_breaks_a_tie_with_one_rng_choice():
    # A Malbec two steps east and two steps west: either straight claims 3 points.
    state = make_state(empties=(EAST, WEST),
                       vineyards=[(Hex(2, 0), MALBEC), (Hex(-2, 0), MALBEC)])
    tied = [PlaceCanal(STRAIGHT, WEST, 0), PlaceCanal(STRAIGHT, EAST, 0)]
    assert [a for a in legal_actions(state, "a")] == tied
    picks = set()
    for seed in SEEDS:
        first, rng = decide_quietly(greedy_bot, state, seed=seed)
        again, _ = decide_quietly(greedy_bot, state, seed=seed)
        twin = random.Random(seed)
        assert first == again == twin.choice(tied)
        assert rng.getstate() == twin.getstate()
        picks.add(first)
    assert picks == set(tied)


def test_greedy_with_every_vineyard_claimed_picks_among_all_canals():
    state = make_state(empties=(EAST, WEST), vineyards=[(Hex(2, 0), MALBEC)],
                       claims=[(Hex(2, 0), "b")], market=(STRAIGHT, CLAW))
    canals = [a for a in legal_actions(state, "a") if isinstance(a, PlaceCanal)]
    assert len(canals) > 2
    picks = set()
    for seed in range(200):
        action, _ = decide_quietly(greedy_bot, state, seed=seed)
        assert action == random.Random(seed).choice(canals)
        picks.add(action)
    assert picks == set(canals)


# --- Greedy: floodgates, bribes, pass ----------------------------------------


def test_greedy_places_a_floodgate_on_a_rival_canal():
    state = make_state(empties=(EAST, WEST),
                       canals=[straight(EAST, "a"), straight(WEST, "b")], market=(GATE,))
    assert any(a.hex == EAST for a in legal_actions(state, "a"))
    for seed in SEEDS:
        action, _ = decide_quietly(greedy_bot, state, seed=seed)
        assert isinstance(action, PlaceFloodgate)
        assert action.hex == WEST


def test_greedy_sees_a_rival_canal_across_an_edge_named_from_its_own_hex():
    # The shared edge EAST|E is listed from EAST (the smaller hex), which is a's canal.
    far = Hex(2, 0)
    state = make_state(empties=(EAST, far),
                       canals=[straight(EAST, "a"), straight(far, "b")], market=(GATE,))
    legal = legal_actions(state, "a")
    assert PlaceFloodgate(EAST, E) in legal
    assert PlaceFloodgate(far, W) not in legal
    for seed in SEEDS:
        action, _ = decide_quietly(greedy_bot, state, seed=seed)
        assert action in (PlaceFloodgate(EAST, E), PlaceFloodgate(far, E))


def test_greedy_with_no_rival_canal_picks_among_all_floodgates():
    state = make_state(canals=[straight(EAST, "a")], market=(GATE,))
    gates = legal_actions(state, "a")
    assert gates == (PlaceFloodgate(EAST, E), PlaceFloodgate(EAST, W))
    for seed in SEEDS:
        action, _ = decide_quietly(greedy_bot, state, seed=seed)
        assert action == random.Random(seed).choice(gates)


def test_greedy_prefers_any_canal_over_a_floodgate():
    state = make_state(empties=(EAST, WEST), canals=[straight(WEST, "b")],
                       market=(GATE, STRAIGHT))
    action, _ = decide_quietly(greedy_bot, state)
    assert action == PlaceCanal(STRAIGHT, EAST, 0)


def test_greedy_passes_where_random_sometimes_bribes():
    state = make_state(canals=[straight(EAST, "b")], floodgates=[Floodgate(EAST, W)],
                       market=())
    legal = legal_actions(state, "a")
    assert Pass() in legal and any(isinstance(a, Bribe) for a in legal)
    random_picks = set()
    for seed in SEEDS:
        action, rng = decide_quietly(greedy_bot, state, seed=seed)
        assert action == Pass()
        assert rng.getstate() == random.Random(seed).getstate()
        random_picks.add(type(random_bot(state, "a", random.Random(seed))))
    assert Bribe in random_picks


# --- Full games and determinism ----------------------------------------------


@pytest.mark.parametrize("seats", ["random", "greedy", "mixed"])
@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("players", [2, 3, 4, 5])
def test_full_games_finish_with_every_move_legal(players, mode, seats):
    for seed in range(5):
        state = new_game(players, seed, mode)
        final, log = play_game(state, seating(state, seats), *game_rngs(seed))
        assert game_over(final)
        rounds = (state.preset or shipped_preset(mode)).rounds_for(players)
        assert len(log) == rounds * players


@pytest.mark.parametrize("seats", ["random", "greedy", "mixed"])
def test_same_game_identity_gives_the_same_game(seats):
    def play():
        state = new_game(4, 11, Mode.NORMAL)
        return play_game(state, seating(state, seats), *game_rngs(11))

    assert play() == play()


@pytest.mark.parametrize("bot", BOTS)
def test_same_state_and_seed_give_the_same_action(bot):
    states = seeded_states(players=4, seed=3, mode=Mode.NORMAL)
    assert len(states) > 40
    for i, (state, player) in enumerate(states):
        assert bot(state, player, random.Random(i)) == bot(state, player, random.Random(i))
