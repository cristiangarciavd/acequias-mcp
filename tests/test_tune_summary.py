"""The fixed-format sweep summary of scripts/tune.py (``--summary PATH``, #179).

No real sweep: the runner is replaced by canned outcomes, except one 2-game
Flash job that checks a v3bribe row against the raw table.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from acequias.model import Mode

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS))
tune = importlib.import_module("tune")


@pytest.mark.parametrize(("advantage", "m", "verdict"), [
    (0.100, 0.050, "pass"),
    (0.1004, 0.0, "pass"),  # displayed as 0.100
    (0.101, 0.0, "FAIL"),
    (0.101, 0.001, "FAIL (within margin)"),  # 0.101 - 0.001 <= 0.10 < 0.101
    (0.150, 0.050, "FAIL (within margin)"),
    (0.151, 0.050, "FAIL"),
])
def test_advantage_verdict_boundary(advantage, m, verdict):
    assert tune.advantage_verdict(advantage, m) == verdict


def test_length_verdict_uses_target_turns():
    assert tune.length_verdict(Mode.NORMAL, 45) == "pass"
    assert tune.length_verdict(Mode.NORMAL, 60) == "pass"
    assert tune.length_verdict(Mode.NORMAL, 61) == "FAIL"
    assert tune.length_verdict(Mode.FLASH, 9.9) == "FAIL"


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def test_failed_job_row_keeps_its_label():
    job = tune.Job("broken", Mode.FLASH, 2, "score_aware", {}, 10, 1)
    outcome = tune.Outcome(tune.FAILED, error="boom")
    families = ("v3", "bribe")
    cells = _cells(tune.summary_row(job, outcome, families))
    assert cells[:3] == ["broken", "score_aware", "failed: boom"]
    assert len(cells) == len(tune.SUMMARY_COLUMNS) + 3 + 4
    assert cells[2] == tune._not_run(outcome)


def test_v3bribe_row_matches_the_raw_table():
    (sweep,) = [s for s in tune.SWEEPS if s.name == "v3bribe"]
    job = tune.sweep_jobs(sweep, [Mode.FLASH], 2, [2])[0]
    (outcome,) = tune.run_all([job], 1, None)
    assert outcome.status == "ok"
    rows = [(job, outcome)]
    families = tune.summary_families(rows)
    assert families == ("v3", "bribe")
    raw = _cells(tune.v3_sweep_row(job, outcome) + tune._blend_columns(outcome.data)
                 + tune._bribe_columns(outcome.data))
    cells = _cells(tune.summary_row(job, outcome, families))
    header = tune.SUMMARY_COLUMNS + tune.SUMMARY_EXTRAS["v3"] + tune.SUMMARY_EXTRAS["bribe"]
    assert len(cells) == len(header)
    named = dict(zip(header, cells))
    assert named["Candidate"] == job.label and named["Seating"] == "score_aware"
    assert named["Advantage ± 95%"] == raw[3]
    assert named["Turns"] == raw[6].split()[0]
    assert raw[9].startswith(named["Winning score"] + " ±")
    for extra in tune.SUMMARY_EXTRAS["v3"][::2] + tune.SUMMARY_EXTRAS["bribe"]:
        assert named[extra] in raw, extra
    assert named["Planted / P"] == raw[8]


def _fake_run(monkeypatch, outcome):
    monkeypatch.setattr(tune, "lower_priority", lambda: None)
    monkeypatch.setattr(tune, "run_all", lambda jobs, *a, **k: [outcome(job) for job in jobs])


def test_summary_absent_writes_nothing_and_stdout_is_unchanged(tmp_path, monkeypatch, capsys):
    _fake_run(monkeypatch, lambda job: tune.Outcome(tune.FAILED, error="x"))
    monkeypatch.chdir(tmp_path)
    args = ["--sweep", "b0", "v3bribe", "--mode", "flash", "--players", "2", "--smoke"]
    assert tune.main(args) == 1
    plain = capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []
    path = tmp_path / "out" / "summary.md"
    assert tune.main([*args, "--summary", str(path)]) == 1
    assert capsys.readouterr().out == plain
    assert [p.name for p in tmp_path.iterdir()] == ["out"]
    assert [p.name for p in path.parent.iterdir()] == ["summary.md"]
    text = path.read_text(encoding="utf-8")
    # Both sweeps, in run order, each headed by one line; every candidate has a row.
    headers = [line for line in text.splitlines() if line.startswith("## ")]
    assert headers == [
        "## Sweep `b0`: 10 games per row, seed 103001. Command: `uv run python scripts/tune.py --sweep b0`",
        "## Sweep `v3bribe`: 10 games per row, seed 168001. Command: `uv run python scripts/tune.py --sweep v3bribe`",
    ]
    assert text.startswith(headers[0])
    assert text.count("| failed: x |") == 1 + len(tune.V3BRIBE_COSTS) * 2


def test_interrupted_run_writes_no_summary(tmp_path, monkeypatch):
    def interrupt(job):
        raise KeyboardInterrupt
    _fake_run(monkeypatch, interrupt)
    path = tmp_path / "summary.md"
    assert tune.main(["--sweep", "b0", "--mode", "flash", "--smoke", "--summary", str(path)]) == 130
    assert not path.exists()


def test_candidate_run_writes_common_columns(tmp_path, monkeypatch, capsys):
    _fake_run(monkeypatch, lambda job: tune.Outcome(tune.INFEASIBLE, error="no board"))
    path = tmp_path / "s.md"
    tune.main(["--candidate", "v3bribe", "optional bribe 2", "--mode", "flash", "--players", "2",
               "--games", "3", "--checkpoint-dir", str(tmp_path / "ck"), "--summary", str(path)])
    capsys.readouterr()
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("## Final validation of `v3bribe: optional bribe 2`: games per row 2p 3, seed ")
    assert ('Command: `uv run python scripts/tune.py --candidate v3bribe "optional bribe 2" '
            '--mode flash --players 2 --games 3 --checkpoint-dir ') in lines[0]
    assert "--summary" not in lines[0]
    assert tune._cells(tune.SUMMARY_COLUMNS) in lines
    assert sum("| infeasible: no board |" in line for line in lines) == len(tune.V2_FINAL_SEATINGS)
