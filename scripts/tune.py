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
does, so a result equals ``simulate_game(rules, n, seed)`` plus one key of
its own, ``floodgates`` (``floodgate_stats``, #160, counted from the logs).
It reimplements no rule; the only other arithmetic here is presentation
(the 95% margin of ``turn_order_advantage``, the pass share, and minutes at
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

Every sweep is defined against the Rules v1 presets (``V1_PRESET``, the
presets shipped before #126), not the shipped Rules v2 ones, so each command
in ``_docs/tuning-results.md`` still plays the games it reported: a job's
overrides are applied over ``V1_OVERRIDES`` (``rules_of``). Sweep
``shipped`` plays the shipped presets themselves (``--candidate shipped
"shipped (Rules v2)"`` validates them). A player count a job's preset is not
for (its ``rounds`` has no entry: shipped Flash is for 2 or 3 players) is
skipped with a note on stderr; with ``--players`` it is an error.

A *configuration* is a mode, a player count (2 to 5), and a seating:
``greedy``, ``score_aware`` or ``lookahead`` (that bot in every seat;
``lookahead`` with its ``POLICIES`` defaults), or ``mixed`` (seats
alternate saboteur and greedy, seat 1 saboteur). Sweeps vary one or two
parameters around their base with ``SWEEP_GAMES`` games: #20's sweeps
around ``SWEEP_BASE`` from ``SWEEP_SEED``; #103's Rules v2 sweeps ``b0``
to ``b5`` and ``b3b`` (score_aware seating) around ``V2_BASE`` (``b0``: the Rules v1
presets) from ``V2_SWEEP_SEED``. ``b3``, ``b3b`` (#130: the constructive
die and the season roll), ``b4`` and ``b5`` (#132: B4's best board with
the constructive die and the season roll) run at B2's best
``--scale`` and ``--rare-bonus``; ``--multiple-bodegas`` (#135) turns on
``multiple_bodegas`` in every b5 candidate, for phase D, and
``--season-global-only`` (#138) turns ``season_roll_personal_faces`` off
in every b5 candidate (combinable). ``--seat-bonus`` (#142, e.g.
``4=1,1,1,0;5=1,1,1,0,0``) sets ``seat_bonus`` and ``--rounds`` (#142, e.g.
``4=5,5=5``) the round count of those player counts (the rest keep the
mode's Rules v1 rounds) in every b5 candidate, the same way. The final validation runs ``PROPOSED``
at ``final_games(players)`` games from ``FINAL_SEED``, a seed no sweep
uses; ``--candidate SWEEP LABEL`` validates one sweep candidate instead
(#103 phase D: seed ``V2_FINAL_SEED`` for a Rules v2 sweep):

    uv run python scripts/tune.py --sweep b0 b1 b2
    uv run python scripts/tune.py --sweep b3 b4 b5 --scale 2 --rare-bonus 1
    uv run python scripts/tune.py --candidate b1 "Rules v2 provisional"

Sweep ``strip`` (#154) plays Rules v3 on the open river strip board (the
shipped presets with vertex planting and ``board_shape`` ``river_strip``,
score_aware seating, seed ``STRIP_SWEEP_SEED``): river hexes per segment
(``--river-hexes``, default 4 5 6) x bag size in pieces per player
(``--bag-per-player``, default ``STRIP_BAG_PER_PLAYER``):

    uv run python scripts/tune.py --sweep strip
    uv run python scripts/tune.py --sweep strip --river-hexes 5 --bag-per-player 10 14

Sweep ``v3`` (#153) varies one Rules v3 value at a time around a river
strip base (``V3_RIVER_HEXES`` river hexes per segment and
``V3_BAG_PER_PLAYER`` pieces per player, or ``--v3-river-hexes`` and
``--v3-bag-per-player``, e.g. strip's best): rounds, action die cost (the
bribe), vineyard points (common / rare, with the bodega and water rights
in proportion), bodega points, the Rules v3 die with its move face
(``V3_DIE_FACES``, #160), river hexes per segment, and bag size;
score_aware seating, seed ``V3_SWEEP_SEED``.

Sweep ``v3split`` (#160) plays Rules v3 with split vineyard scoring at
``acequias.config.V3_POINTS`` (6 / rare 9) around a river strip base of
``V3SPLIT_RIVER_HEXES`` river hexes per segment and ``V3SPLIT_BAG_PER_PLAYER``
pieces per player. Each of 4 setups (``vertex_needs_three_canals`` off / on
x the Rules v3 die with a move face / the old die with 2 resows and no
move) runs its base and one value at a time: bag 20 and 24 per player, 6
river hexes per segment, bodega points 3 / 6 / 9 (the shipped value is the
base), rounds -2 and +2; score_aware seating, seed ``V3SPLIT_SWEEP_SEED``.
Rules v3 rows (sweeps ``strip``, ``v3`` and ``v3split``) get their own
columns: plants, canals and passes per game, planted vineyards per player,
die faces and uses, the bodega rate, and floodgates (placed per game, and
the most on the board at once: mean and max over games, to size the
physical floodgate supply):

    uv run python scripts/tune.py --sweep strip v3
    uv run python scripts/tune.py --sweep v3 --v3-river-hexes 6 --v3-bag-per-player 12
    uv run python scripts/tune.py --sweep v3split

Sweep ``v3blends`` (#166) compares the scoring options around the
``v3split`` base (5 river hexes per segment, bag 16 per player, split
scoring, the move die): the current 3-varietal bodega bonus, blends
(``acequias.config.DEFAULT_BLENDS``, #165's cortes, the bodega bonus off)
scored ``each_once`` or ``disjoint``, and ``each_once`` blends plus the
bodega building (2 distinct reds and 2 distinct whites, on a new spot),
each with its points x0.5 / x1 / x1.5 (``V3BLENDS_FACTORS``; the building
also at 15, ``V3BLENDS_BUILDING_POINTS``); score_aware seating, seed
``V3BLENDS_SWEEP_SEED``. Its rows add the blend and building points per
player, bodegas built per game, the share of players who meet the
bodega requirement, the mean round they first meet it and the share who
build (a building row runs with 2 reds and 2 or 1 whites,
``V3BLENDS_WHITES``), and how often each blend scores (share of
player-games). It runs with the round count end; ``v3end`` (#163) tries the
others:

    uv run python scripts/tune.py --sweep v3blends

Sweep ``v3bribe`` (#168) plays ``bribe_optional`` off and on x the bribe
(``action_die_cost``, ``V3BRIBE_COSTS``) around ``v3_best_base``, the best
#160/#166 setup (5 river hexes per segment, bag 16 per player, split
scoring, any-vertex planting, the move die, ``each_once`` blends with the
old bodega bonus off, and the bodega building: a new spot, 12 points, 2
reds + 2 whites); score_aware seating, seed ``V3BRIBE_SWEEP_SEED``. Its rows
add the blend columns, then floodgates placed and released per game, the
share of floodgate and release rolls used, the mean score swing of a
floodgate use (user less best rival, before the bribe), and the mean debt:

    uv run python scripts/tune.py --sweep v3bribe

Sweep ``v3end`` (#163) diagnoses the 4-5p seat bias and tries end of game
conditions around ``v3end_base`` (``v3_best_base`` with the round count end
written out; edit ``v3_best_base`` to move every v3 sweep), score_aware
seating, seed ``V3END_SWEEP_SEED``. Rows: the base; seats rotated and
shuffled per game (``SEAT_KEY``, a tune-only job key applied by
``play_seated``); the unlimited bag; and each end condition
(``bag_empty``, ``vineyards_out`` at the default markers, ``score_target``
at #160's winning scores x1 / x1.5 / x2) with ``finish_round`` on and off.
Its table has the advantage, win rate by position and by seat, shared
wins, turns counted from the log (and minutes), rounds played, the bodega
rate (a bonus or a building), the share of games the round cap ended and
the winning score; then one line per player count naming the rows under
``ADVANTAGE_BIAS_LIMIT``, and a per-round score trace by position for
every row, one table per player count (``end_stats``):

    uv run python scripts/tune.py --sweep v3end

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
import random
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
    DEFAULT_BLENDS,
    Blend,
    BlendRule,
    BodegaPlacement,
    CONSTRUCTIVE_DIE_FACES,
    V3_DIE_FACES,
    V3_POINTS as V3_SPLIT_POINTS,
    BoardShape,
    PlantingRules,
    ROULETTE_POINTS,
    RULES_V1,
    BribeRules,
    EndCondition,
    Preset,
    SCORE_TARGETS,
    action_die_rules,
    roulette_rules,
    scaled,
    with_overrides,
)
from acequias.config import players_text
from acequias.config import preset as shipped_preset
from acequias.model import DieFace, GameState, Mode, PieceKind, Varietal
from acequias.sim import GameRecord, SimRules, game_seed, play_one, summarize
from acequias.sim import _bots, _preset
from acequias.game import act, game_rngs, play_game, turn_order
from acequias.scoring import calculate_score, winners
from acequias.setup import new_game
from acequias.turn import BuildBodega, PlaceFloodgate, Release, RollActionDie, can_build_bodega

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

V1_PRESET: Mapping[Mode, Preset] = RULES_V1
"""The Rules v1 presets (``acequias.config.RULES_V1``): every sweep's base is defined against them."""


def diff_from(base: Preset, p: Preset) -> dict[str, object]:
    """The fields of ``p`` that differ from ``base`` (the same mode), as overrides."""
    return {
        f.name: getattr(p, f.name)
        for f in dataclasses.fields(Preset)
        if f.name != "mode" and getattr(p, f.name) != getattr(base, f.name)
    }


V1_OVERRIDES: Mapping[Mode, Mapping[str, object]] = {
    mode: diff_from(shipped_preset(mode), V1_PRESET[mode]) for mode in Mode
}
"""``V1_PRESET`` as overrides of the shipped presets: what ``rules_of`` puts under a job's overrides."""

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
sweep changes only the parameters it names. Unnamed fields keep the Rules v1
preset's values (``V1_PRESET``)."""

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
    """The fields of ``p`` that differ from its mode's Rules v1 preset, as overrides."""
    return diff_from(V1_PRESET[p.mode], p)


V2_PRESET: Mapping[Mode, Preset] = {mode: action_die_rules(roulette_rules(V1_PRESET[mode])) for mode in Mode}
"""The Rules v1 preset with ``roulette_rules`` and then ``action_die_rules`` (bag without floodgates)."""
V2_BASE: Mapping[Mode, Mapping[str, object]] = {mode: _diff(V2_PRESET[mode]) for mode in Mode}
"""The overrides every Rules v2 sweep starts from: ``V2_PRESET`` as overrides of the Rules v1 preset."""
SHIPPED_V2: Mapping[Mode, Mapping[str, object]] = {mode: _diff(shipped_preset(mode)) for mode in Mode}
"""The shipped presets (Rules v2, #126) as overrides of the Rules v1 presets."""
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


def v2_sweeps(
    scale: int = 1, rare_bonus: int = 1, multiple_bodegas: bool = False, season_global_only: bool = False,
    seat_bonus: Mapping[int, tuple[int, ...]] | None = None, rounds: Mapping[int, int] | None = None,
) -> tuple[Sweep, ...]:
    """#103 phase B: score_aware seating, seed ``V2_SWEEP_SEED``. B3 and B4
    run at B2's best ``scale`` and ``rare_bonus`` (``--scale``,
    ``--rare-bonus``; the defaults are the provisional 2/3 points). B5
    (#132) combines the best of B2-B4: B4's best board (``B5_BOARD``) with
    the constructive die x cost x season roll, and no die, at the same
    scale and rare bonus; ``multiple_bodegas`` (#135, ``--multiple-bodegas``)
    turns that option on in every b5 candidate, and ``season_global_only``
    (#138, ``--season-global-only``) turns ``season_roll_personal_faces``
    off in every b5 candidate; ``seat_bonus`` (#142, ``--seat-bonus``) sets
    that field, and ``rounds`` (#142, ``--rounds``) the round count of its
    player counts over the mode's Rules v1 rounds, in every b5 candidate."""
    best = f"scale {scale}, rare +{rare_bonus}"
    b5_options = {
        **({"multiple_bodegas": True} if multiple_bodegas else {}),
        **({"season_roll_personal_faces": False} if season_global_only else {}),
    }
    if seat_bonus:
        b5_options["seat_bonus"] = dict(seat_bonus)
    b5_base = {
        mode: {**B5_BOARD[mode], **b5_options,
               **({"rounds": {**V1_PRESET[mode].rounds, **rounds}} if rounds else {})}
        for mode in Mode
    }
    b5_bodegas = (", multiple bodegas" if multiple_bodegas else "") + (
        ", season roll applies season faces only" if season_global_only else "") + (
        f", seat bonus {seat_bonus_label(seat_bonus)}" if seat_bonus else "") + (
        f", rounds {rounds_label(rounds)}" if rounds else "")
    seats = ("score_aware",)
    shipped = {mode: {} for mode in Mode}

    def v2_sweep(name: str, title: str, candidates) -> Sweep:
        return Sweep(name, title, candidates, seats, V2_BASE, V2_SWEEP_SEED)

    def die_label(cost: int, faces: tuple[int, int, int]) -> str:
        return f"cost {cost}, faces {'/'.join(map(str, faces))}"

    return (
        Sweep("b0", "Rules v1 baseline: the Rules v1 presets", {mode: (("shipped (Rules v1)", {}),) for mode in Mode},
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
                 f"season roll every X rounds, and no die; {best}{b5_bodegas}",
                 {mode: tuple(
                     (f"constructive die, cost {cost}, season roll every {every}",
                      v2(mode, scale, rare_bonus, **b5_base[mode], action_die=CONSTRUCTIVE_DIE_FACES,
                         action_die_cost=cost, season_roll_every=every))
                     for cost in (1, 2)
                     for every in B5_SEASON_EVERY[mode]
                 ) + (("no die (no bribe either)", v2(mode, scale, rare_bonus, **b5_base[mode], **NO_DIE)),)
                  for mode in Mode}),
        Sweep("shipped", "The shipped presets (Rules v2, #126)",
              {mode: (("shipped (Rules v2)", dict(SHIPPED_V2[mode])),) for mode in Mode},
              seats, shipped, V2_SWEEP_SEED),
    )


def seat_bonus_label(bonus: Mapping[int, tuple[int, ...]]) -> str:
    """``--seat-bonus`` text: ``4=1,1,1,0;5=1,1,1,0,0``."""
    return ";".join(f"{players}={','.join(map(str, points))}" for players, points in sorted(bonus.items()))


def rounds_label(rounds: Mapping[int, int]) -> str:
    """``--rounds`` text: ``4=5,5=5``."""
    return ",".join(f"{players}={count}" for players, count in sorted(rounds.items()))


def _player_count(text: str) -> int:
    players = int(text)
    if players not in PLAYER_COUNTS:
        raise ValueError(f"player count must be {PLAYER_COUNTS[0]} to {PLAYER_COUNTS[-1]}, got {players}")
    return players


def parse_seat_bonus(text: str) -> dict[int, tuple[int, ...]]:
    """``--seat-bonus``: ``P=b1,b2,...`` per player count, separated by ``;``;
    one value per seat, seat 0 first (round 1's start player)."""
    try:
        bonus = {}
        for part in text.split(";"):
            players, _, points = part.partition("=")
            players = _player_count(players)
            if players in bonus:
                raise ValueError(f"player count {players} is given twice")
            values = tuple(int(v) for v in points.split(","))
            if len(values) != players or any(v < 0 for v in values):
                raise ValueError(f"{players} players need {players} values >= 0, got {points!r}")
            bonus[players] = values
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected e.g. 4=1,1,1,0;5=1,1,1,0,0 ({error})") from None
    return bonus


def parse_rounds(text: str) -> dict[int, int]:
    """``--rounds``: ``P=R`` per player count, separated by ``,``."""
    try:
        rounds = {}
        for part in text.split(","):
            players, _, count = part.partition("=")
            players = _player_count(players)
            if players in rounds:
                raise ValueError(f"player count {players} is given twice")
            rounds[players] = int(count)
            if rounds[players] < 1:
                raise ValueError(f"rounds must be at least 1, got {count!r}")
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"expected e.g. 4=5,5=5 ({error})") from None
    return rounds


# --- Rules v3 river strip (#154) ---------------------------------------------

STRIP_SWEEP_SEED = 154_001
"""The run seed of the river strip sweep (#154); no earlier run used it."""
STRIP_RIVER_HEXES = (4, 5, 6)
"""Sweep ``strip``'s river hexes per segment by default (#154)."""
STRIP_BAG_PER_PLAYER = (12, 16, 20)
"""Sweep ``strip``'s bag sizes by default, in pieces per player (#154)."""


def strip_overrides(mode: Mode, river_hexes: int, bag_per_player: int) -> dict[str, object]:
    """The shipped preset of ``mode`` under Rules v3 on the river strip board,
    as overrides of the Rules v1 preset: vertex planting, ``river_hexes``
    per segment, and a bag of ``bag_per_player`` pieces per player for each
    of the mode's player counts."""
    counts = shipped_preset(mode).player_counts
    return {
        **SHIPPED_V2[mode],
        "planting": PlantingRules.VERTICES,
        "board_shape": BoardShape.RIVER_STRIP,
        "river_hexes_per_segment": river_hexes,
        "bag_size": {players: bag_per_player * players for players in counts},
    }


def strip_sweeps(river_hexes=STRIP_RIVER_HEXES, bag_per_player=STRIP_BAG_PER_PLAYER) -> tuple[Sweep, ...]:
    """Sweep ``strip`` (#154): river hexes per segment x bag size per player, score_aware seating."""
    return (
        Sweep("strip", "Rules v3 river strip: river hexes per segment x bag size (pieces per player)",
              {mode: tuple(
                  (f"{hexes} river hexes/segment, bag {per}/player", strip_overrides(mode, hexes, per))
                  for hexes in river_hexes
                  for per in bag_per_player
              ) for mode in Mode},
              ("score_aware",), {mode: {} for mode in Mode}, STRIP_SWEEP_SEED),
    )


# --- Rules v3 (#153) ------------------------------------------------------------

V3_SWEEP_SEED = 153_001
"""The run seed of sweep ``v3`` (#153); no earlier run used it."""
V3_RIVER_HEXES = 5
"""Sweep ``v3``'s base river hexes per segment (``--v3-river-hexes``)."""
V3_BAG_PER_PLAYER = 16
"""Sweep ``v3``'s base bag size in pieces per player (``--v3-bag-per-player``)."""
V3_ROUND_STEPS = (-4, -2, 2)
"""Sweep ``v3``'s round counts: the shipped rounds of each player count plus these."""
V3_DIE_COSTS = (0, 2)
"""Sweep ``v3``'s action die costs (the bribe of the floodgate and release faces); the base is shipped's."""
V3_POINTS = ((2, 3), (4, 5), (6, 9))
"""Sweep ``v3``'s vineyard points (common, rare); the shipped ones are 6 / 7."""
V3_BODEGA_POINTS = (3, 9, 12)
"""Sweep ``v3``'s bodega points."""


def v3_points(mode: Mode, common: int, rare: int) -> dict[str, object]:
    """Vineyard points ``common`` (``rare`` for ``RARE_VARIETALS``), with the shipped
    bodega and water rights scaled by ``common`` over the shipped common points."""
    p = shipped_preset(mode)
    shipped_common = min(p.varietal_points.values())
    return {
        "varietal_points": {v: rare if v in RARE_VARIETALS else common for v in p.varietal_points},
        "bodega_points": p.bodega_points * common // shipped_common,
        "water_right_points": max(1, p.water_right_points * common // shipped_common),
    }


def v3_sweeps(river_hexes: int = V3_RIVER_HEXES, bag_per_player: int = V3_BAG_PER_PLAYER) -> tuple[Sweep, ...]:
    """Sweep ``v3`` (#153): one Rules v3 value at a time around the river strip base
    (``strip_overrides(mode, river_hexes, bag_per_player)``), score_aware seating."""
    base = {mode: strip_overrides(mode, river_hexes, bag_per_player) for mode in Mode}

    def candidates(mode: Mode) -> tuple[tuple[str, dict], ...]:
        p = shipped_preset(mode)
        rounds = tuple(
            (f"rounds {step:+d} ({rounds_label({n: r + step for n, r in p.rounds.items()})})",
             {"rounds": {n: r + step for n, r in p.rounds.items()}})
            for step in V3_ROUND_STEPS
        )
        costs = tuple((f"die cost {cost}", {"action_die_cost": cost}) for cost in V3_DIE_COSTS)
        points = tuple(
            (f"points {common} / rare {rare}", v3_points(mode, common, rare)) for common, rare in V3_POINTS
        )
        bodega = tuple((f"bodega {b}", {"bodega_points": b}) for b in V3_BODEGA_POINTS)
        hexes = tuple(
            (f"{n} river hexes/segment", {"river_hexes_per_segment": n})
            for n in STRIP_RIVER_HEXES if n != river_hexes
        )
        bags = tuple(
            (f"bag {per}/player", {"bag_size": {n: per * n for n in p.player_counts}})
            for per in STRIP_BAG_PER_PLAYER if per != bag_per_player
        )
        return (
            ("base", {}), *rounds, *costs, *points, *bodega,
            ("move face", {"action_die": V3_DIE_FACES}), *hexes, *bags,
        )

    return (
        Sweep("v3", f"Rules v3, one value at a time around the river strip base ({river_hexes} river "
                    f"hexes/segment, bag {bag_per_player}/player, shipped Rules v2 values)",
              {mode: candidates(mode) for mode in Mode}, ("score_aware",), base, V3_SWEEP_SEED),
    )


# --- Rules v3 split scoring (#160) ------------------------------------------------

V3SPLIT_SWEEP_SEED = 160_001
"""The run seed of sweep ``v3split`` (#160); no earlier run used it."""
V3SPLIT_RIVER_HEXES = (5, 6)
"""Sweep ``v3split``'s river hexes per segment; the first is the base."""
V3SPLIT_BAG_PER_PLAYER = (16, 20, 24)
"""Sweep ``v3split``'s bag sizes in pieces per player; the first is the base."""
V3SPLIT_BODEGA_POINTS = (3, 6, 9)
"""Sweep ``v3split``'s bodega points; the shipped value of the mode is the base."""
V3SPLIT_ROUND_STEPS = (-2, 2)
"""Sweep ``v3split``'s round counts: the shipped rounds of each player count plus these."""
V3SPLIT_DICE = (("move die", V3_DIE_FACES), ("old die", CONSTRUCTIVE_DIE_FACES))
"""Sweep ``v3split``'s action dice: the Rules v3 die (a move face, #160) and the old one
(2 resows, no move)."""


def v3split_sweeps() -> tuple[Sweep, ...]:
    """Sweep ``v3split`` (#160): split scoring at ``acequias.config.V3_POINTS``; 4 setups (three canals
    off / on x move die / old die), each its base and one value at a time."""
    base = {
        mode: {
            **strip_overrides(mode, V3SPLIT_RIVER_HEXES[0], V3SPLIT_BAG_PER_PLAYER[0]),
            "varietal_points": V3_SPLIT_POINTS,
        }
        for mode in Mode
    }

    def candidates(mode: Mode) -> tuple[tuple[str, dict], ...]:
        p = shipped_preset(mode)
        changes = (
            ("base", {}),
            *((f"bag {per}/player", {"bag_size": {n: per * n for n in p.player_counts}})
              for per in V3SPLIT_BAG_PER_PLAYER[1:]),
            *((f"{n} river hexes/segment", {"river_hexes_per_segment": n}) for n in V3SPLIT_RIVER_HEXES[1:]),
            *((f"bodega {b}", {"bodega_points": b}) for b in V3SPLIT_BODEGA_POINTS if b != p.bodega_points),
            *((f"rounds {step:+d} ({rounds_label({n: r + step for n, r in p.rounds.items()})})",
               {"rounds": {n: r + step for n, r in p.rounds.items()}}) for step in V3SPLIT_ROUND_STEPS),
        )
        return tuple(
            (f"{'3 canals' if three else 'any vertex'}, {die_name}: {label}",
             {"vertex_needs_three_canals": three, "action_die": die, **change})
            for three in (False, True)
            for die_name, die in V3SPLIT_DICE
            for label, change in changes
        )

    return (
        Sweep("v3split", f"Rules v3 split scoring ({V3_SPLIT_POINTS[Varietal.MALBEC]} / rare "
                         f"{V3_SPLIT_POINTS[Varietal.BONARDA]}): three canals x die, one value at a time around a "
                         f"river strip base ({V3SPLIT_RIVER_HEXES[0]} river hexes/segment, bag "
                         f"{V3SPLIT_BAG_PER_PLAYER[0]}/player)",
              {mode: candidates(mode) for mode in Mode}, ("score_aware",), base, V3SPLIT_SWEEP_SEED),
    )


# --- Rules v3 blends and bodega buildings (#166) -----------------------------------

V3BLENDS_SWEEP_SEED = 166_001
"""The run seed of sweep ``v3blends`` (#166); no earlier run used it."""
V3BLENDS_FACTORS = ((1, 2), (1, 1), (3, 2))
"""Sweep ``v3blends``'s point factors (x0.5, x1, x1.5) as fractions: each blend's points,
the bodega bonus and the building points times the factor, rounded half up, at least 1."""
V3BLENDS_BUILDING_POINTS = (12, 15)
"""Sweep ``v3blends``'s bodega building points at x1 (owner, #166); x0.5 and x1.5 scale the first."""
V3BLENDS_REDS = 2
"""Sweep ``v3blends``'s distinct red varietals a bodega building needs."""
V3BLENDS_WHITES = (2, 1)
"""Sweep ``v3blends``'s distinct white varietals a bodega building needs (owner, #166)."""


def _times(points: int, factor: tuple[int, int]) -> int:
    """``points`` x ``factor`` (a fraction), rounded half up, at least 1."""
    num, den = factor
    return max(1, (2 * points * num + den) // (2 * den))


def _factor_label(factor: tuple[int, int]) -> str:
    num, den = factor
    return f"x{num / den:g}"


def v3blends_sweeps() -> tuple[Sweep, ...]:
    """Sweep ``v3blends`` (#166): current bodega vs blends (each_once / disjoint) vs blends +
    bodega building, each at points x0.5 / x1 / x1.5, around the ``v3split`` base."""
    base = {
        mode: {
            **strip_overrides(mode, V3SPLIT_RIVER_HEXES[0], V3SPLIT_BAG_PER_PLAYER[0]),
            "varietal_points": V3_SPLIT_POINTS,
            "action_die": V3_DIE_FACES,
        }
        for mode in Mode
    }

    def blends(factor) -> tuple[Blend, ...]:
        return tuple(Blend(b.varietals, _times(b.points, factor)) for b in DEFAULT_BLENDS)

    def candidates(mode: Mode) -> tuple[tuple[str, dict], ...]:
        bodega = shipped_preset(mode).bodega_points
        rows: list[tuple[str, dict]] = []
        for factor in V3BLENDS_FACTORS:
            x = _factor_label(factor)
            points = _times(bodega, factor)
            rows.append((f"current bodega {x} ({points})", {"bodega_points": points}))
            for rule in BlendRule:
                rows.append((f"blends {rule.value} {x}", {
                    "varietal_bodega": False, "blends": blends(factor), "blend_rule": rule,
                }))
            buildings = V3BLENDS_BUILDING_POINTS if factor == (1, 1) else (
                _times(V3BLENDS_BUILDING_POINTS[0], factor),)
            for building in buildings:
                for whites in V3BLENDS_WHITES:
                    rows.append((f"blends each_once + bodega building {building} {x}, "
                                 f"{V3BLENDS_REDS} reds + {whites} whites", {
                        "varietal_bodega": False, "blends": blends(factor),
                        "blend_rule": BlendRule.EACH_ONCE, "bodega_building": True,
                        "bodega_building_points": building,
                        "bodega_min_reds": V3BLENDS_REDS, "bodega_min_whites": whites,
                    }))
        return tuple(rows)

    return (
        Sweep("v3blends", "Rules v3 scoring options (#166): current bodega vs blends (each_once / "
                          "disjoint) vs blends + bodega building, points x0.5 / x1 / x1.5, around the "
                          "v3split base with the move die",
              {mode: candidates(mode) for mode in Mode}, ("score_aware",), base, V3BLENDS_SWEEP_SEED),
    )


# --- Rules v3 optional bribe (#168) ------------------------------------------------

V3BRIBE_SWEEP_SEED = 168_001
"""The run seed of sweep ``v3bribe`` (#168); no earlier run used it."""
V3BRIBE_COSTS = (1, 2, 3, 4, 6)
"""Sweep ``v3bribe``'s bribes (``action_die_cost``)."""


def v3_best_base(mode: Mode) -> dict[str, object]:
    """The best #160/#166 setup, the base of sweep ``v3bribe`` (edit here to move it): the river
    strip at ``V3SPLIT_RIVER_HEXES[0]`` river hexes per segment and bag ``V3SPLIT_BAG_PER_PLAYER[0]``
    per player, split scoring, any-vertex planting, the move die, ``each_once`` blends
    (``DEFAULT_BLENDS``) with the old bodega bonus off, and the bodega building (a new spot,
    ``V3BLENDS_BUILDING_POINTS[0]`` points, ``V3BLENDS_REDS`` reds + ``V3BLENDS_WHITES[0]`` whites)."""
    return {
        **strip_overrides(mode, V3SPLIT_RIVER_HEXES[0], V3SPLIT_BAG_PER_PLAYER[0]),
        "varietal_points": V3_SPLIT_POINTS,
        "vertex_needs_three_canals": False,
        "action_die": V3_DIE_FACES,
        "varietal_bodega": False,
        "blends": DEFAULT_BLENDS,
        "blend_rule": BlendRule.EACH_ONCE,
        "bodega_building": True,
        "bodega_placement": BodegaPlacement.NEW_SPOT,
        "bodega_building_points": V3BLENDS_BUILDING_POINTS[0],
        "bodega_min_reds": V3BLENDS_REDS,
        "bodega_min_whites": V3BLENDS_WHITES[0],
    }


def v3bribe_sweeps(costs=V3BRIBE_COSTS) -> tuple[Sweep, ...]:
    """Sweep ``v3bribe`` (#168): ``bribe_optional`` off / on x the bribe, around ``v3_best_base``."""
    candidates = tuple(
        (f"{'optional' if optional else 'mandatory'} bribe {cost}",
         {"bribe_optional": optional, "action_die_cost": cost})
        for optional in (False, True)
        for cost in costs
    )
    return (
        Sweep("v3bribe", "Rules v3 optional floodgate faces (#168): bribe_optional off / on x bribe "
                         f"{'/'.join(map(str, costs))}, around the best #160/#166 setup",
              {mode: candidates for mode in Mode}, ("score_aware",),
              {mode: v3_best_base(mode) for mode in Mode}, V3BRIBE_SWEEP_SEED),
    )


# --- Rules v3 seat bias and end conditions (#163) -----------------------------------

V3END_SWEEP_SEED = 163_001
"""The run seed of sweep ``v3end`` (#163); no earlier run used it."""
SEAT_KEY = "seat_assignment"
"""A tune-only job key (#163), not a ``Preset`` field: how seats are assigned per game
(``SEAT_ASSIGNMENTS``); ``rules_of`` leaves it out of the preset and ``run_chunk`` applies it."""
SEAT_ASSIGNMENTS = ("fixed", "rotated", "shuffled")
"""``fixed``: as ``new_game`` deals them (seats p1..pN, a random first start player).
``rotated``: game ``i`` starts with seat ``i % P + 1``, so every seat starts equally often.
``shuffled``: the seat numbers (the order around the table) are shuffled per game from the
game seed. The river strip has no segment owned by a seat, so these test whether the bias
follows the seat or the turn position; the turn order rules stay as they are."""
V3END_TARGET_FACTORS = ((1, 1), (3, 2), (2, 1))
"""Sweep ``v3end``'s score targets: ``SCORE_TARGETS`` (#160's winning scores) x1, x1.5, x2."""
ADVANTAGE_BIAS_LIMIT = 0.2
"""#163: the advantage under which an option is said to remove the 4-5p seat bias."""


def v3end_base(mode: Mode) -> dict[str, object]:
    """The base of sweep ``v3end``: ``v3_best_base`` (one place to move it) with the round count end
    written out, so a ``v3end`` row is told apart (``is_v3end``) and plays as the base does."""
    return {**v3_best_base(mode), "end_condition": EndCondition.ROUNDS}


def v3end_sweeps() -> tuple[Sweep, ...]:
    """Sweep ``v3end`` (#163): diagnosis rows (seat assignment, unlimited bag) and each end condition
    x ``finish_round`` on / off, around ``v3end_base``."""

    def candidates(mode: Mode) -> tuple[tuple[str, dict], ...]:
        rows: list[tuple[str, dict]] = [("base", {})]
        rows += [(f"seats {a}", {SEAT_KEY: a}) for a in SEAT_ASSIGNMENTS[1:]]
        rows.append(("unlimited bag", {"unlimited_bag": True}))
        counts = shipped_preset(mode).player_counts
        for finish in (True, False):
            tail = "finish round" if finish else "ends at once"
            rows.append((f"bag_empty, {tail}", {"end_condition": EndCondition.BAG_EMPTY, "finish_round": finish}))
            rows.append((f"vineyards_out, {tail}",
                         {"end_condition": EndCondition.VINEYARDS_OUT, "finish_round": finish}))
            for factor in V3END_TARGET_FACTORS:
                target = {n: _times(SCORE_TARGETS[mode][n], factor) for n in counts}
                rows.append((f"score_target {_factor_label(factor)} ({rounds_label(target)}), {tail}", {
                    "end_condition": EndCondition.SCORE_TARGET, "finish_round": finish, "score_target": target,
                }))
        return tuple(rows)

    return (
        Sweep("v3end", "Rules v3 seat bias diagnosis and end conditions (#163), around the best "
                       "#160/#166 setup (v3_best_base)",
              {mode: candidates(mode) for mode in Mode}, ("score_aware",),
              {mode: v3end_base(mode) for mode in Mode}, V3END_SWEEP_SEED),
    )


V1_SWEEPS = SWEEPS
"""The sweeps of #20 (Rules v1, greedy and mixed seatings)."""
SWEEPS = (V1_SWEEPS + v2_sweeps() + strip_sweeps() + v3_sweeps() + v3split_sweeps() + v3blends_sweeps()
          + v3bribe_sweeps() + v3end_sweeps())
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
    """The job's ``SimRules``: its overrides over ``V1_OVERRIDES`` (they are relative to ``V1_PRESET``)."""
    overrides = {k: v for k, v in job.overrides.items() if k != SEAT_KEY}
    return SimRules(job.mode, job.players, policies(job.seating, job.players),
                    {**V1_OVERRIDES[job.mode], **overrides})


def reseat(start: GameState, assignment: str, i: int, seed: int) -> GameState:
    """``start`` with its seats assigned as ``assignment`` says (``SEAT_ASSIGNMENTS``) for game ``i``
    of game seed ``seed``; deterministic."""
    players = len(start.players)
    if assignment == "fixed":
        return start
    if assignment == "rotated":
        first = f"p{i % players + 1}"
        return dataclasses.replace(start, start_player=first, current_player=first)
    if assignment == "shuffled":
        seats = random.Random(f"seats:{seed}").sample(range(1, players + 1), players)
        return dataclasses.replace(
            start, players=tuple(dataclasses.replace(p, seat=s) for p, s in zip(start.players, seats))
        )
    raise ValueError(f"seat_assignment must be one of {SEAT_ASSIGNMENTS}, got {assignment!r}")


def play_seated(rules: SimRules, seed: int, i: int, assignment: str) -> GameRecord:
    """Game ``i`` (game seed ``seed``) under ``rules`` with ``reseat``'s seats: ``play_one`` with the
    start state reseated; ``fixed`` is ``play_one`` itself."""
    if assignment == "fixed":
        return play_one(rules, seed)
    start = reseat(new_game(rules.players, seed, rules.mode, preset=_preset(rules)), assignment, i, seed)
    bots = _bots(rules)
    final, log = play_game(start, {p.id: bots[p.seat - 1] for p in start.players}, *game_rngs(seed))
    scores = calculate_score(final)
    return GameRecord(seed, start, final, log, scores, winners(scores))


def plays(mode: Mode, players: int, overrides: Mapping[str, object]) -> bool:
    """Whether a job of ``overrides`` (relative to ``V1_PRESET``) is for ``players`` players."""
    rounds = overrides.get("rounds", V1_PRESET[mode].rounds)
    return not isinstance(rounds, Mapping) or players in rounds


def playable(jobs: list[Job]) -> list[Job]:
    """``jobs`` without those whose preset is not for their player count, each skip noted on stderr."""
    kept = []
    for job in jobs:
        if plays(job.mode, job.players, job.overrides):
            kept.append(job)
        else:
            counts = tuple(sorted(job.overrides["rounds"]))
            print(f"skipped {describe_job(job)}: {job.mode.value} is for {players_text(counts)} players here",
                  file=sys.stderr)
    return kept


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
        assignment = job.overrides.get(SEAT_KEY, "fixed")
        if assignment not in SEAT_ASSIGNMENTS:
            raise ValueError(f"seat_assignment must be one of {SEAT_ASSIGNMENTS}, got {assignment!r}")
    except ValueError as error:
        return ChunkResult(INFEASIBLE, error=str(error), priority_warning=_worker_warning)
    except Exception as error:  # noqa: BLE001 - reported with its job, the run goes on
        return ChunkResult(FAILED, error=f"{type(error).__name__}: {error}", priority_warning=_worker_warning)
    records = []
    for i in range(start, stop):
        seed = game_seed(job.seed, i)
        try:
            records.append(play_seated(rules, seed, i, assignment))
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
            data = summarize(rules_of(job), job.seed, games).to_json()
            data["floodgates"] = floodgate_stats(games)
            if is_v3blends(job.overrides):
                data["blend_stats"] = blend_stats(games)
            if is_v3bribe(job.overrides):
                data["bribe_stats"] = bribe_stats(games)
            if is_v3end(job.overrides):
                data["end_stats"] = end_stats(games)
            outcomes.append(Outcome("ok", data=data))
        except Exception as error:  # noqa: BLE001 - reported with its job, the run goes on
            outcomes.append(Outcome(FAILED, error=f"{type(error).__name__}: {error}"))
    for job, outcome in zip(jobs, outcomes):
        if outcome.status == FAILED:
            print(f"FAILED {describe_job(job)}: {outcome.error}", file=sys.stderr, flush=True)
    return outcomes


# --- Formatting --------------------------------------------------------------


def floodgate_stats(records: list[GameRecord]) -> dict[str, float]:
    """Floodgates per game (#160, to size the physical supply): ``placed`` (mean placements),
    ``peak`` (mean of each game's most floodgates on the board at once) and ``peak_max`` (the
    most in any game). Only ``PlaceFloodgate`` adds one and only ``Release`` removes one (a
    d6 ``Bribe`` moves or removes one: counted as neither, so its peak is an upper bound)."""
    placed: list[int] = []
    peaks: list[int] = []
    for record in records:
        on_board = peak = count = len(record.start.board.floodgates)
        for r in record.log:
            if isinstance(r.action, PlaceFloodgate):
                on_board += 1
                count += 1
                peak = max(peak, on_board)
            elif isinstance(r.action, Release):
                on_board -= 1
        placed.append(count)
        peaks.append(peak)
    return {
        "placed": sum(placed) / len(placed),
        "peak": sum(peaks) / len(peaks),
        "peak_max": float(max(peaks)),
    }


def requirement_stats(records: list[GameRecord]) -> dict[str, float | None]:
    """Bodega building requirement figures (#166), replaying each game: ``met`` (the share of
    players who meet the requirement at some point), ``first_round`` (the mean round they
    first meet it, None if nobody does) and ``builders`` (the share of players who build)."""
    players = met = builders = 0
    rounds: list[int] = []
    for record in records:
        p = record.start.preset
        ids = [pl.id for pl in record.start.players]
        players += len(ids)
        builders += len({r.player for r in record.log if isinstance(r.action, BuildBodega)})
        first: dict[str, int] = {}
        state = record.start
        dice = game_rngs(record.game_seed)[0]
        for r in record.log:
            state = act(state, r.player, r.action, dice)
            for pid in ids:
                if pid not in first and can_build_bodega(state.board, pid, p):
                    first[pid] = r.round
        met += len(first)
        rounds += first.values()
    return {
        "met": met / players,
        "first_round": sum(rounds) / len(rounds) if rounds else None,
        "builders": builders / players,
    }


def blend_stats(records: list[GameRecord]) -> dict[str, object]:
    """Blend and bodega building figures (#166): ``blend`` and ``buildings`` (mean points per
    player), ``built`` (bodegas built per game), ``rates`` (per blend name, the share of
    player-games where it scored), and with ``bodega_building`` the ``requirement_stats``
    (``met``, ``first_round``, ``builders``; None without)."""
    players = sum(len(r.scores) for r in records)
    counts: dict[str, int] = {}
    blend = buildings = built = 0
    building = bool(records) and records[0].start.preset.bodega_building
    requirement = requirement_stats(records) if building else None
    for record in records:
        built += sum(1 for r in record.log if isinstance(r.action, BuildBodega))
        for score in record.scores.values():
            blend += score.blend
            buildings += score.buildings
            for name in score.blends:
                counts[name] = counts.get(name, 0) + 1
    return {
        "blend": blend / players,
        "buildings": buildings / players,
        "built": built / len(records),
        "rates": {name: n / players for name, n in sorted(counts.items())},
        "requirement": requirement,
    }


def bribe_stats(records: list[GameRecord]) -> dict[str, float | None]:
    """Optional bribe figures (#168), replaying each game: ``placed`` and ``released`` (per game),
    ``used`` (the share of floodgate and release rolls whose face was used; None with no such
    roll) and ``swing`` (the mean score swing of a floodgate placed or removed: the user's
    total change less the best rival's, before the bribe; None with none)."""
    rolls = used = placed = released = 0
    swings: list[int] = []
    for record in records:
        state = record.start
        dice = game_rngs(record.game_seed)[0]
        for i, r in enumerate(record.log):
            if isinstance(r.action, RollActionDie) and r.face in (DieFace.FLOODGATE, DieFace.RELEASE):
                rolls += 1
                nxt = record.log[i + 1] if i + 1 < len(record.log) else None
                if nxt is not None and isinstance(nxt.action, (PlaceFloodgate, Release)):
                    used += 1
            after = act(state, r.player, r.action, dice)
            if isinstance(r.action, (PlaceFloodgate, Release)):
                placed += isinstance(r.action, PlaceFloodgate)
                released += isinstance(r.action, Release)
                before = calculate_score(state)
                now = calculate_score(dataclasses.replace(after, players=state.players))
                delta = {pid: now[pid].total - before[pid].total for pid in now}
                swings.append(delta[r.player] - max(d for pid, d in delta.items() if pid != r.player))
            state = after
    games = len(records)
    return {
        "placed": placed / games,
        "released": released / games,
        "used": used / rolls if rolls else None,
        "swing": sum(swings) / len(swings) if swings else None,
    }


def end_stats(records: list[GameRecord]) -> dict[str, object]:
    """End of game figures (#163), replaying each game: ``turns`` and ``rounds`` (mean per game; a
    turn is a run of log records by one player in one round), ``capped`` (the share of games whose
    end condition never fired, so the round cap ended them; None under the round count end),
    ``bodega`` (the share of player-games with a bodega bonus or a bodega building), and
    ``trace``: for each round, the games still running at its start and the mean total by
    position (round 1's turn order) at the end of that round, or at the game's end in it."""
    turns = rounds = capped = bodegas = 0
    trace: dict[int, list] = {}
    preset = records[0].start.preset
    for record in records:
        last = None
        for r in record.log:
            if (r.round, r.player) != last:
                turns += 1
                last = (r.round, r.player)
        played = record.log[-1].round if record.log else 0
        rounds += played
        capped += record.final.end_triggered is None
        bodegas += sum(s.bodega > 0 or s.buildings > 0 for s in record.scores.values())
        order = turn_order(record.start, 1)
        state, dice = record.start, game_rngs(record.game_seed)[0]
        log = record.log
        for k, r in enumerate(log):
            state = act(state, r.player, r.action, dice)
            if k + 1 == len(log) or log[k + 1].round != r.round:
                totals = calculate_score(state)
                row = trace.setdefault(r.round, [0, [0] * len(order)])
                row[0] += 1
                for j, pid in enumerate(order):
                    row[1][j] += totals[pid].total
    games = len(records)
    players = len(records[0].start.players)
    return {
        "turns": turns / games,
        "rounds": rounds / games,
        "capped": None if preset.end_condition is EndCondition.ROUNDS else capped / games,
        "bodega": bodegas / (games * players),
        "trace": {str(rnd): {"games": n, "mean": [t / n for t in sums]} for rnd, (n, sums) in sorted(trace.items())},
    }


def _bribe_columns(data: Mapping[str, object]) -> str:
    """The #168 columns: floodgates placed / released per game, share of their rolls used, swing, debt."""
    b = data.get("bribe_stats")
    if b is None:
        return " - |" * BRIBE_COLUMNS
    return (f" {b['placed']:.2f} / {b['released']:.2f} | {_f(b['used'], 3)} | {_f(b['swing'])} "
            f"| {data['score_terms']['debt']['mean']:.2f} |")


def _blend_columns(data: Mapping[str, object]) -> str:
    """The #166 columns: blend points, building points, bodegas built per game, blend rates."""
    b = data.get("blend_stats")
    if b is None:
        return " - |" * BLEND_COLUMNS
    rates = ", ".join(f"{name} {rate:.2f}" for name, rate in b["rates"].items()) or "-"
    req = b.get("requirement")
    if req is None:
        met = " - | - | - |"
    else:
        met = f" {req['met']:.2f} | {_f(req['first_round'], 1)} | {req['builders']:.2f} |"
    return f" {b['blend']:.2f} | {b['buildings']:.2f} | {b['built']:.2f} |{met} {rates} |"


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
V3_NOTE = (
    "Rules v3: a turn is one mandatory roll, then its face's use and 1 action (2 after a good season, "
    "none after a drought). Rolls per face: floodgate / release / resow / good season / drought "
    "/ move. Planted per player: plants per game / P (a moved vineyard keeps its count). Floodgates: "
    "placed per game / most on the board at once, mean / max over games."
)
SWEEP_HEADER = (
    "| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins "
    "| Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points "
    "| Winner varietal rates | Bribe games | Win rate bribers / non-bribers | Mean debt "
    "| Die games | Rolls | Rolls per face | Die use rate |"
)
SWEEP_COLUMNS = 21
V3_SWEEP_HEADER = (
    "| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins "
    "| Turns (min) | Plant / canal / pass per game | Planted per player | Winning score | Score "
    "| Vineyard points | Bodega rate | Bodega points | Rights paid | Mean debt "
    "| Rolls per face | Floodgate / release / resow / move uses | Die use rate | Floodgates |"
)
V3_SWEEP_COLUMNS = 20
BLEND_HEADER = (
    " Blend points | Building points | Bodegas built per game | Requirement met (share of players) "
    "| First round met (mean) | Builders (share of players) | Blend score rates |"
)
"""The columns a #166 sweep (``v3blends``) adds to ``V3_SWEEP_HEADER``."""
BLEND_COLUMNS = 7
BRIBE_HEADER = (
    " Floodgates placed / released per game | Floodgate rolls used | Swing per floodgate use "
    "| Mean debt |"
)
"""The columns a #168 sweep (``v3bribe``) adds after ``BLEND_HEADER``."""
BRIBE_COLUMNS = 4


def is_v3blends(overrides: Mapping[str, object]) -> bool:
    """Whether a job's overrides use a #166 scoring option (blends or bodega buildings)."""
    return bool(overrides.get("blends")) or bool(overrides.get("bodega_building"))


def is_v3bribe(overrides: Mapping[str, object]) -> bool:
    """Whether a job's overrides set ``bribe_optional`` (#168; off too, as sweep ``v3bribe`` does)."""
    return "bribe_optional" in overrides


def is_v3end(overrides: Mapping[str, object]) -> bool:
    """Whether a job is a #163 job: it sets ``end_condition`` (the ``v3end`` base writes it out)."""
    return "end_condition" in overrides


END_HEADER = (
    "| Candidate | P | Advantage ± 95% | Win rate by position | Win rate by seat | Shared wins "
    "| Turns (min) | Rounds | Bodega rate | Ended by the cap | Winning score |"
)
"""The columns of sweep ``v3end`` (#163)."""
END_COLUMNS = 11


def end_row(job: Job, outcome: Outcome) -> str:
    """A ``v3end`` row: ``END_HEADER``'s columns."""
    head = f"| {job.label} | {job.players} |"
    data = outcome.data
    if data is None:
        return f"{head} {_not_run(outcome)} |" + " |" * (END_COLUMNS - 3)
    e = data["end_stats"]
    return (
        f"{head} {data['turn_order_advantage']:.3f} ± {margin(job.players, job.n):.3f} "
        f"| {_list(data['win_rate_by_position'])} | {_list(data['win_rate_by_seat'])} "
        f"| {_f(data['shared_win_rate'])} | {e['turns']:.1f} ({e['turns'] * MINUTES_PER_TURN:.0f}) "
        f"| {e['rounds']:.1f} | {e['bodega']:.3f} | {_f(e['capped'], 3)} | {_spread(data['winning_score'])} |"
    )


def end_report(rows: list[tuple[Job, Outcome]]) -> list[str]:
    """Sweep ``v3end``'s lines after its table: one verdict line per player count (which rows bring
    the advantage under ``ADVANTAGE_BIAS_LIMIT``), then the base row's per-round score trace, and
    each other row's, one table per player count."""
    lines: list[str] = []
    counts = sorted({job.players for job, _ in rows})
    for players in counts:
        mine = [(j, o) for j, o in rows if j.players == players and o.data is not None]
        # Compared as displayed (3 decimals), so a row shown as 0.200 is not listed.
        under = [j.label for j, o in mine if round(o.data["turn_order_advantage"], 3) < ADVANTAGE_BIAS_LIMIT]
        lines.append(f"- {players}p: advantage under {ADVANTAGE_BIAS_LIMIT} with "
                     + (", ".join(f"`{label}`" for label in under) if under else "no option"))
    lines.append("")
    for players in counts:
        lines.append(f"#### Score trace, {players}p (mean total by position at the end of each round)")
        lines.append("")
        header = "| Candidate | Round | Games | " + " | ".join(f"Position {j}" for j in range(1, players + 1)) + " |"
        lines += [header, "|" + " --- |" * (players + 3)]
        for job, outcome in rows:
            if job.players != players or outcome.data is None:
                continue
            for rnd, t in outcome.data["end_stats"]["trace"].items():
                lines.append(f"| {job.label} | {rnd} | {t['games']} | "
                             + " | ".join(f"{x:.1f}" for x in t["mean"]) + " |")
        lines.append("")
    return lines


def is_v3(overrides: Mapping[str, object]) -> bool:
    """Whether a job's overrides play Rules v3 (vertex planting)."""
    return overrides.get("planting") is PlantingRules.VERTICES


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
        " / ".join(f"{rate:.2f}" for rate in faces.values()),
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


def v3_sweep_row(job: Job, outcome: Outcome) -> str:
    """A Rules v3 sweep row: ``V3_SWEEP_HEADER``'s columns."""
    head = f"| {job.label} | {job.players} | {job.seating} |"
    data = outcome.data
    if data is None:
        return f"{head} {_not_run(outcome)} |" + " |" * (V3_SWEEP_COLUMNS - 4)
    a = data["actions_per_game"]
    turns = _turns(job, data)
    terms = data["score_terms"]
    faces = data["die_faces_per_game"]
    return (
        f"{head} {data['turn_order_advantage']:.3f} ± {margin(job.players, job.n):.3f} "
        f"| {_list(data['win_rate_by_position'])} | {_f(data['shared_win_rate'])} "
        f"| {turns} ({turns * MINUTES_PER_TURN}) "
        f"| {a['plant']:.1f} / {a['canal']:.1f} / {a['pass']:.1f} | {a['plant'] / job.players:.2f} "
        f"| {_spread(data['winning_score'])} | {_spread(terms['total'])} "
        f"| {terms['vineyards']['mean']:.2f} | {_f(data['bodega_rate'], 3)} | {terms['bodega']['mean']:.2f} "
        f"| {terms['rights_paid']['mean']:.2f} | {terms['debt']['mean']:.2f} "
        f"| {' / '.join(f'{rate:.2f}' for rate in faces.values())} "
        f"| {a['floodgate']:.2f} / {a['release']:.2f} / {a['resow']:.2f} / {a['move']:.2f} "
        f"| {_f(data['die_use_rate'], 3)} | {_floodgates(data)} |"
    )


def _floodgates(data: Mapping[str, object]) -> str:
    """Floodgates placed per game / most on the board at once (mean / max); "-" when not counted."""
    f = data.get("floodgates")
    if f is None:
        return "-"
    return f"{f['placed']:.2f} / {f['peak']:.2f} / {f['peak_max']:.0f}"


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
            value = "/".join(str(value[p]) for p in sorted(value))
        elif key == "bag_mix":
            value = _bag_label(value)
        elif key == "vineyard_distance":
            value = f"{value[0]}-{value[1]}"
        elif key == "seat_bonus":
            value = seat_bonus_label(value)
        elif key in ("score_target", "vineyard_markers"):
            value = "/".join(f"{p}p {n}" for p, n in sorted(value.items()))
        elif key == "bag_size":
            value = "/".join(f"{p}p {n}" for p, n in sorted(value.items()))
        elif key == "varietal_points":
            value = "/".join(f"{v.name.lower()} {points}" for v, points in value.items())
        elif key == "action_die":
            value = "/".join(str(value.count(f)) for f in DieFace)
        elif key == "blends":
            value = "/".join(f"{b.name} {b.points}" for b in value)
        elif isinstance(value, Enum):
            value = value.value
        parts.append(f"{key}={value}")
    return ", ".join(parts) or "(shipped preset)"


# --- Commands ----------------------------------------------------------------


def sweep_jobs(sweep: Sweep, modes, games: int, players_list=PLAYER_COUNTS, seatings=None) -> list[Job]:
    """The jobs of ``sweep``: its seatings unless ``seatings`` is given; player counts
    a candidate's preset is not for are skipped (``playable``)."""
    return playable([
        Job(label, mode, players, seating, {**sweep.base[mode], **changes}, games, sweep.seed)
        for mode in modes
        for label, changes in sweep.candidates.get(mode, ())
        for players in players_list
        for seating in seatings or sweep.seatings
    ])


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
            if is_v3end(rows[0][0].overrides):
                print("Turns here are counted from the log, since an end condition changes the length.")
                print()
                print(END_HEADER)
                print("|" + " --- |" * END_COLUMNS)
                for job, outcome in rows:
                    print(end_row(job, outcome))
                print()
                for line in end_report(rows):
                    print(line)
                continue
            v3 = is_v3(rows[0][0].overrides)
            blended = v3 and any(is_v3blends(j.overrides) for j, _ in rows)
            bribed = v3 and any(is_v3bribe(j.overrides) for j, _ in rows)
            if v3:
                print(V3_NOTE + "\n")
            header = V3_SWEEP_HEADER + (BLEND_HEADER if blended else "") + (BRIBE_HEADER if bribed else "")
            print(header if v3 else SWEEP_HEADER)
            columns = (
                V3_SWEEP_COLUMNS + (BLEND_COLUMNS if blended else 0) + (BRIBE_COLUMNS if bribed else 0)
            ) if v3 else SWEEP_COLUMNS
            print("|" + " --- |" * columns)
            for job, outcome in rows:
                if not v3:
                    print(sweep_row(job, outcome))
                    continue
                row = v3_sweep_row(job, outcome)
                data = outcome.data
                if blended:
                    row += _blend_columns(data) if data is not None else " |" * BLEND_COLUMNS
                if bribed:
                    row += _bribe_columns(data) if data is not None else " |" * BRIBE_COLUMNS
                print(row)
            print()
    return outcomes


def do_final(run, values: Mapping[Mode, Mapping[str, object]], players_list, seatings, n: int | None, seed: int,
             label: str = "proposed") -> list[Outcome]:
    """The final validation of ``values`` (overrides per mode; its modes are the ones run)."""
    jobs = playable([
        Job(label, mode, players, seating, values[mode], n or final_games(players), seed)
        for mode in values
        for players in players_list
        for seating in seatings
    ])
    outcomes = run(jobs)
    print(f"## Final validation of {'the proposed values' if label == 'proposed' else f'`{label}`'}\n")
    print(f"Seed {seed}; games per configuration: "
          + ", ".join(f"{p}p {n or final_games(p)}" for p in sorted({job.players for job in jobs}))
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
    parser.add_argument("--multiple-bodegas", action="store_true",
                        help="turn on multiple_bodegas (#135) in every b5 candidate (#103 phase D)")
    parser.add_argument("--season-global-only", action="store_true",
                        help="turn off season_roll_personal_faces (#138) in every b5 candidate: "
                             "a season roll applies only the season faces")
    parser.add_argument("--seat-bonus", type=parse_seat_bonus, metavar="P=B,...;P=B,...",
                        help="set seat_bonus (#142) in every b5 candidate, e.g. 4=1,1,1,0;5=1,1,1,0,0: "
                             "bonus points by round 1 position, the start player first")
    parser.add_argument("--rounds", type=parse_rounds, metavar="P=R,...",
                        help="set the round count of these player counts (#142) in every b5 candidate, "
                             "e.g. 4=5,5=5; the others keep the mode's shipped rounds")
    parser.add_argument("--river-hexes", type=_workers, nargs="+", default=list(STRIP_RIVER_HEXES),
                        metavar="N", help="sweep strip (#154): river hexes per segment (default 4 5 6)")
    parser.add_argument("--bag-per-player", type=_workers, nargs="+", default=list(STRIP_BAG_PER_PLAYER),
                        metavar="N", help="sweep strip (#154): bag sizes in pieces per player (default 12 16 20)")
    parser.add_argument("--v3-river-hexes", type=_workers, default=V3_RIVER_HEXES, metavar="N",
                        help=f"sweep v3 (#153): the base river hexes per segment (default {V3_RIVER_HEXES})")
    parser.add_argument("--v3-bag-per-player", type=_workers, default=V3_BAG_PER_PLAYER, metavar="N",
                        help=f"sweep v3 (#153): the base bag size per player (default {V3_BAG_PER_PLAYER})")
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
    sweeps = V1_SWEEPS + v2_sweeps(args.scale, args.rare_bonus, args.multiple_bodegas, args.season_global_only,
                                   args.seat_bonus, args.rounds) + strip_sweeps(args.river_hexes, args.bag_per_player) \
        + v3_sweeps(args.v3_river_hexes, args.v3_bag_per_player) + v3split_sweeps() + v3blends_sweeps()         + v3bribe_sweeps() + v3end_sweeps()
    flags = "" if (args.scale, args.rare_bonus) == (1, 1) else f" --scale {args.scale} --rare-bonus {args.rare_bonus}"
    if args.multiple_bodegas:
        flags += " --multiple-bodegas"
    if args.season_global_only:
        flags += " --season-global-only"
    if args.seat_bonus:
        flags += f' --seat-bonus "{seat_bonus_label(args.seat_bonus)}"'
    if args.rounds:
        flags += f" --rounds {rounds_label(args.rounds)}"
    if tuple(args.river_hexes) != STRIP_RIVER_HEXES:
        flags += " --river-hexes " + " ".join(map(str, args.river_hexes))
    if tuple(args.bag_per_player) != STRIP_BAG_PER_PLAYER:
        flags += " --bag-per-player " + " ".join(map(str, args.bag_per_player))
    if args.v3_river_hexes != V3_RIVER_HEXES:
        flags += f" --v3-river-hexes {args.v3_river_hexes}"
    if args.v3_bag_per_player != V3_BAG_PER_PLAYER:
        flags += f" --v3-bag-per-player {args.v3_bag_per_player}"
    players_list = [args.players] if args.players else list(PLAYER_COUNTS)
    candidate = None
    if args.candidate:
        if args.sweep:
            parser.error("--candidate and --sweep cannot be combined")
        try:
            candidate = find_candidate(sweeps, *args.candidate, modes)
        except ValueError as error:
            parser.error(str(error))
        if args.players:
            for mode, values in candidate[1].items():
                if not plays(mode, args.players, values):
                    parser.error(f"{mode.value} mode is for {players_text(tuple(sorted(values['rounds'])))} "
                                 f"players in candidate {args.candidate[1]!r}, got --players {args.players}")

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
