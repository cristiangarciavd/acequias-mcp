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
from types import MappingProxyType

from acequias.model import MAX_PLAYERS, MIN_PLAYERS, Mode, PieceKind, Varietal

PLAYER_COUNTS = tuple(range(MIN_PLAYERS, MAX_PLAYERS + 1))
MIN_VINEYARD_DISTANCE = 2
MIN_DIE_FACES = 2


@dataclass(frozen=True, slots=True)
class Preset:
    """The numbers for one game mode.

    ``rounds`` maps each player count (2 to 5) to its round count.
    ``vineyard_distance`` is the ``(low, high)`` range, in hexes, of a
    vineyard's distance from the river. ``stone_share`` is the percentage of
    non-river hexes that are stone, and ``bag_mix`` the percentage of the bag
    for each ``PieceKind``. A player whose watered vineyards include
    ``bodega_varietals`` distinct varietals earns ``bodega_points``.
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
        if self.bodega_varietals > len(Varietal):
            raise ValueError(
                f"bodega_varietals must be 1 to {len(Varietal)} (the number of varietals), "
                f"got {self.bodega_varietals}"
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
