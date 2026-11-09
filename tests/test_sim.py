import ast
import dataclasses
import json
import math
import statistics
from pathlib import Path
from types import MappingProxyType

import pytest

from acequias.config import preset as shipped_preset
from acequias.flow import WaterPath
from acequias.game import TurnRecord, play_game
from acequias.hex import Direction, Hex
from acequias.model import Mode, PieceKind, Varietal
from acequias.scoring import Score, WateredVineyard
from acequias.setup import new_game
from acequias.sim import (
    GameRecord,
    SimResult,
    SimRules,
    game_seed,
    play_one,
    simulate_game,
    summarize,
)
from acequias.turn import Bribe, Pass, PlaceCanal, PlaceFloodgate

PLAYER_COUNTS = (2, 3, 4, 5)


def rules(mode=Mode.FLASH, players=2, policies=None, **overrides):
    return SimRules(mode, players, policies or ("random",) * players, overrides)


# --- Input -------------------------------------------------------------------


def test_sim_rules_is_frozen_with_read_only_overrides():
    source = {"market_size": 5}
    r = SimRules(Mode.NORMAL, 2, ["random", "greedy"], source)
    assert r.policies == ("random", "greedy")
    assert r.overrides == {"market_size": 5}
    source["market_size"] = 6
    assert r.overrides["market_size"] == 5
    with pytest.raises(TypeError):
        r.overrides["market_size"] = 7
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.players = 3
    assert SimRules(Mode.FLASH, 2, ("random", "random")).overrides == {}


@pytest.mark.parametrize("players", [1, 6])
def test_player_count_outside_range_raises(players):
    with pytest.raises(ValueError, match="players"):
        SimRules(Mode.FLASH, players, ("random",) * players)


def test_policies_length_must_match_players():
    with pytest.raises(ValueError, match="policies"):
        SimRules(Mode.FLASH, 3, ("random", "random"))


def test_mode_must_be_a_mode():
    with pytest.raises(TypeError, match="mode"):
        SimRules("flash", 2, ("random", "random"))


def test_rules_must_be_sim_rules():
    with pytest.raises(TypeError, match="rules"):
        simulate_game({"mode": Mode.FLASH}, 1, 0)
    with pytest.raises(TypeError, match="rules"):
        play_one(None, 0)


@pytest.mark.parametrize("n", [0, -1])
def test_n_below_one_raises(n):
    with pytest.raises(ValueError, match="n must be at least 1"):
        simulate_game(rules(), n, 0)


@pytest.mark.parametrize("value", [1.0, "1", True, None])
def test_n_and_seed_must_be_ints(value):
    with pytest.raises(TypeError, match="n must be an int"):
        simulate_game(rules(), value, 0)
    with pytest.raises(TypeError, match="seed must be an int"):
        simulate_game(rules(), 1, value)


def test_unknown_policy_raises_the_policy_error_before_any_game(monkeypatch):
    played = []
    monkeypatch.setattr("acequias.sim.new_game", lambda *a, **k: played.append(a))
    with pytest.raises(ValueError, match="unknown policy 'nope'.*'random'.*'greedy'"):
        simulate_game(rules(policies=("random", "nope")), 3, 0)
    assert played == []


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"no_such_field": 1}, "no_such_field"),
        ({"mode": Mode.NORMAL}, "mode"),
        ({"market_size": 0}, "market_size"),
    ],
)
def test_bad_override_raises_naming_the_field(overrides, match):
    with pytest.raises(ValueError, match=match):
        simulate_game(SimRules(Mode.FLASH, 2, ("random", "random"), overrides), 1, 0)


def test_overrides_reach_the_game_through_new_game_only(monkeypatch):
    calls = []
    real_new_game = new_game
    real_play_game = play_game

    def spy_new_game(*args, **kwargs):
        calls.append(kwargs)
        return real_new_game(*args, **kwargs)

    def spy_play_game(state, bots, dice_rng, bot_rng, *rest, **kwargs):
        assert not rest and not kwargs
        return real_play_game(state, bots, dice_rng, bot_rng)

    monkeypatch.setattr("acequias.sim.new_game", spy_new_game)
    monkeypatch.setattr("acequias.sim.play_game", spy_play_game)
    result = simulate_game(rules(market_size=5, rounds={p: 3 for p in PLAYER_COUNTS}), 2, 1)
    assert len(calls) == 2
    used = calls[0]["preset"]
    assert used.market_size == 5 and used.rounds_for(2) == 3
    assert used.bodega_points == shipped_preset(Mode.FLASH).bodega_points
    assert result.preset["market_size"] == 5
    assert result.turns_per_game == 3 * 2


def test_seats_get_their_policy_whatever_the_start_player(monkeypatch):
    seen = {}

    def tagging(name):
        def bot(state, player, rng):
            seen.setdefault(player, name)
            return _first_legal(state, player)

        return bot

    monkeypatch.setattr("acequias.sim.policy", tagging)
    starts = set()
    for seed in range(6):
        record = play_one(rules(players=3, policies=("a", "b", "c")), seed)
        starts.add(record.start.start_player)
        assert seen == {"p1": "a", "p2": "b", "p3": "c"}
    assert len(starts) > 1


def _first_legal(state, player):
    from acequias.turn import legal_actions

    return legal_actions(state, player)[0]


# --- Per-game seeds and replay ------------------------------------------------


def test_game_seed_is_pure_and_distinct():
    seeds = [game_seed(7, i) for i in range(1000)]
    assert all(type(s) is int for s in seeds)
    assert len(set(seeds)) == 1000
    assert seeds == [game_seed(7, i) for i in range(1000)]
    assert game_seed(7, 0) != game_seed(8, 0)


def test_game_seed_rejects_bad_input():
    with pytest.raises(TypeError):
        game_seed(True, 0)
    with pytest.raises(TypeError):
        game_seed(0, 1.0)
    with pytest.raises(ValueError):
        game_seed(0, -1)


def test_game_seed_is_process_independent():
    # Fixed value: a string-seeded random.Random is the same in every process.
    import random

    assert game_seed(0, 0) == random.Random("game:0:0").getrandbits(63)


def test_play_one_returns_a_full_frozen_record():
    r = rules()
    record = play_one(r, 12345)
    assert record.game_seed == 12345
    assert record.start == new_game(2, 12345, Mode.FLASH, preset=shipped_preset(Mode.FLASH))
    assert record.final.round == record.start.preset.rounds_for(2) + 1
    assert len(record.log) == 6 * 2
    assert set(record.scores) == {"p1", "p2"}
    assert record.winners and set(record.winners) <= {"p1", "p2"}
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.winners = ()


def test_run_statistics_equal_those_of_play_one_records():
    r = rules(players=3, policies=("random", "greedy", "random"))
    result = simulate_game(r, 4, 99)
    records = [play_one(r, game_seed(99, i)) for i in range(4)]
    assert summarize(r, 99, records) == result


def test_play_one_replays_a_later_game_of_the_run(monkeypatch):
    r = rules(players=3)
    seen = []
    real = play_one.__globals__["_play"]

    def spy(*args, **kwargs):
        record = real(*args, **kwargs)
        seen.append(record)
        return record

    monkeypatch.setattr("acequias.sim._play", spy)
    simulate_game(r, 3, 5)
    monkeypatch.undo()
    again = play_one(r, game_seed(5, 2))
    assert again.final == seen[2].final
    assert again.log == seen[2].log


def test_same_inputs_give_an_equal_result_and_seeds_matter():
    r = rules(players=3)
    a = simulate_game(r, 3, 1)
    assert a == simulate_game(r, 3, 1)
    assert a.to_json() == simulate_game(r, 3, 1).to_json()

    def stats(result):
        return {k: v for k, v in result.to_json().items() if k != "seed"}

    assert any(stats(simulate_game(r, 3, s)) != stats(a) for s in (2, 3))


# --- Presets the board cannot satisfy ------------------------------------------


@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_impossible_preset_fails_on_game_zero(players, monkeypatch):
    played = []
    monkeypatch.setattr("acequias.sim.play_game", lambda *a: played.append(a))
    r = rules(players=players, vineyard_distance=(3, 3), hexes_per_player=7)
    with pytest.raises(ValueError) as info:
        simulate_game(r, 5, 11)
    message = str(info.value)
    assert "game 0" in message
    assert str(game_seed(11, 0)) in message
    assert "cannot place" in message and "vineyard_distance (3, 3)" in message
    assert played == []


def test_later_game_setup_failure_names_index_and_seed(monkeypatch):
    real = new_game
    bad = game_seed(4, 2)

    def flaky(players, seed, mode, *, preset):
        if seed == bad:
            raise ValueError("no layout within the retry cap")
        return real(players, seed, mode, preset=preset)

    monkeypatch.setattr("acequias.sim.new_game", flaky)
    with pytest.raises(ValueError, match=f"game 2 \\(game seed {bad}\\).*retry cap"):
        simulate_game(rules(), 4, 4)


# --- Statistics on hand-built records ----------------------------------------


def score(player, seat, total, bodega=0, watered=()):
    vineyards = tuple(
        WateredVineyard(Hex(q, 0), varietal, WaterPath((), frozenset()), ())
        for q, varietal in enumerate(watered)
    )
    return Score(player, seat, total - bodega, bodega, 0, 0, 0, total, len(vineyards), vineyards)


CANAL = PlaceCanal(PieceKind.STRAIGHT, Hex(0, 0), 0)
GATE = PlaceFloodgate(Hex(0, 0), Direction.E)
BRIBE = Bribe(Hex(0, 0), Direction.E)


def record(start_player, winners, scores, log):
    base = new_game(2, 0, Mode.FLASH)
    start = dataclasses.replace(base, start_player=start_player, current_player=start_player)
    return GameRecord(
        game_seed=0,
        start=start,
        final=start,
        log=tuple(TurnRecord(1, p, a) for p, a in log),
        scores=MappingProxyType({s.player: s for s in scores}),
        winners=winners,
    )


HAND_RULES = SimRules(Mode.FLASH, 2, ("random", "greedy"))
HAND_RECORDS = (
    # Game 1: p1 starts and wins; p2 bribes; p1 has the bodega.
    record(
        "p1",
        ("p1",),
        [score("p1", 1, 10, bodega=2, watered=[Varietal.MALBEC]),
         score("p2", 2, 5, watered=[Varietal.TORRONTES])],
        [("p1", CANAL), ("p2", BRIBE)],
    ),
    # Game 2: p2 starts; shared win (1/2 each).
    record(
        "p2",
        ("p1", "p2"),
        [score("p1", 1, 7, watered=[Varietal.BONARDA]),
         score("p2", 2, 7, watered=[Varietal.TORRONTES])],
        [("p2", GATE), ("p1", Pass())],
    ),
    # Game 3: p1 starts, p2 wins.
    record(
        "p1",
        ("p2",),
        [score("p1", 1, 3), score("p2", 2, 8, watered=[Varietal.MALBEC])],
        [("p1", CANAL), ("p2", CANAL)],
    ),
    # Game 4: p2 starts and wins.
    record(
        "p2",
        ("p2",),
        [score("p1", 1, 4), score("p2", 2, 9, watered=[Varietal.MALBEC])],
        [("p2", Pass()), ("p1", Pass())],
    ),
)


def test_statistics_of_hand_built_records():
    result = summarize(HAND_RULES, 3, HAND_RECORDS)
    assert result.n == 4 and result.seed == 3 and result.players == 2
    assert result.win_rate_by_position == pytest.approx((0.625, 0.375))
    assert result.win_rate_by_seat == pytest.approx((0.375, 0.625))
    assert result.win_rate_by_policy == pytest.approx({"random": 0.375, "greedy": 0.625})
    assert result.turn_order_advantage == pytest.approx(0.25)
    assert result.shared_win_rate == 0.25

    totals = [10, 5, 7, 7, 3, 8, 4, 9]
    assert result.score_terms["total"] == pytest.approx(
        {"mean": 6.625, "stdev": statistics.pstdev(totals)}
    )
    assert result.score_terms["bodega"] == pytest.approx(
        {"mean": 0.25, "stdev": statistics.pstdev([2, 0, 0, 0, 0, 0, 0, 0])}
    )
    assert result.score_terms["vineyards"]["mean"] == pytest.approx((53 - 2) / 8)
    for term in ("rights_paid", "rights_collected", "debt"):
        assert result.score_terms[term] == {"mean": 0.0, "stdev": 0.0}
    assert result.mean_total_by_position == pytest.approx((7.25, 6.0))
    assert result.winning_score == pytest.approx({"mean": 8.5, "stdev": math.sqrt(1.25)})
    assert result.turns_per_game == 2.0
    assert result.actions_per_game == pytest.approx(
        {"canal": 0.75, "floodgate": 0.25, "bribe": 0.25, "pass": 0.75}
    )
    assert result.games_with_bribe == 0.25
    assert result.games_with_floodgate == 0.25
    assert result.win_rate_bribers == 0.0
    assert result.win_rate_non_bribers == pytest.approx(4 / 7)
    assert result.bodega_rate == pytest.approx(1 / 8)
    assert result.winner_varietal_rate == pytest.approx(
        {"malbec": 0.75, "bonarda": 0.25, "torrontes": 0.25}
    )


def test_turn_order_advantage_of_a_sixty_percent_first_position():
    # Position 1 (the start player) wins 3 games of 5.
    games = [
        record("p1", ("p1",), [score("p1", 1, 5), score("p2", 2, 1)], []),
        record("p2", ("p2",), [score("p1", 1, 1), score("p2", 2, 5)], []),
        record("p1", ("p1",), [score("p1", 1, 5), score("p2", 2, 1)], []),
        record("p1", ("p2",), [score("p1", 1, 1), score("p2", 2, 5)], []),
        record("p2", ("p1",), [score("p1", 1, 5), score("p2", 2, 1)], []),
    ]
    result = summarize(HAND_RULES, 0, games)
    assert result.win_rate_by_position == pytest.approx((0.6, 0.4))
    assert result.turn_order_advantage == pytest.approx(0.2)
    assert result.win_rate_bribers is None
    assert result.win_rate_non_bribers == pytest.approx(0.5)
    assert result.turns_per_game == 0.0


# --- Result shape --------------------------------------------------------------


def _assert_immutable_value(value):
    if isinstance(value, MappingProxyType):
        for k, v in value.items():
            _assert_immutable_value(k)
            _assert_immutable_value(v)
    elif isinstance(value, tuple):
        for v in value:
            _assert_immutable_value(v)
    else:
        assert value is None or type(value) in (int, float, str), value


def test_result_is_frozen_and_holds_only_plain_values():
    result = simulate_game(rules(players=3), 2, 0)
    for f in dataclasses.fields(SimResult):
        _assert_immutable_value(getattr(result, f.name))
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.n = 3
    with pytest.raises(TypeError):
        result.preset["market_size"] = 1


def _assert_plain_json(value):
    if isinstance(value, dict):
        for k, v in value.items():
            assert type(k) is str
            _assert_plain_json(v)
    elif isinstance(value, list):
        for v in value:
            _assert_plain_json(v)
    else:
        assert value is None or type(value) in (int, float, str, bool), value


@pytest.mark.parametrize("n", [1, 3])
def test_to_json_round_trips(n):
    result = simulate_game(rules(players=3, policies=("random", "greedy", "random")), n, 8)
    data = result.to_json()
    _assert_plain_json(data)
    assert json.loads(json.dumps(data, allow_nan=False)) == data
    if n == 1:
        assert data["winning_score"]["stdev"] == 0.0
        assert data["shared_win_rate"] in (0.0, 1.0)


def test_to_json_names():
    data = simulate_game(rules(mode=Mode.NORMAL, players=2), 1, 0).to_json()
    assert data["mode"] == "normal"
    assert data["preset"]["mode"] == "normal"
    assert data["policies"] == ["random", "random"]
    assert data["preset"]["rounds"] == {"2": 10, "3": 15, "4": 12, "5": 10}
    assert data["preset"]["vineyard_distance"] == [4, 4]
    assert set(data["preset"]["bag_mix"]) == {k.name.lower() for k in PieceKind}
    assert data["preset"]["bag_mix"]["gentle_curve"] == 20
    assert set(data["winner_varietal_rate"]) == {"malbec", "bonarda", "torrontes"}
    assert set(data["actions_per_game"]) == {"canal", "floodgate", "bribe", "pass"}
    assert set(data["score_terms"]) == {
        "vineyards", "bodega", "rights_paid", "rights_collected", "debt", "total"
    }
    assert set(data["winning_score"]) == {"mean", "stdev"}


def test_single_game_has_zero_spread():
    result = simulate_game(rules(), 1, 2)
    assert result.winning_score["stdev"] == 0.0
    assert result.score_terms["total"]["stdev"] >= 0.0
    assert not any(
        isinstance(v, float) and (math.isnan(v) or math.isinf(v))
        for v in json.loads(json.dumps(result.to_json()))["mean_total_by_position"]
    )


# --- Modes -------------------------------------------------------------------


def test_each_mode_gives_its_own_labeled_result():
    normal = simulate_game(rules(mode=Mode.NORMAL), 2, 0)
    flash = simulate_game(rules(mode=Mode.FLASH), 2, 0)
    assert normal.mode == "normal" and flash.mode == "flash"
    assert normal.preset["rounds"][2] == shipped_preset(Mode.NORMAL).rounds_for(2)
    assert flash.preset["rounds"][2] == shipped_preset(Mode.FLASH).rounds_for(2)
    assert normal.turns_per_game != flash.turns_per_game


# --- Runs with real bots --------------------------------------------------------


def _assert_sums(result):
    assert sum(result.win_rate_by_position) == pytest.approx(1, abs=1e-9)
    assert sum(result.win_rate_by_seat) == pytest.approx(1, abs=1e-9)
    assert sum(result.win_rate_by_policy.values()) == pytest.approx(1, abs=1e-9)
    assert sum(result.actions_per_game.values()) == pytest.approx(
        result.turns_per_game, abs=1e-9
    )


@pytest.mark.parametrize("mode", list(Mode))
@pytest.mark.parametrize("players", PLAYER_COUNTS)
def test_random_bots_finish_games_for_every_player_count(mode, players):
    result = simulate_game(rules(mode=mode, players=players), 5, 21)
    assert result.n == 5 and result.players == players
    assert len(result.win_rate_by_position) == players
    assert result.turns_per_game == shipped_preset(mode).rounds_for(players) * players
    assert result.win_rate_by_policy.keys() == {"random"}
    _assert_sums(result)


def test_mixed_policies_report_both():
    result = simulate_game(rules(players=4, policies=("random", "greedy") * 2), 4, 3)
    assert set(result.win_rate_by_policy) == {"random", "greedy"}
    _assert_sums(result)


# --- Constraints ----------------------------------------------------------------


def test_sim_uses_no_global_random_hash_or_clock():
    source = Path(__file__).parents[1] / "acequias" / "sim.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "random":
                assert node.attr == "Random", f"random.{node.attr} used"
        if isinstance(node, ast.Name):
            assert node.id != "hash", "hash() used"
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names]
            module = getattr(node, "module", None) or ""
            assert not {"time", "os", "datetime", "server"} & {module.split(".")[0], *names}
