import ast
import dataclasses
from pathlib import Path
from types import MappingProxyType

import pytest

from acequias.config import FLASH, NORMAL, preset, with_overrides
from acequias.flow import water
from acequias.hex import Direction, Hex
from acequias.model import (
    Board,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    Player,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import Score, WateredVineyard, calculate_score, winners

MALBEC, BONARDA, TORRONTES = Varietal.MALBEC, Varietal.BONARDA, Varietal.TORRONTES


# --- Helpers -----------------------------------------------------------------
#
# A lane is one row of the board: a river hex at q = 0, straight W-E canals
# at q = 1..n with the given owners, and a vineyard at q = n + 1. Lanes sit
# on even rows, so no two lanes touch and each vineyard has exactly one path.


@dataclasses.dataclass(frozen=True)
class Lane:
    row: int
    owners: tuple[str, ...]
    varietal: Varietal = MALBEC
    claimant: str | None = None

    @property
    def vineyard(self) -> Hex:
        return Hex(len(self.owners) + 1, self.row)


def lane(row, owners, varietal=MALBEC, claimant=None):
    return Lane(2 * row, tuple(owners), varietal, claimant)


def dry(row, varietal=MALBEC, claimant=None):
    """A vineyard with no canal at all: it stays dry."""
    return Lane(2 * row, (), varietal, claimant)


def make_board(lanes):
    tiles, canals, claims = [], [], []
    for ln in lanes:
        if ln.owners:
            tiles.append(Tile(Hex(0, ln.row), Terrain.RIVER))
        for q, owner in enumerate(ln.owners, start=1):
            h = Hex(q, ln.row)
            tiles.append(Tile(h, Terrain.EMPTY))
            canals.append(PlacedCanal(h, PieceKind.STRAIGHT, 0, owner))
        tiles.append(Tile(ln.vineyard, Terrain.VINEYARD, ln.varietal))
        if ln.claimant is not None:
            claims.append((ln.vineyard, ln.claimant))
    return Board(tiles=tuple(tiles), canals=tuple(canals), claims=tuple(claims))


def make_state(lanes=(), players=("a", "b", "c"), debts=None, mode=Mode.NORMAL, round=1, seats=None):
    debts = debts or {}
    seats = seats or {pid: i for i, pid in enumerate(players)}
    ps = tuple(Player(pid, seats[pid], debts.get(pid, 0)) for pid in players)
    return GameState(
        board=make_board(lanes),
        players=ps,
        mode=mode,
        round=round,
        start_player=players[0],
        current_player=players[0],
    )


def terms(score):
    return (
        score.vineyards,
        score.bodega,
        score.rights_paid,
        score.rights_collected,
        score.debt,
        score.total,
    )


def assert_rights_balance(scores):
    paid = sum(s.rights_paid for s in scores.values())
    collected = sum(s.rights_collected for s in scores.values())
    assert paid == collected


def assert_total_formula(scores):
    for s in scores.values():
        assert s.total == s.vineyards + s.bodega - s.rights_paid + s.rights_collected - s.debt


# --- Result shape ------------------------------------------------------------


def test_every_player_gets_a_breakdown_with_every_field():
    state = make_state([lane(0, ["a"], claimant="a")])
    scores = calculate_score(state)
    assert list(scores) == ["a", "b", "c"]
    for pid, s in scores.items():
        assert isinstance(s, Score)
        assert s.player == pid
        for name in (
            "vineyards",
            "bodega",
            "rights_paid",
            "rights_collected",
            "debt",
            "total",
            "watered",
        ):
            assert isinstance(getattr(s, name), int)
    assert_total_formula(scores)
    assert_rights_balance(scores)


def test_scores_are_listed_in_seat_order():
    state = make_state(players=("a", "b", "c"), seats={"a": 2, "b": 0, "c": 1})
    scores = calculate_score(state)
    assert list(scores) == ["b", "c", "a"]
    assert_rights_balance(scores)


def test_breakdown_lists_each_watered_vineyard_with_path_and_rivals_paid():
    lanes = [
        lane(0, ["c", "b", "a"], MALBEC, claimant="a"),
        lane(1, ["a"], BONARDA, claimant="a"),
        dry(2, TORRONTES, claimant="a"),
    ]
    state = make_state(lanes)
    paths = water(state.board)
    scores = calculate_score(state)
    a = scores["a"]
    assert_rights_balance(scores)

    assert a.watered == 2
    # Listed in hex order: (2, 2) before (4, 0).
    assert a.watered_vineyards == (
        WateredVineyard(lanes[1].vineyard, BONARDA, paths[lanes[1].vineyard], ()),
        WateredVineyard(lanes[0].vineyard, MALBEC, paths[lanes[0].vineyard], ("b", "c")),
    )


def test_a_player_with_nothing_scores_zero_on_every_term():
    state = make_state([lane(0, ["a"], claimant="a")])
    scores = calculate_score(state)
    b = scores["b"]
    assert terms(b) == (0, 0, 0, 0, 0, 0)
    assert b.watered == 0
    assert b.watered_vineyards == ()
    assert_rights_balance(scores)


def test_totals_can_be_negative():
    # b: one watered Bonarda through a (2 - 1 paid) and a debt of 4.
    state = make_state([lane(0, ["a", "b"], BONARDA, claimant="b")], debts={"b": 4})
    scores = calculate_score(state)
    assert terms(scores["b"]) == (2, 0, 1, 0, 4, -3)
    assert terms(scores["a"]) == (0, 0, 0, 1, 0, 1)
    assert_rights_balance(scores)


def test_a_state_with_no_canals_scores_only_debt_whatever_the_round():
    lanes = [dry(0, MALBEC, "a"), dry(1, BONARDA, "b"), dry(2, TORRONTES, "c")]
    for round in (1, 3, 99):
        state = make_state(lanes, debts={"a": 2, "c": 5}, round=round)
        scores = calculate_score(state)
        assert terms(scores["a"]) == (0, 0, 0, 0, 2, -2)
        assert terms(scores["b"]) == (0, 0, 0, 0, 0, 0)
        assert terms(scores["c"]) == (0, 0, 0, 0, 5, -5)
        assert all(s.watered == 0 for s in scores.values())
        assert_rights_balance(scores)


def test_the_state_is_not_changed_and_calls_are_repeatable():
    lanes = [lane(0, ["b", "a"], claimant="a"), lane(1, ["c"], BONARDA, claimant="b")]
    state = make_state(lanes, debts={"c": 1})
    copy = make_state(lanes, debts={"c": 1})
    first = calculate_score(state)
    second = calculate_score(state)
    assert state == copy
    assert first == second
    assert_rights_balance(first)


def test_results_are_immutable():
    state = make_state([lane(0, ["b", "a"], claimant="a")])
    scores = calculate_score(state)
    assert isinstance(scores, MappingProxyType)
    with pytest.raises(TypeError):
        scores["a"] = None
    with pytest.raises(dataclasses.FrozenInstanceError):
        scores["a"].total = 100
    with pytest.raises(dataclasses.FrozenInstanceError):
        scores["a"].watered_vineyards[0].pays = ()
    assert isinstance(scores["a"].watered_vineyards, tuple)
    assert isinstance(scores["a"].watered_vineyards[0].pays, tuple)


def test_rejects_a_non_state_and_a_non_preset():
    with pytest.raises(TypeError):
        calculate_score("not a state")
    with pytest.raises(TypeError):
        calculate_score(make_state(), preset="normal")


# --- Winners -----------------------------------------------------------------


def test_the_highest_total_wins():
    # a: Malbec 3. b: Bonarda 2. c: nothing.
    state = make_state([lane(0, ["a"], MALBEC, "a"), lane(1, ["b"], BONARDA, "b")])
    scores = calculate_score(state)
    assert winners(scores) == ("a",)
    assert_rights_balance(scores)


def test_a_tie_on_total_goes_to_more_watered_vineyards():
    # a: one Malbec = 3, watered 1. b: Bonarda + Torrontés = 3, watered 2.
    state = make_state(
        [
            lane(0, ["a"], MALBEC, "a"),
            lane(1, ["b"], BONARDA, "b"),
            lane(2, ["b"], TORRONTES, "b"),
        ]
    )
    scores = calculate_score(state)
    assert scores["a"].total == scores["b"].total == 3
    assert winners(scores) == ("b",)
    assert_rights_balance(scores)


def test_a_full_tie_is_a_shared_win_in_seat_order():
    # a and c each water one Bonarda: 2 points, 1 watered. b has nothing.
    state = make_state(
        [lane(0, ["a"], BONARDA, "a"), lane(1, ["c"], BONARDA, "c")],
        seats={"a": 2, "b": 1, "c": 0},
    )
    scores = calculate_score(state)
    assert winners(scores) == ("c", "a")
    assert_rights_balance(scores)


def test_everyone_with_nothing_shares_the_win():
    scores = calculate_score(make_state())
    assert winners(scores) == ("a", "b", "c")
    assert_rights_balance(scores)


# --- Vineyards ---------------------------------------------------------------


def test_vineyard_values_add_the_varietal_points_of_watered_claims():
    # Malbec 3 + Bonarda 2 + Torrontés 1 + Malbec 3 = 9.
    state = make_state(
        [
            lane(0, ["a"], MALBEC, "a"),
            lane(1, ["a"], BONARDA, "a"),
            lane(2, ["a"], TORRONTES, "a"),
            lane(3, ["a"], MALBEC, "a"),
        ]
    )
    scores = calculate_score(state)
    assert scores["a"].vineyards == 9
    assert scores["a"].watered == 4
    assert_rights_balance(scores)


def test_a_dry_claimed_vineyard_scores_nothing():
    # a waters a Malbec and a Bonarda; its Torrontés is dry, so it adds no
    # points, no third varietal for the bonus, and no water rights.
    state = make_state(
        [
            lane(0, ["a"], MALBEC, "a"),
            lane(1, ["a"], BONARDA, "a"),
            dry(2, TORRONTES, "a"),
        ]
    )
    scores = calculate_score(state)
    assert terms(scores["a"]) == (5, 0, 0, 0, 0, 5)
    assert scores["a"].watered == 2
    assert [v.varietal for v in scores["a"].watered_vineyards] == [MALBEC, BONARDA]
    assert terms(scores["b"]) == (0, 0, 0, 0, 0, 0)
    assert_rights_balance(scores)


def test_unclaimed_vineyards_give_nothing_and_cause_no_rights():
    # A watered unclaimed Malbec fed through a and b, and a dry unclaimed one.
    state = make_state([lane(0, ["a", "b"], MALBEC), dry(1, MALBEC)])
    scores = calculate_score(state)
    for s in scores.values():
        assert terms(s) == (0, 0, 0, 0, 0, 0)
        assert s.watered == 0
    assert_rights_balance(scores)


# --- Water rights ------------------------------------------------------------


def test_a_path_through_rivals_pays_one_to_each_distinct_rival():
    # a's Malbec is fed through b then c: a pays 2, b and c collect 1 each.
    state = make_state([lane(0, ["b", "c", "a"], MALBEC, "a")])
    scores = calculate_score(state)
    assert terms(scores["a"]) == (3, 0, 2, 0, 0, 1)
    assert terms(scores["b"]) == (0, 0, 0, 1, 0, 1)
    assert terms(scores["c"]) == (0, 0, 0, 1, 0, 1)
    assert_rights_balance(scores)


def test_several_canals_of_one_rival_cost_one():
    # Three of b's canals on one path: a pays b 1, not 3.
    state = make_state([lane(0, ["b", "b", "b", "a"], BONARDA, "a")])
    scores = calculate_score(state)
    assert terms(scores["a"]) == (2, 0, 1, 0, 0, 1)
    assert terms(scores["b"]) == (0, 0, 0, 1, 0, 1)
    assert scores["a"].watered_vineyards[0].pays == ("b",)
    assert_rights_balance(scores)


def test_rights_are_counted_per_vineyard():
    # Two of a's vineyards each cross b: a pays b 2.
    state = make_state(
        [lane(0, ["b", "a"], MALBEC, "a"), lane(1, ["b"], TORRONTES, "a")]
    )
    scores = calculate_score(state)
    assert terms(scores["a"]) == (4, 0, 2, 0, 0, 2)
    assert terms(scores["b"]) == (0, 0, 0, 2, 0, 2)
    assert_rights_balance(scores)


def test_own_canals_cost_nothing():
    state = make_state([lane(0, ["a", "a", "a"], MALBEC, "a")])
    scores = calculate_score(state)
    assert terms(scores["a"]) == (3, 0, 0, 0, 0, 3)
    assert scores["a"].watered_vineyards[0].pays == ()
    assert_rights_balance(scores)


def test_rights_go_both_ways_between_two_players():
    # a pays b for one vineyard and b pays a for another: they cancel out.
    state = make_state(
        [lane(0, ["b", "a"], BONARDA, "a"), lane(1, ["a", "b"], BONARDA, "b")]
    )
    scores = calculate_score(state)
    assert terms(scores["a"]) == (2, 0, 1, 1, 0, 2)
    assert terms(scores["b"]) == (2, 0, 1, 1, 0, 2)
    assert_rights_balance(scores)


# --- Bodega bonus and debt ---------------------------------------------------


def all_three(claimant="a"):
    return [
        lane(0, [claimant], MALBEC, claimant),
        lane(1, [claimant], BONARDA, claimant),
        lane(2, [claimant], TORRONTES, claimant),
    ]


def test_normal_bodega_bonus_for_three_varietals():
    assert (NORMAL.bodega_varietals, NORMAL.bodega_points) == (3, 2)
    scores = calculate_score(make_state(all_three(), mode=Mode.NORMAL))
    # 3 + 2 + 1 = 6, plus the bonus of 2.
    assert terms(scores["a"]) == (6, 2, 0, 0, 0, 8)
    assert scores["b"].bodega == 0
    assert_rights_balance(scores)


def test_flash_bodega_bonus_for_three_varietals():
    assert (FLASH.bodega_varietals, FLASH.bodega_points) == (3, 1)
    scores = calculate_score(make_state(all_three(), mode=Mode.FLASH))
    # 3 + 2 + 1 = 6, plus the bonus of 1.
    assert terms(scores["a"]) == (6, 1, 0, 0, 0, 7)
    assert_rights_balance(scores)


def test_duplicate_varietals_count_once():
    # Two Malbecs and one Bonarda: 2 distinct varietals, no Normal bonus.
    state = make_state(
        [
            lane(0, ["a"], MALBEC, "a"),
            lane(1, ["a"], MALBEC, "a"),
            lane(2, ["a"], BONARDA, "a"),
        ]
    )
    scores = calculate_score(state)
    assert terms(scores["a"]) == (8, 0, 0, 0, 0, 8)
    assert_rights_balance(scores)


def test_no_preset_uses_the_mode_preset():
    state = make_state(all_three(), mode=Mode.FLASH)
    scores = calculate_score(state)
    assert scores == calculate_score(state, preset(Mode.FLASH))
    assert scores != calculate_score(state, NORMAL)
    assert_rights_balance(scores)


def test_a_preset_passed_in_is_used_instead():
    # Malbec + Bonarda: no bonus by default, +2 when two varietals are enough.
    state = make_state([lane(0, ["a"], MALBEC, "a"), lane(1, ["a"], BONARDA, "a")])
    default = calculate_score(state)
    assert default["a"].bodega == 0
    two = with_overrides(NORMAL, bodega_varietals=2)
    with_two = calculate_score(state, two)
    assert terms(with_two["a"]) == (5, 2, 0, 0, 0, 7)
    three_points = with_overrides(NORMAL, bodega_varietals=2, bodega_points=3)
    with_three = calculate_score(state, three_points)
    assert with_three["a"].bodega == 3
    for scores in (default, with_two, with_three):
        assert_rights_balance(scores)


def test_no_preset_uses_the_state_preset_and_an_explicit_preset_wins():
    # All three varietals: Normal gives 2 bodega points, the state's preset 5.
    five = with_overrides(NORMAL, bodega_points=5)
    state = dataclasses.replace(make_state(all_three()), preset=five)
    assert terms(calculate_score(state)["a"]) == (6, 5, 0, 0, 0, 11)
    explicit = with_overrides(NORMAL, bodega_points=7)
    assert calculate_score(state, explicit)["a"].bodega == 7
    assert calculate_score(state, NORMAL)["a"].bodega == 2
    unset = make_state(all_three())
    assert unset.preset is None
    assert calculate_score(unset)["a"].bodega == NORMAL.bodega_points


def test_debt_is_subtracted_in_full():
    state = make_state([lane(0, ["a"], MALBEC, "a")], debts={"a": 7, "b": 3})
    scores = calculate_score(state)
    assert terms(scores["a"]) == (3, 0, 0, 0, 7, -4)
    assert terms(scores["b"]) == (0, 0, 0, 0, 3, -3)
    assert_rights_balance(scores)


# --- A full hand-worked game -------------------------------------------------


def three_player_game():
    """A 3-player Normal game that uses every term.

    a: Malbec own (3), Bonarda via b (2, pays b), Torrontés via b and c
       (1, pays b and c). 6 + bodega 2 - paid 3 + collected 1 - debt 1 = 5.
    b: Malbec via a (3, pays a), Malbec own (3). Only one varietal.
       6 + 0 - paid 1 + collected 2 - debt 2 = 5.
    c: Bonarda own (2), a dry Malbec (0). 2 + 0 - 0 + collected 1 - debt 1 = 2.
    An unclaimed watered Malbec through a gives nothing.
    a and b tie on 5; a has 3 watered vineyards to b's 2, so a wins.
    """
    lanes = [
        lane(0, ["a", "a"], MALBEC, "a"),
        lane(1, ["b", "a"], BONARDA, "a"),
        lane(2, ["c", "b", "c"], TORRONTES, "a"),
        lane(3, ["a", "b"], MALBEC, "b"),
        lane(4, ["b"], MALBEC, "b"),
        lane(5, ["c"], BONARDA, "c"),
        dry(6, MALBEC, "c"),
        lane(7, ["a"], MALBEC),
    ]
    return make_state(lanes, debts={"a": 1, "b": 2, "c": 1}), lanes


def test_a_three_player_game_uses_every_term():
    state, lanes = three_player_game()
    scores = calculate_score(state)

    assert terms(scores["a"]) == (6, 2, 3, 1, 1, 5)
    assert terms(scores["b"]) == (6, 0, 1, 2, 2, 5)
    assert terms(scores["c"]) == (2, 0, 0, 1, 1, 2)
    assert [scores[p].watered for p in "abc"] == [3, 2, 1]
    assert [v.pays for v in scores["a"].watered_vineyards] == [(), ("b",), ("b", "c")]
    # b's vineyards in hex order: own Malbec (2, 8), then via a (3, 6).
    assert [v.pays for v in scores["b"].watered_vineyards] == [(), ("a",)]
    assert [v.hex for v in scores["c"].watered_vineyards] == [lanes[5].vineyard]
    assert_rights_balance(scores)
    assert_total_formula(scores)
    assert winners(scores) == ("a",)


# --- Constraints -------------------------------------------------------------


def test_scoring_imports_only_acequias_modules_and_the_standard_library():
    source = Path(__file__).parent.parent / "acequias" / "scoring.py"
    tree = ast.parse(source.read_text("utf-8"))
    allowed_acequias = {"acequias.config", "acequias.flow", "acequias.hex", "acequias.model"}
    stdlib = {"__future__", "collections", "dataclasses", "types"}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module.startswith("acequias"):
                assert node.module in allowed_acequias
            else:
                assert node.module.split(".")[0] in stdlib
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in stdlib
