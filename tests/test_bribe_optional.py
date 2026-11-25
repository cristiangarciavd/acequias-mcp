"""Rules v3 optional floodgate faces, the bribe paid only when used (#168)."""

import random

import pytest

from acequias.bots import greedy_bot, lookahead_bot, score_aware_bot
from acequias.config import DEFAULT_BLENDS, NORMAL, V3_DIE_FACES, PlantingRules, with_overrides
from acequias.game import game_rngs, play_game, replay
from acequias.model import ActionsLeft, DieFace, Mode
from acequias.setup import new_game
from acequias.sim import _preset_values
from acequias.turn import (
    DeclineFace,
    IllegalAction,
    PlaceFloodgate,
    Release,
    apply,
    bribe_on_use,
    legal_actions,
)
from test_split_scoring import _tune
from test_v3_turn import (
    GATE,
    NORTH_OF_B,
    V3,
    C,
    D,
    Direction,
    Rigged,
    board,
    debt,
    rolled,
    state,
    vineyard,
)

OPTIONAL = with_overrides(V3, bribe_optional=True, action_die_cost=2)
MANDATORY = with_overrides(V3, action_die_cost=2)


# --- The option ------------------------------------------------------------------


def test_the_option_is_off_by_default_and_needs_vertex_planting():
    assert not NORMAL.bribe_optional and not V3.bribe_optional
    with pytest.raises(ValueError, match="bribe_optional needs vertex planting"):
        with_overrides(NORMAL, bribe_optional=True)
    with pytest.raises(TypeError, match="bribe_optional"):
        with_overrides(V3, bribe_optional=1)


def test_preset_values_write_bribe_optional_only_when_set():
    assert "bribe_optional" not in _preset_values(V3)
    assert _preset_values(OPTIONAL)["bribe_optional"] is True


# --- The turn ---------------------------------------------------------------------


@pytest.mark.parametrize("face", [DieFace.FLOODGATE, DieFace.RELEASE])
def test_a_declined_face_costs_nothing(face):
    s = rolled(state(board(floodgates=(GATE,)), preset=OPTIONAL), face)
    assert debt(s) == 0
    assert s.pending_face is face
    assert legal_actions(s, "p1")[-1] == DeclineFace()
    after = apply(s, "p1", DeclineFace(), Rigged())
    assert debt(after) == 0
    assert after.pending_face is None
    assert after.board == s.board
    assert after.actions_left == ActionsLeft(1, 1)


def test_a_placed_floodgate_pays_the_bribe():
    s = rolled(state(preset=OPTIONAL), DieFace.FLOODGATE)
    action = PlaceFloodgate(C, Direction.E)
    assert bribe_on_use(s, action, OPTIONAL) == 2
    after = apply(s, "p1", action, Rigged())
    assert after.board.floodgates == (GATE,)
    assert debt(after) == 2 and debt(after, "p2") == 0
    assert after.market == s.market


def test_a_released_floodgate_pays_the_bribe():
    s = rolled(state(board(floodgates=(GATE,)), preset=OPTIONAL), DieFace.RELEASE)
    after = apply(s, "p1", Release(D, Direction.W), Rigged())
    assert after.board.floodgates == ()
    assert debt(after) == 2


def test_a_face_with_no_use_costs_nothing():
    s = rolled(state(preset=OPTIONAL), DieFace.RELEASE)  # no floodgate on the board
    assert debt(s) == 0 and s.pending_face is None


def test_other_faces_and_mandatory_mode_pay_no_bribe_on_use():
    s = rolled(state(preset=MANDATORY), DieFace.FLOODGATE)
    assert bribe_on_use(s, PlaceFloodgate(C, Direction.E), MANDATORY) == 0


def test_mandatory_mode_is_unchanged():
    s = rolled(state(preset=MANDATORY), DieFace.FLOODGATE)
    assert debt(s) == 2  # paid on the roll
    assert DeclineFace() not in legal_actions(s, "p1")
    with pytest.raises(IllegalAction, match="mandatory"):
        apply(s, "p1", DeclineFace(), Rigged())
    after = apply(s, "p1", PlaceFloodgate(C, Direction.E), Rigged())
    assert debt(after) == 2  # nothing more on use
    empty = rolled(state(preset=MANDATORY), DieFace.RELEASE)
    assert debt(empty) == 2 and empty.pending_face is None


# --- The bots ---------------------------------------------------------------------

# p2's vineyard north of B takes its only third from p2's canal B. A gate up the
# river from B dries it: p2 loses that third, p1 loses nothing (no vineyard).
def _gate_turn(cost: int):
    preset = with_overrides(V3, bribe_optional=True, action_die_cost=cost)
    s = state(board(planted=(vineyard(NORTH_OF_B, "p2"),)), preset=preset)
    return rolled(s, DieFace.FLOODGATE)


@pytest.mark.parametrize("bot", [greedy_bot, score_aware_bot, lookahead_bot])
def test_bots_place_a_floodgate_worth_the_bribe(bot):
    action = bot(_gate_turn(0), "p1", random.Random(0))
    assert isinstance(action, PlaceFloodgate)


@pytest.mark.parametrize("bot", [greedy_bot, score_aware_bot, lookahead_bot])
def test_bots_decline_a_floodgate_not_worth_the_bribe(bot):
    assert bot(_gate_turn(50), "p1", random.Random(0)) == DeclineFace()


def test_greedy_weighs_the_swing_against_the_bribe():
    # The best cut costs p2 a third of a malbec (split_points(6, 1) == 2): worth a bribe of 1, not 2.
    assert isinstance(greedy_bot(_gate_turn(1), "p1", random.Random(0)), PlaceFloodgate)
    assert greedy_bot(_gate_turn(2), "p1", random.Random(0)) == DeclineFace()


@pytest.mark.parametrize("players", [2, 4])
def test_optional_bribe_games_run_and_replay(players):
    preset = with_overrides(V3, bribe_optional=True, action_die_cost=3)
    start = new_game(players, 7, Mode.NORMAL, preset=preset)
    bots = {p.id: greedy_bot for p in start.players}
    final, log = play_game(start, bots, *game_rngs(7))
    gates = sum(isinstance(r.action, (PlaceFloodgate, Release)) for r in log)
    assert all(p.debt % 3 == 0 for p in final.players)
    assert sum(p.debt for p in final.players) == 3 * gates
    assert replay(start, log, game_rngs(7)[0]) == final


# --- tune.py ----------------------------------------------------------------------


def test_tune_v3bribe_sweep_covers_off_and_on_by_bribe():
    tune = _tune()
    (sweep,) = tune.v3bribe_sweeps()
    assert sweep.name == "v3bribe" and "v3bribe" in tune.SWEEP_NAMES
    for mode in Mode:
        candidates = dict(sweep.candidates[mode])
        assert len(candidates) == 10
        assert candidates["optional bribe 6"] == {"bribe_optional": True, "action_die_cost": 6}
        base = sweep.base[mode]
        assert base["bodega_building"] and not base["varietal_bodega"]
        assert base["blends"] == DEFAULT_BLENDS and base["action_die"] == V3_DIE_FACES
        for label, changes in candidates.items():
            job = tune.Job(label, mode, 2, "score_aware", {**base, **changes}, 1, 1)
            p = with_overrides(tune.shipped_preset(mode), **dict(tune.rules_of(job).overrides))
            assert p.planting is PlantingRules.VERTICES and not p.vertex_needs_three_canals
            assert p.bribe_optional is changes["bribe_optional"]


def test_tune_bribe_stats_and_row():
    tune = _tune()
    (sweep,) = tune.v3bribe_sweeps()
    changes = dict(sweep.candidates[Mode.FLASH])["optional bribe 1"]
    job = tune.Job("optional bribe 1", Mode.FLASH, 2, "greedy",
                   {**sweep.base[Mode.FLASH], **changes}, 3, 1)
    outcome = tune.run_chunk(job, 0, 3)
    stats = tune.bribe_stats(outcome.records)
    assert stats["used"] is None or 0 <= stats["used"] <= 1
    assert stats["placed"] >= 0 and stats["released"] >= 0
    data = tune.summarize(tune.rules_of(job), job.seed, outcome.records).to_json()
    data["blend_stats"] = tune.blend_stats(outcome.records)
    data["bribe_stats"] = stats
    assert tune.is_v3bribe(job.overrides)
    row = tune.v3_sweep_row(job, tune.Outcome("ok", data)) + tune._blend_columns(data) + tune._bribe_columns(data)
    assert row.count("|") == tune.V3_SWEEP_COLUMNS + tune.BLEND_COLUMNS + tune.BRIBE_COLUMNS + 1
