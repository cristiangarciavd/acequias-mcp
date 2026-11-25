import ast
import dataclasses
from pathlib import Path

import pytest

from acequias import config
from acequias.config import (
    BlendRule,
    BodegaPlacement,
    BoardShape,
    PlantingRules,
    ACTION_DIE_FACES,
    CONSTRUCTIVE_DIE_FACES,
    FLASH,
    NORMAL,
    ROULETTE_POINTS,
    ROULETTE_SECTORS,
    RULES_V1,
    SHIPPED_POINTS,
    BribeRules,
    Preset,
    VarietalRules,
    action_die_rules,
    players_text,
    preset,
    roulette_rules,
    scaled,
    with_overrides,
)
from acequias.model import MAX_PLAYERS, MIN_PLAYERS, DieFace, Mode, PieceKind, Varietal

PRESETS = [NORMAL, FLASH]
PLAYER_COUNTS = range(MIN_PLAYERS, MAX_PLAYERS + 1)
V1 = RULES_V1[Mode.NORMAL]
"""The Rules v1 Normal preset: fixed varietals and the d6 bribe."""
COUNT_FIELDS = [
    "hexes_per_player",
    "vineyards_per_player",
    "market_size",
    "die_faces",
    "bodega_points",
    "bodega_varietals",
    "water_right_points",
]
ids = pytest.mark.parametrize("p", PRESETS, ids=lambda p: p.mode.name)


def fields_of(p):
    return {f.name: getattr(p, f.name) for f in dataclasses.fields(Preset)}


def build(p, **changes):
    """Build a Preset directly, bypassing with_overrides."""
    values = fields_of(p)
    values.update(changes)
    return Preset(**values)


def both_ways(p, **changes):
    """Raise-checks run on both the direct constructor and with_overrides."""
    return [lambda: build(p, **changes), lambda: with_overrides(p, **changes)]


def assert_raises(p, exc, match=None, **changes):
    for make in both_ways(p, **changes):
        with pytest.raises(exc, match=match):
            make()


# --- Shipped values (README.md) -------------------------------------------

V1_BAG_MIX = {
    PieceKind.STRAIGHT: 40,
    PieceKind.GENTLE_CURVE: 20,
    PieceKind.SHARP_CURVE: 15,
    PieceKind.SYMMETRIC_Y: 5,
    PieceKind.T_BRANCH: 5,
    PieceKind.CLAW: 5,
    PieceKind.FLOODGATE: 10,
}
README_BAG_MIX = {
    PieceKind.STRAIGHT: 44,
    PieceKind.GENTLE_CURVE: 22,
    PieceKind.SHARP_CURVE: 17,
    PieceKind.SYMMETRIC_Y: 6,
    PieceKind.T_BRANCH: 6,
    PieceKind.CLAW: 5,
    PieceKind.FLOODGATE: 0,
}

V1_VARIETAL_POINTS = {Varietal.MALBEC: 3, Varietal.BONARDA: 2, Varietal.TORRONTES: 1}
README_VARIETAL_POINTS = {
    Varietal.MALBEC: 6,
    Varietal.CABERNET_SAUVIGNON: 6,
    Varietal.CABERNET_FRANC: 7,
    Varietal.SYRAH: 6,
    Varietal.MERLOT: 6,
    Varietal.BONARDA: 7,
    Varietal.TORRONTES: 6,
    Varietal.CHARDONNAY: 6,
}

# Rules v3 scoring options (#166): opt-in, off in the shipped presets.
V3_SCORING_DEFAULTS = dict(
    varietal_bodega=True,
    blends=(),
    blend_rule=BlendRule.EACH_ONCE,
    bodega_building=False,
    bodega_placement=BodegaPlacement.NEW_SPOT,
    bodega_min_vineyards=0,
    bodega_min_reds=2,
    bodega_min_whites=2,
    bodega_building_points=12,
    bodegas_per_player=1,
)

# Rules v2, approved by the owner on #103 and shipped in #126.
README_VALUES = {
    Mode.NORMAL: dict(
        rounds={2: 10, 3: 15, 4: 12, 5: 10},
        hexes_per_player=18,
        vineyards_per_player=2,
        stone_share=10,
        vineyard_distance=(4, 4),
        market_size=4,
        bag_mix=README_BAG_MIX,
        die_faces=6,
        bodega_points=6,
        bodega_varietals=3,
        water_right_points=3,
        varietal_rules=VarietalRules.ROULETTE,
        varietal_points=README_VARIETAL_POINTS,
        roulette=ROULETTE_SECTORS,
        grape_clusters_per_player=None,
        bribe_rules=BribeRules.ACTION_DIE,
        action_die_cost=1,
        action_die=CONSTRUCTIVE_DIE_FACES,
        season_points=None,
        drought_points=None,
        season_roll_every=3,
        multiple_bodegas=True,
        season_roll_personal_faces=False,
        seat_bonus={},
        planting=PlantingRules.HEXES,
        vertex_needs_three_canals=False,
        board_shape=BoardShape.FIELD,
        river_hexes_per_segment=5,
        bag_size={},
        **V3_SCORING_DEFAULTS,
    ),
    Mode.FLASH: dict(
        rounds={2: 6, 3: 6},
        hexes_per_player=14,
        vineyards_per_player=2,
        stone_share=10,
        vineyard_distance=(4, 4),
        market_size=4,
        bag_mix=README_BAG_MIX,
        die_faces=6,
        bodega_points=3,
        bodega_varietals=3,
        water_right_points=3,
        varietal_rules=VarietalRules.ROULETTE,
        varietal_points=README_VARIETAL_POINTS,
        roulette=ROULETTE_SECTORS,
        grape_clusters_per_player=None,
        bribe_rules=BribeRules.ACTION_DIE,
        action_die_cost=1,
        action_die=CONSTRUCTIVE_DIE_FACES,
        season_points=None,
        drought_points=None,
        season_roll_every=2,
        multiple_bodegas=True,
        season_roll_personal_faces=False,
        seat_bonus={},
        planting=PlantingRules.HEXES,
        vertex_needs_three_canals=False,
        board_shape=BoardShape.FIELD,
        river_hexes_per_segment=5,
        bag_size={},
        **V3_SCORING_DEFAULTS,
    ),
}

# Rules v1: shipped from #20 until #126, kept as ``RULES_V1``.
V1_VALUES = {
    mode: dict(
        README_VALUES[mode],
        rounds=rounds,
        hexes_per_player=hexes,
        bag_mix=V1_BAG_MIX,
        bodega_points=bodega,
        water_right_points=1,
        varietal_rules=VarietalRules.FIXED,
        varietal_points=V1_VARIETAL_POINTS,
        bribe_rules=BribeRules.D6,
        action_die_cost=2,
        action_die=ACTION_DIE_FACES,
        season_roll_every=None,
        multiple_bodegas=False,
        season_roll_personal_faces=True,
    )
    for mode, rounds, hexes, bodega in (
        (Mode.NORMAL, {2: 10, 3: 15, 4: 12, 5: 10}, 15, 2),
        (Mode.FLASH, {2: 6, 3: 6, 4: 4, 5: 4}, 14, 1),
    )
}


def plain(p):
    """``p``'s fields without ``mode``, its mappings as dicts."""
    return {
        k: dict(v) if k in ("rounds", "bag_mix", "varietal_points", "seat_bonus") else v
        for k, v in fields_of(p).items()
        if k != "mode"
    }


@pytest.mark.parametrize("mode", list(Mode), ids=lambda m: m.name)
def test_shipped_values_match_readme(mode):
    p = preset(mode)
    assert p.mode is mode
    assert plain(p) == README_VALUES[mode]


@pytest.mark.parametrize("mode", list(Mode), ids=lambda m: m.name)
def test_rules_v1_keeps_the_values_shipped_before_126(mode):
    p = RULES_V1[mode]
    assert p.mode is mode
    assert plain(p) == V1_VALUES[mode]


def test_shipped_points_are_the_roulette_points_at_scale_3_with_rare_plus_1():
    assert SHIPPED_POINTS == NORMAL.varietal_points == FLASH.varietal_points
    rare = {Varietal.BONARDA, Varietal.CABERNET_FRANC}
    assert dict(SHIPPED_POINTS) == {v: 6 + (v in rare) for v in ROULETTE_POINTS}


def test_readme_distances_need_the_readme_canal_counts():
    # A vineyard at distance d needs d - 1 canals: 3 in both modes (tuned in #20).
    assert tuple(d - 1 for d in NORMAL.vineyard_distance) == (3, 3)
    assert tuple(d - 1 for d in FLASH.vineyard_distance) == (3, 3)


def test_flash_has_fewer_rounds_for_every_player_count():
    for players in FLASH.player_counts:
        assert FLASH.rounds_for(players) < NORMAL.rounds_for(players)


def test_flash_has_fewer_hexes_per_player():
    assert FLASH.hexes_per_player < NORMAL.hexes_per_player


def test_flash_vineyards_sit_no_farther_from_the_river():
    # #20 moved Flash to Normal's distance: closer vineyards hand seat 1 most wins.
    assert FLASH.vineyard_distance[1] <= NORMAL.vineyard_distance[0]


@ids
def test_preset_records_its_mode(p):
    assert preset(p.mode) is p
    assert isinstance(p.mode, Mode)


@ids
def test_shares_are_whole_number_percentages(p):
    assert type(p.stone_share) is int
    assert all(type(share) is int for share in p.bag_mix.values())
    assert sum(p.bag_mix.values()) == 100


@ids
def test_bag_mix_is_keyed_by_piece_kind(p):
    assert set(p.bag_mix) == set(PieceKind)


def test_normal_is_for_2_to_5_players_and_flash_for_2_to_3():
    assert NORMAL.player_counts == (2, 3, 4, 5)
    assert FLASH.player_counts == (2, 3)


# --- preset() --------------------------------------------------------------


def test_preset_returns_each_mode():
    assert preset(Mode.NORMAL) is NORMAL
    assert preset(Mode.FLASH) is FLASH


@pytest.mark.parametrize("bad", ["normal", "NORMAL", None, 0, NORMAL])
def test_preset_rejects_non_mode(bad):
    with pytest.raises(TypeError):
        preset(bad)


# --- rounds_for() ----------------------------------------------------------


@ids
def test_rounds_for_each_player_count(p):
    for players in p.player_counts:
        assert p.rounds_for(players) == p.rounds[players]


@ids
@pytest.mark.parametrize("players", [0, 1, 6, -2])
def test_rounds_for_out_of_range(p, players):
    with pytest.raises(ValueError, match=f"{p.mode.value} mode is for 2 to"):
        p.rounds_for(players)


@pytest.mark.parametrize("players", [4, 5])
def test_flash_rejects_4_and_5_players_with_a_clear_error(players):
    with pytest.raises(ValueError, match=f"^flash mode is for 2 to 3 players, got {players}$"):
        FLASH.check_players(players)
    with pytest.raises(ValueError, match="flash mode is for 2 to 3 players"):
        FLASH.rounds_for(players)
    NORMAL.check_players(players)


@ids
@pytest.mark.parametrize("players", [True, 2.0, "2", None])
def test_check_players_non_int(p, players):
    with pytest.raises(TypeError):
        p.check_players(players)


@pytest.mark.parametrize(
    ("counts", "text"), [((2, 3, 4, 5), "2 to 5"), ((2, 3), "2 to 3"), ((3,), "3"), ((2, 3, 5), "2, 3 or 5")]
)
def test_players_text(counts, text):
    assert players_text(counts) == text


def test_rounds_can_cover_some_player_counts_only():
    p = with_overrides(NORMAL, rounds={5: 9, 2: 7})
    assert p.player_counts == (2, 5)
    assert list(p.rounds.items()) == [(2, 7), (5, 9)]
    with pytest.raises(ValueError, match="normal mode is for 2 or 5 players, got 3"):
        p.rounds_for(3)


def test_flash_can_be_given_4_and_5_players_back_by_overrides():
    p = with_overrides(FLASH, rounds={2: 6, 3: 6, 4: 4, 5: 4})
    assert p.rounds_for(5) == 4


@ids
def test_rounds_cannot_be_empty(p):
    assert_raises(p, ValueError, match="at least one player count", rounds={})


def test_board_capacity_is_checked_only_for_the_player_counts_played():
    # 2 hexes/player, 1 vineyard/player, 26% stone fills a 2-player board
    # (see test_board_capacity_rounds_stones_up) but not a 5-player one.
    with pytest.raises(ValueError, match="2 players"):
        with_overrides(NORMAL, hexes_per_player=2, vineyards_per_player=1, stone_share=26)
    p = with_overrides(NORMAL, hexes_per_player=2, vineyards_per_player=1, stone_share=26, rounds={5: 4})
    assert p.player_counts == (5,)


def test_seat_bonus_only_for_player_counts_in_rounds():
    with pytest.raises(ValueError, match=r"seat_bonus gives player counts \[4\]; rounds has only 2 to 3"):
        with_overrides(FLASH, seat_bonus={4: (1, 1, 1, 0)})
    assert with_overrides(FLASH, seat_bonus={3: (1, 0, 0)}).seat_bonus[3] == (1, 0, 0)


@ids
@pytest.mark.parametrize("players", [True, False, 2.0, "2", None])
def test_rounds_for_non_int(p, players):
    with pytest.raises(TypeError):
        p.rounds_for(players)


def test_rounds_can_differ_per_player_count():
    p = with_overrides(NORMAL, rounds={2: 14, 3: 13, 4: 12, 5: 11})
    assert [p.rounds_for(n) for n in PLAYER_COUNTS] == [14, 13, 12, 11]


# --- Immutability ----------------------------------------------------------


@ids
@pytest.mark.parametrize("name", [f.name for f in dataclasses.fields(Preset)])
def test_fields_cannot_be_assigned(p, name):
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(p, name, getattr(p, name))


@ids
def test_rounds_cannot_be_changed_in_place(p):
    with pytest.raises(TypeError):
        p.rounds[2] = 99
    with pytest.raises(TypeError):
        del p.rounds[2]
    assert p.rounds_for(2) == README_VALUES[p.mode]["rounds"][2]


@ids
def test_bag_mix_cannot_be_changed_in_place(p):
    with pytest.raises(TypeError):
        p.bag_mix[PieceKind.STRAIGHT] = 0
    with pytest.raises(TypeError):
        del p.bag_mix[PieceKind.CLAW]
    assert p.bag_mix[PieceKind.STRAIGHT] == 44


@ids
def test_vineyard_distance_is_a_tuple(p):
    assert isinstance(p.vineyard_distance, tuple)


def test_mutating_the_input_dicts_does_not_change_the_preset():
    rounds = {2: 9, 3: 9, 4: 9, 5: 9}
    mix = dict(README_BAG_MIX)
    p = with_overrides(NORMAL, rounds=rounds, bag_mix=mix)
    rounds[2] = 1
    mix[PieceKind.STRAIGHT] = 0
    assert p.rounds_for(2) == 9
    assert p.bag_mix[PieceKind.STRAIGHT] == 44


def test_list_distance_is_stored_as_a_tuple():
    p = with_overrides(NORMAL, vineyard_distance=[3, 6])
    assert p.vineyard_distance == (3, 6)


# --- with_overrides() ------------------------------------------------------


@ids
def test_with_no_changes_returns_an_equal_preset(p):
    assert with_overrides(p) == p


def test_with_overrides_returns_a_new_preset_and_leaves_the_original():
    before = fields_of(NORMAL)
    p = with_overrides(NORMAL, hexes_per_player=20, market_size=5)
    assert p.hexes_per_player == 20
    assert p.market_size == 5
    assert p.mode is Mode.NORMAL
    assert p != NORMAL
    assert fields_of(NORMAL) == before
    assert NORMAL.hexes_per_player == 18


def test_with_overrides_unknown_field():
    with pytest.raises(ValueError, match="hexes_per_playr"):
        with_overrides(NORMAL, hexes_per_playr=10)


@pytest.mark.parametrize("mode", list(Mode))
def test_with_overrides_cannot_change_mode(mode):
    with pytest.raises(ValueError, match="mode"):
        with_overrides(FLASH, mode=mode)


def test_with_overrides_needs_a_preset():
    with pytest.raises(TypeError):
        with_overrides(fields_of(NORMAL), market_size=5)


@ids
def test_building_directly_with_same_values_equals_shipped(p):
    assert build(p) == p


# --- Validation: types -----------------------------------------------------


@ids
@pytest.mark.parametrize("name", COUNT_FIELDS)
@pytest.mark.parametrize("bad", [True, False, 4.0, "4", None])
def test_counts_must_be_int(p, name, bad):
    assert_raises(p, TypeError, **{name: bad})


@ids
@pytest.mark.parametrize("bad", [True, 12.0, "12", None])
def test_round_counts_must_be_int(p, bad):
    rounds = dict(p.rounds)
    rounds[3] = bad
    assert_raises(p, TypeError, rounds=rounds)


@ids
@pytest.mark.parametrize("bad", [True, 10.0, "10", None])
def test_stone_share_must_be_int(p, bad):
    assert_raises(p, TypeError, stone_share=bad)


@ids
@pytest.mark.parametrize("bad", [True, 40.0, "40", None])
def test_bag_mix_shares_must_be_int(p, bad):
    mix = dict(p.bag_mix)
    mix[PieceKind.STRAIGHT] = bad
    assert_raises(p, TypeError, bag_mix=mix)


@ids
@pytest.mark.parametrize("bad", [None, 12, [12, 12, 12, 12]])
def test_rounds_must_be_a_mapping(p, bad):
    assert_raises(p, TypeError, rounds=bad)


@ids
@pytest.mark.parametrize("bad", [None, 40, list(README_BAG_MIX.items())])
def test_bag_mix_must_be_a_mapping(p, bad):
    assert_raises(p, TypeError, bag_mix=bad)


@ids
def test_mode_must_be_a_mode(p):
    with pytest.raises(TypeError):
        build(p, mode="normal")


@ids
@pytest.mark.parametrize("bad", [None, 4, "45", (True, 5), (4.0, 5), (4, "5")])
def test_distance_types(p, bad):
    assert_raises(p, TypeError, vineyard_distance=bad)


# --- Validation: values ----------------------------------------------------


@ids
@pytest.mark.parametrize("name", COUNT_FIELDS)
@pytest.mark.parametrize("bad", [0, -1])
def test_counts_must_be_at_least_one(p, name, bad):
    assert_raises(p, ValueError, match=name, **{name: bad})


@ids
@pytest.mark.parametrize("bad", [0, -3])
def test_round_counts_must_be_at_least_one(p, bad):
    rounds = dict(p.rounds)
    rounds[4] = bad
    assert_raises(p, ValueError, match="rounds", rounds=rounds)


@ids
@pytest.mark.parametrize("extra", [1, 6, 0])
def test_rounds_extra_player_count(p, extra):
    rounds = {n: 5 for n in PLAYER_COUNTS}
    rounds[extra] = 5
    assert_raises(p, ValueError, match=str(extra), rounds=rounds)


@ids
@pytest.mark.parametrize("kind", list(PieceKind), ids=lambda k: k.name)
def test_bag_mix_missing_kind(p, kind):
    mix = dict(p.bag_mix)
    del mix[kind]
    assert_raises(p, ValueError, match=kind.name, bag_mix=mix)


@ids
def test_bag_mix_unknown_kind(p):
    mix = dict(p.bag_mix)
    mix["pipe"] = 0
    assert_raises(p, ValueError, match="pipe", bag_mix=mix)


@ids
def test_bag_mix_string_key_is_unknown(p):
    mix = dict(p.bag_mix)
    del mix[PieceKind.STRAIGHT]
    mix["straight"] = 40
    assert_raises(p, ValueError, match="straight", bag_mix=mix)


@ids
@pytest.mark.parametrize("bad", [-1, 101])
def test_stone_share_range(p, bad):
    assert_raises(p, ValueError, match="stone_share", stone_share=bad)


@ids
def test_stone_share_bounds_are_inclusive(p):
    assert with_overrides(p, stone_share=0).stone_share == 0


@ids
@pytest.mark.parametrize("bad", [-5, 101])
def test_bag_mix_share_range(p, bad):
    mix = dict(p.bag_mix)
    mix[PieceKind.CLAW] = bad
    assert_raises(p, ValueError, bag_mix=mix)


@ids
@pytest.mark.parametrize("delta", [1, -1])
def test_bag_mix_must_add_up_to_exactly_100(p, delta):
    mix = dict(p.bag_mix)
    mix[PieceKind.STRAIGHT] += delta
    assert_raises(p, ValueError, match="100", bag_mix=mix)


@ids
def test_bag_mix_share_bounds_are_inclusive(p):
    mix = {kind: 0 for kind in PieceKind}
    mix[PieceKind.STRAIGHT] = 100
    assert with_overrides(p, bag_mix=mix).bag_mix[PieceKind.STRAIGHT] == 100


@ids
def test_board_must_keep_an_empty_hex(p):
    # Vineyards alone fill the board.
    assert_raises(
        p, ValueError, match="empty", vineyards_per_player=p.hexes_per_player, stone_share=0
    )
    # Stones alone fill the board.
    assert_raises(p, ValueError, match="empty", stone_share=100)


def test_board_capacity_rounds_stones_up():
    # 2 hexes/player, 1 vineyard/player, 10% stone: with 2 players, 4 hexes hold
    # 2 vineyards and ceil(0.4) = 1 stone, leaving 1 empty hex.
    p = with_overrides(NORMAL, hexes_per_player=2, vineyards_per_player=1, stone_share=10)
    assert p.stone_share == 10
    # At 26%: 2 vineyards + ceil(1.04) = 2 stones fill all 4 hexes. Rounding
    # down would wrongly leave room.
    with pytest.raises(ValueError, match="2 players"):
        with_overrides(NORMAL, hexes_per_player=2, vineyards_per_player=1, stone_share=26)


def test_board_capacity_tight_but_valid():
    # 4 hexes/player, 1 vineyard/player, 45% stone: the fullest count is
    # 2 players, 8 hexes, 2 vineyards + ceil(3.6) = 4 stones, 2 empty.
    p = with_overrides(NORMAL, hexes_per_player=4, vineyards_per_player=1, stone_share=45)
    assert p.stone_share == 45


def test_one_hex_per_player_with_a_vineyard_is_full():
    with pytest.raises(ValueError, match="empty"):
        with_overrides(NORMAL, hexes_per_player=1, vineyards_per_player=1, stone_share=0)


@ids
@pytest.mark.parametrize("bad", [(1, 3), (0, 2), (-1, 4), (1, 1)])
def test_distance_starts_at_two(p, bad):
    assert_raises(p, ValueError, match="river", vineyard_distance=bad)


@ids
def test_distance_low_not_above_high(p):
    assert_raises(p, ValueError, match="above", vineyard_distance=(5, 4))


@ids
def test_distance_single_value_range_is_allowed(p):
    assert with_overrides(p, vineyard_distance=(3, 3)).vineyard_distance == (3, 3)


@ids
@pytest.mark.parametrize("bad", [(2,), (2, 3, 4), ()])
def test_distance_must_be_a_pair(p, bad):
    assert_raises(p, ValueError, vineyard_distance=bad)


@pytest.mark.parametrize("bad", [4, 10])
def test_bodega_varietals_at_most_three_under_fixed_rules(bad):
    assert_raises(V1, ValueError, match="bodega_varietals", bodega_varietals=bad)


@ids
@pytest.mark.parametrize("bad", [9, 10])
def test_bodega_varietals_at_most_the_roulette_varietals(p, bad):
    # The shipped roulette has 8 distinct varietals.
    assert_raises(p, ValueError, match="bodega_varietals", bodega_varietals=bad)
    assert with_overrides(p, bodega_varietals=8).bodega_varietals == 8


@ids
@pytest.mark.parametrize("good", [1, 2, 3])
def test_bodega_varietals_one_to_three(p, good):
    assert with_overrides(p, bodega_varietals=good).bodega_varietals == good


@ids
def test_die_faces_at_least_two(p):
    assert_raises(p, ValueError, match="die_faces", die_faces=1)
    assert with_overrides(p, die_faces=2).die_faces == 2
    assert with_overrides(p, die_faces=8).die_faces == 8


# --- Module constraints ----------------------------------------------------


def test_config_imports_only_the_model():
    tree = ast.parse(Path(config.__file__).read_text(encoding="utf-8"))
    acequias_imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("acequias"):
            acequias_imports.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.startswith("acequias"), alias.name
    assert acequias_imports == {"acequias.model"}


# --- Action die (#112) -------------------------------------------------------


def test_action_die_faces_and_cost():
    assert ACTION_DIE_FACES == (
        DieFace.FLOODGATE, DieFace.FLOODGATE,
        DieFace.RELEASE, DieFace.RELEASE,
        DieFace.RESOW, DieFace.RESOW,
    )
    assert config.ACTION_DIE_COST == 1
    assert CONSTRUCTIVE_DIE_FACES == (
        DieFace.FLOODGATE, DieFace.RELEASE, DieFace.RESOW, DieFace.RESOW,
        DieFace.GOOD_SEASON, DieFace.DROUGHT,
    )


@pytest.mark.parametrize("mode", list(Mode), ids=lambda m: m.name)
def test_action_die_rules_bag_mix(mode):
    p = action_die_rules(roulette_rules(RULES_V1[mode]))
    assert p.bribe_rules is BribeRules.ACTION_DIE
    assert dict(p.bag_mix) == {
        PieceKind.STRAIGHT: 44,
        PieceKind.GENTLE_CURVE: 22,
        PieceKind.SHARP_CURVE: 17,
        PieceKind.SYMMETRIC_Y: 6,
        PieceKind.T_BRANCH: 6,
        PieceKind.CLAW: 5,
        PieceKind.FLOODGATE: 0,
    }
    # Everything else is the roulette preset's.
    base = fields_of(roulette_rules(RULES_V1[mode]))
    for name, value in fields_of(p).items():
        if name not in ("bribe_rules", "bag_mix"):
            assert value == base[name], name


def test_action_die_rules_needs_roulette():
    with pytest.raises(ValueError, match="RESOW"):
        action_die_rules(V1)


def test_action_die_rules_on_a_die_without_resow_works_under_fixed_rules():
    p = action_die_rules(
        with_overrides(V1, action_die=(DieFace.FLOODGATE, DieFace.RELEASE))
    )
    assert p.bribe_rules is BribeRules.ACTION_DIE
    assert p.varietal_rules is VarietalRules.FIXED


def test_action_die_rejections():
    die = NORMAL
    assert_raises(die, ValueError, "FLOODGATE", bag_mix=V1_BAG_MIX)
    assert_raises(die, ValueError, "RESOW", varietal_rules=VarietalRules.FIXED,
                  varietal_points=V1_VARIETAL_POINTS)
    assert_raises(die, ValueError, "season_roll_every", bribe_rules=BribeRules.D6, bag_mix=V1_BAG_MIX)
    assert_raises(die, ValueError, "at least one face", action_die=())
    assert_raises(die, ValueError, "action_die_cost", action_die_cost=-1)
    assert_raises(die, TypeError, "action_die_cost", action_die_cost=True)
    assert_raises(die, TypeError, "action_die face", action_die=("floodgate",))
    assert_raises(die, TypeError, "bribe_rules", bribe_rules="action_die")


def test_d6_rules_ignore_the_action_die_checks():
    # Under d6 rules a floodgate share and a RESOW face under fixed rules are fine.
    assert V1.bag_mix[PieceKind.FLOODGATE] == 10
    assert DieFace.RESOW in V1.action_die
    with pytest.raises(ValueError, match="action_die_cost"):
        with_overrides(V1, action_die_cost=-1)


def test_action_die_cost_zero_is_accepted_and_kept_by_scaled():
    # #128: cost 0 is for testing only; the shipped cost stays at least 1.
    die = NORMAL
    assert with_overrides(die, action_die_cost=0).action_die_cost == 0
    assert with_overrides(V1, action_die_cost=0).action_die_cost == 0
    assert scaled(with_overrides(die, action_die_cost=0), 3).action_die_cost == 0
    assert config.ACTION_DIE_COST == 1


# --- Score scale (#111) ------------------------------------------------------


@pytest.mark.parametrize("bad", [0, -1, True, 1.0])
def test_water_right_points_rejects(bad):
    exc = ValueError if bad in (0, -1) and not isinstance(bad, (bool, float)) else TypeError
    assert_raises(NORMAL, exc, "water_right_points", water_right_points=bad)


def test_scaled_doubles_every_scoring_value():
    p = scaled(V1, 2)
    assert dict(p.varietal_points) == {
        Varietal.MALBEC: 6,
        Varietal.BONARDA: 4,
        Varietal.TORRONTES: 2,
    }
    assert p.bodega_points == 4
    assert p.water_right_points == 2
    scoring = {"varietal_points", "bodega_points", "water_right_points"}
    for name, value in fields_of(p).items():
        if name not in scoring:
            assert value == getattr(V1, name), name


def test_scaled_triples_every_roulette_varietal():
    p = roulette_rules(V1)
    tripled = scaled(p, 3)
    assert len(tripled.varietal_points) == 8
    assert dict(tripled.varietal_points) == {v: 3 * n for v, n in ROULETTE_POINTS.items()}


def test_scaled_keeps_the_action_die_cost():
    p = scaled(NORMAL, 2)
    assert p.action_die_cost == 1
    assert p.die_faces == NORMAL.die_faces


@ids
def test_scaled_by_one_is_equal_and_leaves_the_original(p):
    before = fields_of(p)
    assert scaled(p, 1) == p
    scaled(p, 3)
    assert fields_of(p) == before


@pytest.mark.parametrize(("bad", "exc"), [(0, ValueError), (-1, ValueError), (True, TypeError), (1.5, TypeError)])
def test_scaled_rejects_bad_factors(bad, exc):
    with pytest.raises(exc, match="factor"):
        scaled(NORMAL, bad)


def test_scaled_needs_a_preset():
    with pytest.raises(TypeError):
        scaled("normal", 2)
