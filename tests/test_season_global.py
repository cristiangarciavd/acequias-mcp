"""A season roll that applies only the season faces (#138): ``season_roll_personal_faces`` off."""

import random

import pytest

from acequias.config import preset, with_overrides
from acequias.game import act
from acequias.model import DieFace, Mode, PieceKind, Player, SeasonRoll
from acequias.scoring import calculate_score
from acequias.setup import new_game
from acequias.sim import SimRules, play_one
from acequias.turn import DeclineFace, PlaceCanal, RollActionDie, legal_actions
from tests.test_season_die import EVERY2, H1, P, _overrides, state

PERSONAL = (DieFace.FLOODGATE, DieFace.RELEASE, DieFace.RESOW)
SEASON = (DieFace.GOOD_SEASON, DieFace.DROUGHT)


def _off(face, **kw):
    return with_overrides(P, action_die=(face,), season_roll_every=2, season_roll_personal_faces=False, **kw)


def test_the_option_is_on_by_default_and_a_bool():
    assert preset(Mode.NORMAL).season_roll_personal_faces is True
    assert preset(Mode.FLASH).season_roll_personal_faces is True
    with pytest.raises(TypeError):
        with_overrides(P, season_roll_personal_faces=0)


@pytest.mark.parametrize("face", PERSONAL)
def test_a_personal_face_on_the_season_roll_does_nothing(face):
    s = state(p=_off(face), season_roll=SeasonRoll.DUE, players=(Player("a", 1, 3), Player("b", 2)))
    rng, ref = random.Random(1), random.Random(1)
    ref.choice(s.preset.action_die)
    after = act(s, "a", RollActionDie(), rng)
    assert rng.getstate() == ref.getstate()  # one draw, as with the option on
    assert after.pending_face is None and after.season_roll is None
    assert after.board == s.board and after.players == s.players  # no cost, no change
    assert after.current_player == "a"  # the start player's own turn, as after a season face
    assert DeclineFace() not in legal_actions(after, "a")
    assert RollActionDie() in legal_actions(after, "a")
    moved = act(after, "a", PlaceCanal(PieceKind.STRAIGHT, H1, 0), random.Random(1))
    assert moved.current_player == "b"


@pytest.mark.parametrize("face", SEASON)
def test_a_season_face_on_the_season_roll_applies_as_before(face):
    on = with_overrides(P, action_die=(face,), season_roll_every=2)
    s_off = state(p=_off(face), season_roll=SeasonRoll.DUE)
    s_on = state(p=on, season_roll=SeasonRoll.DUE)
    off_after = act(s_off, "a", RollActionDie(), random.Random(1))
    on_after = act(s_on, "a", RollActionDie(), random.Random(1))
    assert off_after.players == on_after.players
    assert all((pl.season, pl.drought) != (0, 0) for pl in off_after.players)
    assert off_after.season_roll is None and off_after.current_player == "a"


@pytest.mark.parametrize("face", PERSONAL)
def test_a_voluntary_roll_still_offers_the_personal_faces(face):
    s = state(p=_off(face))
    after = act(s, "a", RollActionDie(), random.Random(1))
    assert after.pending_face is face and after.season_roll is None
    assert DeclineFace() in legal_actions(after, "a")
    assert after.player("a").debt == P.action_die_cost


def test_the_log_names_an_ignored_personal_face():
    p = with_overrides(P, action_die=(DieFace.RELEASE,), season_roll_every=1)
    rules = SimRules(Mode.FLASH, 2, ("greedy", "greedy"), _overrides(p, season_roll_personal_faces=False))
    record = play_one(rules, 3)  # greedy never rolls by choice: every roll is a season roll
    rolls = [r for r in record.log if isinstance(r.action, RollActionDie)]
    assert len(rolls) == preset(Mode.FLASH).rounds_for(2)
    assert all(r.face is DieFace.RELEASE for r in rolls)
    assert not any(isinstance(r.action, DeclineFace) for r in record.log)  # nothing was pending


@pytest.mark.parametrize("policy", ["random", "greedy", "saboteur", "score_aware", "lookahead"])
def test_bots_play_legal_games_with_the_option_off(policy):
    rules = SimRules(Mode.FLASH, 3, (policy,) * 3,
                     _overrides(EVERY2, action_die_cost=1, season_roll_personal_faces=False))
    record = play_one(rules, 2)  # every action goes through act, which rejects an illegal one
    assert calculate_score(record.final) == record.scores
