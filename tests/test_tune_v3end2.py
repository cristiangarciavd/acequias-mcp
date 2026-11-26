"""Sweep ``v3end2`` of scripts/tune.py (#181): rows, turn targets, table and summary columns.

No real sweep: a couple of 2-game Flash jobs run in process.
"""

from __future__ import annotations

import pytest

from acequias.config import EndCondition
from acequias.model import Mode
from acequias.sim import _preset
from test_split_scoring import _tune

tune = _tune()


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _sweep(name):
    (sweep,) = [s for s in tune.SWEEPS if s.name == name]
    return sweep


def test_v3end2_has_18_grid_rows_and_a_control_per_mode_and_count():
    sweep = _sweep("v3end2")
    assert sweep.seed == 181_001 and sweep.seatings == ("score_aware",)
    jobs = tune.sweep_jobs(sweep, list(Mode), 300)
    assert len(jobs) == 6 * 19
    for mode in Mode:
        labels = [label for label, _ in sweep.candidates[mode]]
        assert len(labels) == len(set(labels)) == 19
        assert labels[-1] == tune.V3END2_CONTROL
        assert sweep.base[mode]["end_conditions"] == tune.V3END2_TRIGGERS
        assert {k: v for k, v in sweep.base[mode].items() if k != "end_conditions"} == tune.v3end_base(mode)
    for job in jobs:  # every row builds a preset
        p = _preset(tune.rules_of(job))
        if job.label == tune.V3END2_CONTROL:
            assert p.triggers == () and p.vineyard_supply == {}
        else:
            assert p.triggers == tune.V3END2_TRIGGERS and p.max_spins in (2, 3)
            assert p.vineyard_supply[job.players] in tune.V3END2_SUPPLY[job.mode][job.players]
            assert p.target_for(job.players) in tune.V3END2_TARGETS[job.mode][job.players]


def test_v3end2c_reruns_the_confirm_rows():
    assert tune.V3END2_CONFIRM == () and _sweep("v3end2c").candidates[Mode.NORMAL] == ()
    picked = tuple(label for label, _ in tune.v3end2_candidates(Mode.NORMAL)[:3])
    _, confirm = tune.v3end2_sweeps(picked)
    assert confirm.name == "v3end2c" and confirm.seed == 181_002
    assert [label for label, _ in confirm.candidates[Mode.NORMAL]] == list(picked)
    assert Mode.FLASH not in confirm.candidates


def test_turn_targets_are_total_turns_per_game():
    targets = tune.V3END2_TURN_TARGETS
    assert targets[(Mode.FLASH, 2)] == (16, 24) and targets[(Mode.FLASH, 3)] == (24, 30)
    assert [targets[(Mode.NORMAL, p)] for p in (2, 3, 4, 5)] == [(24, 36), (30, 40), (36, 48), (40, 50)]
    for (mode, players), (low, _) in targets.items():
        assert low >= 8 * players  # the owner's floor: 8 turns per player
    assert tune.turn_target_verdict(Mode.NORMAL, 2, 24) == "pass"
    assert tune.turn_target_verdict(Mode.NORMAL, 2, 36.04) == "pass"  # displayed as 36.0
    assert tune.turn_target_verdict(Mode.NORMAL, 2, 36.1) == "FAIL"
    assert tune.turn_target_verdict(Mode.FLASH, 3, 23.9) == "FAIL"


@pytest.fixture(scope="module")
def rows():
    sweep = _sweep("v3end2")
    jobs = [j for j in tune.sweep_jobs(sweep, [Mode.FLASH], 2, [2])
            if j.label == tune.V3END2_CONTROL or j.label.startswith("supply lo (2=1,3=1), target lo")]
    return [(job, tune.Outcome("ok", data=tune.job_data(job, tune.run_chunk(job, 0, job.n).records)))
            for job in jobs]


def test_v3end2_rows_report_the_new_columns(rows):
    header = _cells(tune.END2_HEADER)
    assert len(header) == tune.END2_COLUMNS
    for job, outcome in rows:
        e = outcome.data["end2_stats"]
        assert "end_stats" not in outcome.data  # no per-round replay
        cells = dict(zip(header, _cells(tune.end2_row(job, outcome))))
        assert len(cells) == tune.END2_COLUMNS
        assert cells["Turns (per player)"] == f"{e['turns']:.1f} ({e['turns'] / 2:.1f})"
        assert cells["Minutes"] == f"{e['turns'] * tune.SECONDS_PER_TURN / 60:.0f}"
        assert cells["Turn target"].split()[0] == tune.turn_target_verdict(Mode.FLASH, 2, e["turns"])
        assert cells["Turn target"].endswith("(16-24)")
        assert cells["Lost turns per game"] == f"{e['lost']:.2f}"
        assert cells["Bodega rate"] == f"{e['bodega']:.3f}"
        if job.label == tune.V3END2_CONTROL:
            assert e["ended"] is None and cells["Supply / target / dead / cap"] == "-"
        else:
            assert sum(e["ended"].values()) == pytest.approx(1)
            assert cells["Supply / target / dead / cap"].count("/") == 3
    report = tune.end2_report(rows)
    assert report[0].startswith("- 2p: meet the turn target:")


def test_v3end2_summary_has_the_end2_columns(rows):
    families = tune.summary_families(rows)
    assert families == ("v3", "end2")
    header = tune.SUMMARY_COLUMNS + tune.SUMMARY_EXTRAS["v3"] + tune.SUMMARY_EXTRAS["end2"]
    section = "\n".join(tune.summary_section(rows, families))
    assert "| " + " | ".join(header) + " |" in section
    for job, outcome in rows:
        e = outcome.data["end2_stats"]
        named = dict(zip(header, _cells(tune.summary_row(job, outcome, families))))
        assert named["Turns"] == f"{round(e['turns'], 1):.1f}"
        assert named["Length"] == tune.turn_target_verdict(job.mode, job.players, e["turns"])
        assert named["Turns / P"] == f"{e['turns'] / job.players:.1f}"
        assert named["Lost turns / game"] == f"{e['lost']:.2f}"
        assert named["Bodega rate"] == f"{e['bodega']:.3f}"
        assert named["Supply / target / dead / cap"] == tune._ended_text(e["ended"])


def test_end2_stats_counts_each_trigger():
    job = tune.sweep_jobs(_sweep("v3end2"), [Mode.FLASH], 3, [2])[0]
    records = tune.run_chunk(job, 0, job.n).records
    stats = tune.end2_stats(records)
    names = [tune.END2_NAMES[r.final.end_trigger or EndCondition.ROUNDS] for r in records]
    assert stats["ended"] == {k: names.count(k) / 3 for k in tune.END2_NAMES.values()}
    assert stats["lost"] == sum(p.lost_turns for r in records for p in r.final.players) / 3
