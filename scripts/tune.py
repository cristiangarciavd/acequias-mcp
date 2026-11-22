"""Tune the open parameters of README.md with the simulation (issues #20 and #103).

Usage (from the repo root):

    uv run python scripts/tune.py                    # final validation of PROPOSED
    uv run python scripts/tune.py --sweep board      # one candidate sweep
    uv run python scripts/tune.py --sweep all        # every sweep, in SWEEP order
    uv run python scripts/tune.py --mode flash --players 3 --seating mixed
    uv run python scripts/tune.py --list             # the sweeps and their candidates
    uv run python scripts/tune.py --sweep all --smoke   # quick check of the runner (10 games)

A light run, to keep using the PC meanwhile (``DEFAULT_WORKERS`` worker
processes, below-normal priority), and an overnight run with most threads:

    uv run python scripts/tune.py --sweep all
    uv run python scripts/tune.py --sweep all --workers 10

Every number comes from ``acequias.sim``: this script builds ``SimRules``
with ``overrides`` (``Preset`` field names, #22), plays game ``i`` of a
configuration as ``play_one(rules, game_seed(seed, i))``, and summarizes the
records in game order with ``summarize``, exactly what ``simulate_game``
does, so a result equals ``simulate_game(rules, n, seed)``. It reimplements
no rule and no statistic; the only arithmetic here is presentation (the 95%
margin of ``turn_order_advantage``, the pass share, and minutes at
``MINUTES_PER_TURN``).

Parallel games (#43): each configuration is split into chunks of
``CHUNK_GAMES`` games by game index, and the chunks of every configuration
share one pool of ``--workers`` processes (default ``DEFAULT_WORKERS``).
The main process and the workers run at below-normal OS priority. Every
game keeps its own seed, so the worker count, the chunk size, and resuming
change only the wall time, never a number. Progress (games done / total,
percent, elapsed time, ETA) goes to stderr; stdout carries only the tables.

Checkpoints: each finished chunk is saved in ``--checkpoint-dir`` (default
``output/tune-checkpoints/``, ignored by git). Stop a run at any time
(Ctrl+C) and run the same command again to resume: saved chunks are loaded,
not replayed. A chunk is reused only when its key matches: mode, players,
policies, overrides, seed, game range, and a SHA-256 of the ``acequias/``
sources, so after a code change or with other arguments old chunks are
ignored and replayed. ``--fresh`` ignores and overwrites the saved chunks
of this run. Old chunks are never cleaned up on their own: delete the
folder (e.g. ``rm -r output/tune-checkpoints``) when a report is done or
after code changes. ``--smoke`` saves and loads nothing.

A *configuration* is a mode, a player count (2 to 5), and a seating:
``greedy``, ``score_aware`` or ``lookahead`` (that bot in every seat;
``lookahead`` with its ``POLICIES`` defaults), or ``mixed`` (seats
alternate saboteur and greedy, seat 1 saboteur). Sweeps vary one or two
parameters around their base with ``SWEEP_GAMES`` games: #20's sweeps
around ``SWEEP_BASE`` from ``SWEEP_SEED``; #103's Rules v2 sweeps ``b0``
to ``b5`` and ``b3b`` (score_aware seating) around ``V2_BASE`` (``b0``: the shipped
presets) from ``V2_SWEEP_SEED``. ``b3``, ``b3b`` (#130: the constructive
die and the season roll), ``b4`` and ``b5`` (#132: B4's best board with
the constructive die and the season roll) run at B2's best
``--scale`` and ``--rare-bonus``. The final validation runs ``PROPOSED``
at ``final_games(players)`` games from ``FINAL_SEED``, a seed no sweep
uses; ``--candidate SWEEP LABEL`` validates one sweep candidate instead
(#103 phase D: seed ``V2_FINAL_SEED`` for a Rules v2 sweep):

    uv run python scripts/tune.py --sweep b0 b1 b2
    uv run python scripts/tune.py --sweep b3 b4 b5 --scale 2 --rare-bonus 1
    uv run python scripts/tune.py --candidate b1 "Rules v2 provisional"

Turns and minutes count turns (rounds x P), not log records: under action
die rules a die turn is 2 records, so ``turns_per_game`` would overcount. A candidate the preset or the board
generator rejects is printed as infeasible with its error, and the run goes
on. Any other error is reported with its configuration as failed, and the
run goes on too. A chunk whose worker process dies (killed, out of memory)
is run once more (``RETRIES``) in a process of its own, then fails only its
configuration; every table is still printed, and the exit status is 1 if
anything failed.

Standard library only. Not a test: it lives outside ``tests/``.
"""

from __future__ import annotations

import argparse
import copyreg
import dataclasses
import hashlib
import math
import multiprocessing
import os
import pickle
import signal
import sys
import time
import zlib
from collections import deque
from collections.abc import Mapping
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType

import acequias
from acequias.config import (
    CONSTRUCTIVE_DIE_FACES,
    ROULETTE_POINTS,
    BribeRules,
    Preset,
    action_die_rules,
    roulette_rules,
    scaled,
    with_overrides,
)
from acequias.config import preset as shipped_preset
from acequias.model import DieFace, Mode, PieceKind, Varietal
from acequias.sim import GameRecord, SimRules, game_seed, play_one, summarize

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
V2_SWEEP_SEED = 103_001
"""The run seed of every Rules v2 sweep (#103); no earlier run used it."""
V2_FINAL_SEED = 103_002
"""The run seed of the Rules v2 final validation (#103, ``--candidate``); no earlier run used it."""
PLAYER_COUNTS = (2, 3, 4, 5)
SEATINGS = ("greedy", "mixed", "score_aware", "lookahead")
"""Every seating ``--seating`` accepts; see ``policies``."""
V1_FINAL_SEATINGS = ("greedy", "mixed")
"""The seatings of the final validation of ``PROPOSED`` (#20)."""
V2_FINAL_SEATINGS = ("score_aware", "lookahead", "greedy")
"""The seatings of a ``--candidate`` validation (#103 phase D); greedy only for comparison with #20."""
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
    """The bot of each seat: ``mixed`` alternates saboteur/greedy from seat 1;
    ``greedy``, ``score_aware`` and ``lookahead`` (its ``POLICIES`` defaults)
    put that bot in every seat."""
    if seating in ("greedy", "score_aware", "lookahead"):
        return (seating,) * players
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

OWNER_HEXES = 15
"""Normal hexes per player decided by the owner on #20: at most about 75
terrain hexes for 5 players (the sweeps favoured 24, 120 hexes)."""
OWNER_ROUNDS_2P = 10
"""Normal 2-player rounds decided by the owner on #20 (10-12): the 2-player
board is full by about 8 rounds, so 10 keeps every real move and is the
shortest game; it misses the 45-60 minute target, a recorded gap."""

PROPOSED: Mapping[Mode, Mapping[str, object]] = {
    Mode.NORMAL: {
        **SWEEP_BASE[Mode.NORMAL],
        "hexes_per_player": OWNER_HEXES,
        "rounds": {**ROTATION_ROUNDS[Mode.NORMAL], 2: OWNER_ROUNDS_2P},
    },
    Mode.FLASH: dict(SWEEP_BASE[Mode.FLASH]),
}
"""The final values, as overrides of the shipped presets: what the default
command validates (see ``_docs/tuning-results.md`` for the reasons and the
owner's decisions)."""


# --- Rules v2 (#103) ---------------------------------------------------------


def _diff(p: Preset) -> dict[str, object]:
    """The fields of ``p`` that differ from its mode's shipped preset, as overrides."""
    shipped = shipped_preset(p.mode)
    return {
        f.name: getattr(p, f.name)
        for f in dataclasses.fields(Preset)
        if f.name != "mode" and getattr(p, f.name) != getattr(shipped, f.name)
    }


V2_PRESET: Mapping[Mode, Preset] = {mode: action_die_rules(roulette_rules(shipped_preset(mode))) for mode in Mode}
"""The shipped preset with ``roulette_rules`` and then ``action_die_rules`` (bag without floodgates)."""
V2_BASE: Mapping[Mode, Mapping[str, object]] = {mode: _diff(V2_PRESET[mode]) for mode in Mode}
"""The overrides every Rules v2 sweep starts from: ``V2_PRESET`` as overrides of the shipped preset."""
RARE_VARIETALS = (Varietal.BONARDA, Varietal.CABERNET_FRANC)
"""The varietals worth a bit more under roulette rules (owner goal 5 of #103)."""
COMMON_POINTS = min(ROULETTE_POINTS.values())
"""The points of a common varietal at scale 1 (``ROULETTE_POINTS``)."""
B3B_SEASON_EVERY: Mapping[Mode, tuple[int, ...]] = {Mode.NORMAL: (2, 3, 4), Mode.FLASH: (2,)}
"""Sweep b3b's ``season_roll_every`` values (#130): a season roll every X rounds."""
B5_SEASON_EVERY: Mapping[Mode, tuple[int, ...]] = {Mode.NORMAL: (3, 4), Mode.FLASH: (2, 3)}
"""Sweep b5's ``season_roll_every`` values (#132)."""
B5_BOARD: Mapping[Mode, Mapping[str, object]] = {
    Mode.NORMAL: {"vineyards_per_player": 2, "hexes_per_player": 18, "vineyard_distance": (4, 4)},
    Mode.FLASH: {},
}
"""Sweep b5's board: B4's best for Normal (2 plots, 18 hexes/player, distance 4, no cap);
Flash keeps its default board."""
NO_DIE = {"bribe_rules": BribeRules.D6}
"""Rules v2 with no action die and no bribe: d6 bribe rules, so the die is never
offered, and a bag without floodgates, so there is nothing to bribe."""


def v2(mode: Mode, scale: int = 1, rare_bonus: int | None = None, **changes: object) -> dict[str, object]:
    """Rules v2 overrides: ``V2_PRESET`` with ``scaled(scale)``; if
    ``rare_bonus`` is given, ``RARE_VARIETALS`` score the common value + it
    (``None`` keeps the scaled points, i.e. + ``scale``); then ``changes``
    (``Preset`` fields, e.g. ``action_die_cost``, ``action_die``,
    ``vineyards_per_player``, ``grape_clusters_per_player``,
    ``hexes_per_player``), unchecked, so a rejected candidate is reported
    as infeasible by the run."""
    p = scaled(V2_PRESET[mode], scale)
    if rare_bonus is not None:
        common = COMMON_POINTS * scale
        p = with_overrides(p, varietal_points={
            v: common + rare_bonus if v in RARE_VARIETALS else common for v in p.varietal_points
        })
    return {**_diff(p), **changes}


def die_faces(floodgate: int, release: int, resow: int) -> tuple[DieFace, ...]:
    """An action die with that many faces of each kind, in ``DieFace`` order."""
    return (DieFace.FLOODGATE,) * floodgate + (DieFace.RELEASE,) * release + (DieFace.RESOW,) * resow


# --- Sweeps ------------------------------------------------------------------


@dataclass(frozen=True)
class Sweep:
    """Candidates per mode, each a label and the overrides it changes from ``base``."""

    name: str
    title: str
    candidates: Mapping[Mode, tuple[tuple[str, Mapping[str, object]], ...]]
    seatings: tuple[str, ...] = ("greedy",)
    base: Mapping[Mode, Mapping[str, object]] = dataclasses.field(default_factory=lambda: SWEEP_BASE)
    seed: int = SWEEP_SEED


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
    Sweep(
        "combined",
        "The best single changes of the sweeps above, combined",
        {
            Mode.NORMAL: (
                ("base", {}),
                ("24 hexes/player", {"hexes_per_player": 24}),
                ("24 hexes/player, branchy bag", {"hexes_per_player": 24, "bag_mix": BAG_VERY_BRANCHY}),
                ("24 hexes/player, branchy bag, no stone",
                 {"hexes_per_player": 24, "bag_mix": BAG_VERY_BRANCHY, "stone_share": 0}),
                ("24 hexes/player, 3 vineyards/player", {"hexes_per_player": 24, "vineyards_per_player": 3}),
            ),
            Mode.FLASH: (
                ("base", {}),
                ("branchy bag", {"bag_mix": BAG_VERY_BRANCHY}),
                ("branchy bag, no stone", {"bag_mix": BAG_VERY_BRANCHY, "stone_share": 0}),
                ("branchy bag, +2 for 2 varietals",
                 {"bag_mix": BAG_VERY_BRANCHY, "bodega_points": 2, "bodega_varietals": 2}),
            ),
        },
    ),
    Sweep(
        "rounds2p",
        f"Normal 2-player rounds on the owner's board ({OWNER_HEXES} hexes/player); "
        "3-5 players keep the full rotations",
        {
            Mode.NORMAL: tuple(
                (f"{_rounds_label(r)}", {"hexes_per_player": OWNER_HEXES, "rounds": r})
                for r in ({**ROTATION_ROUNDS[Mode.NORMAL], 2: n} for n in (8, 10, 12, 24))
            ),
        },
    ),
)


def v2_sweeps(scale: int = 1, rare_bonus: int = 1) -> tuple[Sweep, ...]:
    """#103 phase B: score_aware seating, seed ``V2_SWEEP_SEED``. B3 and B4
    run at B2's best ``scale`` and ``rare_bonus`` (``--scale``,
    ``--rare-bonus``; the defaults are the provisional 2/3 points). B5
    (#132) combines the best of B2-B4: B4's best board (``B5_BOARD``) with
    the constructive die x cost x season roll, and no die, at the same
    scale and rare bonus."""
    best = f"scale {scale}, rare +{rare_bonus}"
    seats = ("score_aware",)
    shipped = {mode: {} for mode in Mode}

    def v2_sweep(name: str, title: str, candidates) -> Sweep:
        return Sweep(name, title, candidates, seats, V2_BASE, V2_SWEEP_SEED)

    def die_label(cost: int, faces: tuple[int, int, int]) -> str:
        return f"cost {cost}, faces {'/'.join(map(str, faces))}"

    return (
        Sweep("b0", "Rules v1 baseline: the shipped presets", {mode: (("shipped (Rules v1)", {}),) for mode in Mode},
              seats, shipped, V2_SWEEP_SEED),
        v2_sweep("b1", "Rules v2 provisional: cost 2, faces 2/2/2, points 2 / rare 3, scale 1, 2 plots, no cap",
                 {mode: (("Rules v2 provisional", {}),) for mode in Mode}),
        v2_sweep("b2", "Score scale x rare bonus (Bonarda and Cabernet Franc: common + 1 or common + scale)",
                 {mode: tuple(
                     (f"scale {k}, points {COMMON_POINTS * k} / rare {COMMON_POINTS * k + bonus}",
                      v2(mode, k, bonus))
                     for k, bonus in ((1, 1), (2, 1), (2, 2), (3, 1), (3, 3))
                 ) for mode in Mode}),
        v2_sweep("b3", f"Action die cost x faces (floodgate/release/resow), and no die; {best}",
                 {mode: tuple(
                     (die_label(cost, faces), v2(mode, scale, rare_bonus, action_die_cost=cost,
                                                 action_die=die_faces(*faces)))
                     for cost in (0, 1, 2)
                     for faces in ((2, 2, 2), (3, 2, 1))
                 ) + (("no die (no bribe either)", v2(mode, scale, rare_bonus, **NO_DIE)),) for mode in Mode}),
        v2_sweep("b3b", "Constructive die (floodgate/release/resow x2/good season/drought) x cost x "
                 f"season roll every X rounds, and no die; {best}",
                 {mode: tuple(
                     (f"constructive die, cost {cost}, season roll every {every}",
                      v2(mode, scale, rare_bonus, action_die=CONSTRUCTIVE_DIE_FACES,
                         action_die_cost=cost, season_roll_every=every))
                     for cost in (1, 2)
                     for every in B3B_SEASON_EVERY[mode]
                 ) + (("no die (no bribe either)", v2(mode, scale, rare_bonus, **NO_DIE)),) for mode in Mode}),
        v2_sweep("b4", f"Vineyard plots and board (distance 4); {best}",
                 {
                     Mode.NORMAL: tuple(
                         (f"{plots} plots, {hexes} hexes/player, cap {cap or 'none'}",
                          v2(Mode.NORMAL, scale, rare_bonus, vineyards_per_player=plots, hexes_per_player=hexes,
                             grape_clusters_per_player=cap, vineyard_distance=(4, 4)))
                         for plots in (2, 3)
                         for hexes in (15, 18)
                         for cap in (None, 2)
                     ),
                     Mode.FLASH: tuple(
                         (f"{plots} plots", v2(Mode.FLASH, scale, rare_bonus, vineyards_per_player=plots))
                         for plots in (2, 3)
                     ),
                 }),
        v2_sweep("b5", "Best board (Normal: 2 plots, 18 hexes/player) x constructive die x cost x "
                 f"season roll every X rounds, and no die; {best}",
                 {mode: tuple(
                     (f"constructive die, cost {cost}, season roll every {every}",
                      v2(mode, scale, rare_bonus, **B5_BOARD[mode], action_die=CONSTRUCTIVE_DIE_FACES,
                         action_die_cost=cost, season_roll_every=every))
                     for cost in (1, 2)
                     for every in B5_SEASON_EVERY[mode]
                 ) + (("no die (no bribe either)", v2(mode, scale, rare_bonus, **B5_BOARD[mode], **NO_DIE)),)
                  for mode in Mode}),
    )


V1_SWEEPS = SWEEPS
"""The sweeps of #20 (Rules v1, greedy and mixed seatings)."""
SWEEPS = V1_SWEEPS + v2_sweeps()
SWEEP_NAMES = tuple(s.name for s in SWEEPS)


# --- Running -----------------------------------------------------------------


DEFAULT_WORKERS = 3
"""Worker processes by default (capped at ``os.cpu_count()``): few enough
that the owner keeps using the PC. Heavy runs pass ``--workers``."""
CHUNK_GAMES = 25
"""Games per chunk: the unit of work of a worker, of progress, and of a checkpoint file."""
PROGRESS_SECONDS = 10
"""The longest time between two progress lines on stderr."""
POLL_SECONDS = 0.5
"""How often the main process wakes up, so Ctrl+C is handled promptly."""
CHECKPOINT_DIR = Path(__file__).resolve().parent.parent / "output" / "tune-checkpoints"
"""Where finished chunks are saved by default (``output/`` is ignored by git)."""
CHECKPOINT_FORMAT = 1
"""Part of every chunk key: bump it when the chunk file layout changes."""
BELOW_NORMAL_PRIORITY_CLASS = 0x4000
"""The Windows priority class of the run (Task Manager: "Below normal")."""
NICENESS = 10
"""The POSIX niceness of the run (``os.nice``): below normal."""


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
"""How many more times a chunk whose worker process died is run, in a process of its own."""
DIED = "worker process died"


@dataclass(frozen=True)
class Outcome:
    """A job's result JSON, or why it has none: ``status`` is ``"ok"``, ``INFEASIBLE``, or ``FAILED``."""

    status: str
    data: dict | None = None
    error: str | None = None


@dataclass(frozen=True)
class ChunkResult:
    """The records of games ``start`` to ``stop - 1`` of a job, or why there are none."""

    status: str
    records: list[GameRecord] | None = None
    error: str | None = None
    priority_warning: str | None = None


def _mapping_proxy(data: dict) -> MappingProxyType:
    return MappingProxyType(data)


# Game records hold read-only mappings, which pickle cannot send between
# processes or save on its own; this rebuilds them from a plain dict.
copyreg.pickle(MappingProxyType, lambda proxy: (_mapping_proxy, (dict(proxy),)))


def rules_of(job: Job) -> SimRules:
    return SimRules(job.mode, job.players, policies(job.seating, job.players), job.overrides)


# --- Priority ------------------------------------------------------------------


def lower_priority() -> str | None:
    """Lower this process to below-normal priority; return a warning if it cannot."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.GetCurrentProcess.restype = wintypes.HANDLE
            kernel32.SetPriorityClass.argtypes = (wintypes.HANDLE, wintypes.DWORD)
            kernel32.SetPriorityClass.restype = wintypes.BOOL
            if not kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            increment = NICENESS - os.nice(0)
            if increment > 0:
                os.nice(increment)
    except Exception as error:  # noqa: BLE001 - a warning, the run goes on
        return f"warning: could not lower the process priority ({type(error).__name__}: {error})"
    return None


def process_priority() -> int:
    """This process's priority: the Windows priority class, or the POSIX niceness."""
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetPriorityClass.argtypes = (wintypes.HANDLE,)
        kernel32.GetPriorityClass.restype = wintypes.DWORD
        return kernel32.GetPriorityClass(kernel32.GetCurrentProcess())
    return os.nice(0)


_worker_warning: str | None = None


def _init_worker() -> None:
    """Pool initializer: lower the priority (not inherited on purpose) and
    leave Ctrl+C to the main process, which stops the workers itself."""
    global _worker_warning
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    _worker_warning = lower_priority()


_warned = False


def warn_priority(warning: str | None) -> None:
    """Print the first priority warning of the run; the rest are the same news."""
    global _warned
    if warning and not _warned:
        _warned = True
        print(f"{warning}; running at normal priority", file=sys.stderr, flush=True)


def make_pool(workers: int) -> ProcessPoolExecutor:
    """A pool of ``workers`` spawned processes at below-normal priority."""
    return ProcessPoolExecutor(
        max_workers=workers, mp_context=multiprocessing.get_context("spawn"), initializer=_init_worker
    )


def _stop(pool: ProcessPoolExecutor) -> None:
    """Stop ``pool`` now: kill its workers so none outlives the run."""
    processes = list((getattr(pool, "_processes", None) or {}).values())
    for process in processes:
        process.terminate()
    pool.shutdown(wait=False, cancel_futures=True)
    for process in processes:
        process.join(5)


# --- Chunks ------------------------------------------------------------------


def run_chunk(job: Job, start: int, stop: int) -> ChunkResult:
    """Play games ``start`` to ``stop - 1`` of ``job`` in this process. Never
    raises: a rejected candidate is ``INFEASIBLE`` and any other exception is
    ``FAILED``, each with its message."""
    try:
        rules = rules_of(job)
    except ValueError as error:
        return ChunkResult(INFEASIBLE, error=str(error), priority_warning=_worker_warning)
    except Exception as error:  # noqa: BLE001 - reported with its job, the run goes on
        return ChunkResult(FAILED, error=f"{type(error).__name__}: {error}", priority_warning=_worker_warning)
    records = []
    for i in range(start, stop):
        seed = game_seed(job.seed, i)
        try:
            records.append(play_one(rules, seed))
        except ValueError as error:
            return ChunkResult(INFEASIBLE, error=f"game {i} (game seed {seed}): {error}",
                               priority_warning=_worker_warning)
        except Exception as error:  # noqa: BLE001 - reported with its job, the run goes on
            return ChunkResult(FAILED, error=f"game {i} (game seed {seed}): {type(error).__name__}: {error}",
                               priority_warning=_worker_warning)
    return ChunkResult("ok", records=records, priority_warning=_worker_warning)


def run_isolated(job: Job, start: int, stop: int) -> ChunkResult:
    """Run one chunk in a process of its own and wait for it, so a process
    that dies again fails this chunk alone."""
    pool = make_pool(1)
    try:
        return pool.submit(run_chunk, job, start, stop).result()
    except BrokenProcessPool as error:
        return ChunkResult(FAILED, error=f"{DIED}: {error}")
    except Exception as error:  # noqa: BLE001 - e.g. a result that cannot be pickled
        return ChunkResult(FAILED, error=f"{type(error).__name__}: {error}")
    finally:
        _stop(pool)


def chunks(n: int, size: int) -> list[tuple[int, int]]:
    """The game ranges ``(start, stop)`` of a job of ``n`` games."""
    return [(start, min(start + size, n)) for start in range(0, n, size)]


def source_fingerprint() -> str:
    """A SHA-256 of the ``acequias/`` sources: a code change invalidates every checkpoint."""
    root = Path(acequias.__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        digest.update(path.relative_to(root).as_posix().encode() + b"\0")
        digest.update(path.read_bytes() + b"\0")
    return digest.hexdigest()


def _canonical(value: object) -> str:
    """A stable text for an override value: mappings sorted by key, sequences as tuples."""
    if isinstance(value, Mapping):
        items = sorted((repr(k), _canonical(v)) for k, v in value.items())
        return "{" + ", ".join(f"{k}: {v}" for k, v in items) + "}"
    if isinstance(value, (list, tuple)):
        return "(" + ", ".join(_canonical(v) for v in value) + ")"
    return repr(value)


class Checkpoints:
    """Finished chunks saved in ``folder``, one file each, named by a hash of their key."""

    def __init__(self, folder: Path, fingerprint: str, fresh: bool = False) -> None:
        self.folder = Path(folder)
        self.fingerprint = fingerprint
        self.fresh = fresh

    def key(self, job: Job, start: int, stop: int) -> str:
        """Everything a chunk's records depend on."""
        return _canonical((
            CHECKPOINT_FORMAT, job.mode.value, job.players, policies(job.seating, job.players),
            job.overrides, job.seed, start, stop, self.fingerprint,
        ))

    def path(self, key: str) -> Path:
        return self.folder / f"{hashlib.sha256(key.encode()).hexdigest()[:40]}.chunk"

    def load(self, job: Job, start: int, stop: int) -> list[GameRecord] | None:
        """The saved records of a chunk, or None (never saved, ``fresh``, or unreadable)."""
        if self.fresh:
            return None
        key = self.key(job, start, stop)
        path = self.path(key)
        if not path.exists():
            return None
        try:
            saved_key, records = pickle.loads(zlib.decompress(path.read_bytes()))
            if saved_key != key or not isinstance(records, list) or len(records) != stop - start:
                raise ValueError("its key or game count does not match")
        except Exception as error:  # noqa: BLE001 - replayed, not fatal
            print(f"checkpoint {path} is unreadable ({type(error).__name__}: {error}); replaying its games",
                  file=sys.stderr, flush=True)
            return None
        return records

    def save(self, job: Job, start: int, stop: int, records: list[GameRecord]) -> None:
        """Save a chunk: written to a temporary name, then renamed, so a
        run killed mid-write never leaves a half-written chunk."""
        key = self.key(job, start, stop)
        path = self.path(key)
        temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            temporary.write_bytes(zlib.compress(pickle.dumps((key, records), pickle.HIGHEST_PROTOCOL)))
            os.replace(temporary, path)
        except OSError as error:
            print(f"warning: could not save checkpoint {path} ({error})", file=sys.stderr, flush=True)
            temporary.unlink(missing_ok=True)


def _clock(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"


class Progress:
    """Games done / total on stderr, with an ETA from the games played in this
    session (chunks loaded from checkpoints count as done, not in the rate)."""

    def __init__(self, total: int, loaded: int) -> None:
        self.total = total
        self.done = loaded
        self.played = 0
        self.started = time.perf_counter()
        self.shown = self.started

    def report(self, force: bool = False) -> None:
        now = time.perf_counter()
        if not force and now - self.shown < PROGRESS_SECONDS:
            return
        self.shown = now
        elapsed = now - self.started
        percent = 100 * self.done / self.total if self.total else 100.0
        eta = _clock((self.total - self.done) * elapsed / self.played) if self.played else "?"
        print(f"progress: {self.done}/{self.total} games ({percent:.1f}%), elapsed {_clock(elapsed)}, ETA {eta}",
              file=sys.stderr, flush=True)


SEATING_COST = {"greedy": 1, "mixed": 4, "score_aware": 10, "lookahead": 50}
"""Rough time per game of each seating relative to greedy (scheduling only)."""


def _cost(job: Job) -> float:
    """A rough cost estimate, so the slowest jobs start first."""
    hexes = job.overrides.get("hexes_per_player", 12)
    return job.n * job.players**2 * hexes * SEATING_COST[job.seating]


def describe_job(job: Job) -> str:
    """The configuration of ``job`` in one line, for progress and error reports."""
    return f"{job.mode.value} {job.players}p {job.seating} {job.label} (n={job.n}, seed={job.seed})"


def run_all(jobs: list[Job], workers: int, checkpoints: Checkpoints | None = None,
            chunk_games: int = CHUNK_GAMES) -> list[Outcome]:
    """Run ``jobs`` and return their outcomes in ``jobs`` order.

    The chunks of every job share one pool of ``workers`` processes; each
    job is summarized from its records in game order. A job never stops the
    run: an infeasible candidate or a failure is recorded with its error
    (that of its lowest failed chunk, so the report does not depend on
    timing) and its remaining chunks are skipped. A process that dies breaks
    the pool: the chunks it was running are run again (``RETRIES``) one at a
    time in a process of their own, so only the culprit fails. Finished
    chunks are saved in ``checkpoints`` (None: nothing is saved or loaded).
    Ctrl+C stops the workers and raises ``KeyboardInterrupt``."""
    parts = [chunks(job.n, chunk_games) for job in jobs]
    records: list[list[list[GameRecord] | None]] = [[None] * len(p) for p in parts]
    errors: list[dict[int, ChunkResult]] = [{} for _ in jobs]
    order = sorted(range(len(jobs)), key=lambda j: -_cost(jobs[j]))
    pending: deque[tuple[int, int]] = deque()
    loaded = 0
    for j in order:
        for c, (start, stop) in enumerate(parts[j]):
            saved = checkpoints.load(jobs[j], start, stop) if checkpoints else None
            if saved is None:
                pending.append((j, c))
            else:
                records[j][c] = saved
                loaded += stop - start
    progress = Progress(sum(job.n for job in jobs), loaded)
    if loaded:
        print(f"resumed {loaded} games from {checkpoints.folder}", file=sys.stderr, flush=True)
        progress.report(force=True)

    def size(j: int, c: int) -> int:
        start, stop = parts[j][c]
        return stop - start

    def finish(j: int, c: int, result: ChunkResult) -> None:
        warn_priority(result.priority_warning)
        if result.status == "ok":
            records[j][c] = result.records
            if checkpoints:
                checkpoints.save(jobs[j], *parts[j][c], result.records)
            progress.done += size(j, c)
            progress.played += size(j, c)
        else:
            if not errors[j]:
                print(f"{result.status.upper()} {describe_job(jobs[j])}: {result.error}",
                      file=sys.stderr, flush=True)
            errors[j][c] = result
            progress.total -= size(j, c)
        progress.report(force=True)

    pool = make_pool(workers)
    running: dict = {}
    try:
        while pending or running:
            while pending and len(running) < workers:
                j, c = pending.popleft()
                if errors[j]:
                    progress.total -= size(j, c)
                    continue
                running[pool.submit(run_chunk, jobs[j], *parts[j][c])] = (j, c)
            if not running:
                continue
            done, _ = wait(running, timeout=POLL_SECONDS, return_when=FIRST_COMPLETED)
            died = []
            for future in done:
                j, c = running.pop(future)
                try:
                    result = future.result()
                except BrokenProcessPool:
                    died.append((j, c))
                    continue
                except Exception as error:  # noqa: BLE001 - e.g. a result that cannot be pickled
                    result = ChunkResult(FAILED, error=f"{type(error).__name__}: {error}")
                finish(j, c, result)
            if died:
                # A dead worker breaks the whole pool: rerun every chunk it was
                # running, each alone, so only the one that dies again fails.
                died += running.values()
                running.clear()
                _stop(pool)
                for j, c in sorted(died):
                    if errors[j]:
                        progress.total -= size(j, c)
                        continue
                    print(f"RETRY {describe_job(jobs[j])} games {parts[j][c][0]}-{parts[j][c][1] - 1}: "
                          f"{DIED}", file=sys.stderr, flush=True)
                    finish(j, c, run_isolated(jobs[j], *parts[j][c]))
                pool = make_pool(workers)
            progress.report()
    except BaseException:
        _stop(pool)
        raise
    pool.shutdown()

    outcomes = []
    for j, job in enumerate(jobs):
        if errors[j]:
            first = errors[j][min(errors[j])]
            outcomes.append(Outcome(first.status, error=first.error))
            continue
        try:
            games = [record for part in records[j] for record in part]
            outcomes.append(Outcome("ok", data=summarize(rules_of(job), job.seed, games).to_json()))
        except Exception as error:  # noqa: BLE001 - reported with its job, the run goes on
            outcomes.append(Outcome(FAILED, error=f"{type(error).__name__}: {error}"))
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


TURNS_NOTE = (
    f"Turns are rounds x P, one per player turn; minutes assume {MINUTES_PER_TURN} minute per turn. "
    "A die turn is 2 log records (the roll, then its use), so `turns_per_game` is not used. "
    "Die columns: games with a roll, rolls per game, rolls per face (floodgate/release/resow), "
    "and the share of rolls used, not declined; \"-\" under d6 rules."
)
SWEEP_HEADER = (
    "| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins "
    "| Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points "
    "| Winner varietal rates | Bribe games | Win rate bribers / non-bribers | Mean debt "
    "| Die games | Rolls | Rolls per face | Die use rate |"
)
SWEEP_COLUMNS = 21


def _varietals(data: Mapping[str, object]) -> str:
    """One rate per varietal in play (the keys of ``winner_varietal_rate``)."""
    return ", ".join(f"{v} {rate:.2f}" for v, rate in data["winner_varietal_rate"].items())


def _turns(job: Job, data: Mapping[str, object]) -> int:
    """Turns per game: rounds x P (every game plays every round)."""
    return data["preset"]["rounds"][str(job.players)] * job.players


def _die(data: Mapping[str, object]) -> list[str]:
    """Games with a roll, rolls per game, rolls per face, and the use rate; "-" under d6 rules."""
    if data["preset"]["bribe_rules"] == BribeRules.D6.value:
        return ["-"] * 4
    faces = data["die_faces_per_game"]
    return [
        f"{data['games_with_die']:.3f}",
        f"{data['actions_per_game']['die']:.2f}",
        " / ".join(f"{faces[f.value]:.2f}" for f in DieFace),
        _f(data["die_use_rate"], 3),
    ]


def _not_run(outcome: Outcome) -> str:
    return f"{outcome.status}: {outcome.error}"


def sweep_row(job: Job, outcome: Outcome) -> str:
    head = f"| {job.label} | {job.players} | {job.seating} |"
    data = outcome.data
    if data is None:
        return f"{head} {_not_run(outcome)} |" + " |" * (SWEEP_COLUMNS - 4)
    a = data["actions_per_game"]
    turns = _turns(job, data)
    return (
        f"{head} {data['turn_order_advantage']:.3f} ± {margin(job.players, job.n):.3f} "
        f"| {_list(data['win_rate_by_position'])} | {_f(data['shared_win_rate'])} "
        f"| {turns} ({turns * MINUTES_PER_TURN}) | {a['pass'] / turns:.2f} "
        f"| {a['canal']:.1f} / {a['floodgate']:.2f} / {a['bribe']:.2f} / {a['pass']:.1f} "
        f"| {_spread(data['winning_score'])} | {_spread(data['score_terms']['total'])} "
        f"| {_f(data['bodega_rate'], 3)} | {data['score_terms']['bodega']['mean']:.3f} | {_varietals(data)} "
        f"| {_f(data['games_with_bribe'])} "
        f"| {_f(data['win_rate_bribers'], 3)} / {_f(data['win_rate_non_bribers'], 3)} "
        f"| {_f(data['score_terms']['debt']['mean'])} | {' | '.join(_die(data))} |"
    )


def detail_rows(job: Job, outcome: Outcome) -> list[str]:
    """The rows of the three final tables: balance and length, actions and the die, scores."""
    name = f"{job.mode.value} | {job.players} | {job.seating}"
    data = outcome.data
    if data is None:
        return [f"| {name} | {_not_run(outcome)} |"] * 3
    a = data["actions_per_game"]
    turns = _turns(job, data)
    adv = data["turn_order_advantage"]
    m = margin(job.players, job.n)
    low, high = TARGET_TURNS[job.mode]
    minutes = turns * MINUTES_PER_TURN
    by_policy = ", ".join(f"{k} {v:.3f}" for k, v in data["win_rate_by_policy"].items())
    varietals = _varietals(data)
    terms = data["score_terms"]
    return [
        f"| {name} | {job.n} | {adv:.3f} ± {m:.3f} | {'yes' if adv <= ADVANTAGE_TARGET else 'no'} "
        f"| {_list(data['win_rate_by_position'])} | {by_policy} | {data['shared_win_rate']:.3f} "
        f"| {turns} | {minutes} | {'yes' if low <= minutes <= high else 'no'} | {a['pass'] / turns:.2f} |",
        f"| {name} | {a['canal']:.2f} | {a['floodgate']:.2f} | {a['bribe']:.2f} | {a['pass']:.2f} "
        f"| {data['games_with_floodgate']:.3f} | {data['games_with_bribe']:.3f} "
        f"| {_f(data['win_rate_bribers'], 3)} | {_f(data['win_rate_non_bribers'], 3)} "
        f"| {terms['debt']['mean']:.2f} | {' | '.join(_die(data))} |",
        f"| {name} | {_spread(terms['total'])} | {_spread(data['winning_score'])} "
        f"| {terms['vineyards']['mean']:.2f} | {terms['bodega']['mean']:.3f} | {data['bodega_rate']:.3f} "
        f"| {terms['rights_paid']['mean']:.2f} | {varietals} |",
    ]


DETAIL_HEADERS = (
    "| Mode | P | Seating | Games | Advantage ± 95% | At most 0.10 | Win rate by position | Win rate by policy "
    "| Shared wins | Turns | Minutes | In length target | Pass share |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    "| Mode | P | Seating | Canal | Floodgate | Bribe | Pass | Games with floodgate | Games with bribe "
    "| Win rate bribers | Win rate non-bribers | Mean debt | Die games | Rolls | Rolls per face | Die use rate |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    "| Mode | P | Seating | Total (mean ± sd) | Winning score (mean ± sd) | Vineyard points "
    "| Bodega points | Bodega rate | Rights paid | Winner varietal rates |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
)
DETAIL_TITLES = ("Balance and length", "Actions, floodgates, bribes, and the action die", "Scores")


def describe(overrides: Mapping[str, object]) -> str:
    parts = []
    for key, value in overrides.items():
        if key == "rounds":
            value = "/".join(str(value[p]) for p in PLAYER_COUNTS)
        elif key == "bag_mix":
            value = _bag_label(value)
        elif key == "vineyard_distance":
            value = f"{value[0]}-{value[1]}"
        elif key == "varietal_points":
            value = "/".join(f"{v.name.lower()} {points}" for v, points in value.items())
        elif key == "action_die":
            value = "/".join(str(value.count(f)) for f in DieFace)
        elif isinstance(value, Enum):
            value = value.value
        parts.append(f"{key}={value}")
    return ", ".join(parts) or "(shipped preset)"


# --- Commands ----------------------------------------------------------------


def sweep_jobs(sweep: Sweep, modes, games: int, players_list=PLAYER_COUNTS, seatings=None) -> list[Job]:
    """The jobs of ``sweep``: its seatings unless ``seatings`` is given."""
    return [
        Job(label, mode, players, seating, {**sweep.base[mode], **changes}, games, sweep.seed)
        for mode in modes
        for label, changes in sweep.candidates.get(mode, ())
        for players in players_list
        for seating in seatings or sweep.seatings
    ]


def do_sweeps(sweeps: list[Sweep], run, modes, games: int, players_list=PLAYER_COUNTS, seatings=None,
              flags: str = "") -> list[Outcome]:
    """Run every job of ``sweeps`` with ``run`` (``run_all`` with the run's
    options) in one pool, so no core idles between sweeps, then print each
    sweep's table."""
    per_sweep = [sweep_jobs(sweep, modes, games, players_list, seatings) for sweep in sweeps]
    outcomes = run([job for jobs in per_sweep for job in jobs])
    at = 0
    for sweep, jobs in zip(sweeps, per_sweep):
        mine, at = outcomes[at:at + len(jobs)], at + len(jobs)
        print(f"## Sweep `{sweep.name}`: {sweep.title}\n")
        print(f"Command: `uv run python scripts/tune.py --sweep {sweep.name}{flags}`. "
              f"{games} games per row, seed {sweep.seed}. {TURNS_NOTE}\n")
        for mode in modes:
            rows = [(j, o) for j, o in zip(jobs, mine) if j.mode is mode]
            if not rows:
                continue
            print(f"### {mode.value.capitalize()}\n")
            print(f"Base: {describe(sweep.base[mode])}.\n")
            print(SWEEP_HEADER)
            print("|" + " --- |" * SWEEP_COLUMNS)
            for job, outcome in rows:
                print(sweep_row(job, outcome))
            print()
    return outcomes


def do_final(run, values: Mapping[Mode, Mapping[str, object]], players_list, seatings, n: int | None, seed: int,
             label: str = "proposed") -> list[Outcome]:
    """The final validation of ``values`` (overrides per mode; its modes are the ones run)."""
    jobs = [
        Job(label, mode, players, seating, values[mode], n or final_games(players), seed)
        for mode in values
        for players in players_list
        for seating in seatings
    ]
    outcomes = run(jobs)
    print(f"## Final validation of {'the proposed values' if label == 'proposed' else f'`{label}`'}\n")
    print(f"Seed {seed}; games per configuration: "
          + ", ".join(f"{p}p {n or final_games(p)}" for p in players_list)
          + f". {TURNS_NOTE}\n")
    for mode in values:
        print(f"- {mode.value.capitalize()}: {describe(values[mode])}")
    print()
    for k, (title, header) in enumerate(zip(DETAIL_TITLES, DETAIL_HEADERS)):
        print(f"### {title}\n")
        print(header)
        for job, outcome in zip(jobs, outcomes):
            print(detail_rows(job, outcome)[k])
        print()
    return outcomes


def find_candidate(sweeps, name: str, label: str, modes) -> tuple[Sweep, dict[Mode, Mapping[str, object]]]:
    """Sweep ``name``'s candidate ``label`` as full overrides per mode (those of ``modes`` that have it)."""
    sweep = next((s for s in sweeps if s.name == name), None)
    if sweep is None:
        raise ValueError(f"unknown sweep {name!r}")
    values = {
        mode: {**sweep.base[mode], **changes}
        for mode in modes
        for lab, changes in sweep.candidates.get(mode, ())
        if lab == label
    }
    if not values:
        labels = sorted({lab for mode in modes for lab, _ in sweep.candidates.get(mode, ())})
        raise ValueError(f"sweep {name!r} has no candidate {label!r}; its candidates are {labels}")
    return sweep, values


def _workers(text: str) -> int:
    value = int(text)
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be at least 1, got {value}")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--sweep", nargs="+", choices=(*SWEEP_NAMES, "all"),
                        help="run these candidate sweeps, or all of them")
    parser.add_argument("--mode", choices=[m.value for m in Mode], help="only this mode")
    parser.add_argument("--players", type=int, choices=PLAYER_COUNTS, help="only this player count")
    parser.add_argument("--seating", choices=SEATINGS,
                        help="only this seating (in a sweep: instead of the sweep's own seatings)")
    parser.add_argument("--candidate", nargs=2, metavar=("SWEEP", "LABEL"),
                        help="final validation of one sweep candidate (#103 phase D): seatings "
                             f"{', '.join(V2_FINAL_SEATINGS)}; seed {V2_FINAL_SEED} for a Rules v2 sweep")
    parser.add_argument("--scale", type=_workers, default=1,
                        help="the score scale of sweeps b3, b3b, b4 and b5: B2's best (default 1)")
    parser.add_argument("--rare-bonus", type=_workers, default=1,
                        help="Bonarda and Cabernet Franc score the common value + this in sweeps b3, b3b, b4 and b5: "
                             "B2's best (default 1)")
    parser.add_argument("--games", type=int,
                        help=f"games per configuration (default: {SWEEP_GAMES} in a sweep, the final count otherwise)")
    parser.add_argument("--smoke", action="store_true",
                        help=f"a quick check of the runner: {SMOKE_GAMES} games per configuration; "
                             "its numbers are not the report's; saves and loads no checkpoints")
    parser.add_argument("--seed", type=int,
                        help=f"run seed of the final validation (default {FINAL_SEED}; "
                             f"{V2_FINAL_SEED} for a Rules v2 --candidate)")
    parser.add_argument("--workers", type=_workers, default=min(DEFAULT_WORKERS, os.cpu_count() or 1),
                        help=f"worker processes, at below-normal priority (default {DEFAULT_WORKERS}, "
                             "capped at the CPU count); changes only the wall time, never a number")
    parser.add_argument("--chunk-games", type=_workers, default=CHUNK_GAMES,
                        help=f"games per chunk of work and checkpoint file (default {CHUNK_GAMES}); "
                             "changes only the wall time, never a number")
    parser.add_argument("--checkpoint-dir", type=Path, default=CHECKPOINT_DIR,
                        help="where finished chunks are saved (default output/tune-checkpoints/). "
                             "Run the same command again to resume a stopped run; delete the folder "
                             "to remove old checkpoints")
    parser.add_argument("--fresh", action="store_true",
                        help="ignore and overwrite the saved checkpoints of this run")
    parser.add_argument("--list", action="store_true", help="list the sweeps and their candidates")
    args = parser.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)  # tables appear as each sweep ends
    games = SMOKE_GAMES if args.smoke else args.games
    if games is not None and games < 1:
        parser.error("--games must be at least 1")
    modes = [Mode(args.mode)] if args.mode else list(Mode)
    sweeps = V1_SWEEPS + v2_sweeps(args.scale, args.rare_bonus)
    flags = "" if (args.scale, args.rare_bonus) == (1, 1) else f" --scale {args.scale} --rare-bonus {args.rare_bonus}"
    players_list = [args.players] if args.players else list(PLAYER_COUNTS)
    candidate = None
    if args.candidate:
        if args.sweep:
            parser.error("--candidate and --sweep cannot be combined")
        try:
            candidate = find_candidate(sweeps, *args.candidate, modes)
        except ValueError as error:
            parser.error(str(error))

    if args.list:
        for sweep in sweeps:
            print(f"{sweep.name}: {sweep.title} [{', '.join(sweep.seatings)}]")
            for mode in Mode:
                for label, _ in sweep.candidates.get(mode, ()):
                    print(f"  {mode.value}: {label}")
        return 0
    warn_priority(lower_priority())
    started = time.perf_counter()
    checkpoints = None if args.smoke else Checkpoints(args.checkpoint_dir, source_fingerprint(), args.fresh)

    def run(jobs: list[Job]) -> list[Outcome]:
        return run_all(jobs, args.workers, checkpoints, args.chunk_games)

    if args.smoke:
        print(f"SMOKE RUN ({SMOKE_GAMES} games per configuration): not the report's numbers\n")
    try:
        if args.sweep:
            chosen = [s for s in sweeps if "all" in args.sweep or s.name in args.sweep]
            outcomes = do_sweeps(chosen, run, modes, games or SWEEP_GAMES, players_list,
                                 [args.seating] if args.seating else None, flags)
        elif candidate:
            sweep, values = candidate
            seed = args.seed if args.seed is not None else (
                V2_FINAL_SEED if sweep.seed == V2_SWEEP_SEED else FINAL_SEED)
            outcomes = do_final(run, values, players_list,
                                [args.seating] if args.seating else list(V2_FINAL_SEATINGS),
                                games, seed, f"{sweep.name}: {args.candidate[1]}")
        else:
            outcomes = do_final(
                run,
                {mode: PROPOSED[mode] for mode in modes},
                players_list,
                [args.seating] if args.seating else list(V1_FINAL_SEATINGS),
                games,
                FINAL_SEED if args.seed is None else args.seed,
            )
    except KeyboardInterrupt:
        if checkpoints:
            print(f"\nInterrupted. Finished chunks are saved in {checkpoints.folder}; "
                  "re-run the same command to resume.", file=sys.stderr, flush=True)
        else:
            print("\nInterrupted. --smoke saves nothing; re-run the same command to start again.",
                  file=sys.stderr, flush=True)
        return 130
    failed = sum(o.status == FAILED for o in outcomes)
    print(f"total wall time {time.perf_counter() - started:.0f} s; {failed} failed job(s)", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
