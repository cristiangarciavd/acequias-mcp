"""The seat bonus (#142): ``Preset.seat_bonus``, its score term, and tune.py's
``--seat-bonus`` and ``--rounds``."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from acequias.config import NORMAL_V2, preset, with_overrides
from acequias.game import turn_order
from acequias.model import Board, GameState, Mode, Player
from acequias.scoring import calculate_score
from acequias.sim import SimRules, game_seed, play_one

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
tune = importlib.import_module("tune")

BONUS = {3: (2, 1, 0), 4: (1, 1, 1, 0)}


def state(round=1, start="a", players=("a", "b", "c"), season=0, drought=0, debt=0):
    ps = tuple(Player(pid, seat, debt, season, drought) for seat, pid in enumerate(players, start=1))
    return GameState(
        board=Board(tiles=(), canals=(), claims=()), players=ps, mode=Mode.NORMAL,
        round=round, start_player=start, current_player=start,
    )


# --- Validation ----------------------------------------------------------------


def test_seat_bonus_is_off_in_the_shipped_presets():
    assert dict(preset(Mode.NORMAL).seat_bonus) == {} and dict(preset(Mode.FLASH).seat_bonus) == {}


def test_seat_bonus_is_read_only_and_in_player_count_order():
    p = with_overrides(NORMAL_V2, seat_bonus={4: [1, 1, 1, 0], 3: (2, 1, 0)})
    assert list(p.seat_bonus) == [3, 4] and p.seat_bonus[4] == (1, 1, 1, 0)
    with pytest.raises(TypeError):
        p.seat_bonus[2] = (0, 0)


@pytest.mark.parametrize("bonus, error", [
    ({4: (1, 1, 0)}, ValueError),
    ({3: (1, 1, 1, 0)}, ValueError),
    ({6: (0,) * 6}, ValueError),
    ({1: (0,)}, ValueError),
    ({3: (1, -1, 0)}, ValueError),
    ({3: (1, 1.5, 0)}, TypeError),
    ({3: (True, 0, 0)}, TypeError),
    ({3: "110"}, TypeError),
    ({3: 1}, TypeError),
    ((3, (1, 1, 0)), TypeError),
])
def test_bad_seat_bonus_is_rejected(bonus, error):
    with pytest.raises(error):
        with_overrides(NORMAL_V2, seat_bonus=bonus)


# --- Scoring -------------------------------------------------------------------


def test_no_bonus_by_default_or_for_an_unlisted_player_count():
    assert all(s.seat_bonus == 0 for s in calculate_score(state(), NORMAL_V2).values())
    p = with_overrides(NORMAL_V2, seat_bonus={4: (1, 1, 1, 0)})
    assert all(s.seat_bonus == 0 for s in calculate_score(state(), p).values())


def test_bonus_follows_round_1_turn_order():
    p = with_overrides(NORMAL_V2, seat_bonus=BONUS)
    scores = calculate_score(state(start="b"), p)
    assert {pid: s.seat_bonus for pid, s in scores.items()} == {"b": 2, "c": 1, "a": 0}
    assert all(s.total == s.seat_bonus for s in scores.values())


@pytest.mark.parametrize("round", [2, 3, 5, 13])
def test_bonus_uses_round_1_start_player_in_later_rounds(round):
    # Round 1 started with "b": the start player of `round` is round - 1 seats later.
    ids = ("a", "b", "c")
    start = ids[(1 + round - 1) % 3]
    p = with_overrides(NORMAL_V2, seat_bonus=BONUS)
    scores = calculate_score(state(round=round, start=start), p)
    assert {pid: s.seat_bonus for pid, s in scores.items()} == {"b": 2, "c": 1, "a": 0}


def test_drought_never_takes_the_bonus_below_zero():
    p = with_overrides(NORMAL_V2, seat_bonus=BONUS)
    scores = calculate_score(state(drought=5, debt=0), p)
    assert [(s.seat_bonus, s.drought, s.total) for s in scores.values()] == [(2, 2, 0), (1, 1, 0), (0, 0, 0)]
    scores = calculate_score(state(season=3, drought=4), p)
    assert [(s.drought, s.total) for s in scores.values()] == [(4, 1), (4, 0), (3, 0)]


def test_simulated_game_gives_the_bonus_by_position():
    rules = SimRules(Mode.FLASH, 3, ("greedy",) * 3, {"seat_bonus": {3: (3, 2, 0)}})
    record = play_one(rules, game_seed(142, 0))
    order = turn_order(record.start, 1)
    assert [record.scores[pid].seat_bonus for pid in order] == [3, 2, 0]
    for s in record.scores.values():
        assert s.total == (s.vineyards + s.bodega - s.rights_paid + s.rights_collected - s.debt
                           + s.season + s.seat_bonus - s.drought + s.blend + s.buildings)


# --- tune.py -------------------------------------------------------------------


def test_parse_seat_bonus_and_rounds():
    assert tune.parse_seat_bonus("4=1,1,1,0;5=1,1,1,0,0") == {4: (1, 1, 1, 0), 5: (1, 1, 1, 0, 0)}
    assert tune.parse_rounds("4=5,5=5") == {4: 5, 5: 5}
    assert tune.seat_bonus_label({5: (1, 1, 1, 0, 0), 4: (1, 1, 1, 0)}) == "4=1,1,1,0;5=1,1,1,0,0"
    assert tune.rounds_label({5: 5, 4: 5}) == "4=5,5=5"


@pytest.mark.parametrize("text", ["4=1,1,0", "6=0,0,0,0,0,0", "4=1,1,1,-1", "4=a,1,1,0", "4", "4=1,1,1,0;4=1,1,1,0"])
def test_bad_seat_bonus_flag_is_an_argument_error(text, capsys):
    with pytest.raises(SystemExit):
        tune.main(["--list", "--seat-bonus", text])
    assert "--seat-bonus" in capsys.readouterr().err


@pytest.mark.parametrize("text", ["4=0", "1=5", "4=x", "4", "4=5,4=6"])
def test_bad_rounds_flag_is_an_argument_error(text, capsys):
    with pytest.raises(SystemExit):
        tune.main(["--list", "--rounds", text])
    assert "--rounds" in capsys.readouterr().err


@pytest.mark.parametrize("mode", list(Mode))
def test_flags_apply_over_every_b5_candidate(mode):
    bonus, rounds = {4: (1, 1, 1, 0), 5: (1, 1, 1, 0, 0)}, {4: 5, 5: 5}
    off = {s.name: s for s in tune.v2_sweeps(2, 1)}
    on = {s.name: s for s in tune.v2_sweeps(2, 1, seat_bonus=bonus, rounds=rounds)}
    for _, changes in off["b5"].candidates[mode]:
        assert "seat_bonus" not in changes
    shipped = tune.V1_PRESET[mode].rounds
    for _, changes in on["b5"].candidates[mode]:
        p = with_overrides(tune.V1_PRESET[mode], **{**tune.V2_BASE[mode], **changes})
        assert dict(p.seat_bonus) == bonus
        assert dict(p.rounds) == {2: shipped[2], 3: shipped[3], 4: 5, 5: 5}
    assert "seat bonus 4=1,1,1,0;5=1,1,1,0,0" in on["b5"].title and "rounds 4=5,5=5" in on["b5"].title
    for name in ("b0", "b1", "b2", "b3", "b3b", "b4"):
        assert on[name] == off[name]


def test_flags_reach_the_candidate_config_line_and_checkpoint_key(tmp_path):
    sweeps = tune.v2_sweeps(seat_bonus={4: (1, 1, 1, 0)}, rounds={4: 5})
    plain = tune.v2_sweeps()
    label = "no die (no bribe either)"
    _, values = tune.find_candidate(sweeps, "b5", label, [Mode.FLASH])
    _, base = tune.find_candidate(plain, "b5", label, [Mode.FLASH])
    line = tune.describe(values[Mode.FLASH])
    assert "seat_bonus=4=1,1,1,0" in line and "rounds=6/6/5/4" in line
    store = tune.Checkpoints(tmp_path, "fingerprint")

    def key(overrides):
        return store.key(tune.Job("t", Mode.FLASH, 4, "score_aware", overrides, 10, 1), 0, 10)

    assert key(values[Mode.FLASH]) != key(base[Mode.FLASH])
    assert "seat_bonus" in key(values[Mode.FLASH])
    assert key(values[Mode.FLASH]) != key({**values[Mode.FLASH], "seat_bonus": {4: (2, 1, 1, 0)}})


def test_flags_reach_the_b5_sweep_listing(capsys):
    assert tune.main(["--list", "--seat-bonus", "4=1,1,1,0", "--rounds", "4=5"]) == 0
    b5 = [line for line in capsys.readouterr().out.splitlines() if line.startswith("b5:")]
    assert len(b5) == 1 and "seat bonus 4=1,1,1,0" in b5[0] and "rounds 4=5" in b5[0]
