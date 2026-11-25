"""The Rules v3 turn (#152): the mandatory action die roll, then one action
(canal, plant, or pass), on vertex planting spots."""

import random
from dataclasses import replace

import pytest

from acequias.board import planting_spots
from acequias.config import NORMAL, V3_DIE_FACES, PlantingRules, BribeRules, with_overrides
from acequias.flow import plantable_spots
from acequias.game import act, game_rngs, play_game, replay
from acequias.hex import Direction, Hex
from acequias.model import (
    ActionsLeft,
    Board,
    DieFace,
    Floodgate,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    PlantedVineyard,
    Player,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import calculate_score
from acequias.setup import new_game
from acequias.sim import SimRules, _preset_values, play_one, simulate_game
from acequias.bots import random_bot
from acequias.turn import (
    Bribe,
    DeclineFace,
    IllegalAction,
    MoveVineyard,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    Plant,
    Release,
    Resow,
    ResowVineyard,
    RollActionDie,
    apply,
    legal_actions,
)

V3 = with_overrides(NORMAL, planting=PlantingRules.VERTICES)
V3_MOVE = with_overrides(V3, action_die=V3_DIE_FACES)

# River on (0, 0); a row of empty hexes east of it. Canals A (p1), B (p2),
# C (p1) carry water in a straight E-W line; D is free.
RIVER = Hex(0, 0)
A, B, C, D = Hex(1, 0), Hex(2, 0), Hex(3, 0), Hex(4, 0)
TILES = (
    Tile(RIVER, Terrain.RIVER),
    Tile(A, Terrain.EMPTY),
    Tile(B, Terrain.EMPTY),
    Tile(C, Terrain.EMPTY),
    Tile(D, Terrain.EMPTY),
    Tile(Hex(1, 1), Terrain.STONE),
)
CANALS = (
    PlacedCanal(A, PieceKind.STRAIGHT, 0, "p1"),
    PlacedCanal(B, PieceKind.STRAIGHT, 0, "p2"),
    PlacedCanal(C, PieceKind.STRAIGHT, 0, "p1"),
)
NORTH_OF_A = A.vertex(2)  # touches A only among the canals: p1 may plant
NORTH_OF_B = B.vertex(2)  # touches B only: p2's
A_AND_B = A.vertex(1)  # touches A and B: both may plant
EAST_OF_C = C.vertex(0)  # touches C and D: p1's
GATE = Floodgate(C, Direction.E)  # on C's open east edge: water keeps flowing to C


class Rigged:
    """An rng whose ``choice`` returns the given values in order (each must be in the sequence)."""

    def __init__(self, *values):
        self.values = list(values)

    def choice(self, seq):
        value = self.values.pop(0)
        assert value in seq
        return value


def board(canals=CANALS, planted=(), floodgates=()) -> Board:
    return Board(
        tiles=TILES, canals=canals, floodgates=floodgates,
        spots=planting_spots(TILES), planted=planted,
    )


def state(b=None, preset=V3, left=None, face=None, market=(PieceKind.STRAIGHT,) * 4):
    return GameState(
        board=board() if b is None else b,
        players=(Player("p1", 1), Player("p2", 2)),
        mode=Mode.NORMAL,
        round=1,
        start_player="p1",
        current_player="p1",
        market=market,
        preset=preset,
        actions_left=left,
        pending_face=face,
    )


def rolled(s, face):
    return apply(s, "p1", RollActionDie(), Rigged(face))


def debt(s, player="p1"):
    return s.player(player).debt


def vineyard(vertex, owner, varietal=Varietal.MALBEC):
    return PlantedVineyard(vertex, owner, varietal)


# --- The roll comes first ------------------------------------------------------


def test_the_roll_is_the_only_legal_action_before_it():
    s = state()
    assert legal_actions(s, "p1") == (RollActionDie(),)
    assert legal_actions(s, "p2") == ()
    for action in (Pass(), Plant(NORTH_OF_A), PlaceCanal(PieceKind.STRAIGHT, D, 0)):
        with pytest.raises(IllegalAction, match="roll the action die first"):
            apply(s, "p1", action, Rigged())


def test_only_the_current_player_acts():
    with pytest.raises(IllegalAction, match="p1's turn"):
        apply(state(), "p2", RollActionDie(), Rigged(DieFace.DROUGHT))


def test_the_roll_cannot_be_repeated_in_a_turn():
    s = rolled(state(), DieFace.DROUGHT)
    with pytest.raises(IllegalAction):
        apply(replace(s, actions_left=ActionsLeft(1, 1)), "p1", RollActionDie(), Rigged())


# --- Floodgate face ------------------------------------------------------------


def test_floodgate_face_costs_the_bribe_and_must_be_placed():
    s = rolled(state(), DieFace.FLOODGATE)
    assert debt(s) == V3.action_die_cost == 1
    assert s.pending_face is DieFace.FLOODGATE
    assert s.actions_left == ActionsLeft(1, 1)
    uses = legal_actions(s, "p1")
    assert uses and all(isinstance(a, PlaceFloodgate) for a in uses)
    with pytest.raises(IllegalAction, match="mandatory"):
        apply(s, "p1", DeclineFace(), Rigged())
    with pytest.raises(IllegalAction):
        apply(s, "p1", Plant(NORTH_OF_A), Rigged())
    after = apply(s, "p1", PlaceFloodgate(C, Direction.E), Rigged())
    assert after.board.floodgates == (GATE,)
    assert after.pending_face is None
    assert after.market == s.market  # from the die, not the market
    assert legal_actions(after, "p1")[-1] == Pass()


def test_floodgate_face_with_no_open_edge_still_costs_the_bribe():
    s = rolled(state(board(canals=())), DieFace.FLOODGATE)
    assert debt(s) == 1
    assert s.pending_face is None
    assert s.actions_left == ActionsLeft(1, 1)


# --- Release face --------------------------------------------------------------


def test_release_face_costs_the_bribe_and_must_remove_a_floodgate():
    s = rolled(state(board(floodgates=(GATE,))), DieFace.RELEASE)
    assert debt(s) == 1
    assert s.pending_face is DieFace.RELEASE
    assert legal_actions(s, "p1") == (Release(C, Direction.E),)
    with pytest.raises(IllegalAction, match="mandatory"):
        apply(s, "p1", DeclineFace(), Rigged())
    after = apply(s, "p1", Release(D, Direction.W), Rigged())  # either side of the edge
    assert after.board.floodgates == ()
    assert after.pending_face is None


def test_release_face_with_no_floodgate_still_costs_the_bribe():
    s = rolled(state(), DieFace.RELEASE)
    assert debt(s) == 1
    assert s.pending_face is None
    assert s.actions_left == ActionsLeft(1, 1)


# --- Resow face ----------------------------------------------------------------


def test_resow_face_is_free_and_respins_any_vineyard():
    planted = (vineyard(NORTH_OF_A, "p1"), vineyard(NORTH_OF_B, "p2"))
    s = rolled(state(board(planted=planted)), DieFace.RESOW)
    assert debt(s) == 0
    assert s.pending_face is DieFace.RESOW
    assert legal_actions(s, "p1") == (
        ResowVineyard(NORTH_OF_A), ResowVineyard(NORTH_OF_B), DeclineFace()
    )
    after = apply(s, "p1", ResowVineyard(NORTH_OF_B), Rigged(Varietal.CABERNET_SAUVIGNON))
    assert after.board.planted_at(NORTH_OF_B) == vineyard(
        NORTH_OF_B, "p2", Varietal.CABERNET_SAUVIGNON
    )
    assert after.pending_face is None
    declined = apply(s, "p1", DeclineFace(), Rigged())
    assert declined.board == s.board and declined.pending_face is None
    with pytest.raises(IllegalAction):
        apply(s, "p1", ResowVineyard(EAST_OF_C), Rigged(Varietal.MALBEC))
    with pytest.raises(IllegalAction):
        apply(s, "p1", MoveVineyard(NORTH_OF_A, EAST_OF_C), Rigged())  # resow only respins


def test_resow_face_with_nothing_planted_has_nothing_pending():
    s = rolled(state(), DieFace.RESOW)
    assert s.pending_face is None
    assert s.actions_left == ActionsLeft(1, 1)


def test_move_face_moves_your_own_vineyard_to_a_legal_spot():
    planted = (vineyard(NORTH_OF_A, "p1", Varietal.SYRAH), vineyard(NORTH_OF_B, "p2"))
    s = rolled(state(board(planted=planted), preset=V3_MOVE), DieFace.MOVE)
    assert debt(s) == 0 and s.pending_face is DieFace.MOVE
    uses = legal_actions(s, "p1")
    moves = [a for a in uses if isinstance(a, MoveVineyard)]
    assert moves == [MoveVineyard(NORTH_OF_A, to) for to in plantable_spots(s.board, "p1")]
    assert uses == (*moves, DeclineFace())  # no resow on the move face
    with pytest.raises(IllegalAction):
        apply(s, "p1", ResowVineyard(NORTH_OF_B), Rigged(Varietal.MALBEC))
    declined = apply(s, "p1", DeclineFace(), Rigged())
    assert declined.board == s.board and declined.pending_face is None
    after = apply(s, "p1", MoveVineyard(NORTH_OF_A, EAST_OF_C), Rigged())
    assert after.board.planted_at(NORTH_OF_A) is None
    assert after.board.planted_at(EAST_OF_C) == vineyard(EAST_OF_C, "p1", Varietal.SYRAH)
    with pytest.raises(IllegalAction, match="no vineyard"):
        apply(s, "p1", MoveVineyard(NORTH_OF_B, EAST_OF_C), Rigged())  # a rival's
    with pytest.raises(IllegalAction, match="may not plant"):
        apply(s, "p1", MoveVineyard(NORTH_OF_A, NORTH_OF_B), Rigged())  # taken


# --- Good season and drought ---------------------------------------------------


def test_good_season_gives_two_actions_but_never_two_canals():
    s = rolled(state(), DieFace.GOOD_SEASON)
    assert debt(s) == 0 and s.pending_face is None
    assert s.actions_left == ActionsLeft(2, 1)
    assert s.player("p1").season == 0  # no season points under Rules v3

    canal = apply(s, "p1", PlaceCanal(PieceKind.STRAIGHT, D, 0), Rigged())
    assert canal.actions_left == ActionsLeft(1, 0)
    legal = legal_actions(canal, "p1")
    assert not any(isinstance(a, PlaceCanal) for a in legal)
    assert Plant(D.vertex(0)) in legal  # the new canal carries water
    with pytest.raises(IllegalAction, match="one canal"):
        apply(canal, "p1", PlaceCanal(PieceKind.STRAIGHT, Hex(5, 0), 0), Rigged())

    plant = apply(s, "p1", Plant(NORTH_OF_A), Rigged(Varietal.MALBEC))
    assert plant.actions_left == ActionsLeft(1, 1)
    both = apply(plant, "p1", Plant(EAST_OF_C), Rigged(Varietal.SYRAH))
    assert both.actions_left == ActionsLeft(0, 0)
    assert legal_actions(both, "p1") == ()
    then_canal = apply(plant, "p1", PlaceCanal(PieceKind.STRAIGHT, D, 0), Rigged())
    assert then_canal.actions_left == ActionsLeft(0, 0)


def test_drought_loses_the_turn():
    s = state()
    after = act(s, "p1", RollActionDie(), Rigged(DieFace.DROUGHT))
    assert after.player("p1").debt == 0 and after.player("p1").drought == 0
    assert after.current_player == "p2"
    assert after.actions_left is None
    assert after.board == s.board


# --- The action ----------------------------------------------------------------


def test_plant_next_to_your_own_watered_canal_with_a_roulette_spin():
    s = state(left=ActionsLeft(1, 1))
    legal = legal_actions(s, "p1")
    plants = [a for a in legal if isinstance(a, Plant)]
    assert plants == [Plant(v) for v in plantable_spots(s.board, "p1")]
    assert Plant(NORTH_OF_B) not in plants
    assert legal[-1] == Pass()
    after = apply(s, "p1", Plant(A_AND_B), Rigged(Varietal.BONARDA))
    assert after.board.planted == (vineyard(A_AND_B, "p1", Varietal.BONARDA),)
    assert after.actions_left == ActionsLeft(0, 0)
    for vertex in (NORTH_OF_B, D.vertex(0), Hex(9, 9).vertex(0)):
        with pytest.raises(IllegalAction, match="may not plant"):
            apply(s, "p1", Plant(vertex), Rigged(Varietal.MALBEC))
    taken = state(board(planted=(vineyard(A_AND_B, "p2"),)), left=ActionsLeft(1, 1))
    with pytest.raises(IllegalAction):
        apply(taken, "p1", Plant(A_AND_B), Rigged(Varietal.MALBEC))


def test_place_a_canal_from_the_market():
    s = state(left=ActionsLeft(1, 1), market=(PieceKind.STRAIGHT, PieceKind.CLAW))
    after = apply(s, "p1", PlaceCanal(PieceKind.STRAIGHT, D, 0), Rigged())
    assert after.board.canal_at(D).owner == "p1"
    assert after.market == (PieceKind.CLAW,)
    assert after.board.claims == () and after.board.planted == ()
    assert after.actions_left == ActionsLeft(0, 0)


def test_pass_is_always_legal_and_ends_the_turn():
    s = state(left=ActionsLeft(2, 1))
    assert len(legal_actions(s, "p1")) > 1 and legal_actions(s, "p1")[-1] == Pass()
    after = act(s, "p1", Pass(), Rigged())
    assert after.current_player == "p2" and after.actions_left is None


def test_a_canal_and_a_plant_keep_the_turn_until_none_is_left():
    s = state(left=ActionsLeft(2, 1))
    after = act(s, "p1", PlaceCanal(PieceKind.STRAIGHT, D, 0), Rigged())
    assert after.current_player == "p1"
    after = act(after, "p1", Plant(D.vertex(0)), Rigged(Varietal.MALBEC))
    assert after.current_player == "p2" and after.actions_left is None


def test_grape_cluster_cap_limits_planting():
    capped = with_overrides(V3, grape_clusters_per_player=1)
    s = state(board(planted=(vineyard(NORTH_OF_A, "p1"),)), preset=capped, left=ActionsLeft(1, 1))
    assert not any(isinstance(a, Plant) for a in legal_actions(s, "p1"))
    with pytest.raises(IllegalAction, match="grape_clusters_per_player"):
        apply(s, "p1", Plant(EAST_OF_C), Rigged(Varietal.MALBEC))


def test_hex_rules_actions_are_illegal_under_v3_and_back():
    s = state(board(floodgates=(GATE,)), left=ActionsLeft(1, 1))
    for action in (Bribe(C, Direction.E), Resow(A), PlaceFloodgate(A, Direction.E), DeclineFace()):
        with pytest.raises(IllegalAction):
            apply(s, "p1", action, Rigged())
    v2 = new_game(2, 1, Mode.NORMAL)
    for action in (Plant(NORTH_OF_A), ResowVineyard(NORTH_OF_A), MoveVineyard(NORTH_OF_A, A_AND_B)):
        with pytest.raises(IllegalAction, match="vertex planting"):
            apply(v2, v2.current_player, action, Rigged())


# --- Options and state checks --------------------------------------------------


def test_v3_options_are_checked():
    with pytest.raises(ValueError, match="action_die bribe rules"):
        with_overrides(V3, bribe_rules=BribeRules.D6)
    with pytest.raises(ValueError, match="needs vertex planting"):
        with_overrides(NORMAL, vertex_needs_three_canals=True)
    with pytest.raises(ValueError, match="MOVE face needs vertex planting"):
        with_overrides(NORMAL, action_die=V3_DIE_FACES)
    with pytest.raises(TypeError):
        with_overrides(V3, vertex_needs_three_canals=1)
    with pytest.raises(ValueError, match="unknown preset field"):
        with_overrides(V3, resow_can_move=True)  # replaced by the move face (#160)
    assert NORMAL.vertex_needs_three_canals is False
    assert NORMAL.is_season_round(3) and not V3.is_season_round(3)


def test_actions_left_is_checked():
    with pytest.raises(ValueError):
        ActionsLeft(1, 2)
    with pytest.raises(ValueError):
        ActionsLeft(-1, 0)
    hex_board = new_game(2, 1, Mode.NORMAL)
    with pytest.raises(ValueError, match="only under vertex planting"):
        replace(hex_board, actions_left=ActionsLeft(1, 1))
    with pytest.raises(ValueError, match="follows a roll"):
        state(board(floodgates=(GATE,)), face=DieFace.RELEASE)


def test_preset_values_write_vertex_needs_three_canals_only_when_set():
    assert "vertex_needs_three_canals" not in _preset_values(NORMAL)
    assert "vertex_needs_three_canals" not in _preset_values(V3)
    three = with_overrides(V3, vertex_needs_three_canals=True)
    assert _preset_values(three)["vertex_needs_three_canals"] is True
    assert "move" in _preset_values(V3_MOVE)["action_die"]


# --- Whole games ---------------------------------------------------------------


@pytest.mark.parametrize("players", [2, 3, 4, 5])
def test_play_game_runs_a_v3_game_end_to_end(players):
    start = new_game(players, 11, Mode.NORMAL, preset=V3_MOVE)
    assert start.season_roll is None and start.actions_left is None
    bots = {p.id: random_bot for p in start.players}
    final, log = play_game(start, bots, *game_rngs(11))
    assert final.round == V3.rounds_for(players) + 1
    rolls = sum(isinstance(r.action, RollActionDie) for r in log)
    assert rolls == V3.rounds_for(players) * players  # one mandatory roll per turn
    assert all(r.face is not None for r in log if isinstance(r.action, RollActionDie))
    assert any(isinstance(r.action, Plant) for r in log)
    assert final.board.claims == ()
    assert all(p.season == 0 and p.drought == 0 for p in final.players)
    for score in calculate_score(final).values():
        assert score.total == (
            score.vineyards + score.bodega - score.rights_paid + score.rights_collected - score.debt
        )
    assert replay(start, log, game_rngs(11)[0]) == final


def test_v3_games_are_deterministic_and_counted_by_the_sim():
    rules = SimRules(Mode.NORMAL, 3, ("random",) * 3, {"planting": PlantingRules.VERTICES})
    assert play_one(rules, 5) == play_one(rules, 5)
    result = simulate_game(rules, 3, 2)
    assert {"plant", "move"} <= set(result.actions_per_game)
    assert result.actions_per_game["plant"] > 0
    assert sum(result.actions_per_game.values()) == pytest.approx(result.turns_per_game)
    assert result.preset["planting"] == "vertices"
