"""Tune the open parameters of README.md with the simulation (issue #20).

Usage (from the repo root):

    uv run python scripts/tune.py                    # final validation of PROPOSED
    uv run python scripts/tune.py --sweep board      # one candidate sweep
    uv run python scripts/tune.py --sweep all        # every sweep, in SWEEP order
    uv run python scripts/tune.py --mode flash --players 3 --seating mixed
    uv run python scripts/tune.py --list             # the sweeps and their candidates
    uv run python scripts/tune.py --sweep all --smoke   # quick check of the runner (10 games)

Every number comes from ``acequias.sim.simulate_game``: this script builds
``SimRules`` with ``overrides`` (``Preset`` field names, #22), runs them,
and formats the ``SimResult`` fields. It reimplements no rule and no
statistic; the only arithmetic here is presentation (the 95% margin of
``turn_order_advantage``, the pass share, and minutes at
``MINUTES_PER_TURN``).

A *configuration* is a mode, a player count (2 to 5), and a seating:
``greedy`` (every seat greedy) or ``mixed`` (seats alternate saboteur and
greedy, seat 1 saboteur). Sweeps vary one or two parameters around
``SWEEP_BASE`` with ``SWEEP_GAMES`` games from ``SWEEP_SEED``; the final
validation runs ``PROPOSED`` at ``final_games(players)`` games from
``FINAL_SEED``, a seed no sweep uses. A candidate the preset or the board
generator rejects is printed as infeasible with its error, and the run goes
on. Any other error is reported with its configuration as failed, and the
run goes on too. Each configuration runs in a process of its own, so a
process that dies (killed, out of memory) fails only its configuration,
which is run once more; every table is still printed, and the exit status
is 1 if anything failed.

``--jobs`` runs that many configurations at a time (one process and one
``simulate_game`` call each); it changes only the wall time, never a
number. Wall times go to stderr, so stdout is identical between runs.

Standard library only. Not a test: it lives outside ``tests/``.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import threading
import time
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass

from acequias.model import Mode, PieceKind
from acequias.sim import SimResult, SimRules, simulate_game

# --- Constants ---------------------------------------------------------------

MINUTES_PER_TURN = 1
"""Assumed play time of one turn (README.md, Quality criteria); measured at the table in #70."""
SWEEP_SEED = 20_001
"""The run seed of every sweep."""
FINAL_SEED = 20_002
"""The run seed of the final validation; no sweep uses it."""
SWEEP_GAMES = 500
"""Games per configuration in a sweep."""
SMOKE_GAMES = 10
"""Games per configuration with ``--smoke``, a quick check that the runner works."""
PLAYER_COUNTS = (2, 3, 4, 5)
SEATINGS = ("greedy", "mixed")
ADVANTAGE_TARGET = 0.10
"""README.md, Quality criteria: turn-order advantage at most 10%."""
TARGET_TURNS = {Mode.NORMAL: (45, 60), Mode.FLASH: (10, 20)}
"""README.md, Quality criteria: 45-60 min (Normal) and 10-20 min (Flash) at 1 minute per turn."""


def final_games(players: int) -> int:
    """Games per configuration in the final validation: a 95% margin of at most 0.05."""
    return max(2000, 1600 * (players - 1))


def margin(players: int, n: int) -> float:
    """The 95% margin of ``turn_order_advantage`` with ``n`` games (issue #20)."""
    return 1.96 * math.sqrt((players - 1) / n)


def policies(seating: str, players: int) -> tuple[str, ...]:
    """The bot of each seat: all greedy, or saboteur/greedy alternating from seat 1."""
    if seating == "greedy":
        return ("greedy",) * players
    if seating == "mixed":
        return tuple("saboteur" if k % 2 == 0 else "greedy" for k in range(players))
    raise ValueError(f"unknown seating {seating!r}")


def rounds_for_turns(mode: Mode, end: str) -> dict[int, int]:
    """Rounds per player count at the low or high end of the mode's turn target."""
    low, high = TARGET_TURNS[mode]
    if end == "low":
        return {p: -(-low // p) for p in PLAYER_COUNTS}
    return {p: high // p for p in PLAYER_COUNTS}


def bag(straight, gentle, sharp, y, t, claw, floodgate) -> dict[PieceKind, int]:
    """A bag mix in percent, in README order."""
    return {
        PieceKind.STRAIGHT: straight,
        PieceKind.GENTLE_CURVE: gentle,
        PieceKind.SHARP_CURVE: sharp,
        PieceKind.SYMMETRIC_Y: y,
        PieceKind.T_BRANCH: t,
        PieceKind.CLAW: claw,
        PieceKind.FLOODGATE: floodgate,
    }


BAG_CURRENT = bag(40, 20, 15, 5, 5, 5, 10)
BAG_BRANCHY = bag(20, 15, 10, 15, 15, 15, 10)
BAG_VERY_BRANCHY = bag(10, 10, 5, 25, 20, 20, 10)
BAG_FEWER_GATES = bag(40, 20, 15, 10, 5, 5, 5)
BAG_MORE_GATES = bag(35, 20, 15, 5, 5, 5, 15)

LOW_ROUNDS = {mode: rounds_for_turns(mode, "low") for mode in Mode}
HIGH_ROUNDS = {mode: rounds_for_turns(mode, "high") for mode in Mode}
CURRENT_ROUNDS = {Mode.NORMAL: {p: 12 for p in PLAYER_COUNTS}, Mode.FLASH: {p: 5 for p in PLAYER_COUNTS}}
ROTATION_ROUNDS = {
    Mode.NORMAL: {2: 24, 3: 15, 4: 12, 5: 10},
    Mode.FLASH: {2: 6, 3: 6, 4: 4, 5: 4},
}
"""Rounds inside the length target that are a whole number of start-player
rotations (a multiple of the player count), so every seat starts a round
equally often. Flash with 5 players has none (5 rounds is 25 turns), so it
takes the target's high end, 4."""

SWEEP_BASE: Mapping[Mode, Mapping[str, object]] = {
    Mode.NORMAL: {
        "rounds": ROTATION_ROUNDS[Mode.NORMAL],
        "hexes_per_player": 18,
        "stone_share": 10,
        "vineyard_distance": (4, 4),
    },
    Mode.FLASH: {
        "rounds": ROTATION_ROUNDS[Mode.FLASH],
        "hexes_per_player": 14,
        "stone_share": 10,
        "vineyard_distance": (4, 4),
    },
}
"""The overrides every sweep starts from (chosen from an exploratory board sweep); each
sweep changes only the parameters it names. Unnamed fields keep the shipped
preset's values."""

PROPOSED: Mapping[Mode, Mapping[str, object]] = {
    Mode.NORMAL: dict(SWEEP_BASE[Mode.NORMAL]),
    Mode.FLASH: dict(SWEEP_BASE[Mode.FLASH]),
}
"""The proposed values, as overrides of the shipped presets: what the
default command validates."""


# --- Sweeps ------------------------------------------------------------------


@dataclass(frozen=True)
class Sweep:
    """Candidates per mode, each a label and the overrides it changes from ``SWEEP_BASE``."""

    name: str
    title: str
    candidates: Mapping[Mode, tuple[tuple[str, Mapping[str, object]], ...]]
    seatings: tuple[str, ...] = ("greedy",)


def _grid(distances, hexes) -> tuple[tuple[str, dict], ...]:
    return tuple(
        (f"distance {d[0]}-{d[1]}, {h} hexes/player", {"vineyard_distance": d, "hexes_per_player": h})
        for d in distances
        for h in hexes
    )


def _one(field: str, values, fmt=str) -> tuple[tuple[str, dict], ...]:
    return tuple((f"{field} = {fmt(v)}", {field: v}) for v in values)


def _bag_label(mix: Mapping[PieceKind, int]) -> str:
    return "/".join(str(mix[k]) for k in PieceKind)


def _rounds_label(rounds: Mapping[int, int]) -> str:
    return "rounds " + "/".join(str(rounds[p]) for p in PLAYER_COUNTS)


SWEEPS: tuple[Sweep, ...] = (
    Sweep(
        "board",
        "Vineyard distance x hexes per player (stone share from the base)",
        {
            Mode.NORMAL: _grid([(3, 4), (4, 4), (4, 5)], [12, 18, 24]),
            Mode.FLASH: _grid([(2, 3), (3, 4), (4, 4)], [7, 10, 14]),
        },
    ),
    Sweep(
        "stone",
        "Stone share (percent of non-river hexes)",
        {mode: _one("stone_share", [0, 5, 10, 15]) for mode in Mode},
    ),
    Sweep(
        "vineyards",
        "Vineyards per player",
        {mode: _one("vineyards_per_player", [2, 3]) for mode in Mode},
    ),
    Sweep(
        "bag",
        "Bag mix (straight/gentle/sharp/Y/T/claw/floodgate, percent)",
        {
            mode: tuple(
                (f"bag {_bag_label(mix)}", {"bag_mix": mix})
                for mix in (BAG_CURRENT, BAG_BRANCHY, BAG_VERY_BRANCHY, BAG_FEWER_GATES, BAG_MORE_GATES)
            )
            for mode in Mode
        },
    ),
    Sweep(
        "market",
        "Market size",
        {mode: _one("market_size", [3, 4, 5]) for mode in Mode},
    ),
    Sweep(
        "rounds",
        "Rounds per player count (2/3/4/5 players): current, low and high end of the length target, "
        "and whole start-player rotations",
        {
            mode: tuple(
                (f"{name}: {_rounds_label(r)}", {"rounds": r})
                for name, r in (
                    ("current", CURRENT_ROUNDS[mode]),
                    ("target low", LOW_ROUNDS[mode]),
                    ("target high", HIGH_ROUNDS[mode]),
                    ("full rotations", ROTATION_ROUNDS[mode]),
                )
            )
            for mode in Mode
        },
    ),
    Sweep(
        "die",
        "Bribe die faces, mixed seating (the saboteur bribes only when the swing beats (faces + 1) / 2)",
        {mode: _one("die_faces", [4, 6, 8], lambda v: f"d{v}") for mode in Mode},
        seatings=("mixed",),
    ),
    Sweep(
        "bodega",
        "Flash bodega bonus: points for watered vineyards of N distinct varietals "
        "(Normal's bodega rate is in the final validation)",
        {
            Mode.FLASH: (
                ("+1 for 3 varietals (current)", {"bodega_points": 1, "bodega_varietals": 3}),
                ("+2 for 2 varietals", {"bodega_points": 2, "bodega_varietals": 2}),
            ),
        },
        seatings=SEATINGS,
    ),
)
SWEEP_NAMES = tuple(s.name for s in SWEEPS)


# --- Running -----------------------------------------------------------------


@dataclass(frozen=True)
class Job:
    """One configuration to simulate."""

    label: str
    mode: Mode
    players: int
    seating: str
    overrides: Mapping[str, object]
    n: int
    seed: int


INFEASIBLE = "infeasible"
"""Outcome status: the preset or the board generator rejected the candidate (a ``ValueError``)."""
FAILED = "failed"
"""Outcome status: the run broke for another reason (a bug, or a worker process that died)."""
RETRIES = 1
"""How many more times a job whose worker process died is run, in a fresh process."""


@dataclass(frozen=True)
class Outcome:
    """A job's result JSON, or why it has none: ``status`` is ``"ok"``, ``INFEASIBLE``, or ``FAILED``."""

    status: str
    data: dict | None = None
    error: str | None = None
    seconds: float = 0.0


def run_job(job: Job) -> Outcome:
    """Run one job in this process. Never raises: a rejected candidate is
    ``INFEASIBLE`` and any other exception is ``FAILED``, each with its message."""
    start = time.perf_counter()
    try:
        rules = SimRules(job.mode, job.players, policies(job.seating, job.players), job.overrides)
        result: SimResult = simulate_game(rules, job.n, job.seed)
    except ValueError as error:
        return Outcome(INFEASIBLE, error=str(error), seconds=time.perf_counter() - start)
    except Exception as error:  # noqa: BLE001 - reported with its job, the run goes on
        return Outcome(FAILED, error=f"{type(error).__name__}: {error}", seconds=time.perf_counter() - start)
    return Outcome("ok", data=result.to_json(), seconds=time.perf_counter() - start)


def _cost(job: Job) -> float:
    """A rough cost estimate, so the slowest jobs start first."""
    hexes = job.overrides.get("hexes_per_player", 12)
    return job.n * job.players**2 * hexes * (4 if job.seating == "mixed" else 1)


def describe_job(job: Job) -> str:
    """The configuration of ``job`` in one line, for progress and error reports."""
    return f"{job.mode.value} {job.players}p {job.seating} {job.label} (n={job.n}, seed={job.seed})"


def run_isolated(job: Job) -> Outcome:
    """Run ``job`` in a process of its own and wait for it. A process that
    dies (killed, out of memory) breaks only its own one-worker pool, so it
    fails this job alone instead of every job sharing a pool with it."""
    try:
        with ProcessPoolExecutor(max_workers=1) as pool:
            return pool.submit(run_job, job).result()
    except BrokenProcessPool as error:
        return Outcome(FAILED, error=f"worker process died: {error}")
    except Exception as error:  # noqa: BLE001 - e.g. a result that cannot be pickled
        return Outcome(FAILED, error=f"{type(error).__name__}: {error}")


def run_all(jobs: list[Job], workers: int) -> list[Outcome]:
    """Run ``jobs``, ``workers`` at a time, and return their outcomes in ``jobs`` order.

    A job never stops the run: infeasible candidates and failures are
    recorded with their error and configuration. Each job runs in its own
    process (``run_isolated``), so a process that dies fails only its job;
    such a job is run again up to ``RETRIES`` times before it is recorded as
    ``FAILED``. Failures are listed on stderr at the end."""
    outcomes: list[Outcome | None] = [None] * len(jobs)
    started = time.perf_counter()
    lock = threading.Lock()

    def run(i: int) -> None:
        for attempt in range(RETRIES + 1):
            outcome = run_isolated(jobs[i])
            if not (outcome.status == FAILED and outcome.error.startswith("worker process died")):
                break
            if attempt < RETRIES:
                print(f"RETRY {describe_job(jobs[i])}: {outcome.error}", file=sys.stderr, flush=True)
        with lock:
            outcomes[i] = outcome
            done = sum(o is not None for o in outcomes)
            note = "" if outcome.status == "ok" else f" {outcome.status.upper()}: {outcome.error}"
            print(
                f"[{done}/{len(jobs)}] {describe_job(jobs[i])}: {outcome.seconds:.0f} s "
                f"(elapsed {time.perf_counter() - started:.0f} s){note}",
                file=sys.stderr,
                flush=True,
            )

    order = sorted(range(len(jobs)), key=lambda i: -_cost(jobs[i]))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as threads:
        for future in [threads.submit(run, i) for i in order]:
            future.result()
    for job, outcome in zip(jobs, outcomes):
        if outcome.status == FAILED:
            print(f"FAILED {describe_job(job)}: {outcome.error}", file=sys.stderr, flush=True)
    return outcomes


# --- Formatting --------------------------------------------------------------


def _f(x: float | None, digits: int = 2) -> str:
    return "n/a" if x is None else f"{x:.{digits}f}"


def _spread(s: Mapping[str, float]) -> str:
    return f"{s['mean']:.2f} ± {s['stdev']:.2f}"


def _list(xs) -> str:
    return " / ".join(f"{x:.2f}" for x in xs)


SWEEP_HEADER = (
    "| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins "
    "| Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bribe games | Mean debt |"
)


def _not_run(outcome: Outcome) -> str:
    return f"{outcome.status}: {outcome.error}"


def sweep_row(job: Job, outcome: Outcome) -> str:
    head = f"| {job.label} | {job.players} | {job.seating} |"
    data = outcome.data
    if data is None:
        return f"{head} {_not_run(outcome)} |" + " |" * 10
    a = data["actions_per_game"]
    turns = data["turns_per_game"]
    return (
        f"{head} {data['turn_order_advantage']:.3f} ± {margin(job.players, job.n):.3f} "
        f"| {_list(data['win_rate_by_position'])} | {_f(data['shared_win_rate'])} "
        f"| {turns:.0f} ({turns * MINUTES_PER_TURN:.0f}) | {a['pass'] / turns:.2f} "
        f"| {a['canal']:.1f} / {a['floodgate']:.2f} / {a['bribe']:.2f} / {a['pass']:.1f} "
        f"| {_spread(data['winning_score'])} | {_spread(data['score_terms']['total'])} "
        f"| {_f(data['bodega_rate'], 3)} | {_f(data['games_with_bribe'])} "
        f"| {_f(data['score_terms']['debt']['mean'])} |"
    )


def detail_rows(job: Job, outcome: Outcome) -> list[str]:
    """The rows of the three final tables: balance and length, actions and bribes, scores."""
    name = f"{job.mode.value} | {job.players} | {job.seating}"
    data = outcome.data
    if data is None:
        return [f"| {name} | {_not_run(outcome)} |"] * 3
    a = data["actions_per_game"]
    turns = data["turns_per_game"]
    adv = data["turn_order_advantage"]
    m = margin(job.players, job.n)
    low, high = TARGET_TURNS[job.mode]
    minutes = turns * MINUTES_PER_TURN
    by_policy = ", ".join(f"{k} {v:.3f}" for k, v in data["win_rate_by_policy"].items())
    varietals = " / ".join(f"{data['winner_varietal_rate'][v]:.2f}" for v in ("malbec", "bonarda", "torrontes"))
    terms = data["score_terms"]
    return [
        f"| {name} | {job.n} | {adv:.3f} ± {m:.3f} | {'yes' if adv <= ADVANTAGE_TARGET else 'no'} "
        f"| {_list(data['win_rate_by_position'])} | {by_policy} | {data['shared_win_rate']:.3f} "
        f"| {turns:.0f} | {minutes:.0f} | {'yes' if low <= minutes <= high else 'no'} | {a['pass'] / turns:.2f} |",
        f"| {name} | {a['canal']:.2f} | {a['floodgate']:.2f} | {a['bribe']:.2f} | {a['pass']:.2f} "
        f"| {data['games_with_floodgate']:.3f} | {data['games_with_bribe']:.3f} "
        f"| {_f(data['win_rate_bribers'], 3)} | {_f(data['win_rate_non_bribers'], 3)} "
        f"| {terms['debt']['mean']:.2f} |",
        f"| {name} | {_spread(terms['total'])} | {_spread(data['winning_score'])} "
        f"| {terms['vineyards']['mean']:.2f} | {terms['bodega']['mean']:.3f} | {data['bodega_rate']:.3f} "
        f"| {terms['rights_paid']['mean']:.2f} | {varietals} |",
    ]


DETAIL_HEADERS = (
    "| Mode | P | Seating | Games | Advantage ± 95% | At most 0.10 | Win rate by position | Win rate by policy "
    "| Shared wins | Turns | Minutes | In length target | Pass share |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    "| Mode | P | Seating | Canal | Floodgate | Bribe | Pass | Games with floodgate | Games with bribe "
    "| Win rate bribers | Win rate non-bribers | Mean debt |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    "| Mode | P | Seating | Total (mean ± sd) | Winning score (mean ± sd) | Vineyard points "
    "| Bodega points | Bodega rate | Rights paid | Winner has Malbec / Bonarda / Torrontés |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
)
DETAIL_TITLES = ("Balance and length", "Actions, floodgates, and bribes", "Scores")


def describe(overrides: Mapping[str, object]) -> str:
    parts = []
    for key, value in overrides.items():
        if key == "rounds":
            value = "/".join(str(value[p]) for p in PLAYER_COUNTS)
        elif key == "bag_mix":
            value = _bag_label(value)
        elif key == "vineyard_distance":
            value = f"{value[0]}-{value[1]}"
        parts.append(f"{key}={value}")
    return ", ".join(parts) or "(shipped preset)"


# --- Commands ----------------------------------------------------------------


def sweep_jobs(sweep: Sweep, modes, games: int) -> list[Job]:
    return [
        Job(label, mode, players, seating, {**SWEEP_BASE[mode], **changes}, games, SWEEP_SEED)
        for mode in modes
        for label, changes in sweep.candidates.get(mode, ())
        for players in PLAYER_COUNTS
        for seating in sweep.seatings
    ]


def do_sweeps(sweeps: list[Sweep], workers: int, modes, games: int) -> list[Outcome]:
    """Run every job of ``sweeps`` in one pool (so no core idles between
    sweeps), then print each sweep's table."""
    per_sweep = [sweep_jobs(sweep, modes, games) for sweep in sweeps]
    outcomes = run_all([job for jobs in per_sweep for job in jobs], workers)
    at = 0
    for sweep, jobs in zip(sweeps, per_sweep):
        mine, at = outcomes[at:at + len(jobs)], at + len(jobs)
        print(f"## Sweep `{sweep.name}`: {sweep.title}\n")
        print(f"Command: `uv run python scripts/tune.py --sweep {sweep.name}`. "
              f"{games} games per row, seed {SWEEP_SEED}.\n")
        for mode in modes:
            rows = [(j, o) for j, o in zip(jobs, mine) if j.mode is mode]
            if not rows:
                continue
            print(f"### {mode.value.capitalize()}\n")
            print(f"Base: {describe(SWEEP_BASE[mode])}.\n")
            print(SWEEP_HEADER)
            print("|" + " --- |" * 14)
            for job, outcome in rows:
                print(sweep_row(job, outcome))
            print()
    return outcomes


def do_final(workers: int, modes, players_list, seatings, n: int | None, seed: int) -> list[Outcome]:
    jobs = [
        Job("proposed", mode, players, seating, PROPOSED[mode], n or final_games(players), seed)
        for mode in modes
        for players in players_list
        for seating in seatings
    ]
    outcomes = run_all(jobs, workers)
    print("## Final validation of the proposed values\n")
    print(f"Seed {seed}; games per configuration: "
          + ", ".join(f"{p}p {n or final_games(p)}" for p in players_list)
          + f". Minutes assume {MINUTES_PER_TURN} minute per turn.\n")
    for mode in modes:
        print(f"- {mode.value.capitalize()}: {describe(PROPOSED[mode])}")
    print()
    for k, (title, header) in enumerate(zip(DETAIL_TITLES, DETAIL_HEADERS)):
        print(f"### {title}\n")
        print(header)
        for job, outcome in zip(jobs, outcomes):
            print(detail_rows(job, outcome)[k])
        print()
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sweep", nargs="+", choices=(*SWEEP_NAMES, "all"),
                        help="run these candidate sweeps, or all of them")
    parser.add_argument("--mode", choices=[m.value for m in Mode], help="only this mode")
    parser.add_argument("--players", type=int, choices=PLAYER_COUNTS,
                        help="only this player count (final validation)")
    parser.add_argument("--seating", choices=SEATINGS, help="only this seating (final validation)")
    parser.add_argument("--games", type=int,
                        help=f"games per configuration (default: {SWEEP_GAMES} in a sweep, the final count otherwise)")
    parser.add_argument("--smoke", action="store_true",
                        help=f"a quick check of the runner: {SMOKE_GAMES} games per configuration; "
                             "its numbers are not the report's")
    parser.add_argument("--seed", type=int, default=FINAL_SEED,
                        help=f"run seed of the final validation (default {FINAL_SEED})")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                        help="parallel processes; changes the wall time only")
    parser.add_argument("--list", action="store_true", help="list the sweeps and their candidates")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # tables appear as each sweep ends
    games = SMOKE_GAMES if args.smoke else args.games
    if games is not None and games < 1:
        parser.error("--games must be at least 1")
    modes = [Mode(args.mode)] if args.mode else list(Mode)

    started = time.perf_counter()
    if args.list:
        for sweep in SWEEPS:
            print(f"{sweep.name}: {sweep.title} [{', '.join(sweep.seatings)}]")
            for mode in Mode:
                for label, _ in sweep.candidates.get(mode, ()):
                    print(f"  {mode.value}: {label}")
        return 0
    if args.smoke:
        print(f"SMOKE RUN ({SMOKE_GAMES} games per configuration): not the report's numbers\n")
    if args.sweep:
        chosen = [s for s in SWEEPS if "all" in args.sweep or s.name in args.sweep]
        outcomes = do_sweeps(chosen, args.jobs, modes, games or SWEEP_GAMES)
    else:
        outcomes = do_final(
            args.jobs,
            modes,
            [args.players] if args.players else list(PLAYER_COUNTS),
            [args.seating] if args.seating else list(SEATINGS),
            games,
            args.seed,
        )
    failed = sum(o.status == FAILED for o in outcomes)
    print(f"total wall time {time.perf_counter() - started:.0f} s; {failed} failed job(s)", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
