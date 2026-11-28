"""Rules v3 shared vineyard supply, respins, lost and dead turns, and the combined end (#181)."""

import hashlib

import pytest

from acequias.board import planting_spots
from acequias.config import EndCondition, with_overrides
from acequias.game import act, fired_trigger, game_over
from acequias.model import ActionsLeft, DieFace, GameState, Mode, PieceKind, Player, Varietal
from acequias.scoring import calculate_score
from acequias.sim import _preset, _preset_values, play_one
from acequias.turn import (
    IllegalAction,
    Pass,
    PlaceCanal,
    Plant,
    ResowVineyard,
    RollActionDie,
    apply,
    legal_actions,
    supply_left,
)
from server.schemas import overrides_from_json
from test_split_scoring import _tune
from test_v3_turn import (
    A_AND_B,
    D,
    EAST_OF_C,
    NORTH_OF_A,
    NORTH_OF_B,
    TILES,
    V3,
    Rigged,
    board,
    vineyard,
)

M, S, B = Varietal.MALBEC, Varietal.SYRAH, Varietal.BONARDA
SUPPLY = with_overrides(V3, vineyard_supply={2: 1}, max_spins=2)
"""m = 1: two pieces of each varietal, one of Bonarda and Cabernet Franc (14 in all)."""
TRIGGERS = (EndCondition.SUPPLY_EMPTY, EndCondition.SCORE_TARGET, EndCondition.DEAD_TURNS)
ALL_PIECES = (
    M, M, Varietal.CABERNET_SAUVIGNON, Varietal.CABERNET_SAUVIGNON, S, S, Varietal.MERLOT,
    Varietal.MERLOT, Varietal.TORRONTES, Varietal.TORRONTES, Varietal.CHARDONNAY,
    Varietal.CHARDONNAY, B, Varietal.CABERNET_FRANC,
)
RESERVED = {A_AND_B, EAST_OF_C, D.vertex(0), NORTH_OF_A, NORTH_OF_B}
SPARE = [v for v in planting_spots(TILES) if v not in RESERVED]


def filled(varietals):
    """p2's vineyards of ``varietals`` on spare spots: pieces taken from the supply."""
    return tuple(vineyard(spot, "p2", v) for spot, v in zip(SPARE, varietals, strict=False))


def without(pieces, *taken):
    rest = list(pieces)
    for v in taken:
        rest.remove(v)
    return tuple(rest)


def state(planted=(), preset=SUPPLY, left=None, dead=(0, 0), round=1, current="p1"):
    return GameState(
        board=board(planted=planted),
        players=(Player("p1", 1, dead_turns=dead[0]), Player("p2", 2, dead_turns=dead[1])),
        mode=Mode.NORMAL,
        round=round,
        start_player="p1",
        current_player=current,
        market=(PieceKind.STRAIGHT,) * 4,
        preset=preset,
        actions_left=left,
    )


def end_preset(supply=1, target=10_000, spins=1):
    return with_overrides(V3, vineyard_supply={n: supply for n in V3.player_counts}, max_spins=spins,
                          end_conditions=TRIGGERS, score_target={2: target})


# --- The options -----------------------------------------------------------------


def test_defaults_keep_todays_rules_and_options_are_checked():
    assert V3.vineyard_supply == {} and V3.max_spins == 1 and V3.end_conditions == ()
    assert V3.triggers == () and V3.supply_for(2) is None
    for name in ("vineyard_supply", "max_spins", "end_conditions"):
        assert name not in _preset_values(V3)
    assert supply_left(state(preset=V3)) is None
    assert dict(SUPPLY.supply_for(2)) == {v: ALL_PIECES.count(v) for v in set(ALL_PIECES)}
    assert sum(SUPPLY.supply_for(2).values()) == 14
    p = end_preset()
    assert p.triggers == TRIGGERS and p.round_cap(2) == 2 * p.rounds_for(2)
    assert _preset_values(p)["end_conditions"] == ("supply_empty", "score_target", "dead_turns")
    assert overrides_from_json({"end_conditions": ["supply_empty", "dead_turns"],
                                "vineyard_supply": {"2": 3}}) == {
        "end_conditions": (EndCondition.SUPPLY_EMPTY, EndCondition.DEAD_TURNS), "vineyard_supply": {2: 3}}
    with pytest.raises(ValueError, match="needs vineyard_supply"):
        with_overrides(V3, end_conditions=(EndCondition.SUPPLY_EMPTY,))
    with pytest.raises(ValueError, match="cannot hold rounds"):
        with_overrides(V3, end_conditions=(EndCondition.ROUNDS,))
    with pytest.raises(ValueError, match="twice"):
        with_overrides(V3, end_conditions=(EndCondition.DEAD_TURNS, EndCondition.DEAD_TURNS))
    with pytest.raises(ValueError, match="not both"):
        with_overrides(V3, end_condition=EndCondition.BAG_EMPTY, end_conditions=(EndCondition.DEAD_TURNS,))
    with pytest.raises(ValueError, match="max_spins"):
        with_overrides(V3, max_spins=0)
    from acequias.config import NORMAL_V2
    with pytest.raises(ValueError, match="vertex planting"):
        with_overrides(NORMAL_V2, vineyard_supply={2: 1})


V3END_MAIN = {
    ('FLASH', 2, 'base'): '4f3edf56d9b7',
    ('FLASH', 2, 'seats rotated'): '4f3edf56d9b7',
    ('FLASH', 2, 'seats shuffled'): '4f3edf56d9b7',
    ('FLASH', 2, 'unlimited bag'): '4f3edf56d9b7',
    ('FLASH', 2, 'bag_empty, finish round'): '186e042f704b',
    ('FLASH', 2, 'vineyards_out, finish round'): '591af5e1ed71',
    ('FLASH', 2, 'score_target x1 (2=14,3=14), finish round'): '591af5e1ed71',
    ('FLASH', 2, 'score_target x1.5 (2=21,3=21), finish round'): '186e042f704b',
    ('FLASH', 2, 'score_target x2 (2=28,3=28), finish round'): '186e042f704b',
    ('FLASH', 2, 'bag_empty, ends at once'): '186e042f704b',
    ('FLASH', 2, 'vineyards_out, ends at once'): '3a3c8b45c128',
    ('FLASH', 2, 'score_target x1 (2=14,3=14), ends at once'): '3a3c8b45c128',
    ('FLASH', 2, 'score_target x1.5 (2=21,3=21), ends at once'): '186e042f704b',
    ('FLASH', 2, 'score_target x2 (2=28,3=28), ends at once'): '186e042f704b',
    ('NORMAL', 4, 'base'): '7d05becd2400',
    ('NORMAL', 4, 'seats rotated'): '7d05becd2400',
    ('NORMAL', 4, 'seats shuffled'): '58f5ede16ec9',
    ('NORMAL', 4, 'unlimited bag'): '7d05becd2400',
    ('NORMAL', 4, 'bag_empty, finish round'): '8adbe39e905c',
    ('NORMAL', 4, 'vineyards_out, finish round'): '6bc49777ddb2',
    ('NORMAL', 4, 'score_target x1 (2=30,3=51,4=43,5=37), finish round'): '83392d3b6dbe',
    ('NORMAL', 4, 'score_target x1.5 (2=45,3=77,4=65,5=56), finish round'): '8adbe39e905c',
    ('NORMAL', 4, 'score_target x2 (2=60,3=102,4=86,5=74), finish round'): '8adbe39e905c',
    ('NORMAL', 4, 'bag_empty, ends at once'): '8adbe39e905c',
    ('NORMAL', 4, 'vineyards_out, ends at once'): '70e31486797c',
    ('NORMAL', 4, 'score_target x1 (2=30,3=51,4=43,5=37), ends at once'): 'e10b812d5fd6',
    ('NORMAL', 4, 'score_target x1.5 (2=45,3=77,4=65,5=56), ends at once'): '8adbe39e905c',
    ('NORMAL', 4, 'score_target x2 (2=60,3=102,4=86,5=74), ends at once'): '8adbe39e905c',
}
"""A digest of the log, totals and winners of game seed 11 of every ``v3end`` row (greedy seats,
Flash 2p and Normal 4p), recorded on ``main`` before #181."""


def test_v3end_rows_play_the_same_games_as_before_181():
    """The new fields at their defaults (no supply, one spin, the single end condition) change no
    game; the shipped presets are pinned by ``test_golden_games``."""
    tune = _tune()
    sweep = next(s for s in tune.SWEEPS if s.name == "v3end")
    for (mode, players, label), expected in V3END_MAIN.items():
        changes = dict(sweep.candidates[Mode[mode]])[label]
        job = tune.Job(label, Mode[mode], players, "greedy", {**sweep.base[Mode[mode]], **changes}, 1, 0)
        r = tune.play_seated(tune.rules_of(job), 11, 0, changes.get(tune.SEAT_KEY, "fixed"))
        totals = tuple(sorted((pid, s.total) for pid, s in r.scores.items()))
        digest = hashlib.sha256(repr((r.log, totals, r.winners)).encode()).hexdigest()[:12]
        assert digest == expected, (mode, players, label)


# --- Supply and respins -------------------------------------------------------------


def test_planting_uses_up_a_varietal_and_a_later_spin_respins():
    s = state(left=ActionsLeft(2, 1))
    assert supply_left(s)[B] == 1
    s = apply(s, "p1", Plant(A_AND_B), Rigged(B))
    assert supply_left(s)[B] == 0 and sum(supply_left(s).values()) == 13
    rng = Rigged(B, S)  # Bonarda is used up: spun again
    s = apply(s, "p1", Plant(EAST_OF_C), rng)
    assert rng.values == []
    assert s.board.planted_at(EAST_OF_C) == vineyard(EAST_OF_C, "p1", S)
    assert supply_left(s)[S] == 1


def test_two_failed_spins_lose_the_turn_and_keep_earlier_canals():
    s = state(filled(without(ALL_PIECES, M)), left=ActionsLeft(2, 1))  # only Malbec left
    s = act(s, "p1", PlaceCanal(PieceKind.STRAIGHT, D, 0), Rigged())
    assert s.current_player == "p1" and s.actions_left == ActionsLeft(1, 0)
    rng = Rigged(S, B)
    after = act(s, "p1", Plant(D.vertex(0)), rng)
    assert rng.values == []
    assert after.board.planted_at(D.vertex(0)) is None
    assert after.board.canal_at(D).owner == "p1"  # the canal stays
    assert after.current_player == "p2" and after.actions_left is None  # nothing left
    assert after.player("p1").dead_turns == 1 and after.player("p1").lost_turns == 1


def test_a_failed_plant_loses_the_actions_left_after_a_good_season():
    s = state(filled(without(ALL_PIECES, M)), preset=with_overrides(SUPPLY, max_spins=1),
              left=ActionsLeft(2, 1))
    after = apply(s, "p1", Plant(EAST_OF_C), Rigged(S))
    assert after.actions_left == ActionsLeft(0, 0, lost=True)
    assert legal_actions(after, "p1") == ()


def test_a_failed_resow_keeps_the_varietal_and_ends_the_turn():
    full = filled(ALL_PIECES)  # the whole supply is on the board
    syrah = next(v for v in full if v.varietal is S)
    s = apply(state(full), "p1", RollActionDie(), Rigged(DieFace.RESOW))
    assert s.pending_face is DieFace.RESOW and s.actions_left == ActionsLeft(1, 1)
    failed = act(s, "p1", ResowVineyard(syrah.vertex), Rigged(M, B))
    assert failed.board.planted_at(syrah.vertex) == syrah
    assert failed.pending_face is None and failed.current_player == "p2"
    assert failed.player("p1").dead_turns == 1
    # The vineyard's own piece goes back first, so its own varietal always works.
    ok = apply(s, "p1", ResowVineyard(syrah.vertex), Rigged(M, S))
    assert ok.board.planted_at(syrah.vertex) == syrah
    assert ok.actions_left == ActionsLeft(1, 1, planted=True)  # #184: a resow that works counts as planted


def test_plant_is_illegal_while_the_supply_is_empty():
    s = state(filled(ALL_PIECES), left=ActionsLeft(1, 1))
    assert sum(supply_left(s).values()) == 0
    legal = legal_actions(s, "p1")
    assert not any(isinstance(a, Plant) for a in legal) and legal[-1] == Pass()
    with pytest.raises(IllegalAction, match="supply is empty"):
        apply(s, "p1", Plant(EAST_OF_C), Rigged(M))
    assert any(isinstance(a, Plant) for a in legal_actions(state(left=ActionsLeft(1, 1)), "p1"))


# --- Dead turns -------------------------------------------------------------------


def test_a_turn_with_no_spin_resets_the_dead_turn_counter():
    s = state(preset=end_preset(supply=3), left=ActionsLeft(1, 1), dead=(1, 1))
    after = act(s, "p1", Pass(), Rigged())
    assert after.player("p1").dead_turns == 0 and after.player("p2").dead_turns == 1
    drought = act(after, "p2", RollActionDie(), Rigged(DieFace.DROUGHT))
    assert drought.player("p2").dead_turns == 0
    assert drought.end_triggered is None


def test_the_dead_turn_trigger_ends_the_game_at_once():
    s = state(filled(without(ALL_PIECES, M)), preset=end_preset(), left=ActionsLeft(1, 1), dead=(1, 2))
    after = act(s, "p1", Plant(EAST_OF_C), Rigged(S))  # one spin, on a used-up varietal
    assert after.player("p1").dead_turns == 2
    assert after.end_trigger is EndCondition.DEAD_TURNS and after.end_triggered == 1
    assert game_over(after) and after.round == 1  # p2 never plays round 1
    assert fired_trigger(after) is EndCondition.DEAD_TURNS


# --- The combined end -----------------------------------------------------------------


def test_the_supply_empty_trigger_ends_the_game_after_the_round():
    s = state(filled(without(ALL_PIECES, M)), preset=end_preset(), left=ActionsLeft(1, 1))
    after = act(s, "p1", Plant(EAST_OF_C), Rigged(M))  # the last piece
    assert after.end_triggered == 1 and after.end_trigger is EndCondition.SUPPLY_EMPTY
    assert not game_over(after) and after.current_player == "p2"
    end = act(after, "p2", RollActionDie(), Rigged(DieFace.DROUGHT))
    assert game_over(end) and end.round == 2 and end.end_trigger is EndCondition.SUPPLY_EMPTY


def test_the_score_target_trigger_ends_the_game_after_the_round():
    s = state((vineyard(NORTH_OF_A, "p1"),), preset=end_preset(supply=3, target=1), left=ActionsLeft(1, 1))
    assert calculate_score(s)["p1"].total >= 1
    after = act(s, "p1", Pass(), Rigged())
    assert after.end_triggered == 1 and after.end_trigger is EndCondition.SCORE_TARGET
    assert not game_over(after)
    end = act(after, "p2", RollActionDie(), Rigged(DieFace.DROUGHT))
    assert game_over(end) and end.round == 2


def test_a_game_with_no_trigger_ends_at_the_cap():
    p = end_preset(supply=3)
    cap = p.round_cap(2)
    s = state(preset=p, round=cap, current="p2", left=ActionsLeft(1, 1))
    end = act(s, "p2", Pass(), Rigged())
    assert end.round == cap + 1 and game_over(end)
    assert end.end_triggered is None and end.end_trigger is EndCondition.ROUNDS
    # Under the round count end nothing is recorded.
    plain = act(state(preset=V3, round=V3.rounds_for(2), current="p2", left=ActionsLeft(1, 1)),
                "p2", Pass(), Rigged())
    assert game_over(plain) and plain.end_trigger is None


@pytest.mark.parametrize("spins", [1, 3])
def test_a_finished_game_records_its_trigger(spins):
    tune = _tune()
    overrides = {**tune.V1_OVERRIDES[Mode.FLASH], **tune.v3_best_base(Mode.FLASH),
                 "vineyard_supply": {2: 1, 3: 1}, "max_spins": spins, "end_conditions": TRIGGERS,
                 "score_target": {2: 30, 3: 30}}
    from acequias.sim import SimRules
    record = play_one(SimRules(Mode.FLASH, 2, ("greedy",) * 2, overrides), 5)
    assert game_over(record.final)
    assert record.final.end_trigger in (*TRIGGERS, EndCondition.ROUNDS)
    left = supply_left(record.final)
    assert all(n >= 0 for n in left.values())
    assert _preset(SimRules(Mode.FLASH, 2, ("greedy",) * 2, overrides)).max_spins == spins


# --- Fractional supply multiplier (#188) --------------------------------------


@pytest.mark.parametrize(("m", "two", "one", "total"), [
    (1, 2, 1, 14), (2, 4, 2, 28), (1.25, 3, 1, 20), (1.5, 3, 2, 22), (0.5, 1, 1, 8), (0.2, 1, 1, 8),
    (1.75, 4, 2, 28), (2.0, 4, 2, 28),
])
def test_fractional_supply_rounds_half_up_at_least_one(m, two, one, total):
    supply = with_overrides(V3, vineyard_supply={2: m}).supply_for(2)
    sectors = {v: ALL_PIECES.count(v) for v in set(ALL_PIECES)}
    assert sorted(set(sectors.values())) == [1, 2]
    assert {v: supply[v] for v in sectors} == {v: two if n == 2 else one for v, n in sectors.items()}
    assert sum(supply.values()) == total


def test_integer_supply_is_unchanged():
    supply = with_overrides(V3, vineyard_supply={2: 3}).supply_for(2)
    assert dict(supply) == {v: 3 * ALL_PIECES.count(v) for v in set(ALL_PIECES)}
    assert all(type(n) is int for n in supply.values())


@pytest.mark.parametrize("bad", [0, -1, -0.5, 0.0, True, False, "1", None, float("nan"), float("inf")])
def test_supply_rejects_bad_multipliers(bad):
    with pytest.raises(ValueError, match=r"vineyard_supply\[2\]"):
        with_overrides(V3, vineyard_supply={2: bad})
