"""scripts/tune.py support for #103's Rules v2 sweeps (#125).

Small runs only (2-player Flash, a few games), so the suite stays fast.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from acequias.config import (
    BribeRules,
    action_die_rules,
    preset,
    roulette_rules,
    scaled,
    with_overrides,
)
from acequias.model import DieFace, Mode, PieceKind, Varietal
from acequias.sim import SimRules, simulate_game

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
TUNE = SCRIPTS / "tune.py"
sys.path.insert(0, str(SCRIPTS))
tune = importlib.import_module("tune")


def run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TUNE), "--mode", "flash", "--players", "2", "--workers", "2", *args],
        capture_output=True, text=True, encoding="utf-8", timeout=300,
    )


def result(mode: Mode, players: int, seating: str, overrides, n: int, seed: int) -> dict:
    job = tune.Job("t", mode, players, seating, overrides, n, seed)
    return simulate_game(tune.rules_of(job), n, seed).to_json()


def test_new_seatings_put_one_bot_in_every_seat():
    assert set(tune.SEATINGS) == {"greedy", "mixed", "score_aware", "lookahead"}
    for players in tune.PLAYER_COUNTS:
        assert tune.policies("score_aware", players) == ("score_aware",) * players
        assert tune.policies("lookahead", players) == ("lookahead",) * players
    with pytest.raises(ValueError):
        tune.policies("random", 2)


# Numbers of the greedy and mixed seatings before #125 (3 games, SWEEP_SEED, SWEEP_BASE).
BEFORE = {
    ("greedy", Mode.FLASH, 3): (("greedy",) * 3, [0.611111111111111, 0.1111111111111111, 0.27777777777777773],
                                0.4444444444444444, 13.333333333333334),
    ("greedy", Mode.NORMAL, 2): (("greedy",) * 2, [0.5, 0.5], 0.8333333333333334, 10.666666666666666),
    ("mixed", Mode.FLASH, 3): (("saboteur", "greedy", "saboteur"), [1 / 3] * 3, 0.0, 14.0),
    ("mixed", Mode.NORMAL, 2): (("saboteur", "greedy"), [0.6666666666666666, 0.3333333333333333],
                                0.3333333333333333, 10.666666666666666),
}


@pytest.mark.parametrize("key", BEFORE)
def test_greedy_and_mixed_give_the_same_numbers_as_before(key):
    seating, mode, players = key
    seats, by_position, total, canals = BEFORE[key]
    assert tune.policies(seating, players) == seats
    data = result(mode, players, seating, tune.SWEEP_BASE[mode], 3, tune.SWEEP_SEED)
    assert data["win_rate_by_position"] == pytest.approx(by_position)
    assert data["score_terms"]["total"]["mean"] == pytest.approx(total)
    assert data["actions_per_game"]["canal"] == pytest.approx(canals)


@pytest.mark.parametrize("mode", list(Mode))
def test_v2_base_is_roulette_then_action_die_rules(mode):
    expected = action_die_rules(roulette_rules(preset(mode)))
    assert with_overrides(preset(mode), **tune.V2_BASE[mode]) == expected
    assert expected.bag_mix[PieceKind.FLOODGATE] == 0


@pytest.mark.parametrize("mode", list(Mode))
def test_v2_candidates_express_scale_points_die_and_board(mode):
    v2 = action_die_rules(roulette_rules(preset(mode)))
    assert with_overrides(preset(mode), **tune.v2(mode)) == v2
    assert with_overrides(preset(mode), **tune.v2(mode, 3)) == scaled(v2, 3)
    p = with_overrides(preset(mode), **tune.v2(mode, 2, 1))
    assert p.varietal_points[Varietal.BONARDA] == p.varietal_points[Varietal.CABERNET_FRANC] == 5
    assert p.varietal_points[Varietal.MALBEC] == 4 and p.bodega_points == 2 * preset(mode).bodega_points
    faces = tune.die_faces(3, 2, 1)
    p = with_overrides(preset(mode), **tune.v2(
        mode, action_die_cost=1, action_die=faces, vineyards_per_player=3,
        grape_clusters_per_player=2, hexes_per_player=18))
    assert (p.action_die_cost, p.action_die, p.vineyards_per_player, p.grape_clusters_per_player,
            p.hexes_per_player) == (1, faces, 3, 2, 18)
    assert faces.count(DieFace.FLOODGATE) == 3 and faces.count(DieFace.RESOW) == 1


def test_phase_b_sweeps_are_listed_with_new_seeds(capsys):
    assert tune.V2_SWEEP_SEED == 103_001 and tune.V2_FINAL_SEED == 103_002
    assert {tune.V2_SWEEP_SEED, tune.V2_FINAL_SEED}.isdisjoint({tune.SWEEP_SEED, tune.FINAL_SEED})
    v2 = {s.name: s for s in tune.v2_sweeps()}
    assert list(v2) == ["b0", "b1", "b2", "b3", "b4"]
    for sweep in v2.values():
        assert sweep.seed == tune.V2_SWEEP_SEED and sweep.seatings == ("score_aware",)
    assert v2["b0"].base == {mode: {} for mode in Mode}
    assert v2["b1"].base == tune.V2_BASE
    assert [len(v2["b2"].candidates[m]) for m in Mode] == [5, 5]
    assert [len(v2["b3"].candidates[m]) for m in Mode] == [7, 7]
    assert (len(v2["b4"].candidates[Mode.NORMAL]), len(v2["b4"].candidates[Mode.FLASH])) == (8, 2)
    assert tune.main(["--list"]) == 0
    out = capsys.readouterr().out
    for name in v2:
        assert f"\n{name}: " in out
    assert "no die" in out


@pytest.mark.parametrize("mode", list(Mode))
def test_no_die_candidate_never_offers_the_die_or_a_bribe(mode):
    label, changes = tune.v2_sweeps()[3].candidates[mode][-1]
    assert label.startswith("no die")
    p = with_overrides(preset(mode), **{**tune.V2_BASE[mode], **changes})
    assert p.bribe_rules is BribeRules.D6 and p.bag_mix[PieceKind.FLOODGATE] == 0


def test_b3_and_b4_follow_the_best_scale():
    b3 = tune.v2_sweeps(2, 2)[3]
    for label, changes in b3.candidates[Mode.FLASH]:
        if label.startswith("cost 0"):
            continue  # Preset rejects cost 0 (#125 comment); the run reports it as infeasible
        assert with_overrides(preset(Mode.FLASH), **{**b3.base[Mode.FLASH], **changes}).varietal_points[
            Varietal.BONARDA] == 6


def test_cost_weights_the_smart_seatings():
    jobs = {s: tune.Job("t", Mode.NORMAL, 5, s, {}, 100, 1) for s in tune.SEATINGS}
    greedy = tune._cost(jobs["greedy"])
    assert tune._cost(jobs["score_aware"]) == 10 * greedy
    assert tune._cost(jobs["lookahead"]) == 50 * greedy


def test_rows_under_v1_and_v2_rules():
    v1_job = tune.Job("v1", Mode.FLASH, 2, "greedy", {}, 3, tune.V2_SWEEP_SEED)
    v1 = tune.Outcome("ok", simulate_game(tune.rules_of(v1_job), 3, v1_job.seed).to_json())
    overrides = tune.v2(Mode.FLASH, 2, 2)
    v2_job = tune.Job("v2", Mode.FLASH, 2, "score_aware", overrides, 10, tune.V2_SWEEP_SEED)
    v2 = tune.Outcome("ok", simulate_game(tune.rules_of(v2_job), 10, v2_job.seed).to_json())

    # Varietals: one rate per key, 3 under fixed rules and 8 under roulette rules.
    assert tune._varietals(v1.data).count(", ") == 2
    assert tune._varietals(v2.data).count(", ") == 7
    # Die columns: "-" under d6 rules, numbers under action die rules.
    assert tune._die(v1.data) == ["-"] * 4
    assert v2.data["actions_per_game"]["die"] > 0, "the seed must roll the die"
    assert "-" not in tune._die(v2.data)
    # Turns are rounds x P; turns_per_game counts a die turn twice.
    turns = preset(Mode.FLASH).rounds[2] * 2
    assert tune._turns(v2_job, v2.data) == turns
    assert v2.data["turns_per_game"] == pytest.approx(turns + v2.data["actions_per_game"]["die"])

    for job, outcome in ((v1_job, v1), (v2_job, v2), (v1_job, tune.Outcome(tune.FAILED, error="x"))):
        assert tune.sweep_row(job, outcome).count("|") == tune.SWEEP_COLUMNS + 1
    for row, header in zip(tune.detail_rows(v2_job, v2), tune.DETAIL_HEADERS):
        assert row.count("|") == header.splitlines()[0].count("|")


def test_smoke_runs_every_new_sweep():
    done = run_script("--sweep", "b0", "b1", "b2", "b3", "b4", "--smoke")
    assert done.returncode == 0, done.stderr
    for name in ("b0", "b1", "b2", "b3", "b4"):
        assert f"## Sweep `{name}`" in done.stdout
    assert "failed" not in done.stdout


@pytest.mark.parametrize("seating", ["score_aware", "lookahead"])
def test_candidate_validation_with_each_new_seating(seating, tmp_path):
    done = run_script("--candidate", "b1", "Rules v2 provisional", "--seating", seating, "--games", "2",
                      "--checkpoint-dir", str(tmp_path))
    assert done.returncode == 0, done.stderr
    assert "## Final validation of `b1: Rules v2 provisional`" in done.stdout
    assert f"Seed {tune.V2_FINAL_SEED};" in done.stdout
    assert f"| flash | 2 | {seating} |" in done.stdout


def test_unknown_candidate_is_an_argument_error(capsys):
    with pytest.raises(SystemExit) as raised:
        tune.main(["--candidate", "b1", "nope"])
    assert raised.value.code == 2
    assert "no candidate" in capsys.readouterr().err


def test_rules_of_accepts_the_new_seatings():
    rules = tune.rules_of(tune.Job("t", Mode.FLASH, 3, "lookahead", {}, 1, 1))
    assert rules == SimRules(Mode.FLASH, 3, ("lookahead",) * 3)
