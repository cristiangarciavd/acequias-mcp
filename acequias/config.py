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

from acequias.model import MAX_PLAYERS, MIN_PLAYERS, Mode, PieceKind, Varietal

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
    ``bodega_varietals`` distinct varietals earns ``bodega_points``.

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
    varietal_rules: VarietalRules
    varietal_points: Mapping[Varietal, int]
    roulette: tuple[Varietal, ...]
    grape_clusters_per_player: int | None

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

    def rounds_for(self, players: int) -> int:
        """The round count for a game of ``players`` players (2 to 5)."""
        _check_int("players", players)
        if players not in self.rounds:
            raise ValueError(
                f"players must be {MIN_PLAYERS} to {MAX_PLAYERS}, got {players}"
            )
        return self.rounds[players]


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
    varietal_rules=VarietalRules.FIXED,
    varietal_points={Varietal.MALBEC: 3, Varietal.BONARDA: 2, Varietal.TORRONTES: 1},
    roulette=ROULETTE_SECTORS,
    grape_clusters_per_player=None,
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
    varietal_rules=VarietalRules.FIXED,
    varietal_points=NORMAL.varietal_points,
    roulette=ROULETTE_SECTORS,
    grape_clusters_per_player=None,
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
