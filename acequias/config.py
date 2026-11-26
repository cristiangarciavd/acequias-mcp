"""The Normal and Flash presets: every number the game needs, in one place.

Values are the ones in ``README.md`` (Game modes, Setup, Bodega bonus):
Rules v2, tuned by the simulation in #20 and #103 (``scripts/tune.py``,
``_docs/tuning-results.md``) and approved by the owner on #103. Board
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
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType

from acequias.model import MAX_PLAYERS, MIN_PLAYERS, DieFace, Mode, PieceKind, Varietal

PLAYER_COUNTS = tuple(range(MIN_PLAYERS, MAX_PLAYERS + 1))
MIN_VINEYARD_DISTANCE = 2
MIN_DIE_FACES = 2


class VarietalRules(Enum):
    """How vineyards get their varietal.

    ``FIXED``: the board generator puts a varietal from ``varietal_points``
    on every vineyard tile (Rules v1). ``ROULETTE``: vineyard tiles are
    blank, and a player who claims one spins the roulette to plant it (the
    shipped game).
    """

    FIXED = "fixed"
    ROULETTE = "roulette"


class BribeRules(Enum):
    """What the bribe action is.

    ``D6``: roll the bribe die, add the roll to your debt, and remove or
    move a floodgate (Rules v1). ``ACTION_DIE``: pay a fixed cost in debt,
    roll the action die, and use its face; floodgates come only from the
    die (the shipped game).
    """

    D6 = "d6"
    ACTION_DIE = "action_die"


class PlantingRules(Enum):
    """Where vineyards grow.

    ``HEXES``: on vineyard tiles the board generator places (Rules v1 and
    v2, the shipped game). ``VERTICES``: on hex vertices, like Catan
    settlements (Rules v3, #149): the board has no vineyard tiles, every
    vertex touching a non-river hex is a planting spot, and a player plants
    one next to their own watered canal. Needs roulette varietal rules.
    """

    HEXES = "hexes"
    VERTICES = "vertices"


class BoardShape(Enum):
    """What the board is.

    ``FIELD``: the generated board of river, vineyard, stone and empty
    hexes (``acequias.board.generate_board``; the shipped game). ``RIVER_STRIP``:
    Rules v3's open board (#150, #154): only a strip of river hexes, with an
    unbounded, obstacle-free table to the east; the bag limits the game.
    Needs vertex planting and a ``bag_size`` for every player count.
    """

    FIELD = "field"
    RIVER_STRIP = "river_strip"


class BlendRule(Enum):
    """How blend (*corte*) bonuses score (Rules v3, #166; ``Preset.blends``).

    ``EACH_ONCE``: every blend whose varietals a player holds scores once; one
    vineyard may count for several blends. ``DISJOINT``: the best-scoring set
    of distinct blends that uses no vineyard twice.
    """

    EACH_ONCE = "each_once"
    DISJOINT = "disjoint"


class BodegaPlacement(Enum):
    """Where a bodega building goes (Rules v3, #166; ``Preset.bodega_placement``).

    ``NEW_SPOT``: on a free vertex the player may plant on (next to their own
    watered canal). ``REPLACE``: in place of one of the player's planted
    vineyards, which leaves the board.
    """

    NEW_SPOT = "new_spot"
    REPLACE = "replace"


class EndCondition(Enum):
    """What ends the game (Rules v3, opt-in, #163; ``Preset.end_condition``).

    ``ROUNDS``: after the preset's round count (the default; every shipped
    game). ``BAG_EMPTY``: when the canal bag and the market are both empty.
    ``VINEYARDS_OUT``: when a player has planted all their vineyard markers
    (``Preset.markers_for``). ``SCORE_TARGET``: when a player's total
    reaches ``Preset.target_for``. ``SUPPLY_EMPTY`` (#181): when the shared
    vineyard supply (``Preset.vineyard_supply``) has no piece left.
    ``DEAD_TURNS`` (#181): when every player has lost ``DEAD_TURN_LIMIT``
    turns in a row (``Player.dead_turns``); it always ends the game at once.
    With ``Preset.finish_round`` the game ends after the round in which
    the trigger fired; otherwise right after the turn that fired it. A game
    whose trigger never fires ends after ``END_CAP_FACTOR`` times the round
    count (``Preset.round_cap``). ``Preset.end_conditions`` combines several
    triggers: the first to fire ends the game.
    """

    ROUNDS = "rounds"
    BAG_EMPTY = "bag_empty"
    VINEYARDS_OUT = "vineyards_out"
    SCORE_TARGET = "score_target"
    SUPPLY_EMPTY = "supply_empty"
    DEAD_TURNS = "dead_turns"


END_CAP_FACTOR = 2
"""Under an end condition other than ``ROUNDS``, the game ends at the latest after this many
times the preset's round count (#163: the shipped rounds x2)."""
DEAD_TURN_LIMIT = 2
"""``EndCondition.DEAD_TURNS`` (#181) fires once every player has lost this many turns in a row."""
VINEYARD_MARKERS: Mapping[Mode, Mapping[int, int]] = MappingProxyType({
    Mode.NORMAL: MappingProxyType({2: 6, 3: 9, 4: 7, 5: 6}),
    Mode.FLASH: MappingProxyType({2: 3, 3: 3}),
})
"""Vineyard markers per player by default for ``VINEYARDS_OUT`` (#163): about the vineyards
planted per player in #160's any-vertex games."""
SCORE_TARGETS: Mapping[Mode, Mapping[int, int]] = MappingProxyType({
    Mode.NORMAL: MappingProxyType({2: 30, 3: 51, 4: 43, 5: 37}),
    Mode.FLASH: MappingProxyType({2: 14, 3: 14}),
})
"""Score targets by default for ``SCORE_TARGET`` (#163): #160's mean winning scores."""


@dataclass(frozen=True, slots=True)
class Blend:
    """A blend (*corte*): a set of at least 2 varietals, and its bonus points (#166).

    Any varietals may blend: red, white (``Varietal.is_white``) or mixed.
    """

    varietals: frozenset[Varietal]
    points: int

    def __post_init__(self) -> None:
        value = self.varietals
        if isinstance(value, (str, bytes, Mapping)) or not hasattr(value, "__iter__"):
            raise TypeError(f"a blend's varietals must be a set of varietals, got {value!r}")
        items = tuple(value)
        for v in items:
            _check_type("blend varietal", v, Varietal)
        varietals = frozenset(items)
        if len(varietals) != len(items):
            raise ValueError(f"a blend lists a varietal twice: {items!r}")
        if len(varietals) < 2:
            raise ValueError(f"a blend needs at least 2 varietals, got {len(varietals)}")
        _set(self, "varietals", varietals)
        _check_count("blend points", self.points)

    def __repr__(self) -> str:
        """Stable across processes: the varietals in ``Varietal`` order, not set order."""
        names = ", ".join(f"Varietal.{v.name}" for v in Varietal if v in self.varietals)
        return f"Blend(frozenset({{{names}}}), {self.points})"

    @property
    def name(self) -> str:
        """The varietals' names in ``Varietal`` order, joined by " + "."""
        return " + ".join(v.display_name for v in Varietal if v in self.varietals)


RIVER_HEXES_PER_SEGMENT = 5
"""River hexes in each segment of the river strip, by default (owner, #150)."""


ACTION_DIE_FACES: tuple[DieFace, ...] = (
    DieFace.FLOODGATE,
    DieFace.FLOODGATE,
    DieFace.RELEASE,
    DieFace.RELEASE,
    DieFace.RESOW,
    DieFace.RESOW,
)
"""An action die of 6 faces, in order: two of each (#103's first draft, kept for tuning)."""

CONSTRUCTIVE_DIE_FACES: tuple[DieFace, ...] = (
    DieFace.FLOODGATE,
    DieFace.RELEASE,
    DieFace.RESOW,
    DieFace.RESOW,
    DieFace.GOOD_SEASON,
    DieFace.DROUGHT,
)
"""The constructive action die (#130), in order: floodgate, release, two
resows, good season, drought: the shipped ``action_die`` (#103)."""

V3_DIE_FACES: tuple[DieFace, ...] = (
    DieFace.FLOODGATE,
    DieFace.RELEASE,
    DieFace.RESOW,
    DieFace.MOVE,
    DieFace.GOOD_SEASON,
    DieFace.DROUGHT,
)
"""The Rules v3 action die (owner, #160), in order: floodgate, release, resow,
move, good season, drought: six distinct faces. ``MOVE`` needs vertex
planting."""

ACTION_DIE_COST = 1
"""The debt a roll of the action die costs (#103)."""


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

# Points under roulette rules at scale 1: Bonarda and Cabernet Franc are
# worth a bit more. ``roulette_rules`` uses them; the shipped presets use
# ``SHIPPED_POINTS`` (#103).
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

SHIPPED_POINTS: Mapping[Varietal, int] = MappingProxyType(
    {
        Varietal.MALBEC: 6,
        Varietal.CABERNET_SAUVIGNON: 6,
        Varietal.CABERNET_FRANC: 7,
        Varietal.SYRAH: 6,
        Varietal.MERLOT: 6,
        Varietal.BONARDA: 7,
        Varietal.TORRONTES: 6,
        Varietal.CHARDONNAY: 6,
    }
)
"""The shipped points of a watered vineyard (#103): ``ROULETTE_POINTS`` at
scale 3 with a rare bonus of 1, so 6 for a common varietal and 7 for the
rare Bonarda and Cabernet Franc."""

V3_POINTS: Mapping[Varietal, int] = MappingProxyType(
    {v: 9 if v in (Varietal.BONARDA, Varietal.CABERNET_FRANC) else 6 for v in SHIPPED_POINTS}
)
"""Rules v3 vineyard values (#160): 6 for a common varietal, 9 for the rare
Bonarda and Cabernet Franc, so each third of a split vineyard is a whole
number (``acequias.scoring``). Opt-in, like the rest of Rules v3."""


@dataclass(frozen=True, slots=True)
class Preset:
    """The numbers for one game mode.

    ``rounds`` maps each player count the mode is for (some or all of 2
    to 5) to its round count; a player count it does not list cannot be
    played (``player_counts``, ``check_players``).
    ``vineyard_distance`` is the ``(low, high)`` range, in hexes, of a
    vineyard's distance from the river. ``stone_share`` is the percentage of
    non-river hexes that are stone, and ``bag_mix`` the percentage of the bag
    for each ``PieceKind``. A player whose watered vineyards include
    ``bodega_varietals`` distinct varietals earns ``bodega_points``. With
    ``multiple_bodegas`` (off by default, on in the shipped presets) a player earns it once per
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

    ``bribe_rules`` says what the bribe action is: the d6 bribe (Rules v1)
    or the action die (shipped). ``action_die_cost`` is the debt one roll of the
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
    (``None``: off, the default; on in the shipped presets) starts every X-th round with a free roll
    of the action die by the season die's holder, which passes to the
    next seat after each season roll (``acequias.game.season_holder``);
    it needs action die rules. With ``season_roll_personal_faces`` off
    (on by default, off in the shipped presets), a season roll applies only a season face: a
    personal face it rolls does nothing (voluntary rolls are unchanged).

    ``seat_bonus`` (empty by default: off) maps a player count to each
    seat's bonus points at the start, in round 1's turn order: entry 0 is
    the first start player's, entry 1 the next seat's, and so on (the
    "position" of ``acequias.sim``). A player count it does not list gets
    no bonus; only player counts in ``rounds`` may be listed. Each tuple
    has one int >= 0 per player. The bonus is a term
    of the final score (``acequias.scoring``). It is read-only, keyed in
    player count order.

    ``planting`` (``HEXES`` by default and in the shipped presets) says
    where vineyards grow: on vineyard tiles, or on vertices (Rules v3,
    opt-in). Under ``VERTICES`` the board has no vineyard tiles, so
    ``vineyards_per_player`` and ``vineyard_distance`` place nothing, and
    roulette varietal rules and action die bribe rules are required. Vertex
    planting also turns on the Rules v3 turn (``acequias.turn``): a
    mandatory die roll, then one action; ``action_die_cost`` is then the
    bribe the floodgate and release faces cost, and ``season_roll_every``
    is ignored (no season roll, ``is_season_round`` is always False).
    ``vertex_needs_three_canals`` (off by default; vertex planting only,
    #160) allows planting only on a vertex whose 3 hexes all hold a canal;
    off, a vertex with a river or empty hex may be planted and that third
    scores for nobody. Vertex vineyards are scored split in thirds
    (``acequias.scoring``), with no water rights. The ``MOVE`` die face
    (``V3_DIE_FACES``) needs vertex planting.

    ``board_shape`` (``FIELD`` by default and in the shipped presets) says
    what the board is; ``RIVER_STRIP`` (Rules v3, opt-in, #154) is the open
    board: a base river segment for 2 players plus one per extra player,
    each of ``river_hexes_per_segment`` river hexes, and no stones or
    vineyard tiles, so ``hexes_per_player``, ``stone_share`` and
    ``vineyard_distance`` place nothing. ``bag_size`` (empty by default)
    maps a player count to the pieces in the bag (market included); a
    player count it does not list gets one piece per empty hex of the
    board. ``RIVER_STRIP`` needs vertex planting and a ``bag_size`` for
    every player count, since its table has no fixed hexes to count.

    Rules v3 scoring options (#166, opt-in): ``varietal_bodega`` (on by
    default) turns the ``bodega_varietals`` bodega bonus on or off.
    ``blends`` is the blend (*corte*) table, one ``Blend`` each (empty by
    default: no blends; ``DEFAULT_BLENDS`` is #165's table); a player holds a
    varietal when they own a watered third of a vineyard of it, and
    ``blend_rule`` says how the held blends score (``BlendRule``).
    ``bodega_building`` (off by default) adds the "build a bodega" action
    (one action, any turn the requirement holds): a bodega worth
    ``bodega_building_points``, split in thirds like a vineyard, with no
    varietal, never moved. ``bodega_placement`` says where it goes
    (``BodegaPlacement``: by default on a new free spot the player may
    plant on, or replacing one of their vineyards). It needs
    ``bodega_min_reds`` distinct red and ``bodega_min_whites`` distinct
    white varietals (``Varietal.is_white``) and at least
    ``bodega_min_vineyards`` vineyards, among the vineyards the player
    planted (owner, #166), counted before the build; 0 turns a condition off. ``bodegas_per_player`` caps
    a player's bodegas (``None``: no cap). Blends and bodega buildings
    need vertex planting.

    ``bribe_optional`` (Rules v3, opt-in, #168; off by default and in the
    shipped presets) makes the floodgate and release faces optional: the
    bribe (``action_die_cost``) is paid only when the player places or
    removes a floodgate, and declining costs nothing. Off, those faces are
    mandatory when they have a use and the bribe is paid on the roll. It
    needs vertex planting.

    End of the game (opt-in, #163): ``end_condition`` (``EndCondition``,
    ``ROUNDS`` by default and in the shipped presets) says what ends the
    game, and ``finish_round`` (on by default) whether the round in which
    the trigger fired is played out. ``vineyard_markers`` and
    ``score_target`` map a player count to the markers per player and the
    target score (empty by default: ``VINEYARD_MARKERS`` and
    ``SCORE_TARGETS`` of the mode). Under ``VINEYARDS_OUT`` a player
    cannot plant more vineyards than their markers. Any end condition
    but ``ROUNDS`` needs vertex planting. ``unlimited_bag`` (off by
    default) makes the bag never run out: each piece drawn goes back to
    the bottom of the bag, so the market always refills.

    Combined end and the shared supply (opt-in, #181; off in the shipped
    presets): ``end_conditions`` lists several triggers (no ``ROUNDS``, no
    repeats); the first to fire ends the game, and it replaces
    ``end_condition``, which must then stay ``ROUNDS``. ``vineyard_supply``
    maps a player count to a multiplier ``m``: the shared supply then holds
    ``m`` pieces per roulette sector of each varietal (``supply_for``), and
    every planted vineyard takes one piece of its varietal (empty by
    default: no supply). ``max_spins`` (1 by default) is how many spins a
    plant or a resow may make: a spin that lands on a varietal with no
    piece left is spun again, up to ``max_spins`` spins in total; when all
    fail the player loses the rest of the turn. Both need vertex planting.
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
    season_roll_personal_faces: bool = True
    seat_bonus: Mapping[int, tuple[int, ...]] = field(default_factory=lambda: MappingProxyType({}))
    planting: PlantingRules = PlantingRules.HEXES
    vertex_needs_three_canals: bool = False
    board_shape: BoardShape = BoardShape.FIELD
    river_hexes_per_segment: int = RIVER_HEXES_PER_SEGMENT
    bag_size: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))
    varietal_bodega: bool = True
    blends: tuple[Blend, ...] = ()
    blend_rule: BlendRule = BlendRule.EACH_ONCE
    bodega_building: bool = False
    bodega_placement: BodegaPlacement = BodegaPlacement.NEW_SPOT
    bodega_min_vineyards: int = 0
    bodega_min_reds: int = 2
    bodega_min_whites: int = 2
    bodega_building_points: int = 12
    bodegas_per_player: int | None = 1
    bribe_optional: bool = False
    end_condition: EndCondition = EndCondition.ROUNDS
    finish_round: bool = True
    vineyard_markers: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))
    score_target: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))
    unlimited_bag: bool = False
    vineyard_supply: Mapping[int, int] = field(default_factory=lambda: MappingProxyType({}))
    max_spins: int = 1
    end_conditions: tuple[EndCondition, ...] = ()

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
        _check_type("season_roll_personal_faces", self.season_roll_personal_faces, bool)
        _set(self, "seat_bonus", _seat_bonus(self.seat_bonus, self.player_counts))
        _check_type("planting", self.planting, PlantingRules)
        if (
            self.planting is PlantingRules.VERTICES
            and self.varietal_rules is not VarietalRules.ROULETTE
        ):
            raise ValueError("vertex planting needs roulette varietal rules")
        if self.planting is PlantingRules.VERTICES and self.bribe_rules is not BribeRules.ACTION_DIE:
            raise ValueError("vertex planting needs action_die bribe rules")
        _check_type("vertex_needs_three_canals", self.vertex_needs_three_canals, bool)
        if self.vertex_needs_three_canals and self.planting is not PlantingRules.VERTICES:
            raise ValueError("vertex_needs_three_canals needs vertex planting")
        if DieFace.MOVE in self.action_die and self.planting is not PlantingRules.VERTICES:
            raise ValueError("the action die's MOVE face needs vertex planting")
        _check_type("board_shape", self.board_shape, BoardShape)
        _check_count("river_hexes_per_segment", self.river_hexes_per_segment)
        _set(self, "bag_size", _bag_size(self.bag_size, self.player_counts))
        if self.board_shape is BoardShape.RIVER_STRIP:
            if self.planting is not PlantingRules.VERTICES:
                raise ValueError("the river strip board needs vertex planting")
            missing = [n for n in self.player_counts if n not in self.bag_size]
            if missing:
                raise ValueError(
                    f"the river strip board needs a bag_size for every player count; "
                    f"none for {missing}"
                )
        self._check_v3_scoring()
        _check_type("bribe_optional", self.bribe_optional, bool)
        if self.bribe_optional and self.planting is not PlantingRules.VERTICES:
            raise ValueError("bribe_optional needs vertex planting")
        self._check_end()
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
        for players in self.player_counts:
            hexes = players * self.hexes_per_player
            vineyards = players * self.vineyard_tiles_per_player
            stones = _ceil_share(self.stone_share, hexes)
            if vineyards + stones >= hexes:
                raise ValueError(
                    f"with {players} players, {vineyards} vineyards and {stones} stone hexes "
                    f"leave no empty hex out of {hexes}"
                )

    def _check_v3_scoring(self) -> None:
        """Check and normalize the #166 options: blends and bodega buildings."""
        _check_type("varietal_bodega", self.varietal_bodega, bool)
        _set(self, "blends", _blends(self.blends))
        _check_type("blend_rule", self.blend_rule, BlendRule)
        _check_type("bodega_building", self.bodega_building, bool)
        _check_type("bodega_placement", self.bodega_placement, BodegaPlacement)
        _check_count("bodega_building_points", self.bodega_building_points)
        for name in ("bodega_min_vineyards", "bodega_min_reds", "bodega_min_whites"):
            _check_non_negative(name, getattr(self, name))
        whites = len({v for v in self.roulette if v.is_white})
        reds = len({v for v in self.roulette if not v.is_white})
        if self.bodega_building and (
            self.bodega_min_whites > whites or self.bodega_min_reds > reds
        ):
            raise ValueError(
                f"bodega_min_reds and bodega_min_whites must be at most the roulette's "
                f"{reds} reds and {whites} whites, got {self.bodega_min_reds} and "
                f"{self.bodega_min_whites}"
            )
        if self.bodegas_per_player is not None:
            _check_count("bodegas_per_player", self.bodegas_per_player)
        vertices = self.planting is PlantingRules.VERTICES
        if self.blends and not vertices:
            raise ValueError("blends need vertex planting")
        if self.bodega_building and not vertices:
            raise ValueError("bodega_building needs vertex planting")
        missing = sorted(
            {v.name for b in self.blends for v in b.varietals if v not in self.roulette}
        )
        if missing:
            raise ValueError(f"blend varietals {missing} are not on the roulette")

    def _check_end(self) -> None:
        """Check and normalize the #163 options: the end condition and the unlimited bag."""
        _check_type("end_condition", self.end_condition, EndCondition)
        _check_type("finish_round", self.finish_round, bool)
        _check_type("unlimited_bag", self.unlimited_bag, bool)
        _set(self, "vineyard_markers", _per_count("vineyard_markers", self.vineyard_markers, self.player_counts))
        _set(self, "score_target", _per_count("score_target", self.score_target, self.player_counts))
        _set(self, "vineyard_supply", _per_count("vineyard_supply", self.vineyard_supply, self.player_counts))
        _check_count("max_spins", self.max_spins)
        vertices = self.planting is PlantingRules.VERTICES
        if self.vineyard_supply and not vertices:
            raise ValueError("vineyard_supply needs vertex planting")
        if self.max_spins != 1 and not vertices:
            raise ValueError("max_spins needs vertex planting")
        ends = self.end_conditions
        if isinstance(ends, (str, bytes, Mapping)) or not hasattr(ends, "__iter__"):
            raise TypeError(f"end_conditions must be a sequence of EndCondition, got {ends!r}")
        ends = tuple(ends)
        for end in ends:
            _check_type("end_conditions item", end, EndCondition)
        if EndCondition.ROUNDS in ends:
            raise ValueError("end_conditions cannot hold rounds: the round cap always applies")
        if len(set(ends)) != len(ends):
            raise ValueError("end_conditions holds a trigger twice")
        if ends and self.end_condition is not EndCondition.ROUNDS:
            raise ValueError("set end_conditions or end_condition, not both")
        _set(self, "end_conditions", ends)
        for end in self.triggers:
            self._check_trigger(end)

    def _check_trigger(self, end: EndCondition) -> None:
        """Check that ``end`` (one of ``triggers``) can fire under this preset."""
        if self.planting is not PlantingRules.VERTICES:
            raise ValueError(f"end_condition {end.value} needs vertex planting")
        if end is EndCondition.SUPPLY_EMPTY:
            missing = [n for n in self.player_counts if n not in self.vineyard_supply]
            if missing:
                raise ValueError(f"end_condition {end.value} needs vineyard_supply for {missing}")
            return
        defaults = {
            EndCondition.VINEYARDS_OUT: ("vineyard_markers", VINEYARD_MARKERS),
            EndCondition.SCORE_TARGET: ("score_target", SCORE_TARGETS),
        }.get(end)
        if defaults is not None:
            name, table = defaults
            given = getattr(self, name)
            missing = [n for n in self.player_counts if n not in given and n not in table[self.mode]]
            if missing:
                raise ValueError(f"end_condition {end.value} needs {name} for {missing}")

    @property
    def triggers(self) -> tuple[EndCondition, ...]:
        """The end triggers in play, in order: ``end_conditions``, else ``end_condition`` unless it
        is ``ROUNDS`` (then none: the game ends after the round count)."""
        if self.end_conditions:
            return self.end_conditions
        return () if self.end_condition is EndCondition.ROUNDS else (self.end_condition,)

    def supply_for(self, players: int) -> Mapping[Varietal, int] | None:
        """The shared vineyard supply of a game of ``players`` players (#181): of each roulette
        varietal, its sectors times ``vineyard_supply[players]`` pieces; None without a supply."""
        self.check_players(players)
        m = self.vineyard_supply.get(players)
        if m is None:
            return None
        counts: dict[Varietal, int] = {}
        for v in self.roulette:
            counts[v] = counts.get(v, 0) + m
        return MappingProxyType(counts)

    def markers_for(self, players: int) -> int:
        """Vineyard markers per player for ``VINEYARDS_OUT``: ``vineyard_markers`` or the default."""
        self.check_players(players)
        return self.vineyard_markers.get(players, VINEYARD_MARKERS[self.mode].get(players, 0))

    def target_for(self, players: int) -> int:
        """The target score for ``SCORE_TARGET``: ``score_target`` or the default."""
        self.check_players(players)
        return self.score_target.get(players, SCORE_TARGETS[self.mode].get(players, 0))

    def round_cap(self, players: int) -> int:
        """The last round a game can reach: the round count, or ``END_CAP_FACTOR`` times it
        under an end condition other than ``ROUNDS``."""
        rounds = self.rounds_for(players)
        return rounds * END_CAP_FACTOR if self.triggers else rounds

    def plant_cap(self, players: int) -> int | None:
        """The most vineyards a player may hold: ``grape_clusters_per_player``, and under
        ``VINEYARDS_OUT`` at most ``markers_for(players)``; ``None``: no cap."""
        cap = self.grape_clusters_per_player
        if EndCondition.VINEYARDS_OUT in self.triggers:
            markers = self.markers_for(players)
            cap = markers if cap is None else min(cap, markers)
        return cap

    @property
    def vineyard_tiles_per_player(self) -> int:
        """Vineyard tiles per player on the board: ``vineyards_per_player``, or 0 under vertex planting."""
        if self.planting is PlantingRules.VERTICES:
            return 0
        return self.vineyards_per_player

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
        """Whether ``round`` starts with a free season roll: every ``season_roll_every``-th round.

        Never under vertex planting (Rules v3 has no season roll).
        """
        if self.planting is PlantingRules.VERTICES:
            return False
        return self.season_roll_every is not None and round % self.season_roll_every == 0

    @property
    def player_counts(self) -> tuple[int, ...]:
        """The player counts this preset is for, in order: the keys of ``rounds``."""
        return tuple(self.rounds)

    def check_players(self, players: object) -> None:
        """Raise ``ValueError`` unless ``players`` is one of ``player_counts``.

        ``TypeError`` if it is not an int. The message names the mode and
        its player counts, e.g. "flash mode is for 2 to 3 players, got 4".
        """
        _check_int("players", players)
        if players not in self.rounds:
            raise ValueError(
                f"{self.mode.value} mode is for {players_text(self.player_counts)} players, "
                f"got {players}"
            )

    def rounds_for(self, players: int) -> int:
        """The round count for a game of ``players`` players (one of ``player_counts``)."""
        self.check_players(players)
        return self.rounds[players]


def players_text(counts: tuple[int, ...]) -> str:
    """``counts`` in words: "2 to 5" for consecutive counts, "2, 3 or 5" otherwise."""
    if len(counts) == 1:
        return str(counts[0])
    if list(counts) == list(range(counts[0], counts[-1] + 1)):
        return f"{counts[0]} to {counts[-1]}"
    return ", ".join(map(str, counts[:-1])) + f" or {counts[-1]}"


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
    if not value:
        raise ValueError(
            f"rounds must give at least one player count ({MIN_PLAYERS} to {MAX_PLAYERS})"
        )
    extra = [n for n in value if n not in PLAYER_COUNTS or isinstance(n, bool)]
    if extra:
        raise ValueError(
            f"rounds gives player counts {extra}; only {MIN_PLAYERS} to {MAX_PLAYERS} are allowed"
        )
    counts = [players for players in PLAYER_COUNTS if players in value]
    for players in counts:
        _check_count(f"rounds[{players}]", value[players])
    return MappingProxyType({players: value[players] for players in counts})


def _seat_bonus(value: object, counts: tuple[int, ...]) -> Mapping[int, tuple[int, ...]]:
    _check_type("seat_bonus", value, Mapping)
    extra = [n for n in value if n not in counts or isinstance(n, bool)]
    if extra:
        raise ValueError(
            f"seat_bonus gives player counts {extra}; rounds has only {players_text(counts)}"
        )
    bonus: dict[int, tuple[int, ...]] = {}
    for players in counts:
        if players not in value:
            continue
        points = value[players]
        if isinstance(points, (str, bytes, Mapping)) or not hasattr(points, "__iter__"):
            raise TypeError(f"seat_bonus[{players}] must be a tuple of ints, got {points!r}")
        points = tuple(points)
        if len(points) != players:
            raise ValueError(
                f"seat_bonus[{players}] must give one value per seat ({players}), got {len(points)}"
            )
        for seat, bonus_points in enumerate(points):
            _check_non_negative(f"seat_bonus[{players}][{seat}]", bonus_points)
        bonus[players] = points
    return MappingProxyType(bonus)


def _bag_size(value: object, counts: tuple[int, ...]) -> Mapping[int, int]:
    _check_type("bag_size", value, Mapping)
    extra = [n for n in value if n not in counts or isinstance(n, bool)]
    if extra:
        raise ValueError(
            f"bag_size gives player counts {extra}; rounds has only {players_text(counts)}"
        )
    for players in counts:
        if players in value:
            _check_count(f"bag_size[{players}]", value[players])
    return MappingProxyType({n: value[n] for n in counts if n in value})


def _per_count(name: str, value: object, counts: tuple[int, ...]) -> Mapping[int, int]:
    """A mapping of player count (one of ``counts``) to an int of 1 or more, read-only."""
    _check_type(name, value, Mapping)
    extra = [n for n in value if n not in counts or isinstance(n, bool)]
    if extra:
        raise ValueError(f"{name} gives player counts {extra}; rounds has only {players_text(counts)}")
    for players in counts:
        if players in value:
            _check_count(f"{name}[{players}]", value[players])
    return MappingProxyType({n: value[n] for n in counts if n in value})


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


def _blends(value: object) -> tuple[Blend, ...]:
    """The blend table as a tuple of ``Blend``: each a ``Blend`` or a (varietals, points) pair."""
    if isinstance(value, Mapping):
        value = tuple(value.items())
    if isinstance(value, (str, bytes)) or not hasattr(value, "__iter__"):
        raise TypeError(f"blends must be a sequence of blends, got {value!r}")
    blends = []
    for item in value:
        if not isinstance(item, Blend):
            if isinstance(item, (str, bytes)) or not hasattr(item, "__len__") or len(item) != 2:
                raise TypeError(
                    f"a blend must be a Blend or a (varietals, points) pair, got {item!r}"
                )
            item = Blend(item[0], item[1])
        blends.append(item)
    sets = [b.varietals for b in blends]
    if len(set(sets)) != len(sets):
        raise ValueError("blends lists the same set of varietals twice")
    return tuple(blends)


def _action_die(value: object) -> tuple[DieFace, ...]:
    if isinstance(value, (str, bytes, Mapping)) or not hasattr(value, "__iter__"):
        raise TypeError(f"action_die must be a sequence of die faces, got {value!r}")
    faces = tuple(value)
    if not faces:
        raise ValueError("action_die must have at least one face")
    for face in faces:
        _check_type("action_die face", face, DieFace)
    return faces


def _blend(points: int, *varietals: Varietal) -> Blend:
    return Blend(frozenset(varietals), points)


_MA, _CS, _CF = Varietal.MALBEC, Varietal.CABERNET_SAUVIGNON, Varietal.CABERNET_FRANC
DEFAULT_BLENDS: tuple[Blend, ...] = (
    _blend(2, _MA, _CS),
    _blend(2, _MA, Varietal.BONARDA),
    _blend(2, _MA, Varietal.SYRAH),
    _blend(3, _MA, _CF),
    _blend(3, Varietal.CHARDONNAY, Varietal.TORRONTES),
    _blend(3, _MA, Varietal.TORRONTES),
    _blend(4, _MA, _CS, Varietal.MERLOT),
    _blend(4, _MA, _CS, _CF),
    _blend(4, _MA, _CS, Varietal.BONARDA),
    _blend(5, _MA, _CS, Varietal.MERLOT, _CF),
)
"""The default corte (blend) table (#165, ``_docs/blends.md``'s 10 main blends), in its
order, with starting points to be tuned (#166): a common 2-varietal blend 2, an
uncommon one 3, Chardonnay + Torrontés and Malbec + Torrontés 3, a 3-varietal
blend 4, the 4-varietal one 5. Opt-in: ``Preset.blends`` is empty by default."""


# --- Presets and access ----------------------------------------------------


# Rules v2, approved by the owner on #103 (candidate B, phases D-F of
# ``_docs/tuning-results.md``). ``die_faces`` (the d6 bribe) is unused under
# action die rules.
NORMAL = Preset(
    mode=Mode.NORMAL,
    rounds={2: 10, 3: 15, 4: 12, 5: 10},
    hexes_per_player=18,
    vineyards_per_player=2,
    stone_share=10,
    vineyard_distance=(4, 4),
    market_size=4,
    bag_mix={
        PieceKind.STRAIGHT: 44,
        PieceKind.GENTLE_CURVE: 22,
        PieceKind.SHARP_CURVE: 17,
        PieceKind.SYMMETRIC_Y: 6,
        PieceKind.T_BRANCH: 6,
        PieceKind.CLAW: 5,
        PieceKind.FLOODGATE: 0,
    },
    die_faces=6,
    bodega_points=6,
    bodega_varietals=3,
    water_right_points=3,
    varietal_rules=VarietalRules.ROULETTE,
    varietal_points=SHIPPED_POINTS,
    roulette=ROULETTE_SECTORS,
    grape_clusters_per_player=None,
    bribe_rules=BribeRules.ACTION_DIE,
    action_die_cost=ACTION_DIE_COST,
    action_die=CONSTRUCTIVE_DIE_FACES,
    season_roll_every=3,
    multiple_bodegas=True,
    season_roll_personal_faces=False,
)

# Flash is for 2 or 3 players only: at 4 and 5 its short game was biased
# (too many ties, a turn-order advantage no fix removed; #103 phases E-F).
FLASH = Preset(
    mode=Mode.FLASH,
    rounds={2: 6, 3: 6},
    hexes_per_player=14,
    vineyards_per_player=2,
    stone_share=10,
    vineyard_distance=(4, 4),
    market_size=4,
    bag_mix=NORMAL.bag_mix,
    die_faces=6,
    bodega_points=3,
    bodega_varietals=3,
    water_right_points=3,
    varietal_rules=VarietalRules.ROULETTE,
    varietal_points=SHIPPED_POINTS,
    roulette=ROULETTE_SECTORS,
    grape_clusters_per_player=None,
    bribe_rules=BribeRules.ACTION_DIE,
    action_die_cost=ACTION_DIE_COST,
    action_die=CONSTRUCTIVE_DIE_FACES,
    season_roll_every=2,
    multiple_bodegas=True,
    season_roll_personal_faces=False,
)

_PRESETS: Mapping[Mode, Preset] = MappingProxyType({Mode.NORMAL: NORMAL, Mode.FLASH: FLASH})

_V1_BAG = {
    PieceKind.STRAIGHT: 40,
    PieceKind.GENTLE_CURVE: 20,
    PieceKind.SHARP_CURVE: 15,
    PieceKind.SYMMETRIC_Y: 5,
    PieceKind.T_BRANCH: 5,
    PieceKind.CLAW: 5,
    PieceKind.FLOODGATE: 10,
}
_V1_POINTS = {Varietal.MALBEC: 3, Varietal.BONARDA: 2, Varietal.TORRONTES: 1}

RULES_V1: Mapping[Mode, Preset] = MappingProxyType(
    {
        mode: Preset(
            mode=mode,
            rounds=rounds,
            hexes_per_player=hexes,
            vineyards_per_player=2,
            stone_share=10,
            vineyard_distance=(4, 4),
            market_size=4,
            bag_mix=_V1_BAG,
            die_faces=6,
            bodega_points=bodega,
            bodega_varietals=3,
            water_right_points=1,
            varietal_rules=VarietalRules.FIXED,
            varietal_points=_V1_POINTS,
            roulette=ROULETTE_SECTORS,
            grape_clusters_per_player=None,
            bribe_rules=BribeRules.D6,
            action_die_cost=2,
            action_die=ACTION_DIE_FACES,
        )
        for mode, rounds, hexes, bodega in (
            (Mode.NORMAL, {2: 10, 3: 15, 4: 12, 5: 10}, 15, 2),
            (Mode.FLASH, {2: 6, 3: 6, 4: 4, 5: 4}, 14, 1),
        )
    }
)
"""The Rules v1 presets, shipped from #20 until #126: fixed varietals, the d6
bribe, floodgates in the bag, Flash for 2 to 5 players. Not shipped: the
tuning sweeps (``scripts/tune.py``) and the engine tests of those rules pin
them."""


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
