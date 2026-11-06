import ast
import dataclasses
from pathlib import Path

import pytest

from acequias import config
from acequias.config import FLASH, NORMAL, Preset, preset, with_overrides
from acequias.model import MAX_PLAYERS, MIN_PLAYERS, Mode, PieceKind

PRESETS = [NORMAL, FLASH]
PLAYER_COUNTS = range(MIN_PLAYERS, MAX_PLAYERS + 1)
COUNT_FIELDS = [
    "hexes_per_player",
    "vineyards_per_player",
    "market_size",
    "die_faces",
    "bodega_points",
    "bodega_varietals",
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

README_BAG_MIX = {
    PieceKind.STRAIGHT: 40,
    PieceKind.GENTLE_CURVE: 20,
    PieceKind.SHARP_CURVE: 15,
    PieceKind.SYMMETRIC_Y: 5,
    PieceKind.T_BRANCH: 5,
    PieceKind.CLAW: 5,
    PieceKind.FLOODGATE: 10,
}

README_VALUES = {
    Mode.NORMAL: dict(
        rounds={2: 12, 3: 12, 4: 12, 5: 12},
        hexes_per_player=12,
        vineyards_per_player=2,
        stone_share=10,
        vineyard_distance=(4, 5),
        market_size=4,
        bag_mix=README_BAG_MIX,
        die_faces=6,
        bodega_points=2,
        bodega_varietals=3,
    ),
    Mode.FLASH: dict(
        rounds={2: 5, 3: 5, 4: 5, 5: 5},
        hexes_per_player=7,
        vineyards_per_player=2,
        stone_share=10,
        vineyard_distance=(2, 3),
        market_size=4,
        bag_mix=README_BAG_MIX,
        die_faces=6,
        bodega_points=1,
        bodega_varietals=3,
    ),
}


@pytest.mark.parametrize("mode", list(Mode), ids=lambda m: m.name)
def test_shipped_values_match_readme(mode):
    p = preset(mode)
    expected = README_VALUES[mode]
    actual = fields_of(p)
    assert actual.pop("mode") is mode
    assert {k: dict(v) if k in ("rounds", "bag_mix") else v for k, v in actual.items()} == expected


def test_readme_distances_need_the_readme_canal_counts():
    # A vineyard at distance d needs d - 1 canals: 3-4 in Normal, 1-2 in Flash.
    assert tuple(d - 1 for d in NORMAL.vineyard_distance) == (3, 4)
    assert tuple(d - 1 for d in FLASH.vineyard_distance) == (1, 2)


def test_flash_has_fewer_rounds_for_every_player_count():
    for players in PLAYER_COUNTS:
        assert FLASH.rounds_for(players) < NORMAL.rounds_for(players)


def test_flash_has_fewer_hexes_per_player():
    assert FLASH.hexes_per_player < NORMAL.hexes_per_player


def test_flash_vineyards_sit_closer_to_the_river():
    assert FLASH.vineyard_distance[1] < NORMAL.vineyard_distance[0]


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


@ids
def test_rounds_has_one_value_per_player_count(p):
    assert set(p.rounds) == set(PLAYER_COUNTS)


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
    for players in PLAYER_COUNTS:
        assert p.rounds_for(players) == p.rounds[players]


@ids
@pytest.mark.parametrize("players", [0, 1, 6, -2])
def test_rounds_for_out_of_range(p, players):
    with pytest.raises(ValueError, match="2 to 5"):
        p.rounds_for(players)


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
    assert p.bag_mix[PieceKind.STRAIGHT] == 40


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
    assert p.bag_mix[PieceKind.STRAIGHT] == 40


def test_list_distance_is_stored_as_a_tuple():
    p = with_overrides(NORMAL, vineyard_distance=[3, 6])
    assert p.vineyard_distance == (3, 6)


# --- with_overrides() ------------------------------------------------------


@ids
def test_with_no_changes_returns_an_equal_preset(p):
    assert with_overrides(p) == p


def test_with_overrides_returns_a_new_preset_and_leaves_the_original():
    before = fields_of(NORMAL)
    p = with_overrides(NORMAL, hexes_per_player=15, market_size=5)
    assert p.hexes_per_player == 15
    assert p.market_size == 5
    assert p.mode is Mode.NORMAL
    assert p != NORMAL
    assert fields_of(NORMAL) == before
    assert NORMAL.hexes_per_player == 12


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
@pytest.mark.parametrize("missing", list(PLAYER_COUNTS))
def test_rounds_missing_player_count(p, missing):
    rounds = {n: 5 for n in PLAYER_COUNTS if n != missing}
    assert_raises(p, ValueError, match=str(missing), rounds=rounds)


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


@ids
@pytest.mark.parametrize("bad", [4, 10])
def test_bodega_varietals_at_most_three(p, bad):
    assert_raises(p, ValueError, match="bodega_varietals", bodega_varietals=bad)


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
