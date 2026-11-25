"""More vineyard plots and the grape-cluster cap (#110).

Both are preset options: ``vineyards_per_player`` (plots per player) and
``grape_clusters_per_player`` (the claim cap, ``None`` = no cap). The
shipped presets keep today's game.
"""

import random

import pytest
from mcp import Client

from acequias.board import generate_board
from acequias.bots import greedy_bot, policy
from acequias.config import RULES_V1, Preset, roulette_rules, with_overrides
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
from acequias.sim import SimRules, game_seed, play_one, simulate_game
from acequias.turn import Pass, PlaceCanal, PlaceFloodgate, apply, legal_actions
from server.app import app

PIN_RULES_V1 = True
"""``conftest.py``: these tests check the engine under the Rules v1 presets."""
NORMAL, FLASH = RULES_V1[Mode.NORMAL], RULES_V1[Mode.FLASH]

E, NE, NW, W, SW, SE = list(Direction)
STRAIGHT, GENTLE, SHARP, Y, T, CLAW, GATE = list(PieceKind)

# A row west to east: river, three empty hexes, a vineyard; an empty hex
# west of the river too.
R = Hex(0, 0)
H0 = Hex(-1, 0)
H1, H2, H3 = Hex(1, 0), Hex(2, 0), Hex(3, 0)
V = Hex(4, 0)
V_NE, V_SE = H2.neighbor(NE), H2.neighbor(SE)
LOW, HIGH = sorted((V_NE, V_SE))
Y_ROT = next(r for r in range(6) if Y.edges(r) == {W, NE, SE})


def make_board(vineyards=(V, V_NE, V_SE), empties=(H1, H2, H3), canals=(), claims=(),
               varietal=Varietal.MALBEC):
    tiles = [Tile(R, Terrain.RIVER)]
    tiles += [Tile(h, Terrain.VINEYARD, varietal) for h in vineyards]
    tiles += [Tile(h, Terrain.EMPTY) for h in empties]
    return Board(tiles=tuple(tiles), canals=tuple(canals), claims=tuple(claims))


def make_state(board, cap, market=(Y,), base=NORMAL, current="b"):
    return GameState(
        board=board,
        players=(Player("a", 1), Player("b", 2)),
        mode=base.mode,
        round=1,
        start_player="a",
        current_player=current,
        market=market,
        preset=with_overrides(base, grape_clusters_per_player=cap),
    )


def straight(hex, owner="a"):
    return PlacedCanal(hex, STRAIGHT, 0, owner)


def claims_of(state, player):
    return sorted(h for h, p in state.board.claims if p == player)


# --- Presets -------------------------------------------------------------------


@pytest.mark.parametrize("p", [NORMAL, FLASH], ids=["NORMAL", "FLASH"])
def test_shipped_presets_have_no_cap(p):
    assert p.grape_clusters_per_player is None


@pytest.mark.parametrize("value", [0, -1])
def test_cap_must_be_at_least_one(value):
    with pytest.raises(ValueError, match="grape_clusters_per_player"):
        with_overrides(NORMAL, grape_clusters_per_player=value)


@pytest.mark.parametrize("value", [True, 2.0, "2"])
def test_cap_must_be_an_int_or_none(value):
    with pytest.raises(TypeError, match="grape_clusters_per_player"):
        with_overrides(NORMAL, grape_clusters_per_player=value)


@pytest.mark.parametrize("value", [None, 1, 5])
def test_cap_accepts_none_and_positive_ints(value):
    assert with_overrides(NORMAL, grape_clusters_per_player=value).grape_clusters_per_player == value


def test_cap_is_a_preset_field():
    assert "grape_clusters_per_player" in Preset.__dataclass_fields__


# --- Plots ---------------------------------------------------------------------


def _reachable(board):
    """Vineyards next to a chain of empty hexes that touches the river (own BFS)."""
    terrain = {t.hex: t.terrain for t in board.tiles}
    frontier = [
        h for h, t in terrain.items()
        if t is Terrain.EMPTY and any(terrain.get(h.neighbor(d)) is Terrain.RIVER for d in Direction)
    ]
    seen = set(frontier)
    while frontier:
        h = frontier.pop()
        for d in Direction:
            n = h.neighbor(d)
            if n not in seen and terrain.get(n) is Terrain.EMPTY:
                seen.add(n)
                frontier.append(n)
    return {
        h for h, t in terrain.items()
        if t is Terrain.VINEYARD and any(h.neighbor(d) in seen for d in Direction)
    }


@pytest.mark.parametrize("players", [2, 3, 4, 5])
def test_three_plots_per_player_fit_a_normal_board(players):
    p = with_overrides(NORMAL, vineyards_per_player=3)
    for seed in range(50):
        board = generate_board(players, seed, Mode.NORMAL, preset=p)
        rivers = [t.hex for t in board.tiles if t.terrain is Terrain.RIVER]
        vineyards = [t.hex for t in board.tiles if t.terrain is Terrain.VINEYARD]
        assert len(vineyards) == 3 * players
        assert all(min(v.distance(r) for r in rivers) == 4 for v in vineyards)
        assert len(_reachable(board)) >= players


def test_four_plots_per_player_do_not_fit_a_normal_board():
    p = with_overrides(NORMAL, vineyards_per_player=4)
    with pytest.raises(ValueError, match="vineyards_per_player"):
        generate_board(2, 0, Mode.NORMAL, preset=p)


@pytest.mark.parametrize("bot", ["random", "greedy", "saboteur"])
def test_more_plots_and_hexes_play_full_games(bot):
    overrides = {"vineyards_per_player": 4, "hexes_per_player": 20}
    for players in (2, 5):
        rules = SimRules(Mode.NORMAL, players, (bot,) * players, overrides)
        record = play_one(rules, game_seed(3, players))
        vineyards = [t for t in record.final.board.tiles if t.terrain is Terrain.VINEYARD]
        assert len(vineyards) == 4 * players
        assert record.winners


# --- Claiming under a cap ------------------------------------------------------


def test_with_one_cluster_left_only_the_lower_hex_is_claimed():
    board = make_board(canals=[straight(H1)], claims=[(V, "b")])
    new = apply(make_state(board, cap=2), "b", PlaceCanal(Y, H2, Y_ROT), random.Random(1))
    assert claims_of(new, "b") == sorted([V, LOW])
    assert new.board.claimant(HIGH) is None
    assert HIGH in watered(new)


def watered(state):
    from acequias.flow import water

    return set(water(state.board))


def test_without_a_cap_both_are_claimed():
    board = make_board(canals=[straight(H1)], claims=[(V, "b")])
    new = apply(make_state(board, cap=None), "b", PlaceCanal(Y, H2, Y_ROT), random.Random(1))
    assert claims_of(new, "b") == sorted([V, LOW, HIGH])


def _leftover_state(market):
    board = make_board(canals=[straight(H1)], claims=[(V, "b")])
    state = make_state(board, cap=2, market=(Y, *market))
    return apply(state, "b", PlaceCanal(Y, H2, Y_ROT), random.Random(1))


def test_the_next_placement_claims_the_leftover():
    state = _leftover_state(market=(GATE,))
    # "a" gates the edge toward the vineyard "b" already holds; the leftover stays watered.
    gate_dir = NE if LOW == V_NE else SE
    new = apply(state, "a", PlaceFloodgate(H2, gate_dir), random.Random(1))
    assert new.board.claimant(HIGH) == "a"


def test_a_pass_does_not_claim_the_leftover():
    state = _leftover_state(market=())
    assert legal_actions(state, "a") == (Pass(),)
    new = apply(state, "a", Pass(), random.Random(1))
    assert new.board.claimant(HIGH) is None


def test_a_player_at_the_cap_claims_nothing_and_the_action_is_legal():
    board = make_board(canals=[straight(H1)], claims=[(V, "b")])
    state = make_state(board, cap=1)
    action = PlaceCanal(Y, H2, Y_ROT)
    assert action in legal_actions(state, "b")
    new = apply(state, "b", action, random.Random(1))
    assert claims_of(new, "b") == [V]
    assert new.board.claimant(LOW) is None and new.board.claimant(HIGH) is None
    assert new.board.canal_at(H2) is not None


def test_under_roulette_rules_only_claimed_vineyards_spin():
    p = roulette_rules(with_overrides(NORMAL, grape_clusters_per_player=2))
    board = make_board(canals=[straight(H1)], claims=[(V, "b")], varietal=None)
    state = GameState(
        board=board,
        players=(Player("a", 1), Player("b", 2)),
        mode=Mode.NORMAL,
        round=1,
        start_player="a",
        current_player="b",
        market=(Y,),
        preset=p,
    )
    rng = random.Random(7)
    new = apply(state, "b", PlaceCanal(Y, H2, Y_ROT), rng)
    expected = random.Random(7)
    spin = expected.choice(p.roulette)
    assert rng.getstate() == expected.getstate()  # exactly one spin
    assert new.board.plantings == ((LOW, spin),)
    assert new.board.claimant(HIGH) is None


def test_game_state_rejects_more_claims_than_the_cap():
    board = make_board(claims=[(V, "b"), (V_NE, "b")])
    with pytest.raises(ValueError, match="grape_clusters_per_player"):
        make_state(board, cap=1)
    assert make_state(board, cap=2).board.claims == board.claims


# --- Bots ----------------------------------------------------------------------


def test_greedy_at_the_cap_does_not_steer_toward_an_unclaimed_vineyard():
    # Without a cap greedy extends H1 toward V; at the cap it places a floodgate.
    board = make_board(vineyards=(V, V_NE), empties=(H0, H1, H2, H3),
                       canals=[straight(H1)], claims=[(V_NE, "b")])
    market = (STRAIGHT, GATE)
    uncapped = greedy_bot(make_state(board, cap=None, market=market), "b", random.Random(0))
    assert uncapped == PlaceCanal(STRAIGHT, H2, 0)
    for seed in range(10):
        action = greedy_bot(make_state(board, cap=1, market=market), "b", random.Random(seed))
        assert isinstance(action, PlaceFloodgate)


def test_greedy_at_the_cap_with_no_floodgate_picks_any_canal():
    board = make_board(vineyards=(V, V_NE), empties=(H0, H1, H2, H3),
                       canals=[straight(H1)], claims=[(V_NE, "b")])
    state = make_state(board, cap=1, market=(STRAIGHT,))
    picks = {greedy_bot(state, "b", random.Random(seed)) for seed in range(30)}
    assert picks <= set(legal_actions(state, "b"))
    assert any(a.hex == H0 for a in picks)  # not only the canal toward V


def test_saboteur_counts_only_vineyards_it_can_claim():
    # At the cap, watering V gains "b" nothing, so the saboteur sees no swing
    # and falls back to greedy (a floodgate at the cap).
    board = make_board(vineyards=(V, V_NE), canals=[straight(H1), straight(H2)],
                       claims=[(V_NE, "b")])
    state = make_state(board, cap=1, market=(STRAIGHT, GATE))
    action = policy("saboteur")(state, "b", random.Random(0))
    assert action != PlaceCanal(STRAIGHT, H3, 0)


# --- Simulation and JSON -------------------------------------------------------


def test_simulate_with_a_cap_of_one_is_deterministic_and_respects_it():
    rules = SimRules(Mode.NORMAL, 3, ("greedy", "saboteur", "random"),
                     {"grape_clusters_per_player": 1})
    first = simulate_game(rules, 4, 5)
    assert first.to_json() == simulate_game(rules, 4, 5).to_json()
    assert first.to_json()["preset"]["grape_clusters_per_player"] == 1
    for i in range(4):
        final = play_one(rules, game_seed(5, i)).final
        counts = {}
        for _, p in final.board.claims:
            counts[p] = counts.get(p, 0) + 1
        assert all(n <= 1 for n in counts.values())


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def _simulate(overrides):
    async with Client(app) as client:
        return await client.call_tool(
            "simulate_game",
            {"mode": "flash", "players": 2, "games": 1, "seed": 1, "overrides": overrides},
        )


@pytest.mark.anyio
@pytest.mark.parametrize("value", [2, None])
async def test_simulate_game_tool_accepts_and_echoes_the_cap(value):
    result = await _simulate({"grape_clusters_per_player": value})
    assert not result.is_error
    assert result.structured_content["preset"]["grape_clusters_per_player"] == value


@pytest.mark.anyio
async def test_simulate_game_tool_echoes_no_cap_by_default():
    result = await _simulate({})
    assert not result.is_error
    assert result.structured_content["preset"]["grape_clusters_per_player"] is None


@pytest.mark.anyio
@pytest.mark.parametrize("value", ["2", 2.0])
async def test_simulate_game_tool_rejects_a_non_int_cap(value):
    result = await _simulate({"grape_clusters_per_player": value})
    assert result.is_error
