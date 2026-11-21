"""The parallel, low-priority, resumable runner of scripts/tune.py (#43).

Small runs only (2-player Flash, a few games), so the suite stays fast.
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from acequias.model import Mode
from acequias.sim import simulate_game

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
TUNE = SCRIPTS / "tune.py"

# Imported by name with scripts/ on sys.path, so spawned workers (which get
# the parent's sys.path) can import it to run its functions.
sys.path.insert(0, str(SCRIPTS))
tune = importlib.import_module("tune")


def flash_job(seating: str = "greedy", n: int = 5, overrides=None, seed: int = 7) -> "tune.Job":
    return tune.Job("test", Mode.FLASH, 2, seating, overrides or {}, n, seed)


def run_script(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TUNE), "--mode", "flash", "--players", "2", *args],
        capture_output=True, text=True, encoding="utf-8", timeout=120,
    )


class _Die:
    """Kills the worker process that unpickles it."""

    def __reduce__(self):
        return (os._exit, (3,))


def test_worker_runs_below_normal_priority():
    pool = tune.make_pool(1)
    try:
        priority = pool.submit(tune.process_priority).result(timeout=60)
    finally:
        tune._stop(pool)
    if sys.platform == "win32":
        assert priority == tune.BELOW_NORMAL_PRIORITY_CLASS
    else:
        assert priority >= tune.NICENESS


def test_parallel_chunks_equal_simulate_game(tmp_path):
    jobs = [flash_job("greedy", 5), flash_job("mixed", 4)]
    store = tune.Checkpoints(tmp_path, "fingerprint")
    outcomes = tune.run_all(jobs, 2, store, chunk_games=2)
    for job, outcome in zip(jobs, outcomes):
        assert outcome.status == "ok"
        assert outcome.data == simulate_game(tune.rules_of(job), job.n, job.seed).to_json()
    assert len(list(tmp_path.glob("*.chunk"))) == 3 + 2
    assert not list(tmp_path.glob("*.tmp"))


def test_failures_are_reported_and_the_run_goes_on(capsys):
    ok = flash_job("greedy", 3)
    infeasible = flash_job("greedy", 3, {"hexes_per_player": -1})
    dies = flash_job("greedy", 2, {"marker": _Die()})
    outcomes = tune.run_all([ok, infeasible, dies], 2, None, chunk_games=1)
    assert outcomes[0].status == "ok"
    assert outcomes[0].data == simulate_game(tune.rules_of(ok), 3, ok.seed).to_json()
    assert outcomes[1].status == tune.INFEASIBLE
    assert outcomes[2].status == tune.FAILED and outcomes[2].error.startswith(tune.DIED)
    assert "RETRY" in capsys.readouterr().err


def test_checkpoint_key_covers_arguments_and_code(tmp_path, capsys):
    job = flash_job(n=2)
    records = tune.run_chunk(job, 0, 2).records
    store = tune.Checkpoints(tmp_path, "code-1")
    store.save(job, 0, 2, records)
    assert len(store.load(job, 0, 2)) == 2
    assert tune.Checkpoints(tmp_path, "code-2").load(job, 0, 2) is None
    assert tune.Checkpoints(tmp_path, "code-1", fresh=True).load(job, 0, 2) is None
    for other in (flash_job(n=2, seed=8), flash_job("mixed", n=2), flash_job(n=2, overrides={"stone_share": 0})):
        assert store.load(other, 0, 2) is None
    assert store.load(job, 0, 1) is None
    # A corrupt file is reported and replayed, not fatal.
    (path,) = tmp_path.glob("*.chunk")
    path.write_bytes(b"not a chunk")
    assert store.load(job, 0, 2) is None
    assert "unreadable" in capsys.readouterr().err


def test_workers_flag_rejects_zero_and_negative(capsys):
    for value in ("0", "-2"):
        with pytest.raises(SystemExit) as raised:
            tune.main(["--workers", value])
        assert raised.value.code == 2
    assert "--workers" in capsys.readouterr().err


def test_stdout_is_identical_across_workers_and_resume(tmp_path):
    args = ("--seating", "greedy", "--games", "7", "--chunk-games", "2")
    serial = run_script(*args, "--workers", "1", "--checkpoint-dir", str(tmp_path / "a"))
    parallel = run_script(*args, "--workers", "4", "--checkpoint-dir", str(tmp_path / "b"))
    assert serial.returncode == parallel.returncode == 0, serial.stderr + parallel.stderr
    assert serial.stdout == parallel.stdout
    assert "progress: 7/7 games (100.0%)" in parallel.stderr

    chunks = sorted((tmp_path / "b").glob("*.chunk"))
    assert len(chunks) == 4
    for path in chunks[:2]:
        path.unlink()
    resumed = run_script(*args, "--workers", "2", "--checkpoint-dir", str(tmp_path / "b"))
    assert resumed.returncode == 0, resumed.stderr
    assert resumed.stdout == serial.stdout
    assert "resumed" in resumed.stderr
    assert len(list((tmp_path / "b").glob("*.chunk"))) == 4


def test_smoke_writes_no_checkpoints(tmp_path):
    result = run_script("--seating", "greedy", "--smoke", "--workers", "1", "--checkpoint-dir", str(tmp_path / "c"))
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("SMOKE RUN")
    assert not (tmp_path / "c").exists()
