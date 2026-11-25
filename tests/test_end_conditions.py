"""Rules v3 end of game conditions and the seat bias diagnosis (#163)."""

import dataclasses

import pytest

import acequias.game as game_module
from acequias.config import NORMAL, EndCondition, PlantingRules, with_overrides
from acequias.game import act, end_fired, game_over, game_rngs, turn_order
from acequias.model import Mode
from acequias.scoring import calculate_score, winners
from acequias.sim import SimRules, _preset, _preset_values, play_one
from server.schemas import overrides_from_json
from test_split_scoring import _tune

SEED = 7


def rules(players=2, mode=Mode.FLASH, **changes) -> SimRules:
    """Greedy seats (fast) on ``v3_best_base`` (the #163 sweep base) with ``changes``."""
    tune = _tune()
    overrides = {**tune.V1_OVERRIDES[mode], **tune.v3_best_base(mode), **changes}
    return SimRules(mode, players, ("greedy",) * players, overrides)


def turn_ends(record):
    """``(index, state)`` after each log record that ends a turn (the next record is another
    player's or round's, or there is none), replaying the game."""
    state, dice = record.start, game_rngs(record.game_seed)[0]
    log = record.log
    for k, r in enumerate(log):
        state = act(state, r.player, r.action, dice)
        if k + 1 == len(log) or (log[k + 1].round, log[k + 1].player) != (r.round, r.player):
            yield k, state


def turns_by_player(record):
    turns: dict[str, int] = {}
    last = None
    for r in record.log:
        if (r.round, r.player) != last:
            turns[r.player] = turns.get(r.player, 0) + 1
            last = (r.round, r.player)
    return turns


# --- The options ---------------------------------------------------------------


def test_defaults_are_the_round_count_end():
    assert NORMAL.end_condition is EndCondition.ROUNDS
    assert NORMAL.finish_round and not NORMAL.unlimited_bag
    assert NORMAL.round_cap(4) == NORMAL.rounds_for(4)
    v3 = with_overrides(NORMAL, planting=PlantingRules.VERTICES)
    for name in ("end_condition", "finish_round", "vineyard_markers", "score_target", "unlimited_bag"):
        assert name not in _preset_values(v3)


def test_options_are_checked():
    with pytest.raises(ValueError, match="needs vertex planting"):
        with_overrides(NORMAL, end_condition=EndCondition.BAG_EMPTY)
    with pytest.raises(TypeError, match="end_condition"):
        with_overrides(NORMAL, end_condition="bag_empty")
    with pytest.raises(TypeError, match="finish_round"):
        with_overrides(NORMAL, finish_round=1)
    with pytest.raises(ValueError, match="score_target gives player counts"):
        with_overrides(NORMAL, score_target={6: 10})
    with pytest.raises(ValueError, match="vineyard_markers"):
        with_overrides(NORMAL, vineyard_markers={2: 0})


def test_markers_and_targets_default_by_mode_and_cap_is_twice_the_rounds():
    p = _preset(rules(4, Mode.NORMAL, end_condition=EndCondition.VINEYARDS_OUT))
    assert [p.markers_for(n) for n in (2, 3, 4, 5)] == [6, 9, 7, 6]
    assert [p.target_for(n) for n in (2, 3, 4, 5)] == [30, 51, 43, 37]
    assert p.round_cap(4) == 2 * p.rounds_for(4)
    assert p.plant_cap(3) == 9
    f = _preset(rules(end_condition=EndCondition.SCORE_TARGET, score_target={2: 20}))
    assert f.target_for(2) == 20 and f.target_for(3) == 14 and f.markers_for(2) == 3
    assert _preset_values(f)["end_condition"] == "score_target"
    assert dict(_preset_values(f)["score_target"]) == {2: 20}


def test_server_overrides_take_the_new_keys():
    changes = overrides_from_json({
        "end_condition": "vineyards_out", "finish_round": False,
        "vineyard_markers": {"2": 4}, "score_target": {"3": 40}, "unlimited_bag": True,
    })
    assert changes == {
        "end_condition": EndCondition.VINEYARDS_OUT, "finish_round": False,
        "vineyard_markers": {2: 4}, "score_target": {3: 40}, "unlimited_bag": True,
    }


# --- Default unchanged -------------------------------------------------------------


@pytest.mark.parametrize("players", [2, 3])
def test_default_end_plays_the_same_game(players):
    base = play_one(rules(players), SEED)
    explicit = play_one(rules(players, end_condition=EndCondition.ROUNDS, finish_round=False), SEED)
    assert explicit.log == base.log and explicit.scores == base.scores and explicit.winners == base.winners
    assert base.final.end_triggered is None
    assert base.final.round == _preset(rules(players)).rounds_for(players) + 1


# --- Triggers -----------------------------------------------------------------------


def _fires_once(record):
    """The log index of the turn that fired the end condition; no earlier turn end fired it."""
    fired = [k for k, state in turn_ends(record) if end_fired(state)]
    assert fired, "the trigger never fired"
    return fired[0]


@pytest.mark.parametrize("finish", [True, False])
def test_bag_empty_ends_when_bag_and_market_are_empty(finish):
    record = play_one(rules(end_condition=EndCondition.BAG_EMPTY, finish_round=finish, bag_size={2: 6, 3: 6}), SEED)
    k = _fires_once(record)
    trigger_round = record.log[k].round
    assert record.final.end_triggered == trigger_round
    assert not record.final.bag and not record.final.market
    if finish:
        assert record.log[-1].round == trigger_round and record.final.round == trigger_round + 1
        assert len(set(turns_by_player(record).values())) == 1  # everyone the same turns
    else:
        assert k == len(record.log) - 1  # the trigger turn is the last
        assert record.final.round == trigger_round
    assert game_over(record.final)


def test_bag_empty_ends_even_with_vineyards_still_plantable():
    from acequias.flow import plantable_spots

    record = play_one(rules(end_condition=EndCondition.BAG_EMPTY, bag_size={2: 6, 3: 6}), SEED)
    board = record.final.board
    assert record.final.end_triggered is not None
    assert any(plantable_spots(board, p.id, False) for p in record.final.players)


@pytest.mark.parametrize("finish", [True, False])
def test_vineyards_out_ends_when_a_player_plants_all_markers(finish):
    record = play_one(rules(end_condition=EndCondition.VINEYARDS_OUT, finish_round=finish,
                            vineyard_markers={2: 2, 3: 2}), SEED)
    k = _fires_once(record)
    assert record.final.end_triggered == record.log[k].round
    held: dict[str, int] = {}
    for v in record.final.board.planted:
        held[v.owner] = held.get(v.owner, 0) + 1
    assert max(held.values()) == 2  # the markers cap planting
    if not finish:
        assert k == len(record.log) - 1


@pytest.mark.parametrize("finish", [True, False])
def test_score_target_ends_when_a_player_reaches_it(finish):
    record = play_one(rules(end_condition=EndCondition.SCORE_TARGET, finish_round=finish,
                            score_target={2: 8, 3: 8}), SEED)
    k = _fires_once(record)
    trigger_round = record.log[k].round
    assert record.final.end_triggered == trigger_round
    if finish:
        assert record.log[-1].round == trigger_round
        assert len(set(turns_by_player(record).values())) == 1
    else:
        assert k == len(record.log) - 1
    scores = calculate_score(record.final)
    assert record.winners == winners(scores)  # the usual tiebreak decides


def test_score_target_counts_every_player_not_only_the_mover():
    record = play_one(rules(), SEED)
    for _, state in turn_ends(record):
        totals = calculate_score(state)
        mover = state.current_player
        others = [t.total for pid, t in totals.items() if pid != mover]
        if max(others) > totals[mover].total and max(others) > 0:
            break
    target = max(others)
    p = with_overrides(state.preset, end_condition=EndCondition.SCORE_TARGET, score_target={2: target})
    assert end_fired(dataclasses.replace(state, preset=p))
    assert not end_fired(dataclasses.replace(
        state, preset=with_overrides(p, score_target={2: target + 1000})))


def test_a_trigger_that_never_fires_ends_at_the_cap():
    r = rules(end_condition=EndCondition.SCORE_TARGET, score_target={2: 10_000, 3: 10_000})
    record = play_one(r, SEED)
    assert record.final.end_triggered is None
    assert record.log[-1].round == 2 * _preset(r).rounds_for(2)
    stats = _tune().end_stats([record])
    assert stats["capped"] == 1.0


@pytest.mark.parametrize("position", ["first", "last"])
@pytest.mark.parametrize("finish", [True, False])
def test_trigger_on_the_first_or_last_seat_of_a_round(monkeypatch, position, finish):
    """A trigger forced at the end of round 2's first or last turn."""
    r = rules(3, end_condition=EndCondition.SCORE_TARGET, finish_round=finish)
    start = play_one(r, SEED).start
    order = turn_order(start, 2)
    target = order[0] if position == "first" else order[-1]

    def fake(state):
        return state.round == 2 and state.actions_left is None and state.pending_face is None \
            and _last_mover[0] == target

    _last_mover = [None]
    real_act = game_module.act

    def tracking_act(state, player, action, rng):
        _last_mover[0] = player
        return real_act(state, player, action, rng)

    monkeypatch.setattr(game_module, "end_fired", fake)
    monkeypatch.setattr(game_module, "act", tracking_act)
    record = play_one(r, SEED)
    assert record.final.end_triggered == 2
    assert record.log[-1].player == (order[-1] if finish else target)
    assert record.log[-1].round == 2
    if finish:
        assert record.final.round == 3
        assert set(turns_by_player(record).values()) == {2}


def test_unlimited_bag_never_runs_out():
    r = rules(unlimited_bag=True, bag_size={2: 6, 3: 6})
    record = play_one(r, SEED)
    assert len(record.final.bag) == len(record.start.bag)
    assert len(record.final.market) == len(record.start.market)


# --- Seat assignment and the round trace (tune.py) --------------------------------------


def test_seat_assignments_are_deterministic_for_a_seed():
    tune = _tune()
    r = rules(3)
    for assignment in ("rotated", "shuffled"):
        a = tune.play_seated(r, SEED, 4, assignment)
        b = tune.play_seated(r, SEED, 4, assignment)
        assert a.start == b.start and a.log == b.log and a.winners == b.winners
    starts = {tune.play_seated(r, SEED, i, "rotated").start.start_player for i in range(3)}
    assert starts == {"p1", "p2", "p3"}
    shuffled = tune.play_seated(r, SEED, 0, "shuffled").start
    assert sorted(p.seat for p in shuffled.players) == [1, 2, 3]
    assert tune.play_seated(r, SEED, 0, "fixed") == play_one(r, SEED)


def test_rules_of_keeps_the_seat_key_out_of_the_preset():
    tune = _tune()
    (sweep,) = tune.v3end_sweeps()
    job = next(j for j in tune.sweep_jobs(sweep, [Mode.FLASH], 1, [2]) if j.label == "seats shuffled")
    assert tune.SEAT_KEY not in tune.rules_of(job).overrides
    result = tune.run_chunk(job, 0, 1)
    assert result.status == "ok"


def test_round_trace_has_one_row_per_round():
    tune = _tune()
    records = [play_one(rules(), tune.game_seed(SEED, i)) for i in range(2)]
    stats = tune.end_stats(records)
    rounds = max(rec.log[-1].round for rec in records)
    assert list(stats["trace"]) == [str(n) for n in range(1, rounds + 1)]
    assert all(len(row["mean"]) == 2 and row["games"] == 2 for row in stats["trace"].values())
    last = stats["trace"][str(rounds)]["mean"]
    by_position = [sum(rec.scores[pid].total for rec in records for j, pid in
                       enumerate(turn_order(rec.start, 1)) if j == k) / 2 for k in range(2)]
    assert last == pytest.approx(by_position)
    assert stats["capped"] is None and stats["turns"] == 2 * rounds


def test_v3end_sweep_rows_and_base():
    tune = _tune()
    (sweep,) = tune.v3end_sweeps()
    assert sweep.name == "v3end" and "v3end" in tune.SWEEP_NAMES
    assert sweep.seatings == ("score_aware",)
    for mode in Mode:
        assert sweep.base[mode] == {**tune.v3_best_base(mode), "end_condition": EndCondition.ROUNDS}
        labels = [label for label, _ in sweep.candidates[mode]]
        assert labels[:4] == ["base", "seats rotated", "seats shuffled", "unlimited bag"]
        assert len(labels) == 4 + 2 * (2 + len(tune.V3END_TARGET_FACTORS))
        assert all(tune.is_v3end({**sweep.base[mode], **c}) for _, c in sweep.candidates[mode])


def test_verdict_compares_the_displayed_advantage():
    tune = _tune()
    (sweep,) = tune.v3end_sweeps()
    jobs = tune.sweep_jobs(sweep, [Mode.FLASH], 1, [2])[:2]
    outcomes = [tune.Outcome("ok", data={"turn_order_advantage": x, "end_stats": {"trace": {}}}) for x in (0.19999999, 0.1994)]
    line = tune.end_report(list(zip(jobs, outcomes)))[0]
    assert f"`{jobs[1].label}`" in line and f"`{jobs[0].label}`" not in line
