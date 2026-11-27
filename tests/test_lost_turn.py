"""Rules v3 lost turn (#184): a turn is lost only if no plant or resow succeeded earlier in it."""

from acequias.config import with_overrides
from acequias.game import act, game_over
from acequias.model import ActionsLeft, DieFace, Mode, PieceKind, Varietal
from acequias.sim import SimRules, play_one
from acequias.turn import (
    BuildBodega,
    DeclineFace,
    PlaceCanal,
    Plant,
    ResowVineyard,
    RollActionDie,
    apply,
    supply_left,
)
from test_end_supply import ALL_PIECES, SUPPLY, TRIGGERS, filled, state, without
from test_split_scoring import _tune
from test_v3_turn import A_AND_B, D, EAST_OF_C, NORTH_OF_A, V3, Rigged, vineyard

M, S, B = Varietal.MALBEC, Varietal.SYRAH, Varietal.BONARDA
TWO_MALBEC = filled(without(ALL_PIECES, M, M))  # only the 2 Malbec pieces left


def test_good_season_plant_then_failed_plant_ends_the_turn_but_is_not_lost():
    s = state(TWO_MALBEC, left=ActionsLeft(2, 1), dead=(1, 0))
    s = act(s, "p1", Plant(NORTH_OF_A), Rigged(M))
    assert s.actions_left == ActionsLeft(1, 1, planted=True) and s.current_player == "p1"
    before = s
    after = act(s, "p1", Plant(EAST_OF_C), Rigged(S, B))  # Syrah and Bonarda are used up
    assert after.board.planted_at(EAST_OF_C) is None and after.board == before.board
    assert after.current_player == "p2" and after.actions_left is None
    p1 = after.player("p1")
    assert p1.dead_turns == 0 and p1.lost_turns == 0  # not lost: the counter resets
    ended = apply(before, "p1", Plant(EAST_OF_C), Rigged(S, B))
    assert ended.actions_left == ActionsLeft(0, 0, planted=True)


def test_good_season_first_plant_failing_is_still_lost():
    s = state(TWO_MALBEC, left=ActionsLeft(2, 1))
    after = act(s, "p1", Plant(NORTH_OF_A), Rigged(S, B))
    assert after.current_player == "p2"
    assert after.player("p1").dead_turns == 1 and after.player("p1").lost_turns == 1


def test_a_failed_plant_after_no_spin_is_lost():
    one = act(state(TWO_MALBEC, left=ActionsLeft(1, 1)), "p1", Plant(EAST_OF_C), Rigged(S, B))
    assert one.player("p1").lost_turns == 1
    canal = act(state(TWO_MALBEC, left=ActionsLeft(2, 1)), "p1", PlaceCanal(PieceKind.STRAIGHT, D, 0), Rigged())
    canal = act(canal, "p1", Plant(D.vertex(0)), Rigged(S, B))
    assert canal.board.canal_at(D).owner == "p1" and canal.player("p1").lost_turns == 1


def test_a_bodega_then_a_failed_plant_is_lost():
    mine = (Varietal.CABERNET_SAUVIGNON, Varietal.MERLOT, Varietal.TORRONTES, Varietal.CHARDONNAY)
    planted = filled(without(ALL_PIECES, M, M))
    planted = tuple(vineyard(v.vertex, "p1", v.varietal) if v.varietal in mine else v
                    for v in planted)
    p = with_overrides(SUPPLY, bodega_building=True)
    s = state(planted, preset=p, left=ActionsLeft(2, 1))
    s = act(s, "p1", BuildBodega(A_AND_B), Rigged())
    assert s.board.bodegas and s.actions_left == ActionsLeft(1, 1)
    after = act(s, "p1", Plant(EAST_OF_C), Rigged(S, B))
    assert after.board.bodegas == s.board.bodegas
    assert after.player("p1").lost_turns == 1 and after.player("p1").dead_turns == 1


def _resow_rolled(planted):
    return apply(state(planted), "p1", RollActionDie(), Rigged(DieFace.RESOW))


def test_a_failed_resow_is_lost_and_ends_the_turn_before_the_actions():
    full = filled(ALL_PIECES)
    syrah = next(v for v in full if v.varietal is S)
    after = act(_resow_rolled(full), "p1", ResowVineyard(syrah.vertex), Rigged(M, B))
    assert after.board.planted_at(syrah.vertex) == syrah and after.current_player == "p2"
    assert after.player("p1").lost_turns == 1


def test_a_resow_that_succeeds_counts_as_planted():
    planted = filled(without(ALL_PIECES, M))  # one Malbec left
    syrah = next(v for v in planted if v.varietal is S)
    s = act(_resow_rolled(planted), "p1", ResowVineyard(syrah.vertex), Rigged(S))
    assert s.actions_left == ActionsLeft(1, 1, planted=True)
    after = act(s, "p1", Plant(EAST_OF_C), Rigged(S, B))
    assert after.current_player == "p2" and after.player("p1").lost_turns == 0
    declined = act(_resow_rolled(planted), "p1", DeclineFace(), Rigged())
    after = act(declined, "p1", Plant(EAST_OF_C), Rigged(S, B))
    assert after.player("p1").lost_turns == 1


def test_a_failed_plant_changes_neither_supply_nor_board():
    s = state(TWO_MALBEC, left=ActionsLeft(1, 1))
    after = apply(s, "p1", Plant(EAST_OF_C), Rigged(S, B))
    assert after.board == s.board and supply_left(after) == supply_left(s)


def test_without_a_supply_nothing_is_marked_planted():
    s = apply(state(preset=V3, left=ActionsLeft(2, 1)), "p1", Plant(NORTH_OF_A), Rigged(M))
    assert s.actions_left == ActionsLeft(1, 1)


def test_bots_play_a_supply_game_to_the_end():
    tune = _tune()
    overrides = {**tune.V1_OVERRIDES[Mode.FLASH], **tune.v3_best_base(Mode.FLASH),
                 "vineyard_supply": {2: 1, 3: 1}, "max_spins": 1, "end_conditions": TRIGGERS,
                 "score_target": {2: 30, 3: 30}}
    for policy in ("greedy", "score_aware"):
        record = play_one(SimRules(Mode.FLASH, 2, (policy,) * 2, overrides), 3)
        assert game_over(record.final)
        assert all(p.lost_turns >= p.dead_turns >= 0 for p in record.final.players)
