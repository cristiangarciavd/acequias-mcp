"""Varietal rules (#85): the fixed default stays as it was; the roulette is opt-in.

Covers the preset fields, board generation, the spins in ``turn.apply``,
scoring, the bots, the simulation, validation, and the JSON of the
``calculate_score`` tool.
"""

import hashlib
import random
from collections import Counter

import pytest
from mcp import Client

from acequias.assembly import assembly_instructions
from acequias.board import generate_board
from acequias.config import (
    RULES_V1,
    ROULETTE_POINTS,
    ROULETTE_SECTORS,
    VarietalRules,
    preset,
    roulette_rules,
    with_overrides,
)
from acequias.hex import Direction, Hex
from acequias.model import (
    Board,
    Floodgate,
    GameState,
    Mode,
    PieceKind,
    PlacedCanal,
    Player,
    Terrain,
    Tile,
    Varietal,
)
from acequias.scoring import calculate_score
from acequias.sim import SimRules, game_seed, play_one, simulate_game
from acequias.turn import Bribe, IllegalAction, PlaceCanal, apply
from server.app import app
from server.schemas import (
    claim_from_json,
    claims_to_json,
    overrides_from_json,
    planting_from_json,
)

PIN_RULES_V1 = True
"""``conftest.py``: these tests check the engine under the Rules v1 presets."""
NORMAL, FLASH = RULES_V1[Mode.NORMAL], RULES_V1[Mode.FLASH]

V = Varietal
ROULETTE = {"varietal_rules": VarietalRules.ROULETTE, "varietal_points": ROULETTE_POINTS}
ALL_NAMES = [
    "malbec",
    "cabernet_sauvignon",
    "cabernet_franc",
    "syrah",
    "merlot",
    "bonarda",
    "torrontes",
    "chardonnay",
]


# --- Presets -------------------------------------------------------------------


@pytest.mark.parametrize("p", [NORMAL, FLASH], ids=["NORMAL", "FLASH"])
def test_shipped_presets_keep_fixed_rules_and_points_in_order(p):
    assert p.varietal_rules is VarietalRules.FIXED
    assert list(p.varietal_points.items()) == [(V.MALBEC, 3), (V.BONARDA, 2), (V.TORRONTES, 1)]
    assert p.roulette == ROULETTE_SECTORS


def test_roulette_sectors_and_provisional_points():
    assert len(ROULETTE_SECTORS) == 14
    counts = Counter(ROULETTE_SECTORS)
    assert set(counts) == set(Varietal)
    assert counts[V.BONARDA] == counts[V.CABERNET_FRANC] == 1
    assert all(n == 2 for v, n in counts.items() if v not in (V.BONARDA, V.CABERNET_FRANC))
    assert ROULETTE_POINTS[V.BONARDA] == ROULETTE_POINTS[V.CABERNET_FRANC] == 3
    assert all(ROULETTE_POINTS[v] == 2 for v in Varietal if v not in (V.BONARDA, V.CABERNET_FRANC))
    assert sum(ROULETTE_POINTS[v] for v in ROULETTE_SECTORS) == 30  # 30 / 14 per spin


def test_roulette_rules_changes_only_the_varietal_rules_and_points():
    p = roulette_rules(NORMAL)
    assert p.varietal_rules is VarietalRules.ROULETTE
    assert dict(p.varietal_points) == dict(ROULETTE_POINTS)
    assert with_overrides(p, varietal_rules=VarietalRules.FIXED, varietal_points=NORMAL.varietal_points) == NORMAL


def test_preset_rejects_a_roulette_sector_without_points():
    with pytest.raises(ValueError, match="no entry in varietal_points"):
        with_overrides(NORMAL, varietal_rules=VarietalRules.ROULETTE)


def test_preset_rejects_fixed_bodega_varietals_above_the_varietals_in_play():
    with pytest.raises(ValueError, match="bodega_varietals"):
        with_overrides(NORMAL, bodega_varietals=4)
    # Under roulette rules 8 distinct varietals are in play, so 4 is fine.
    assert with_overrides(roulette_rules(NORMAL), bodega_varietals=4).bodega_varietals == 4
    with pytest.raises(ValueError, match="bodega_varietals"):
        with_overrides(roulette_rules(NORMAL), roulette=(V.MALBEC, V.SYRAH))


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"roulette": ()}, ValueError),
        ({"roulette": "malbec"}, TypeError),
        ({"roulette": (V.MALBEC, "syrah")}, TypeError),
        ({"varietal_points": {}}, ValueError),
        ({"varietal_points": {V.MALBEC: 0, V.BONARDA: 2, V.TORRONTES: 1}}, ValueError),
        ({"varietal_points": {"malbec": 3}}, ValueError),
        ({"varietal_rules": "roulette"}, TypeError),
    ],
)
def test_preset_rejects_bad_varietal_values(changes, error):
    with pytest.raises(error):
        with_overrides(NORMAL, **changes)


def test_varietal_points_are_read_only():
    with pytest.raises(TypeError):
        NORMAL.varietal_points[V.MALBEC] = 5


# --- Board generation ----------------------------------------------------------

# sha256 of every tile of generate_board(players, seed, mode) for both modes,
# 2 to 5 players and seeds 0 to 59, computed with the code before #85.
FIXED_BOARDS_DIGEST = "43eba6d214509d84493e7422d34c09fd05e94558b1627a14964051ae2d1d88c1"


def test_fixed_boards_are_identical_to_before():
    h = hashlib.sha256()
    for mode in Mode:
        for players in range(2, 6):
            for seed in range(60):
                for t in generate_board(players, seed, mode).tiles:
                    name = t.varietal and t.varietal.name
                    h.update(f"{t.hex.q},{t.hex.r},{t.terrain.value},{name};".encode())
                h.update(b"|")
    assert h.hexdigest() == FIXED_BOARDS_DIGEST


@pytest.mark.parametrize("mode", list(Mode), ids=lambda m: m.name)
@pytest.mark.parametrize("players", [2, 5])
def test_roulette_boards_have_blank_vineyards_and_the_same_layout(mode, players):
    p = roulette_rules(preset(mode))
    for seed in range(5):
        board = generate_board(players, seed, mode, preset=p)
        fixed = generate_board(players, seed, mode)
        vineyards = [t for t in board.tiles if t.terrain is Terrain.VINEYARD]
        assert len(vineyards) == players * p.vineyards_per_player
        assert all(t.varietal is None for t in vineyards)
        # The varietal shuffles are skipped, so the board can differ from the
        # fixed one only after the layout's own draws; terrain counts match.
        assert Counter(t.terrain for t in board.tiles) == Counter(t.terrain for t in fixed.tiles)


def test_assembly_reads_a_blank_vineyard_without_a_varietal():
    board = Board(tiles=(Tile(Hex(0, 0), Terrain.RIVER), Tile(Hex(1, 0), Terrain.VINEYARD)))
    steps = assembly_instructions(board)
    assert steps[1].text == "Row 1, hex 2: vineyard"
    assert steps[1].varietal is None


# --- Model ---------------------------------------------------------------------

R, H1 = Hex(0, 0), Hex(1, 0)
VA, VB = Hex(2, -1), Hex(2, 0)  # NE and E of H1


def blank_board(**kw):
    tiles = (
        Tile(R, Terrain.RIVER),
        Tile(H1, Terrain.EMPTY),
        Tile(VA, Terrain.VINEYARD),
        Tile(VB, Terrain.VINEYARD),
    )
    return Board(tiles=tiles, **kw)


def roulette_state(board, market=(PieceKind.T_BRANCH,), mode=Mode.NORMAL, **kw):
    return GameState(
        board=board,
        players=(Player("a", 1), Player("b", 2)),
        mode=mode,
        round=1,
        start_player="a",
        current_player="a",
        market=market,
        preset=roulette_rules(preset(mode)),
        **kw,
    )


def test_varietal_at_reads_the_tile_then_the_planting():
    board = blank_board(claims=((VA, "a"),), plantings=((VA, V.SYRAH),))
    assert board.varietal_at(VA) is V.SYRAH
    assert board.varietal_at(VB) is None
    assert board.varietal_at(R) is None
    fixed = Board(tiles=(Tile(VA, Terrain.VINEYARD, V.MALBEC),))
    assert fixed.varietal_at(VA) is V.MALBEC


def test_board_rejects_a_planting_on_an_unclaimed_vineyard():
    with pytest.raises(ValueError, match="unclaimed"):
        blank_board(plantings=((VA, V.SYRAH),))


def test_board_rejects_bad_plantings():
    with pytest.raises(ValueError, match="not a vineyard"):
        blank_board(claims=((VA, "a"),), plantings=((H1, V.SYRAH),))
    with pytest.raises(ValueError, match="two plantings"):
        blank_board(claims=((VA, "a"),), plantings=((VA, V.SYRAH), (VA, V.MERLOT)))
    tiles = (Tile(VA, Terrain.VINEYARD, V.MALBEC),)
    with pytest.raises(ValueError, match="already has"):
        Board(tiles=tiles, claims=((VA, "a"),), plantings=((VA, V.SYRAH),))
    with pytest.raises(TypeError):
        blank_board(claims=((VA, "a"),), plantings=((VA, "syrah"),))


def test_board_plantings_are_stored_in_hex_order():
    claims = ((VA, "a"), (VB, "b"))
    a = blank_board(claims=claims, plantings=((VB, V.MERLOT), (VA, V.SYRAH)))
    b = blank_board(claims=claims, plantings=((VA, V.SYRAH), (VB, V.MERLOT)))
    assert a == b
    assert a.plantings == ((VA, V.SYRAH), (VB, V.MERLOT))


def test_game_state_rejects_a_blank_vineyard_under_fixed_rules():
    with pytest.raises(ValueError, match="needs a varietal"):
        GameState(
            board=blank_board(),
            players=(Player("a", 1), Player("b", 2)),
            mode=Mode.NORMAL,
            round=1,
            start_player="a",
            current_player="a",
        )


def test_game_state_rejects_a_varietal_tile_under_roulette_rules():
    board = Board(tiles=(Tile(R, Terrain.RIVER), Tile(VA, Terrain.VINEYARD, V.MALBEC)))
    with pytest.raises(ValueError, match="roulette"):
        roulette_state(board)


def test_game_state_rejects_an_unscored_varietal_or_a_planting_under_fixed_rules():
    tiles = (Tile(R, Terrain.RIVER), Tile(VA, Terrain.VINEYARD, V.SYRAH))
    fields = dict(
        players=(Player("a", 1), Player("b", 2)),
        mode=Mode.NORMAL,
        round=1,
        start_player="a",
        current_player="a",
    )
    with pytest.raises(ValueError, match="no points"):
        GameState(board=Board(tiles=tiles), **fields)
    planted = blank_board(claims=((VA, "a"),), plantings=((VA, V.MALBEC),))
    with pytest.raises(ValueError):
        GameState(board=planted, **fields)


# --- Turn engine: spins --------------------------------------------------------

T_BOTH = PlaceCanal(PieceKind.T_BRANCH, H1, 0)  # opens W (river), E (VB), NE (VA)


def test_a_claim_of_two_vineyards_spins_twice_lower_hex_first():
    for seed in range(50):
        ref = random.Random(seed)
        first, second = ref.choice(ROULETTE_SECTORS), ref.choice(ROULETTE_SECTORS)
        if first is not second:
            break
    rng = random.Random(seed)
    after = apply(roulette_state(blank_board()), "a", T_BOTH, rng)
    assert VA < VB
    assert after.board.claims == ((VA, "a"), (VB, "a"))
    assert after.board.plantings == ((VA, first), (VB, second))
    assert rng.getstate() == ref.getstate()


def test_a_rejected_action_draws_nothing():
    rng = random.Random(7)
    before = rng.getstate()
    state = roulette_state(blank_board())
    with pytest.raises(IllegalAction):
        apply(state, "a", PlaceCanal(PieceKind.STRAIGHT, H1, 0), rng)  # not in market
    with pytest.raises(IllegalAction):
        apply(state, "a", Bribe(H1, Direction.E), rng)  # no floodgate
    assert rng.getstate() == before


def test_an_action_that_claims_nothing_draws_nothing():
    rng = random.Random(7)
    before = rng.getstate()
    tiles = (
        Tile(R, Terrain.RIVER),
        Tile(H1, Terrain.EMPTY),
        Tile(Hex(2, 0), Terrain.EMPTY),
        Tile(Hex(3, 0), Terrain.VINEYARD),
    )
    state = roulette_state(Board(tiles=tiles), market=(PieceKind.STRAIGHT,))
    after = apply(state, "a", PlaceCanal(PieceKind.STRAIGHT, H1, 0), rng)
    assert after.board.claims == () and after.board.plantings == ()
    assert rng.getstate() == before


def test_a_bribe_that_waters_a_vineyard_rolls_the_die_then_spins():
    canal = PlacedCanal(H1, PieceKind.STRAIGHT, 0, "b")  # opens W (river) and E (VB)
    board = blank_board(canals=(canal,), floodgates=(Floodgate(H1, Direction.E),))
    state = roulette_state(board, market=())
    rng, ref = random.Random(3), random.Random(3)
    roll = ref.randint(1, state.preset.die_faces)
    spin = ref.choice(ROULETTE_SECTORS)
    after = apply(state, "a", Bribe(H1, Direction.E), rng)
    assert after.player("a").debt == roll
    assert after.board.claims == ((VB, "a"),)
    assert after.board.plantings == ((VB, spin),)
    assert rng.getstate() == ref.getstate()


def test_fixed_rules_draw_nothing_on_a_claim():
    tiles = (
        Tile(R, Terrain.RIVER),
        Tile(H1, Terrain.EMPTY),
        Tile(VA, Terrain.VINEYARD, V.MALBEC),
        Tile(VB, Terrain.VINEYARD, V.BONARDA),
    )
    state = GameState(
        board=Board(tiles=tiles),
        players=(Player("a", 1), Player("b", 2)),
        mode=Mode.NORMAL,
        round=1,
        start_player="a",
        current_player="a",
        market=(PieceKind.T_BRANCH,),
    )
    rng = random.Random(1)
    before = rng.getstate()
    after = apply(state, "a", T_BOTH, rng)
    assert len(after.board.claims) == 2 and after.board.plantings == ()
    assert rng.getstate() == before


def test_spins_follow_the_sector_shares():
    rng = random.Random(2026)
    counts = Counter(rng.choice(ROULETTE_SECTORS) for _ in range(14_000))
    for v in Varietal:
        expected = 1000 if v in (V.BONARDA, V.CABERNET_FRANC) else 2000
        assert abs(counts[v] - expected) <= 0.1 * expected, (v, counts[v])
    singles = (counts[V.BONARDA] + counts[V.CABERNET_FRANC]) / 2
    doubles = sum(counts[v] for v in Varietal if v not in (V.BONARDA, V.CABERNET_FRANC)) / 6
    assert singles / doubles == pytest.approx(0.5, abs=0.05)


# --- Scoring -------------------------------------------------------------------


def lanes_state(varietals, claimant="a"):
    """One watered lane per varietal (river, a canal of ``claimant``, a blank vineyard)."""
    tiles, canals, claims, plantings = [], [], [], []
    for i, varietal in enumerate(varietals):
        row = 2 * i
        river, canal, vineyard = Hex(0, row), Hex(1, row), Hex(2, row)
        tiles += [
            Tile(river, Terrain.RIVER),
            Tile(canal, Terrain.EMPTY),
            Tile(vineyard, Terrain.VINEYARD),
        ]
        canals.append(PlacedCanal(canal, PieceKind.STRAIGHT, 0, claimant))
        claims.append((vineyard, claimant))
        plantings.append((vineyard, varietal))
    board = Board(tiles=tuple(tiles), canals=tuple(canals), claims=tuple(claims),
                  plantings=tuple(plantings))
    return roulette_state(board, market=())


def test_two_malbecs_count_once_for_the_bodega_bonus():
    score = calculate_score(lanes_state([V.MALBEC, V.MALBEC, V.SYRAH]))["a"]
    assert score.bodega == 0
    assert score.vineyards == 2 + 2 + 2
    assert [v.varietal for v in score.watered_vineyards] == [V.MALBEC, V.MALBEC, V.SYRAH]


def test_three_different_varietals_earn_the_bodega_bonus():
    state = lanes_state([V.MALBEC, V.SYRAH, V.BONARDA])
    score = calculate_score(state)["a"]
    assert score.bodega == state.preset.bodega_points
    assert score.vineyards == 2 + 2 + 3


def test_vineyard_points_follow_the_preset():
    state = lanes_state([V.CABERNET_FRANC, V.CHARDONNAY])
    points = {V.CABERNET_FRANC: 7, V.CHARDONNAY: 5}
    p = with_overrides(state.preset, varietal_points={**ROULETTE_POINTS, **points})
    assert calculate_score(state, p)["a"].vineyards == 12


def test_scoring_rejects_a_watered_claim_never_planted():
    state = lanes_state([V.MALBEC])
    board = Board(tiles=state.board.tiles, canals=state.board.canals, claims=state.board.claims)
    with pytest.raises(ValueError, match="no varietal"):
        calculate_score(roulette_state(board, market=()))


# --- Simulation and bots -------------------------------------------------------


def test_a_roulette_game_plants_every_claimed_vineyard_and_nothing_else():
    rules = SimRules(Mode.FLASH, 3, ("greedy", "saboteur", "random"), ROULETTE)
    for i in range(3):
        record = play_one(rules, game_seed(85, i))
        board = record.final.board
        claimed = [h for h, _ in board.claims]
        assert [h for h, _ in board.plantings] == claimed
        assert all(t.varietal is None for t in board.tiles if t.terrain is Terrain.VINEYARD)


@pytest.mark.parametrize("policy", ["greedy", "saboteur", "random"])
def test_each_bot_plays_roulette_games_to_the_end(policy):
    rules = SimRules(Mode.NORMAL, 2, (policy, policy), ROULETTE)
    for i in range(2):
        record = play_one(rules, game_seed(86, i))
        assert record.final.preset.varietal_rules is VarietalRules.ROULETTE
        assert record.log


def test_roulette_simulation_is_repeatable_and_reports_all_eight_varietals():
    rules = SimRules(Mode.FLASH, 2, ("greedy", "saboteur"), ROULETTE)
    first = simulate_game(rules, 4, 11)
    assert first.to_json() == simulate_game(rules, 4, 11).to_json()
    assert list(first.winner_varietal_rate) == ALL_NAMES
    preset_json = first.to_json()["preset"]
    assert preset_json["varietal_rules"] == "roulette"
    assert preset_json["roulette"] == [
        "malbec", "malbec", "cabernet_sauvignon", "cabernet_sauvignon", "syrah", "syrah",
        "merlot", "merlot", "torrontes", "torrontes", "chardonnay", "chardonnay",
        "bonarda", "cabernet_franc",
    ]
    assert preset_json["varietal_points"]["cabernet_franc"] == 3


def test_fixed_simulation_keeps_three_varietal_keys():
    result = simulate_game(SimRules(Mode.FLASH, 2, ("greedy", "greedy")), 2, 1)
    assert list(result.winner_varietal_rate) == ["malbec", "bonarda", "torrontes"]
    assert result.to_json()["preset"]["varietal_points"] == {"malbec": 3, "bonarda": 2, "torrontes": 1}


# --- JSON ----------------------------------------------------------------------


def test_overrides_from_json_converts_the_varietal_fields():
    changes = overrides_from_json(
        {"varietal_rules": "roulette", "varietal_points": {"syrah": 4}, "roulette": ["syrah"]}
    )
    assert changes == {
        "varietal_rules": VarietalRules.ROULETTE,
        "varietal_points": {V.SYRAH: 4},
        "roulette": (V.SYRAH,),
    }
    for bad in ({"varietal_rules": "wheel"}, {"varietal_points": {"pinot": 1}},
                {"roulette": ["pinot"]}):
        with pytest.raises(ValueError):
            overrides_from_json(bad)


def test_a_claim_with_a_varietal_round_trips():
    items = [
        {"q": 2, "r": -1, "player": "a", "varietal": "cabernet_franc"},
        {"q": 2, "r": 0, "player": "b", "varietal": None},
    ]
    board = blank_board(
        claims=tuple(claim_from_json(i) for i in items),
        plantings=tuple(p for p in map(planting_from_json, items) if p is not None),
    )
    assert board.varietal_at(VA) is V.CABERNET_FRANC
    assert claims_to_json(board) == items
    assert planting_from_json({"q": 2, "r": 0, "player": "b"}) is None


def roulette_game(claims):
    hexes, canals = [], []
    for i in range(len(claims)):
        row = 2 * i
        hexes += [
            {"q": 0, "r": row, "terrain": "river", "varietal": None},
            {"q": 1, "r": row, "terrain": "empty", "varietal": None},
            {"q": 2, "r": row, "terrain": "vineyard", "varietal": None},
        ]
        canals.append({"q": 1, "r": row, "kind": "straight", "rotation": 0, "owner": "a"})
    return {
        "mode": "normal",
        "hexes": hexes,
        "canals": canals,
        "claims": [
            {"q": 2, "r": 2 * i, "player": "a", "varietal": v} for i, v in enumerate(claims)
        ],
        "players": [{"id": "a", "debt": 0}, {"id": "b", "debt": 0}],
    }


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_calculate_score_scores_planted_claims_with_roulette_overrides():
    points = {name: 2 for name in ALL_NAMES} | {"bonarda": 3, "cabernet_franc": 3}
    arguments = roulette_game(["malbec", "syrah", "cabernet_franc"])
    arguments["overrides"] = {"varietal_rules": "roulette", "varietal_points": points}
    async with Client(app) as client:
        result = await client.call_tool("calculate_score", arguments)
    assert not result.is_error
    a = result.structured_content["scores"][0]
    assert a["vineyards"] == 2 + 2 + 3
    assert a["bodega"] == NORMAL.bodega_points
    assert [v["varietal"] for v in a["watered_vineyards"]] == ["malbec", "syrah", "cabernet_franc"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("claims", "overrides", "message"),
    [
        (["pinot_noir"], {"varietal_rules": "roulette"}, "pinot_noir"),
        (["malbec"], {}, "varietal"),  # fixed rules: blank vineyards are not allowed
        (["malbec"], {"varietal_rules": "roulette"}, "varietal_points"),  # sectors without points
    ],
)
async def test_calculate_score_reports_bad_varietal_input_as_tool_errors(claims, overrides, message):
    arguments = roulette_game(claims)
    if overrides:
        arguments["overrides"] = overrides
    async with Client(app) as client:
        result = await client.call_tool("calculate_score", arguments)
    assert result.is_error
    assert message in "".join(b.text for b in result.content if b.type == "text")
