import ast
import dataclasses
import random
from collections import Counter
from pathlib import Path

import pytest

from acequias.config import preset as shipped_preset
from acequias.config import with_overrides
from acequias.game import (
    TurnRecord,
    act,
    game_over,
    game_rngs,
    play_game,
    replay,
    turn_order,
)
from acequias.model import GameState, Mode, Player
from acequias.setup import new_game
from acequias.turn import Bribe, IllegalAction, Pass, legal_actions

PLAYER_COUNTS = (2, 3, 4, 5)


# --- Helpers -----------------------------------------------------------------


def first_bot(state, player, rng):
    """Takes the first legal action; draws nothing."""
    return legal_actions(state, player)[0]


def random_bot(state, player, rng):
    """Takes a random legal action (bribes included, so dice get rolled)."""
    return rng.choice(legal_actions(state, player))


def pass_bot(state, player, rng):
    return Pass()


def bots_for(state, bot):
    return {p.id: bot for p in state.players}


def game(players=2, seed=1, mode=Mode.NORMAL, **kw):
    return new_game(players, seed, mode, **kw)


def rounds_of(state):
    return (state.preset or shipped_preset(state.mode)).rounds_for(len(state.players))


def with_start(state, seat):
    """``state`` with round 1 started by the player in ``seat``."""
    pid = next(p.id for p in state.players if p.seat == seat)
    return dataclasses.replace(state, start_player=pid, current_player=pid)


def pass_only(state):
    """``state`` with nothing to place, so every player can only pass."""
    return dataclasses.replace(state, market=(), bag=())


def play_to_end(state, rng=None):
    rng = rng or random.Random(0)
    states = [state]
    while not game_over(state):
        state = act(state, state.current_player, first_bot(state, state.current_player, rng), rng)
        states.append(state)
    return states


# --- Round count -------------------------------------------------------------


def test_preset_round_count_sets_the_length_of_a_game():
    for count in (1, 3, 7):
        p = with_overrides(shipped_preset(Mode.NORMAL), rounds={n: count for n in PLAYER_COUNTS})
        state = game(3, preset=p)
        final, log = play_game(state, bots_for(state, first_bot), random.Random(0), random.Random(0))
        assert len(log) == count * 3
        assert final.round == count + 1
        assert final.preset is p


def test_round_count_can_differ_by_player_count():
    p = with_overrides(shipped_preset(Mode.FLASH), rounds={2: 2, 3: 4, 4: 5, 5: 6})
    for n in PLAYER_COUNTS:
        state = pass_only(game(n, mode=Mode.FLASH, preset=p))
        final, log = play_game(state, bots_for(state, pass_bot), random.Random(0), random.Random(0))
        assert len(log) == p.rounds[n] * n


def test_a_state_without_preset_uses_the_shipped_round_count():
    for mode in Mode:
        state = dataclasses.replace(pass_only(game(2, mode=mode)), preset=None)
        final, log = play_game(state, bots_for(state, pass_bot), random.Random(0), random.Random(0))
        assert len(log) == shipped_preset(mode).rounds_for(2) * 2
        assert final.preset is None


# --- Turn order --------------------------------------------------------------


def test_five_players_starting_at_seat_four():
    state = with_start(game(5), 4)
    assert turn_order(state, 1) == ("p4", "p5", "p1", "p2", "p3")
    assert turn_order(state, 2) == ("p5", "p1", "p2", "p3", "p4")
    assert turn_order(state, 3) == ("p1", "p2", "p3", "p4", "p5")


def test_seat_order_does_not_depend_on_the_order_of_players():
    base = game(4)
    players = (Player("d", 4), Player("b", 2), Player("a", 7), Player("c", 3))
    state = GameState(
        board=dataclasses.replace(base.board, canals=(), claims=()),
        players=players,
        mode=Mode.NORMAL,
        round=1,
        start_player="a",
        current_player="a",
        market=(),
        bag=(),
    )
    assert turn_order(state, 1) == ("a", "b", "c", "d")
    assert turn_order(state, 2) == ("b", "c", "d", "a")
    final, log = play_game(state, bots_for(state, pass_bot), random.Random(0), random.Random(0))
    assert [r.player for r in log[:8]] == list("abcd" + "bcda")


def test_every_player_acts_once_per_round_in_turn_order():
    state = game(5, seed=3)
    final, log = play_game(state, bots_for(state, first_bot), random.Random(0), random.Random(0))
    for r in range(1, rounds_of(state) + 1):
        in_round = [rec.player for rec in log if rec.round == r]
        assert tuple(in_round) == turn_order(state, r)
    assert Counter(rec.player for rec in log) == {p.id: rounds_of(state) for p in state.players}


def test_turn_order_is_the_same_for_every_state_of_a_game():
    for n in PLAYER_COUNTS:
        states = play_to_end(game(n, seed=n, mode=Mode.FLASH))
        total = rounds_of(states[0])
        expected = [turn_order(states[0], r) for r in range(1, total + 1)]
        for s in states:
            assert [turn_order(s, r) for r in range(1, total + 1)] == expected


def test_round_one_starts_with_the_setup_start_player_and_rotates():
    for seed in range(5):
        state = game(4, seed=seed)
        seats = sorted(state.players, key=lambda p: p.seat)
        ids = [p.id for p in seats]
        start = ids.index(state.start_player)
        for r in range(1, rounds_of(state) + 1):
            assert turn_order(state, r)[0] == ids[(start + r - 1) % 4]


@pytest.mark.parametrize("bad", [0, -1, 13, 100])
def test_turn_order_outside_the_game_raises(bad):
    with pytest.raises(ValueError, match="round"):
        turn_order(game(2), bad)


def test_turn_order_rejects_a_non_int_round():
    with pytest.raises(TypeError):
        turn_order(game(2), "1")
    with pytest.raises(TypeError):
        turn_order(game(2), True)


def start_counts(state):
    return Counter(turn_order(state, r)[0] for r in range(1, rounds_of(state) + 1))


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("n", PLAYER_COUNTS)
def test_rounds_started_differ_by_at_most_one(mode, n):
    for seat in range(1, n + 1):
        state = with_start(game(n, mode=mode), seat)
        counts = start_counts(state)
        values = [counts[p.id] for p in state.players]
        assert sum(values) == rounds_of(state)
        assert max(values) - min(values) <= 1


@pytest.mark.parametrize(
    "mode, n, expected",
    [
        (Mode.NORMAL, 2, {"p1": 5, "p2": 5}),
        (Mode.NORMAL, 4, {"p1": 3, "p2": 3, "p3": 3, "p4": 3}),
        (Mode.FLASH, 2, {"p1": 3, "p2": 3}),
        (Mode.FLASH, 5, {"p1": 1, "p2": 1, "p3": 1, "p4": 1}),
    ],
)
def test_rounds_started_concrete_cases(mode, n, expected):
    assert start_counts(with_start(game(n, mode=mode), 1)) == expected


# --- Taking a turn -----------------------------------------------------------


def test_act_advances_to_the_next_player_within_a_round():
    state = with_start(game(3), 2)
    rng = random.Random(0)
    after = act(state, "p2", first_bot(state, "p2", rng), rng)
    assert (after.round, after.start_player, after.current_player) == (1, "p2", "p3")
    after = act(after, "p3", first_bot(after, "p3", rng), rng)
    assert (after.round, after.start_player, after.current_player) == (1, "p2", "p1")


def test_act_after_the_last_player_starts_the_next_round():
    state = with_start(game(3), 2)
    rng = random.Random(0)
    for player in ("p2", "p3", "p1"):
        state = act(state, player, first_bot(state, player, rng), rng)
    assert (state.round, state.start_player, state.current_player) == (2, "p3", "p3")


def test_act_applies_the_action_and_does_not_change_its_input():
    state = game(2)
    snapshot = dataclasses.replace(state)
    action = first_bot(state, state.current_player, None)
    after = act(state, state.current_player, action, random.Random(0))
    assert state == snapshot
    assert len(after.board.canals) == 1
    assert after.board.canals[0].owner == state.current_player


def test_act_for_the_wrong_player_raises_before_apply():
    state = game(2)
    other = next(p.id for p in state.players if p.id != state.current_player)
    snapshot = dataclasses.replace(state)
    rng = random.Random(5)
    rng_state = rng.getstate()
    with pytest.raises(ValueError, match=f"{state.current_player}'s turn"):
        act(state, other, first_bot(state, other, rng), rng)
    assert state == snapshot
    assert rng.getstate() == rng_state


def test_act_for_an_unknown_player_raises():
    state = game(2)
    with pytest.raises(ValueError, match=state.current_player):
        act(state, "nobody", Pass(), random.Random(0))


def test_act_with_an_illegal_action_raises_from_apply():
    state = game(2)
    snapshot = dataclasses.replace(state)
    rng = random.Random(5)
    rng_state = rng.getstate()
    with pytest.raises(IllegalAction):
        act(state, state.current_player, Pass(), rng)  # placements exist, so pass is illegal
    assert state == snapshot
    assert rng.getstate() == rng_state


def test_act_passes_its_rng_to_apply_for_bribes():
    state, _ = _state_with_a_bribe()
    player = state.current_player
    bribe = next(a for a in legal_actions(state, player) if isinstance(a, Bribe))
    rng = random.Random(9)
    after = act(state, player, bribe, rng)
    roll = random.Random(9).randint(1, 6)
    assert after.player(player).debt == state.player(player).debt + roll


def _state_with_a_bribe():
    """A mid-game state from a seeded random game where the current player can bribe."""
    state = game(2, seed=1)
    dice, bots = game_rngs(1)
    while not game_over(state):
        player = state.current_player
        if any(isinstance(a, Bribe) for a in legal_actions(state, player)):
            return state, dice
        state = act(state, player, random_bot(state, player, bots), dice)
    raise AssertionError("no bribe was possible")


# --- End of the game ---------------------------------------------------------


def test_game_over_exactly_past_the_last_round():
    states = play_to_end(game(2, mode=Mode.FLASH))
    total = rounds_of(states[0])
    assert [game_over(s) for s in states] == [False] * (len(states) - 1) + [True]
    final = states[-1]
    assert final.round == total + 1
    assert all(s.round <= total for s in states[:-1])


def test_final_state_rotates_like_any_round_change():
    states = play_to_end(with_start(game(3, mode=Mode.FLASH), 1))
    final = states[-1]
    # Flash 3p has 6 rounds; round 7 would start with seat 7 -> seat 1.
    assert final.start_player == final.current_player == "p1"
    GameState(**{f.name: getattr(final, f.name) for f in dataclasses.fields(GameState)})


def test_act_on_a_finished_game_raises():
    final = play_to_end(game(2, mode=Mode.FLASH))[-1]
    rng = random.Random(0)
    rng_state = rng.getstate()
    with pytest.raises(ValueError, match="game is over"):
        act(final, final.current_player, Pass(), rng)
    assert rng.getstate() == rng_state


@pytest.mark.parametrize(
    "mode, n, turns",
    [(Mode.NORMAL, 2, 20), (Mode.NORMAL, 5, 50), (Mode.FLASH, 2, 12), (Mode.FLASH, 5, 20)],
)
def test_a_full_game_has_rounds_times_players_turns(mode, n, turns):
    state = game(n, seed=7, mode=mode)
    final, log = play_game(state, bots_for(state, random_bot), *game_rngs(7))
    assert len(log) == turns
    assert game_over(final)
    assert final.round == rounds_of(state) + 1


def test_a_game_where_everyone_can_only_pass_still_ends():
    state = pass_only(game(4))
    assert all(legal_actions(state, p.id) == (Pass(),) for p in state.players)
    final, log = play_game(state, bots_for(state, pass_bot), random.Random(0), random.Random(0))
    assert len(log) == 48
    assert all(rec.action == Pass() for rec in log)
    assert game_over(final)
    assert final.board == state.board


# --- Playing a game ----------------------------------------------------------


def test_play_game_calls_bots_with_the_decide_signature():
    state = game(3, mode=Mode.FLASH)
    calls = []
    bot_rng = random.Random(2)

    def spy(s, player, rng):
        calls.append((s, player, rng))
        return first_bot(s, player, rng)

    final, log = play_game(state, bots_for(state, spy), random.Random(0), bot_rng)
    assert len(calls) == len(log) == 18
    for (s, player, rng), rec in zip(calls, log):
        assert s.current_player == player == rec.player
        assert s.round == rec.round
        assert rng is bot_rng


def test_play_game_log_records_round_player_and_action():
    state = game(2, mode=Mode.FLASH)
    final, log = play_game(state, bots_for(state, first_bot), random.Random(0), random.Random(0))
    assert isinstance(log, tuple)
    assert all(isinstance(rec, TurnRecord) for rec in log)
    assert [rec.round for rec in log] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6]
    with pytest.raises(dataclasses.FrozenInstanceError):
        log[0].round = 2


def test_play_game_rejects_a_missing_bot_before_playing():
    state = game(3)
    bots = bots_for(state, first_bot)
    del bots["p2"]
    with pytest.raises(ValueError, match="p2"):
        play_game(state, bots, random.Random(0), random.Random(0))


def test_play_game_rejects_an_unknown_bot_before_playing():
    state = game(2)
    called = []

    def bot(s, p, rng):
        called.append(p)
        return first_bot(s, p, rng)

    bots = {**bots_for(state, bot), "p9": bot}
    with pytest.raises(ValueError, match="p9"):
        play_game(state, bots, random.Random(0), random.Random(0))
    assert called == []


def test_play_game_raises_when_a_bot_plays_an_illegal_action():
    state = game(2)
    with pytest.raises(IllegalAction):
        play_game(state, bots_for(state, pass_bot), random.Random(0), random.Random(0))


def test_play_game_on_a_finished_game_returns_it_unchanged():
    final = play_to_end(game(2, mode=Mode.FLASH))[-1]
    again, log = play_game(final, bots_for(final, first_bot), random.Random(0), random.Random(0))
    assert again == final
    assert log == ()


def test_play_game_from_mid_game_plays_only_the_remaining_turns():
    states = play_to_end(game(3, mode=Mode.FLASH))
    mid = states[7]
    final, log = play_game(mid, bots_for(mid, first_bot), random.Random(0), random.Random(0))
    assert len(log) == 18 - 7
    assert final == states[-1]


def test_dice_do_not_depend_on_how_many_numbers_bots_draw():
    def drawing_bot(draws):
        def bot(s, player, rng):
            for _ in range(draws):
                rng.random()
            actions = legal_actions(s, player)
            return next((a for a in actions if isinstance(a, Bribe)), actions[0])
        return bot

    results = []
    for draws in (0, 1, 5):
        state = game(2, seed=4)
        final, log = play_game(state, bots_for(state, drawing_bot(draws)), random.Random(11),
                               random.Random(3))
        assert any(isinstance(rec.action, Bribe) for rec in log)
        results.append(final)
    assert results[0] == results[1] == results[2]


def test_bots_only_draw_from_bot_rng():
    state = game(2, seed=4)
    dice_rng = random.Random(11)

    def bot(s, player, rng):
        assert rng is not dice_rng
        return random_bot(s, player, rng)

    play_game(state, bots_for(state, bot), dice_rng, random.Random(3))


# --- Replaying a game --------------------------------------------------------


@pytest.mark.parametrize("seed", [1, 2, 3])
@pytest.mark.parametrize("mode", list(Mode))
def test_replay_with_the_same_dice_gives_the_same_final_state(seed, mode):
    state = game(3, seed=seed, mode=mode)
    final, log = play_game(state, bots_for(state, random_bot), *game_rngs(seed))
    if mode is Mode.NORMAL:
        assert any(isinstance(rec.action, Bribe) for rec in log)
    dice_rng, _ = game_rngs(seed)
    assert replay(state, log, dice_rng) == final


def test_replay_with_other_dice_changes_only_debt():
    state = game(2, seed=1)
    final, log = play_game(state, bots_for(state, random_bot), *game_rngs(1))
    assert any(isinstance(rec.action, Bribe) for rec in log)
    debts = set()
    for dice_seed in range(5):
        other = replay(state, log, random.Random(dice_seed))
        assert other.board == final.board
        assert other.board.claims == final.board.claims
        debts.add(tuple(p.debt for p in other.players))
    debts.add(tuple(p.debt for p in final.players))
    assert len(debts) > 1


def test_replay_rejects_a_record_for_the_wrong_player():
    state = game(2, mode=Mode.FLASH)
    final, log = play_game(state, bots_for(state, first_bot), random.Random(0), random.Random(0))
    other = next(p.id for p in state.players if p.id != log[0].player)
    bad = (dataclasses.replace(log[0], player=other), *log[1:])
    with pytest.raises(ValueError, match="turn"):
        replay(state, bad, random.Random(0))


def test_replay_rejects_a_record_for_the_wrong_round():
    state = game(2, mode=Mode.FLASH)
    final, log = play_game(state, bots_for(state, first_bot), random.Random(0), random.Random(0))
    bad = (*log[:2], dataclasses.replace(log[2], round=1), *log[3:])
    with pytest.raises(ValueError, match="round"):
        replay(state, bad, random.Random(0))


def test_replay_past_the_end_raises():
    state = game(2, mode=Mode.FLASH)
    final, log = play_game(state, bots_for(state, first_bot), random.Random(0), random.Random(0))
    extra = TurnRecord(final.round, final.current_player, Pass())
    with pytest.raises(ValueError):
        replay(state, (*log, extra), random.Random(0))


def test_replay_of_an_empty_log_returns_the_state():
    state = game(2)
    assert replay(state, (), random.Random(0)) == state


# --- Game identity -----------------------------------------------------------


def test_game_rngs_are_deterministic_and_distinct():
    for seed in (0, 1, 12345):
        dice, bots = game_rngs(seed)
        dice2, bots2 = game_rngs(seed)
        a, b, c = dice.random(), bots.random(), random.Random(seed).random()
        assert a == dice2.random()
        assert b == bots2.random()
        assert len({a, b, c}) == 3
    assert game_rngs(1)[0].random() != game_rngs(2)[0].random()


def test_game_rngs_use_string_seeds():
    # The documented, process-independent seeding: string seeds hash with sha512.
    dice, bots = game_rngs(42)
    assert dice.getstate() == random.Random("dice:42").getstate()
    assert bots.getstate() == random.Random("bots:42").getstate()


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("n", [2, 4])
def test_the_same_game_identity_gives_the_same_game(mode, n):
    def run(seed):
        state = new_game(n, seed, mode)
        return play_game(state, bots_for(state, random_bot), *game_rngs(seed))

    for seed in (5, 6):
        assert run(seed) == run(seed)
    assert run(5) != run(6)


# --- Module rules ------------------------------------------------------------


def test_game_module_uses_no_global_randomness():
    source = Path(__file__).parents[1] / "acequias" / "game.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "random":
                assert node.attr == "Random", f"game.py uses random.{node.attr}"
        if isinstance(node, ast.ImportFrom):
            assert node.module != "random"
