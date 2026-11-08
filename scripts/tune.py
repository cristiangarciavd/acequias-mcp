"""Tune the open parameters of README.md with the simulation (issue #20).

Usage (from the repo root):

    uv run python scripts/tune.py                    # final validation of PROPOSED
    uv run python scripts/tune.py --sweep board      # one candidate sweep
    uv run python scripts/tune.py --sweep all        # every sweep, in SWEEP order
    uv run python scripts/tune.py --mode flash --players 3 --seating mixed
    uv run python scripts/tune.py --list             # the sweeps and their candidates

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
on.

``--jobs`` runs configurations in parallel processes (one
``simulate_game`` call each); it changes only the wall time, never a
number. Wall times go to stderr, so stdout is identical between runs.

Standard library only. Not a test: it lives outside ``tests/``.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from collections.abc import Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
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

SWEEP_BASE: Mapping[Mode, Mapping[str, object]] = {
    Mode.NORMAL: {
        "rounds": LOW_ROUNDS[Mode.NORMAL],
        "hexes_per_player": 18,
        "stone_share": 0,
        "vineyard_distance": (4, 4),
    },
    Mode.FLASH: {
        "rounds": LOW_ROUNDS[Mode.FLASH],
        "hexes_per_player": 10,
        "stone_share": 0,
        "vineyard_distance": (3, 4),
    },
}
"""The overrides every sweep starts from (chosen from exploratory runs); each
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
        "Rounds per player count (2/3/4/5 players): current, low and high end of the length target",
        {
            mode: tuple(
                (f"{name}: {_rounds_label(r)}", {"rounds": r})
                for name, r in (
                    ("current", CURRENT_ROUNDS[mode]),
                    ("target low", LOW_ROUNDS[mode]),
                    ("target high", HIGH_ROUNDS[mode]),
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


def run_job(job: Job) -> tuple[dict | None, str | None, float]:
    """``(result JSON, None, seconds)``, or ``(None, error, seconds)`` if infeasible."""
    start = time.perf_counter()
    try:
        rules = SimRules(job.mode, job.players, policies(job.seating, job.players), job.overrides)
        result: SimResult = simulate_game(rules, job.n, job.seed)
    except ValueError as error:
        return None, str(error), time.perf_counter() - start
    return result.to_json(), None, time.perf_counter() - start


def _cost(job: Job) -> float:
    """A rough cost estimate, so the slowest jobs start first."""
    hexes = job.overrides.get("hexes_per_player", 12)
    return job.n * job.players**2 * hexes * (4 if job.seating == "mixed" else 1)


def run_all(jobs: list[Job], workers: int) -> list[tuple[dict | None, str | None]]:
    """Run ``jobs`` and return their outcomes in ``jobs`` order."""
    outcomes: list = [None] * len(jobs)
    started = time.perf_counter()
    order = sorted(range(len(jobs)), key=lambda i: -_cost(jobs[i]))
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(run_job, jobs[i]): i for i in order}
        for done, future in enumerate(as_completed(futures), 1):
            i = futures[future]
            data, error, seconds = future.result()
            outcomes[i] = (data, error)
            job = jobs[i]
            print(
                f"[{done}/{len(jobs)}] {job.mode.value} {job.players}p {job.seating} "
                f"{job.label}: {seconds:.0f} s (elapsed {time.perf_counter() - started:.0f} s)",
                file=sys.stderr,
                flush=True,
            )
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


def sweep_row(job: Job, data: dict | None, error: str | None) -> str:
    head = f"| {job.label} | {job.players} | {job.seating} |"
    if data is None:
        return f"{head} infeasible: {error} |" + " |" * 10
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


def detail_rows(job: Job, data: dict | None, error: str | None) -> list[str]:
    """The rows of the three final tables: balance and length, actions and bribes, scores."""
    name = f"{job.mode.value} | {job.players} | {job.seating}"
    if data is None:
        return [f"| {name} | infeasible: {error} |"] * 3
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
    "| Mode | P | Seating | Games | Advantage ± 95% | ≤ 0.10 | Win rate by position | Win rate by policy "
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


def do_sweep(sweep: Sweep, workers: int) -> None:
    jobs = [
        Job(label, mode, players, seating, {**SWEEP_BASE[mode], **changes}, SWEEP_GAMES, SWEEP_SEED)
        for mode in Mode
        for label, changes in sweep.candidates.get(mode, ())
        for players in PLAYER_COUNTS
        for seating in sweep.seatings
    ]
    outcomes = run_all(jobs, workers)
    print(f"## Sweep `{sweep.name}`: {sweep.title}\n")
    print(f"Command: `uv run python scripts/tune.py --sweep {sweep.name}`. "
          f"{SWEEP_GAMES} games per row, seed {SWEEP_SEED}.\n")
    for mode in Mode:
        rows = [(j, o) for j, o in zip(jobs, outcomes) if j.mode is mode]
        if not rows:
            continue
        print(f"### {mode.value.capitalize()}\n")
        print(f"Base: {describe(SWEEP_BASE[mode])}.\n")
        print(SWEEP_HEADER)
        print("|" + " --- |" * 14)
        for job, (data, error) in rows:
            print(sweep_row(job, data, error))
        print()


def do_final(workers: int, modes, players_list, seatings, n: int | None, seed: int) -> None:
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
        for job, (data, error) in zip(jobs, outcomes):
            print(detail_rows(job, data, error)[k])
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sweep", choices=(*SWEEP_NAMES, "all"), help="run one candidate sweep, or all")
    parser.add_argument("--mode", choices=[m.value for m in Mode], help="only this mode (final validation)")
    parser.add_argument("--players", type=int, choices=PLAYER_COUNTS, help="only this player count")
    parser.add_argument("--seating", choices=SEATINGS, help="only this seating")
    parser.add_argument("--games", type=int, help="games per configuration (default: the final count)")
    parser.add_argument("--seed", type=int, default=FINAL_SEED, help=f"run seed (default {FINAL_SEED})")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                        help="parallel processes; changes the wall time only")
    parser.add_argument("--list", action="store_true", help="list the sweeps and their candidates")
    args = parser.parse_args()

    started = time.perf_counter()
    if args.list:
        for sweep in SWEEPS:
            print(f"{sweep.name}: {sweep.title} [{', '.join(sweep.seatings)}]")
            for mode in Mode:
                for label, _ in sweep.candidates.get(mode, ()):
                    print(f"  {mode.value}: {label}")
        return
    if args.sweep:
        for sweep in SWEEPS if args.sweep == "all" else [s for s in SWEEPS if s.name == args.sweep]:
            do_sweep(sweep, args.jobs)
    else:
        do_final(
            args.jobs,
            [Mode(args.mode)] if args.mode else list(Mode),
            [args.players] if args.players else list(PLAYER_COUNTS),
            [args.seating] if args.seating else list(SEATINGS),
            args.games,
            args.seed,
        )
    print(f"total wall time {time.perf_counter() - started:.0f} s", file=sys.stderr)


if __name__ == "__main__":
    main()
