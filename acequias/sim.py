"""The simulation: many complete bot games and their balance statistics.

``simulate_game(rules, n, seed)`` plays ``n`` games with the bots named in
``rules`` and returns a ``SimResult``, an immutable value with the
statistics used to tune the open parameters in ``README.md`` and to check
the quality criteria (turn-order advantage of 10% or less in each mode).

Every game has its own seed, ``game_seed(seed, i)``, and
``play_one(rules, game_seed)`` plays any single game of a run again.
A game is ``new_game`` with the run's preset, then ``play_game`` with
``game_rngs(game_seed)``, then ``calculate_score`` and ``winners``. This
module draws no random numbers except to derive game seeds, reads every
rule value from the preset, and reimplements no rules. Standard library
only.

``SimResult.to_json`` uses the JSON names of ``server/schemas.py``: modes by
value, varietals and piece kinds by lowercase ASCII enum name. ``acequias``
never imports ``server``, so the few names are written out here.
"""

from __future__ import annotations

import dataclasses
import random
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType

from acequias.bots import policy
from acequias.config import Preset, preset as shipped_preset, with_overrides
from acequias.game import Bot, TurnRecord, game_rngs, play_game, turn_order
from acequias.model import MAX_PLAYERS, MIN_PLAYERS, GameState, Mode, Varietal
from acequias.scoring import Score, calculate_score, winners
from acequias.setup import new_game
from acequias.turn import Bribe, Pass, PlaceCanal, PlaceFloodgate

__all__ = [
    "SimRules",
    "GameRecord",
    "SimResult",
    "game_seed",
    "play_one",
    "simulate_game",
    "summarize",
]

SCORE_TERMS = ("vineyards", "bodega", "rights_paid", "rights_collected", "debt", "total")
"""The ``Score`` fields summarized in ``SimResult.score_terms``."""

ACTION_NAMES = (
    (PlaceCanal, "canal"),
    (PlaceFloodgate, "floodgate"),
    (Bribe, "bribe"),
    (Pass, "pass"),
)
"""Each action type and its key in ``SimResult.actions_per_game``."""


# --- Input -------------------------------------------------------------------


@dataclass(frozen=True)
class SimRules:
    """What to simulate: the mode, the player count, a bot per seat, and preset overrides.

    ``policies[k]`` is the policy name of the player in seat ``k + 1`` (id
    ``"p{k+1}"``), whatever the start player is. ``overrides`` maps
    ``Preset`` field names to values that replace the mode's shipped
    preset (``with_overrides``); it is stored read-only.
    """

    mode: Mode
    players: int
    policies: tuple[str, ...]
    overrides: Mapping[str, object] = field(
        default_factory=lambda: MappingProxyType({}), hash=False
    )

    def __post_init__(self) -> None:
        if not isinstance(self.mode, Mode):
            raise TypeError(f"mode must be a Mode, got {self.mode!r}")
        _check_int("players", self.players)
        if not MIN_PLAYERS <= self.players <= MAX_PLAYERS:
            raise ValueError(
                f"players must be {MIN_PLAYERS} to {MAX_PLAYERS}, got {self.players}"
            )
        if isinstance(self.policies, (str, bytes)) or not isinstance(self.policies, Iterable):
            raise TypeError(f"policies must be a sequence of policy names, got {self.policies!r}")
        policies = tuple(self.policies)
        if len(policies) != self.players:
            raise ValueError(
                f"policies must name one policy per player ({self.players}), "
                f"got {len(policies)}"
            )
        object.__setattr__(self, "policies", policies)
        if not isinstance(self.overrides, Mapping):
            raise TypeError(f"overrides must be a mapping, got {self.overrides!r}")
        object.__setattr__(self, "overrides", MappingProxyType(dict(self.overrides)))


# --- One game ----------------------------------------------------------------


@dataclass(frozen=True)
class GameRecord:
    """One finished game: its seed, start and final states, turn log, scores, and winners."""

    game_seed: int
    start: GameState
    final: GameState
    log: tuple[TurnRecord, ...]
    scores: Mapping[str, Score] = field(hash=False)
    winners: tuple[str, ...]


def game_seed(seed: int, i: int) -> int:
    """The seed of game ``i`` (0 or more) of the run with ``seed``.

    Pure and process-independent: ``random.Random`` hashes a string seed the
    same way in every process.
    """
    _check_int("seed", seed)
    _check_int("i", i)
    if i < 0:
        raise ValueError(f"i must be 0 or more, got {i}")
    return random.Random(f"game:{seed}:{i}").getrandbits(63)


def play_one(rules: SimRules, game_seed: int) -> GameRecord:
    """Play the game with ``game_seed`` under ``rules`` and return its record.

    Game ``i`` of ``simulate_game(rules, n, seed)`` is
    ``play_one(rules, game_seed(seed, i))``.
    """
    _check_rules(rules)
    _check_int("game_seed", game_seed)
    return _play(rules, _preset(rules), _bots(rules), game_seed, index=None)


def _play(
    rules: SimRules, preset: Preset, bots: Sequence[Bot], seed: int, index: int | None
) -> GameRecord:
    try:
        start = new_game(rules.players, seed, rules.mode, preset=preset)
    except ValueError as error:
        if index is None:
            raise
        raise ValueError(f"game {index} (game seed {seed}) cannot be set up: {error}") from error
    by_id = {p.id: bots[p.seat - 1] for p in start.players}
    final, log = play_game(start, by_id, *game_rngs(seed))
    scores = calculate_score(final)
    return GameRecord(seed, start, final, log, scores, winners(scores))


# --- The run -----------------------------------------------------------------


@dataclass(frozen=True)
class SimResult:
    """The balance statistics of one simulation run, and the inputs that produced it.

    Notation: a run has ``n`` games of ``P`` players; a *player-game* is one
    player in one game. *Position* ``j`` (1 to ``P``) is the player's place
    in ``turn_order(start, 1)``, so position 1 starts round 1. When ``k``
    players share a win, each gets ``1/k`` *win credit*, so every game
    hands out exactly 1.
    """

    mode: str
    """The mode's JSON name, ``"normal"`` or ``"flash"``."""
    players: int
    """The player count ``P``."""
    policies: tuple[str, ...]
    """The policy name of each seat, seat 1 first."""
    n: int
    """The number of games played."""
    seed: int
    """The run seed; game ``i`` used ``game_seed(seed, i)``."""
    preset: Mapping[str, object] = field(hash=False)
    """Every value of the preset used, after overrides: ``mode`` by value,
    ``rounds`` by player count, ``vineyard_distance`` as ``(low, high)``,
    ``bag_mix`` keyed by lowercase piece kind name, the rest as ints."""

    win_rate_by_position: tuple[float, ...]
    """Entry ``j - 1``: total win credit of position-``j`` players / ``n``. Adds up to 1."""
    win_rate_by_seat: tuple[float, ...]
    """Entry ``s - 1``: total win credit of the seat-``s`` player / ``n``. Adds up to 1."""
    win_rate_by_policy: Mapping[str, float] = field(hash=False)
    """Policy name: total win credit of the seats with that policy / ``n``. Adds up to 1."""
    turn_order_advantage: float
    """``max_j |win_rate_by_position[j] - 1/P| * P``: 0.10 means a position wins
    10% more or less than its fair share."""
    shared_win_rate: float
    """Share of games with more than one winner."""
    score_terms: Mapping[str, Mapping[str, float]] = field(hash=False)
    """For each ``Score`` term (vineyards, bodega, rights_paid, rights_collected,
    debt, total): ``{"mean", "stdev"}`` over all player-games (population
    standard deviation)."""
    mean_total_by_position: tuple[float, ...]
    """Entry ``j - 1``: the mean ``total`` of position-``j`` players."""
    winning_score: Mapping[str, float] = field(hash=False)
    """``{"mean", "stdev"}`` of each game's highest ``total`` (population
    standard deviation; one value per game, shared wins included)."""
    turns_per_game: float
    """The mean log length (rounds * P)."""
    actions_per_game: Mapping[str, float] = field(hash=False)
    """The mean number of each action per game, keyed ``"canal"``,
    ``"floodgate"``, ``"bribe"``, ``"pass"``; they add up to ``turns_per_game``."""
    games_with_bribe: float
    """Share of games whose log has at least one ``Bribe``."""
    games_with_floodgate: float
    """Share of games whose log has at least one ``PlaceFloodgate``."""
    win_rate_bribers: float | None
    """Mean win credit of player-games with at least one ``Bribe``; None if there are none."""
    win_rate_non_bribers: float | None
    """Mean win credit of player-games with no ``Bribe``; None if there are none."""
    bodega_rate: float
    """Share of player-games with a bodega bonus (``bodega > 0``)."""
    winner_varietal_rate: Mapping[str, float] = field(hash=False)
    """Varietal JSON name: share of games in which at least one winner has a
    watered vineyard of that varietal."""

    def to_json(self) -> dict[str, object]:
        """The result as plain JSON data: dicts with string keys, lists, str, int, float, None."""
        return {f.name: _to_json(getattr(self, f.name)) for f in dataclasses.fields(self)}


def simulate_game(rules: SimRules, n: int, seed: int) -> SimResult:
    """Play ``n`` games under ``rules`` from run ``seed`` and return their statistics.

    Game ``i`` (0 to ``n - 1``, in order) is
    ``play_one(rules, game_seed(seed, i))``. The same arguments always give
    an equal result. Raises ``ValueError`` naming the game index and seed
    when the board generator cannot meet the preset; no partial result is
    returned.
    """
    _check_rules(rules)
    _check_int("n", n)
    _check_int("seed", seed)
    if n < 1:
        raise ValueError(f"n must be at least 1, got {n}")
    preset = _preset(rules)
    bots = _bots(rules)
    records = [_play(rules, preset, bots, game_seed(seed, i), index=i) for i in range(n)]
    return summarize(rules, seed, records)


def summarize(rules: SimRules, seed: int, records: Iterable[GameRecord]) -> SimResult:
    """The ``SimResult`` of ``records``, the games of run ``seed`` under ``rules`` in order.

    ``simulate_game`` is ``summarize`` over the ``play_one`` records of its
    game seeds; a run whose games were played elsewhere (e.g. in parallel)
    is summarized the same way.
    """
    _check_rules(rules)
    _check_int("seed", seed)
    records = tuple(records)
    for i, record in enumerate(records):
        if not isinstance(record, GameRecord):
            raise TypeError(f"records[{i}] must be a GameRecord, got {record!r}")
    if not records:
        raise ValueError("records must hold at least one game")
    n = len(records)
    count = rules.players
    preset = _preset(rules)

    by_position = [0.0] * count
    by_seat = [0.0] * count
    by_policy = {name: 0.0 for name in rules.policies}
    totals_by_position: list[list[int]] = [[] for _ in range(count)]
    terms: dict[str, list[int]] = {term: [] for term in SCORE_TERMS}
    best_totals: list[int] = []
    turns: list[int] = []
    actions = {name: 0 for _, name in ACTION_NAMES}
    shared = with_bribe = with_floodgate = bodegas = 0
    briber_credit: list[float] = []
    other_credit: list[float] = []
    varietal_games = {varietal: 0 for varietal in Varietal}

    for record in records:
        order = turn_order(record.start, 1)
        won = set(record.winners)
        credit = 1 / len(won) if won else 0.0
        if len(won) > 1:
            shared += 1
        bribers = {r.player for r in record.log if isinstance(r.action, Bribe)}
        if bribers:
            with_bribe += 1
        if any(isinstance(r.action, PlaceFloodgate) for r in record.log):
            with_floodgate += 1
        turns.append(len(record.log))
        for r in record.log:
            for kind, name in ACTION_NAMES:
                if isinstance(r.action, kind):
                    actions[name] += 1

        for player in record.start.players:
            score = record.scores[player.id]
            mine = credit if player.id in won else 0.0
            position = order.index(player.id)
            by_position[position] += mine
            by_seat[player.seat - 1] += mine
            by_policy[rules.policies[player.seat - 1]] += mine
            totals_by_position[position].append(score.total)
            for term in SCORE_TERMS:
                terms[term].append(getattr(score, term))
            if score.bodega > 0:
                bodegas += 1
            (briber_credit if player.id in bribers else other_credit).append(mine)
        best_totals.append(max(s.total for s in record.scores.values()))

        for varietal in Varietal:
            if any(
                v.varietal is varietal
                for winner in record.winners
                for v in record.scores[winner].watered_vineyards
            ):
                varietal_games[varietal] += 1

    win_rate_by_position = tuple(credit / n for credit in by_position)
    fair = 1 / count
    return SimResult(
        mode=_MODE_NAMES[rules.mode],
        players=count,
        policies=rules.policies,
        n=n,
        seed=seed,
        preset=_preset_values(preset),
        win_rate_by_position=win_rate_by_position,
        win_rate_by_seat=tuple(credit / n for credit in by_seat),
        win_rate_by_policy=MappingProxyType({k: v / n for k, v in by_policy.items()}),
        turn_order_advantage=max(abs(rate - fair) for rate in win_rate_by_position) * count,
        shared_win_rate=shared / n,
        score_terms=MappingProxyType({term: _spread(terms[term]) for term in SCORE_TERMS}),
        mean_total_by_position=tuple(statistics.fmean(t) for t in totals_by_position),
        winning_score=_spread(best_totals),
        turns_per_game=statistics.fmean(turns),
        actions_per_game=MappingProxyType({k: v / n for k, v in actions.items()}),
        games_with_bribe=with_bribe / n,
        games_with_floodgate=with_floodgate / n,
        win_rate_bribers=statistics.fmean(briber_credit) if briber_credit else None,
        win_rate_non_bribers=statistics.fmean(other_credit) if other_credit else None,
        bodega_rate=bodegas / (n * count),
        winner_varietal_rate=MappingProxyType(
            {_VARIETAL_NAMES[v]: games / n for v, games in varietal_games.items()}
        ),
    )


# --- JSON names (as in server/schemas.py) -------------------------------------

_MODE_NAMES = {mode: mode.value for mode in Mode}
_VARIETAL_NAMES = {varietal: varietal.name.lower() for varietal in Varietal}


def _preset_values(preset: Preset) -> Mapping[str, object]:
    values: dict[str, object] = {}
    for f in dataclasses.fields(Preset):
        value = getattr(preset, f.name)
        if f.name == "mode":
            value = _MODE_NAMES[value]
        elif f.name == "rounds":
            value = MappingProxyType(dict(value))
        elif f.name == "bag_mix":
            value = MappingProxyType({kind.name.lower(): share for kind, share in value.items()})
        elif f.name == "vineyard_distance":
            value = tuple(value)
        values[f.name] = value
    return MappingProxyType(values)


def _to_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(k): _to_json(v) for k, v in value.items()}
    if isinstance(value, tuple):
        return [_to_json(v) for v in value]
    return value


# --- Helpers -----------------------------------------------------------------


def _spread(values: Sequence[int]) -> Mapping[str, float]:
    return MappingProxyType(
        {"mean": statistics.fmean(values), "stdev": float(statistics.pstdev(values))}
    )


def _preset(rules: SimRules) -> Preset:
    return with_overrides(shipped_preset(rules.mode), **rules.overrides)


def _bots(rules: SimRules) -> tuple[Bot, ...]:
    return tuple(policy(name) for name in rules.policies)


def _check_rules(rules: object) -> None:
    if not isinstance(rules, SimRules):
        raise TypeError(f"rules must be a SimRules, got {rules!r}")


def _check_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {value!r}")
