"""The Normal and Flash presets: every number the game needs, in one place.

Values are the ones in ``README.md`` (Game modes, Setup, Bodega bonus),
tuned by the simulation in #20 (``scripts/tune.py``,
``_docs/tuning-results.md``). Board
generation, setup, scoring, the round loop, and the simulation read them
from here instead of hard-coding them.

A ``Preset`` is a frozen dataclass whose mappings are read-only, and it
validates itself when built, so an invalid preset cannot exist. Tuning goes
through ``with_overrides``, which builds a new, validated preset.

Shares (bag mix, stone share) are whole-number percentages, so "adds up to
100" is an exact check.

This module depends on nothing in ``acequias`` except ``acequias.model``.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from acequias.model import MAX_PLAYERS, MIN_PLAYERS, DieFace, Mode, PieceKind, Varietal

PLAYER_COUNTS = tuple(range(MIN_PLAYERS, MAX_PLAYERS + 1))
MIN_VINEYARD_DISTANCE = 2
MIN_DIE_FACES = 2


class VarietalRules(Enum):
    """How vineyards get their varietal.

    ``FIXED``: the board generator puts a varietal from ``varietal_points``
    on every vineyard tile (the shipped game). ``ROULETTE``: vineyard tiles
    are blank, and a player who claims one spins the roulette to plant it.
    """

    FIXED = "fixed"
    ROULETTE = "roulette"


class BribeRules(Enum):
    """What the bribe action is.

    ``D6``: roll the bribe die, add the roll to your debt, and remove or
    move a floodgate (the shipped game). ``ACTION_DIE``: pay a fixed cost
    in debt, roll the action die, and use its face (floodgate, release, or
    resow); floodgates come only from the die.
    """

    D6 = "d6"
    ACTION_DIE = "action_die"


ACTION_DIE_FACES: tuple[DieFace, ...] = (
    DieFace.FLOODGATE,
    DieFace.FLOODGATE,
    DieFace.RELEASE,
    DieFace.RELEASE,
    DieFace.RESOW,
    DieFace.RESOW,
)
"""The action die's 6 faces, in order: two of each."""

CONSTRUCTIVE_DIE_FACES: tuple[DieFace, ...] = (
    DieFace.FLOODGATE,
    DieFace.RELEASE,
    DieFace.RESOW,
    DieFace.RESOW,
    DieFace.GOOD_SEASON,
    DieFace.DROUGHT,
)
"""The constructive action die (#130), in order: floodgate, release, two
resows, good season, drought. An opt-in ``action_die``; ``ACTION_DIE_FACES``
stays the default."""

# Provisional: the debt a roll of the action die costs. The owner's range is
# 2 or 3; the final value is tuned in #103.
ACTION_DIE_COST = 2


ROULETTE_SECTORS: tuple[Varietal, ...] = (
    Varietal.MALBEC,
    Varietal.MALBEC,
    Varietal.CABERNET_SAUVIGNON,
    Varietal.CABERNET_SAUVIGNON,
    Varietal.SYRAH,
    Varietal.SYRAH,
    Varietal.MERLOT,
    Varietal.MERLOT,
    Varietal.TORRONTES,
    Varietal.TORRONTES,
    Varietal.CHARDONNAY,
    Varietal.CHARDONNAY,
    Varietal.BONARDA,
    Varietal.CABERNET_FRANC,
)
"""The roulette's 14 equal sectors, in order: Bonarda and Cabernet Franc
have one each, every other varietal two."""

# Provisional points under roulette rules: Bonarda and Cabernet Franc are
# worth a bit more. The final values are tuned in #103 (with #111's scale).
ROULETTE_POINTS: Mapping[Varietal, int] = MappingProxyType(
    {
        Varietal.MALBEC: 2,
        Varietal.CABERNET_SAUVIGNON: 2,
        Varietal.CABERNET_FRANC: 3,
        Varietal.SYRAH: 2,
        Varietal.MERLOT: 2,
        Varietal.BONARDA: 3,
        Varietal.TORRONTES: 2,
        Varietal.CHARDONNAY: 2,
    }
)


@dataclass(frozen=True, slots=True)
class Preset:
    """The numbers for one game mode.

    ``rounds`` maps each player count (2 to 5) to its round count.
    ``vineyard_distance`` is the ``(low, high)`` range, in hexes, of a
    vineyard's distance from the river. ``stone_share`` is the percentage of
    non-river hexes that are stone, and ``bag_mix`` the percentage of the bag
    for each ``PieceKind``. A player whose watered vineyards include
    ``bodega_varietals`` distinct varietals earns ``bodega_points``. With
    ``multiple_bodegas`` (off by default) a player earns it once per
    disjoint group of ``bodega_varietals`` watered vineyards of distinct
    varietals (``acequias.scoring.bodega_count``).
    ``water_right_points`` is what a watered claimed vineyard pays each
    distinct rival who owns a canal on its water path.

    ``varietal_rules`` says how vineyards get their varietal (fixed on the
    board, or planted by the roulette on claim). ``varietal_points`` maps
    each varietal in play to the points a watered vineyard of it scores
    (read-only, in the order given); under fixed rules its keys are the
    varietals the board generator deals. ``roulette`` lists the roulette's
    sectors in order, one varietal each; it is used only under roulette
    rules.

    ``vineyards_per_player`` is the number of vineyard plots per player on
    the board. ``grape_clusters_per_player`` caps the claims each player can
    hold; ``None`` means no cap (the shipped game).

    ``bribe_rules`` says what the bribe action is: the d6 bribe (shipped)
    or the action die. ``action_die_cost`` is the debt one roll of the
    action die costs, and ``action_die`` its faces in order; both are used
    only under ``action_die`` rules, where the bag has no floodgates
    (``bag_mix`` gives them 0) and a ``RESOW`` face needs roulette rules.
    ``die_faces`` is the bribe d6, used only under ``d6`` rules.

    Season faces of the action die (``GOOD_SEASON``, ``DROUGHT``) give
    every player ``season_gain`` or take ``drought_loss`` from them (a
    drought never takes a score below 0; see ``acequias.scoring``).
    ``season_points`` and ``drought_points`` set those values; ``None``
    (the default) derives them: ``season_gain`` is one common vineyard
    plot's value (``common_vineyard_points``), and ``drought_loss`` half
    of ``season_gain``, rounded down, at least 1. ``season_roll_every``
    (``None``: off, the default) starts every X-th round with a free roll
    of the action die by the season die's holder, which passes to the
    next seat after each season roll (``acequias.game.season_holder``);
    it needs action die rules.
    """

    mode: Mode
    rounds: Mapping[int, int]
    hexes_per_player: int
    vineyards_per_player: int
    stone_share: int
    vineyard_distance: tuple[int, int]
    market_size: int
    bag_mix: Mapping[PieceKind, int]
    die_faces: int
    bodega_points: int
    bodega_varietals: int
    water_right_points: int
    varietal_rules: VarietalRules
    varietal_points: Mapping[Varietal, int]
    roulette: tuple[Varietal, ...]
    grape_clusters_per_player: int | None
    bribe_rules: BribeRules
    action_die_cost: int
    action_die: tuple[DieFace, ...]
    season_points: int | None = None
    drought_points: int | None = None
    season_roll_every: int | None = None
    multiple_bodegas: bool = False

    def __post_init__(self) -> None:
        _check_type("mode", self.mode, Mode)
        _set(self, "rounds", _rounds(self.rounds))
        for name in (
            "hexes_per_player",
            "vineyards_per_player",
            "market_size",
            "die_faces",
            "bodega_points",
            "bodega_varietals",
            "water_right_points",
        ):
            _check_count(name, getattr(self, name))
        _check_share("stone_share", self.stone_share)
        _set(self, "vineyard_distance", _distance(self.vineyard_distance))
        _set(self, "bag_mix", _bag_mix(self.bag_mix))

        if self.die_faces < MIN_DIE_FACES:
            raise ValueError(f"die_faces must be at least {MIN_DIE_FACES}, got {self.die_faces}")
        _check_type("varietal_rules", self.varietal_rules, VarietalRules)
        _set(self, "varietal_points", _varietal_points(self.varietal_points))
        _set(self, "roulette", _roulette(self.roulette))
        if self.grape_clusters_per_player is not None:
            _check_count("grape_clusters_per_player", self.grape_clusters_per_player)
        _check_type("bribe_rules", self.bribe_rules, BribeRules)
        _check_non_negative("action_die_cost", self.action_die_cost)
        _set(self, "action_die", _action_die(self.action_die))
        for name in ("season_points", "drought_points", "season_roll_every"):
            if getattr(self, name) is not None:
                _check_count(name, getattr(self, name))
        _check_type("multiple_bodegas", self.multiple_bodegas, bool)
        if self.season_roll_every is not None and self.bribe_rules is not BribeRules.ACTION_DIE:
            raise ValueError("season_roll_every needs action_die bribe rules")
        if self.bribe_rules is BribeRules.ACTION_DIE:
            if self.bag_mix[PieceKind.FLOODGATE] != 0:
                raise ValueError(
                    "under action_die rules floodgates come only from the die, so "
                    f"bag_mix[FLOODGATE] must be 0, got {self.bag_mix[PieceKind.FLOODGATE]}"
                )
            if (
                DieFace.RESOW in self.action_die
                and self.varietal_rules is not VarietalRules.ROULETTE
            ):
                raise ValueError("the action die's RESOW face needs roulette varietal rules")
        if self.varietal_rules is VarietalRules.FIXED:
            in_play = len(self.varietal_points)
            where = "varietal_points"
        else:
            unscored = sorted({v.name for v in self.roulette if v not in self.varietal_points})
            if unscored:
                raise ValueError(
                    f"roulette sectors {unscored} have no entry in varietal_points"
                )
            in_play = len(set(self.roulette))
            where = "roulette"
        if self.bodega_varietals > in_play:
            raise ValueError(
                f"bodega_varietals must be 1 to {in_play} (the distinct varietals in "
                f"{where} under {self.varietal_rules.value} rules), got {self.bodega_varietals}"
            )
        for players in PLAYER_COUNTS:
            hexes = players * self.hexes_per_player
            vineyards = players * self.vineyards_per_player
            stones = _ceil_share(self.stone_share, hexes)
            if vineyards + stones >= hexes:
                raise ValueError(
                    f"with {players} players, {vineyards} vineyards and {stones} stone hexes "
                    f"leave no empty hex out of {hexes}"
                )

    @property
    def season_gain(self) -> int:
        """What a good season face gives every player: ``season_points``, or one common plot's value."""
        if self.season_points is not None:
            return self.season_points
        return common_vineyard_points(self)

    @property
    def drought_loss(self) -> int:
        """What a drought face takes from every player: ``drought_points``, or half the season gain."""
        if self.drought_points is not None:
            return self.drought_points
        return max(1, self.season_gain // 2)

    def is_season_round(self, round: int) -> bool:
        """Whether ``round`` starts with a free season roll: every ``season_roll_every``-th round."""
        return self.season_roll_every is not None and round % self.season_roll_every == 0

    def rounds_for(self, players: int) -> int:
        """The round count for a game of ``players`` players (2 to 5)."""
        _check_int("players", players)
        if players not in self.rounds:
            raise ValueError(
                f"players must be {MIN_PLAYERS} to {MAX_PLAYERS}, got {players}"
            )
        return self.rounds[players]


def common_vineyard_points(p: Preset) -> int:
    """The points of one common vineyard plot under ``p``.

    The most frequent value among the plots a game can deal: the points of
    each roulette sector under roulette rules, of each varietal in
    ``varietal_points`` under fixed rules. Ties go to the lower value.
    Under ``ROULETTE_POINTS`` it is 2 (12 of the 14 sectors), and it
    scales with ``scaled``.
    """
    if p.varietal_rules is VarietalRules.ROULETTE:
        values = [p.varietal_points[v] for v in p.roulette]
    else:
        values = list(p.varietal_points.values())
    return min(set(values), key=lambda v: (-values.count(v), v))


# --- Helpers ---------------------------------------------------------------


def _set(obj: object, name: str, value: object) -> None:
    object.__setattr__(obj, name, value)


def _check_type(name: str, value: object, cls: type) -> None:
    if not isinstance(value, cls):
        raise TypeError(f"{name} must be a {cls.__name__}, got {value!r}")


def _check_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {value!r}")


def _check_count(name: str, value: object) -> None:
    _check_int(name, value)
    if value < 1:
        raise ValueError(f"{name} must be at least 1, got {value}")


def _check_non_negative(name: str, value: object) -> None:
    _check_int(name, value)
    if value < 0:
        raise ValueError(f"{name} must be at least 0, got {value}")


def _check_share(name: str, value: object) -> None:
    _check_int(name, value)
    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be a percentage from 0 to 100, got {value}")


def _ceil_share(share: int, total: int) -> int:
    """``share`` percent of ``total``, rounded up, in exact integer arithmetic."""
    return -(-share * total // 100)


def _rounds(value: object) -> Mapping[int, int]:
    _check_type("rounds", value, Mapping)
    missing = [n for n in PLAYER_COUNTS if n not in value]
    if missing:
        raise ValueError(f"rounds has no value for player counts {missing}")
    extra = [n for n in value if n not in PLAYER_COUNTS]
    if extra:
        raise ValueError(
            f"rounds gives player counts {extra}; only {MIN_PLAYERS} to {MAX_PLAYERS} are allowed"
        )
    for players in PLAYER_COUNTS:
        _check_count(f"rounds[{players}]", value[players])
    return MappingProxyType({players: value[players] for players in PLAYER_COUNTS})


def _distance(value: object) -> tuple[int, int]:
    if isinstance(value, (str, bytes, Mapping)) or not hasattr(value, "__iter__"):
        raise TypeError(f"vineyard_distance must be a (low, high) pair, got {value!r}")
    pair = tuple(value)
    if len(pair) != 2:
        raise ValueError(f"vineyard_distance must be a (low, high) pair, got {value!r}")
    low, high = pair
    _check_int("vineyard_distance low", low)
    _check_int("vineyard_distance high", high)
    if low < MIN_VINEYARD_DISTANCE:
        raise ValueError(
            f"vineyard_distance must start at {MIN_VINEYARD_DISTANCE} or more "
            f"(a vineyard is never next to the river), got {low}"
        )
    if low > high:
        raise ValueError(f"vineyard_distance low end {low} is above its high end {high}")
    return (low, high)


def _bag_mix(value: object) -> Mapping[PieceKind, int]:
    _check_type("bag_mix", value, Mapping)
    unknown = [k for k in value if not isinstance(k, PieceKind)]
    if unknown:
        raise ValueError(f"bag_mix has unknown piece kinds {unknown!r}")
    missing = [k.name for k in PieceKind if k not in value]
    if missing:
        raise ValueError(f"bag_mix has no share for {missing}")
    for kind in PieceKind:
        _check_share(f"bag_mix[{kind.name}]", value[kind])
    total = sum(value[kind] for kind in PieceKind)
    if total != 100:
        raise ValueError(f"bag_mix shares must add up to exactly 100, got {total}")
    return MappingProxyType({kind: value[kind] for kind in PieceKind})


def _varietal_points(value: object) -> Mapping[Varietal, int]:
    _check_type("varietal_points", value, Mapping)
    if not value:
        raise ValueError("varietal_points must give points to at least one varietal")
    unknown = [k for k in value if not isinstance(k, Varietal)]
    if unknown:
        raise ValueError(f"varietal_points has unknown varietals {unknown!r}")
    for varietal, points in value.items():
        _check_count(f"varietal_points[{varietal.name}]", points)
    return MappingProxyType(dict(value))


def _roulette(value: object) -> tuple[Varietal, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not hasattr(value, "__iter__"):
        raise TypeError(f"roulette must be a sequence of varietals, got {value!r}")
    sectors = tuple(value)
    if not sectors:
        raise ValueError("roulette must have at least one sector")
    for sector in sectors:
        _check_type("roulette sector", sector, Varietal)
    return sectors


def _action_die(value: object) -> tuple[DieFace, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not hasattr(value, "__iter__"):
        raise TypeError(f"action_die must be a sequence of die faces, got {value!r}")
    faces = tuple(value)
    if not faces:
        raise ValueError("action_die must have at least one face")
    for face in faces:
        _check_type("action_die face", face, DieFace)
    return faces


# --- Presets and access ----------------------------------------------------


NORMAL = Preset(
    mode=Mode.NORMAL,
    rounds={2: 10, 3: 15, 4: 12, 5: 10},
    hexes_per_player=15,
    vineyards_per_player=2,
    stone_share=10,
    vineyard_distance=(4, 4),
    market_size=4,
    bag_mix={
        PieceKind.STRAIGHT: 40,
        PieceKind.GENTLE_CURVE: 20,
        PieceKind.SHARP_CURVE: 15,
        PieceKind.SYMMETRIC_Y: 5,
        PieceKind.T_BRANCH: 5,
        PieceKind.CLAW: 5,
        PieceKind.FLOODGATE: 10,
    },
    die_faces=6,
    bodega_points=2,
    bodega_varietals=3,
    water_right_points=1,
    varietal_rules=VarietalRules.FIXED,
    varietal_points={Varietal.MALBEC: 3, Varietal.BONARDA: 2, Varietal.TORRONTES: 1},
    roulette=ROULETTE_SECTORS,
    grape_clusters_per_player=None,
    bribe_rules=BribeRules.D6,
    action_die_cost=ACTION_DIE_COST,
    action_die=ACTION_DIE_FACES,
)

FLASH = Preset(
    mode=Mode.FLASH,
    rounds={2: 6, 3: 6, 4: 4, 5: 4},
    hexes_per_player=14,
    vineyards_per_player=2,
    stone_share=10,
    vineyard_distance=(4, 4),
    market_size=4,
    bag_mix=NORMAL.bag_mix,
    die_faces=6,
    bodega_points=1,
    bodega_varietals=3,
    water_right_points=1,
    varietal_rules=VarietalRules.FIXED,
    varietal_points=NORMAL.varietal_points,
    roulette=ROULETTE_SECTORS,
    grape_clusters_per_player=None,
    bribe_rules=BribeRules.D6,
    action_die_cost=ACTION_DIE_COST,
    action_die=ACTION_DIE_FACES,
)

_PRESETS: Mapping[Mode, Preset] = MappingProxyType({Mode.NORMAL: NORMAL, Mode.FLASH: FLASH})


def preset(mode: Mode) -> Preset:
    """The shipped preset for ``mode``."""
    _check_type("mode", mode, Mode)
    return _PRESETS[mode]


def with_overrides(p: Preset, **changes: object) -> Preset:
    """A new, validated copy of ``p`` with ``changes`` applied; ``p`` is unchanged.

    ``mode`` cannot be overridden, so a preset's label always matches the
    mode it was built for.
    """
    _check_type("p", p, Preset)
    names = {f.name for f in dataclasses.fields(Preset)}
    for name in changes:
        if name not in names:
            raise ValueError(f"unknown preset field {name!r}")
        if name == "mode":
            raise ValueError("mode cannot be overridden")
    return dataclasses.replace(p, **changes)


def roulette_rules(p: Preset) -> Preset:
    """``p`` under roulette rules, with the provisional ``ROULETTE_POINTS``."""
    return with_overrides(
        p, varietal_rules=VarietalRules.ROULETTE, varietal_points=ROULETTE_POINTS
    )


def action_die_rules(p: Preset) -> Preset:
    """``p`` under action die rules: no floodgates in the bag.

    The floodgate share goes to 0 and the other shares are rescaled to add
    up to 100 by the largest remainder method (ties in ``PieceKind``
    order). ``p`` must be under roulette rules for the die's ``RESOW``
    face: ``action_die_rules(roulette_rules(preset(mode)))``; otherwise the
    ``Preset`` check raises ``ValueError``.
    """
    _check_type("p", p, Preset)
    kinds = [k for k in PieceKind if k is not PieceKind.FLOODGATE]
    total = sum(p.bag_mix[k] for k in kinds)
    if total == 0:
        raise ValueError("bag_mix has only floodgates; nothing is left once they leave the bag")
    mix = {k: p.bag_mix[k] * 100 // total for k in kinds}
    short = 100 - sum(mix.values())
    by_remainder = sorted(kinds, key=lambda k: (-(p.bag_mix[k] * 100 % total), kinds.index(k)))
    for k in by_remainder[:short]:
        mix[k] += 1
    mix[PieceKind.FLOODGATE] = 0
    return with_overrides(p, bribe_rules=BribeRules.ACTION_DIE, bag_mix=mix)


def scaled(p: Preset, factor: int) -> Preset:
    """A copy of ``p`` with every scoring value multiplied by ``factor``.

    ``varietal_points`` (each value), ``bodega_points`` and
    ``water_right_points`` are multiplied; everything else is kept,
    including ``bodega_varietals``, the roulette and the rounds. Explicit
    ``season_points`` and ``drought_points`` are multiplied too (derived
    ones follow ``varietal_points``). Debt is
    **not** scaled: the bribe d6 (``die_faces``) and ``action_die_cost``
    stay as they are, and #103 picks them against the scale. ``factor``
    must be an int of at least 1; ``p`` is unchanged.
    """
    _check_type("p", p, Preset)
    _check_count("factor", factor)
    return with_overrides(
        p,
        varietal_points={v: points * factor for v, points in p.varietal_points.items()},
        bodega_points=p.bodega_points * factor,
        water_right_points=p.water_right_points * factor,
        season_points=None if p.season_points is None else p.season_points * factor,
        drought_points=None if p.drought_points is None else p.drought_points * factor,
    )
