"""Benchmark the simulation: wall time per game and a digest of every result.

Run it with ``uv run python scripts/bench_sim.py``: each benchmark runs
``REPEATS`` times in this process, and the best (lowest) wall time of
``simulate_game`` is printed, total and per game, with the SHA-256 of the
result's JSON. Equal digests before and after a change mean the results
did not move.

``--profile`` runs each benchmark once under ``cProfile`` instead and
prints the top functions by own time.
"""

from __future__ import annotations

import argparse
import cProfile
import hashlib
import json
import pstats
import time

from acequias.model import Mode
from acequias.sim import SimRules, simulate_game

BENCHMARKS = (
    ("B1", SimRules(Mode.NORMAL, 5, ("greedy",) * 5), 20),
    ("B2", SimRules(Mode.NORMAL, 5, ("saboteur", "greedy", "saboteur", "greedy", "saboteur")), 10),
)
"""Each benchmark: its name, the rules, and the number of games ``n``."""
SEED = 84
"""The run seed of every benchmark."""
REPEATS = 3
"""How many times each benchmark runs; the best wall time is printed."""
PROFILE_TOP = 15
"""How many functions ``--profile`` prints, by own time."""


def digest(result) -> str:
    """The SHA-256 of the result's JSON, keys sorted."""
    return hashlib.sha256(json.dumps(result.to_json(), sort_keys=True).encode()).hexdigest()


def bench() -> None:
    for name, rules, n in BENCHMARKS:
        times = []
        digests = set()
        for _ in range(REPEATS):
            start = time.perf_counter()
            result = simulate_game(rules, n, SEED)
            times.append(time.perf_counter() - start)
            digests.add(digest(result))
        if len(digests) != 1:
            raise SystemExit(f"{name}: the runs gave different results: {sorted(digests)}")
        best = min(times)
        print(
            f"{name}: {rules.mode.value} {rules.players}p {','.join(rules.policies)} "
            f"n={n} seed={SEED}"
        )
        print(f"  best of {REPEATS}: {best:.2f} s total, {best / n:.3f} s per game")
        print(f"  sha256: {digests.pop()}")


def profile() -> None:
    for name, rules, n in BENCHMARKS:
        print(f"{name}: one run under cProfile, top {PROFILE_TOP} by own time")
        profiler = cProfile.Profile()
        profiler.runcall(simulate_game, rules, n, SEED)
        pstats.Stats(profiler).sort_stats("tottime").print_stats(PROFILE_TOP)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--profile", action="store_true", help="profile each benchmark once instead of timing it"
    )
    args = parser.parse_args()
    profile() if args.profile else bench()


if __name__ == "__main__":
    main()
