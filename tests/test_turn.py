import ast
import dataclasses
import random
from pathlib import Path

import pytest

from acequias.config import NORMAL, with_overrides
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
from acequias.setup import new_game
from acequias.turn import (
    Bribe,
    IllegalAction,
    Pass,
    PlaceCanal,
    PlaceFloodgate,
    apply,
    legal_actions,
)

E, NE, NW, W, SW, SE = list(Direction)
STRAIGHT, GENTLE, SHARP, Y, T, CLAW, GATE = list(PieceKind)
DIRECTIONS = list(Direction)

# A row west to east: river, three empty hexes, a vineyard.
R = Hex(0, 0)
H1, H2, H3 = Hex(1, 0), Hex(2, 0), Hex(3, 0)
V = Hex(4, 0)


# --- Helpers -----------------------------------------------------------------


def make_board(river=(R,), vineyards=(V,), stones=(), empties=(H1, H2, H3),
               canals=(), floodgates=(), claims=()):
    tiles = [Tile(h, Terrain.RIVER) for h in river]
    tiles += [Tile(h, Terrain.VINEYARD, Varietal.MALBEC) for h in vineyards]
    tiles += [Tile(h, Terrain.STONE) for h in stones]
    tiles += [Tile(h, Terrain.EMPTY) for h in empties]
    return Board(tiles=tuple(tiles), canals=tuple(canals),
                 floodgates=tuple(floodgates), claims=tuple(claims))


def make_state(board=None, market=(STRAIGHT,), bag=(), preset=None, **kw):
    fields = dict(
        board=board if board is not None else make_board(),
        players=(Player("a", 1), Player("b", 2, debt=4)),
        mode=Mode.NORMAL,
        round=1,
        start_player="a",
        current_player="a",
        market=market,
        bag=bag,
        preset=preset,
    )
    fields.update(kw)
    return GameState(**fields)


def straight(hex, owner="a"):
    """A straight running east-west."""
    return PlacedCanal(hex, STRAIGHT, 0, owner)


def rng():
    return random.Random(1)


def rejects(state, player, action, match):
    r = rng()
    before = r.getstate()
    with pytest.raises(ValueError, match=match or None):
        apply(state, player, action, r)
    assert r.getstate() == before


# --- API ---------------------------------------------------------------------


def test_actions_are_frozen_and_hashable():
    actions = [PlaceCanal(STRAIGHT, H1, 0), PlaceFloodgate(H1, E), Bribe(H1, E),
               Bribe(H1, E, (H2, W)), Pass()]
    for action in actions:
        assert hash(action) == hash(dataclasses.replace(action))
        with pytest.raises(dataclasses.FrozenInstanceError):
            action.hex = H2
    assert len(set(actions + [PlaceCanal(STRAIGHT, H1, 0), Pass()])) == len(actions)


def test_action_fields_are_type_checked():
    with pytest.raises(TypeError):
        PlaceCanal("straight", H1, 0)
    with pytest.raises(TypeError):
        PlaceFloodgate(H1, "E")
    with pytest.raises(TypeError):
        Bribe(H1, E, to=[H2, W])


def test_unknown_player_is_a_value_error():
    with pytest.raises(ValueError, match="not one of the game's players"):
        apply(make_state(), "z", PlaceCanal(STRAIGHT, H1, 0), rng())
    with pytest.raises(ValueError, match="not one of the game's players"):
        legal_actions(make_state(), "z")


@pytest.mark.parametrize("action", [None, "pass", (STRAIGHT, H1, 0), Floodgate(H1, E)])
def test_a_non_action_is_a_type_error(action):
    with pytest.raises(TypeError):
        apply(make_state(), "a", action, rng())


def test_turn_fields_are_copied_unchanged():
    state = make_state(current_player="b", start_player="b", round=3)
    new = apply(state, "a", PlaceCanal(STRAIGHT, H1, 0), rng())
    assert (new.current_player, new.start_player, new.round) == ("b", "b", 3)


def test_a_placement_changes_only_the_fields_it_affects():
    preset = with_overrides(NORMAL, die_faces=8)
    state = make_state(market=(STRAIGHT, GATE), bag=(CLAW, Y), preset=preset)
    new = apply(state, "b", PlaceCanal(STRAIGHT, H1, 3), rng())

    assert new.preset is preset
    assert new.mode is state.mode
    assert new.players == state.players
    assert [p.id for p in new.players] == ["a", "b"]
    assert (new.round, new.start_player, new.current_player) == (1, "a", "a")
    assert new.market == (GATE, CLAW)
    assert new.bag == (Y,)
    assert new.board.tiles == state.board.tiles
    assert new.board.canals == (PlacedCanal(H1, STRAIGHT, 0, "b"),)
    assert new.board.floodgates == ()
    assert new.board.claims == ()
    assert state.board.canals == ()  # the input is unchanged
    assert state.market == (STRAIGHT, GATE)


def test_legal_actions_order_and_no_duplicates():
    board = make_board(canals=[straight(H1), straight(H2, "b")],
                       floodgates=[Floodgate(H2, E)])
    state = make_state(board, market=(GATE, STRAIGHT, SHARP, STRAIGHT))
    actions = legal_actions(state, "a")
    assert len(set(actions)) == len(actions)
    assert actions == legal_actions(state, "a")

    kinds = [type(a) for a in actions]
    order = [PlaceCanal, PlaceFloodgate, Bribe]
    assert kinds == sorted(kinds, key=order.index)

    canals = [a for a in actions if isinstance(a, PlaceCanal)]
    assert canals == sorted(canals, key=lambda a: (list(PieceKind).index(a.kind), a.hex, a.rotation))
    # The only free empty hex is H3; only the east-west straight reaches H2.
    assert [a.rotation for a in canals if a.kind is STRAIGHT] == [0]
    assert {a.hex for a in canals} == {H3}

    gates = [a for a in actions if isinstance(a, PlaceFloodgate)]
    assert gates == sorted(gates, key=lambda a: (a.hex, DIRECTIONS.index(a.direction)))
    # H1-H2 is listed once, from H1; H2 E already has a gate.
    assert gates == [PlaceFloodgate(H1, E), PlaceFloodgate(H1, W)]

    bribes = [a for a in actions if isinstance(a, Bribe)]
    assert bribes == [Bribe(H2, E), Bribe(H2, E, (H1, E)), Bribe(H2, E, (H1, W))]


def test_a_straight_in_the_market_gives_three_rotations_not_six():
    state = make_state(make_board(river=(R,), empties=(H1,)), market=(STRAIGHT, STRAIGHT))
    actions = legal_actions(state, "a")
    # Only rotations that open W reach the river: straight E-W, listed once.
    assert actions == (PlaceCanal(STRAIGHT, H1, 0),)
    # With the river on every side of H1, every distinct rotation connects.
    ring = make_board(river=Hex(1, 0).neighbors(), vineyards=(), empties=(H1,))
    actions = legal_actions(make_state(ring, market=(STRAIGHT, STRAIGHT)), "a")
    assert actions == tuple(PlaceCanal(STRAIGHT, H1, r) for r in range(3))


def test_equivalent_spellings_give_the_same_state():
    state = make_state(market=(STRAIGHT,))
    assert apply(state, "a", PlaceCanal(STRAIGHT, H1, 3), rng()) == apply(
        state, "a", PlaceCanal(STRAIGHT, H1, 0), rng())

    board = make_board(canals=[straight(H1), straight(H2)])
    state = make_state(board, market=(GATE,))
    a = apply(state, "a", PlaceFloodgate(H1, E), rng())
    b = apply(state, "a", PlaceFloodgate(H2, W), rng())
    assert a == b
    # The edge facing a vineyard, named from the vineyard.
    board = make_board(canals=[straight(H1), straight(H2), straight(H3)])
    state = make_state(board, market=(GATE,))
    assert apply(state, "a", PlaceFloodgate(V, W), rng()) == apply(
        state, "a", PlaceFloodgate(H3, E), rng())

    gated = make_state(make_board(canals=[straight(H1), straight(H2)],
                                  floodgates=[Floodgate(H1, E)]))
    assert apply(gated, "a", Bribe(H2, W, (H2, E)), rng()) == apply(
        gated, "a", Bribe(H1, E, (Hex(3, 0), W)), rng())


# --- Random states -----------------------------------------------------------


def _edge_spellings(hex, direction):
    return {(hex, direction), (hex.neighbor(direction), direction.opposite())}


def _canonical(action):
    """The action's set of equivalent spellings, as comparable keys."""
    if isinstance(action, PlaceCanal):
        if not action.kind.is_canal or not 0 <= action.rotation < 6:
            return {action}
        edges = action.kind.edges(action.rotation)
        return {PlaceCanal(action.kind, action.hex, r) for r in range(6)
                if action.kind.edges(r) == edges}
    if isinstance(action, PlaceFloodgate):
        return {PlaceFloodgate(h, d) for h, d in _edge_spellings(action.hex, action.direction)}
    if isinstance(action, Bribe):
        tos = [None] if action.to is None else list(_edge_spellings(*action.to))
        return {Bribe(h, d, to) for h, d in _edge_spellings(action.hex, action.direction)
                for to in tos}
    return {action}


def _random_hex(r, state):
    h = r.choice(state.board.tiles).hex
    return h.neighbor(r.choice(DIRECTIONS)) if r.random() < 0.2 else h


def _random_action(r, state):
    """Any action at all, mostly illegal: random fields on and near the board."""
    choice = r.randrange(4)
    if choice == 0:
        return PlaceCanal(r.choice(list(PieceKind)), _random_hex(r, state), r.randrange(-1, 7))
    if choice == 1:
        return PlaceFloodgate(_random_hex(r, state), r.choice(DIRECTIONS))
    if choice == 2:
        to = None if r.random() < 0.3 else (_random_hex(r, state), r.choice(DIRECTIONS))
        if state.board.floodgates and r.random() < 0.5:
            gate = r.choice(state.board.floodgates)
            return Bribe(gate.hex, gate.direction, to)
        return Bribe(_random_hex(r, state), r.choice(DIRECTIONS), to)
    return Pass()


def _mutated(r, action, state):
    """A listed action with one field changed: often still legal, often not."""
    if isinstance(action, PlaceCanal):
        field = r.randrange(3)
        if field == 0:
            return dataclasses.replace(action, kind=r.choice(list(PieceKind)))
        if field == 1:
            return dataclasses.replace(action, hex=action.hex.neighbor(r.choice(DIRECTIONS)))
        return dataclasses.replace(action, rotation=r.randrange(6))
    if isinstance(action, PlaceFloodgate):
        if r.random() < 0.5:
            return dataclasses.replace(action, direction=r.choice(DIRECTIONS))
        return dataclasses.replace(action, hex=action.hex.neighbor(r.choice(DIRECTIONS)))
    if isinstance(action, Bribe):
        to = (_random_hex(r, state), r.choice(DIRECTIONS))
        return dataclasses.replace(action, to=to if action.to is None or r.random() < 0.5 else None)
    return _random_action(r, state)


def _respelled(r, action):
    """An equivalent spelling of a listed action."""
    return r.choice(sorted(_canonical(action), key=repr))


@pytest.mark.parametrize("seed", range(8))
def test_random_games_accept_listed_actions_and_reject_illegal_ones(seed):
    r = random.Random(seed)
    state = new_game(2 + seed % 4, seed, list(Mode)[seed % 2])
    ids = [p.id for p in state.players]
    dice = random.Random(seed)
    for step in range(50):
        player = ids[step % len(ids)]
        actions = legal_actions(state, player)
        assert actions
        assert actions == legal_actions(state, player)
        listed = set(actions)
        assert len(listed) == len(actions)
        if actions == (Pass(),):
            break  # the game is stuck: nothing to place and nothing to bribe

        if step % 5 == 0:  # every listed action is accepted
            for action in actions:
                apply(state, player, action, random.Random(0))

        for action in r.sample(actions, min(5, len(actions))):
            spelling = _respelled(r, action)
            assert apply(state, player, spelling, random.Random(0)) == apply(
                state, player, action, random.Random(0))

        candidates = [_random_action(r, state) for _ in range(10)]
        candidates += [_mutated(r, r.choice(actions), state) for _ in range(10)]
        for action in candidates:
            if _canonical(action) & listed:
                apply(state, player, action, random.Random(0))
            else:
                rejects(state, player, action, "")

        # Prefer placements so the board fills up.
        placements = [a for a in actions if isinstance(a, (PlaceCanal, PlaceFloodgate))]
        pool = placements if placements and r.random() < 0.85 else actions
        state = apply(state, player, r.choice(pool), dice)


# --- Place a canal -----------------------------------------------------------


def test_canal_kind_must_be_in_the_market():
    rejects(make_state(market=(SHARP, GATE)), "a", PlaceCanal(STRAIGHT, H1, 0), "market has no")


def test_floodgate_is_not_a_canal_shape():
    rejects(make_state(market=(GATE,)), "a", PlaceCanal(GATE, H1, 0), "not a canal shape")


@pytest.mark.parametrize("rotation", [-1, 6])
def test_canal_rotation_must_be_0_to_5(rotation):
    rejects(make_state(), "a", PlaceCanal(STRAIGHT, H1, rotation), "rotation")


@pytest.mark.parametrize(
    "hex, match",
    [(Hex(1, 5), "off the board"), (R, "river"), (V, "vineyard"), (Hex(1, 1), "stone"),
     (H1, "already has a canal")],
)
def test_canal_target_must_be_a_free_empty_tile(hex, match):
    board = make_board(stones=(Hex(1, 1),), canals=[straight(H1)])
    rejects(make_state(board), "a", PlaceCanal(STRAIGHT, hex, 0), match)


def test_canal_must_connect_to_the_river_or_a_canal():
    rejects(make_state(), "a", PlaceCanal(STRAIGHT, H2, 0), "no opening facing")
    # A straight on H1 turned north-south faces neither the river nor a canal.
    rejects(make_state(), "a", PlaceCanal(STRAIGHT, H1, 1), "no opening facing")
    # A canal on H2 whose W side is closed does not connect to H1's E opening.
    board = make_board(canals=[straight(H1)])
    rejects(make_state(board, market=(SHARP,)), "a", PlaceCanal(SHARP, H2, 1), "no opening facing")


def test_canal_may_connect_to_a_dry_or_gated_canal():
    dry = make_board(canals=[straight(H2)])  # H2 is not connected to the river
    new = apply(make_state(dry), "a", PlaceCanal(STRAIGHT, H3, 0), rng())
    assert new.board.canal_at(H3) is not None

    gated = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, E)])
    new = apply(make_state(gated), "a", PlaceCanal(STRAIGHT, H2, 0), rng())
    assert new.board.canal_at(H2) is not None


def test_dead_ends_are_legal_and_the_owner_is_recorded():
    # A claw at H1 opening W (river), and NW and SW off the board.
    claw = next(r for r in range(6) if CLAW.edges(r) == {W, NW, SW})
    new = apply(make_state(market=(CLAW,)), "b", PlaceCanal(CLAW, H1, claw), rng())
    assert new.board.canal_at(H1) == PlacedCanal(H1, CLAW, claw, "b")


# --- Place a floodgate -------------------------------------------------------


def test_floodgate_must_be_in_the_market():
    board = make_board(canals=[straight(H1)])
    rejects(make_state(board, market=(STRAIGHT,)), "a", PlaceFloodgate(H1, E), "no floodgate")


def test_floodgate_needs_an_open_canal_edge():
    board = make_board(canals=[straight(H1)])
    state = make_state(board, market=(GATE,))
    rejects(state, "a", PlaceFloodgate(H1, NE), "not an open edge of a canal")
    rejects(state, "a", PlaceFloodgate(H3, W), "not an open edge of a canal")


def test_floodgate_edge_must_be_free_from_either_side():
    board = make_board(canals=[straight(H1), straight(H2)], floodgates=[Floodgate(H1, E)])
    state = make_state(board, market=(GATE,))
    rejects(state, "a", PlaceFloodgate(H1, E), "already has a floodgate")
    rejects(state, "a", PlaceFloodgate(H2, W), "already has a floodgate")


@pytest.mark.parametrize("hex, direction", [(H1, W), (H3, E), (H1, E)])
def test_floodgate_may_face_river_vineyard_or_canal(hex, direction):
    board = make_board(canals=[straight(H1), straight(H2, "b"), straight(H3, "b")])
    new = apply(make_state(board, market=(GATE,)), "a", PlaceFloodgate(hex, direction), rng())
    assert new.board.has_floodgate(hex, direction)


# --- Market ------------------------------------------------------------------


def test_market_takes_the_first_copy_and_refills_from_the_top_of_the_bag():
    state = make_state(market=(GATE, STRAIGHT, CLAW, STRAIGHT), bag=(Y, T, SHARP))
    new = apply(state, "a", PlaceCanal(STRAIGHT, H1, 0), rng())
    assert new.market == (GATE, CLAW, STRAIGHT, Y)
    assert new.bag == (T, SHARP)


def test_market_shrinks_when_the_bag_is_empty():
    state = make_state(make_board(canals=[straight(H1)]), market=(GATE, STRAIGHT), bag=())
    new = apply(state, "a", PlaceFloodgate(H1, E), rng())
    assert new.market == (STRAIGHT,)
    assert new.bag == ()


# --- Claims ------------------------------------------------------------------


def test_one_action_claims_every_newly_watered_vineyard():
    # H1 straight to H2; a Y on H2 opening W, NE, SE feeds two vineyards.
    v_ne, v_se = H2.neighbor(NE), H2.neighbor(SE)
    board = make_board(vineyards=(V, v_ne, v_se), canals=[straight(H1)])
    y = next(r for r in range(6) if Y.edges(r) == {W, NE, SE})
    new = apply(make_state(board, market=(Y,)), "b", PlaceCanal(Y, H2, y), rng())
    assert dict(new.board.claims) == {v_ne: "b", v_se: "b"}


def test_a_claim_is_never_reassigned():
    board = make_board(canals=[straight(H1), straight(H2)], claims=[(V, "a")])
    state = make_state(board, market=(STRAIGHT,))
    # V is dry and claimed by "a"; "b" waters it through a new canal.
    new = apply(state, "b", PlaceCanal(STRAIGHT, H3, 0), rng())
    assert new.board.claimant(V) == "a"


def test_a_claim_survives_going_dry_and_being_rewatered_by_a_rival():
    state = make_state(make_board(canals=[straight(H1), straight(H2)]),
                       market=(STRAIGHT, GATE, GATE))
    state = apply(state, "a", PlaceCanal(STRAIGHT, H3, 0), rng())
    assert state.board.claimant(V) == "a"
    state = apply(state, "b", PlaceFloodgate(H1, E), rng())  # V dry
    state = apply(state, "b", Bribe(H1, E), rng())  # watered again by b's bribe
    assert state.board.claimant(V) == "a"


# --- Bribe -------------------------------------------------------------------


def test_bribe_needs_a_floodgate_on_the_board():
    rejects(make_state(make_board(canals=[straight(H1)])), "a", Bribe(H1, E),
            "needs a floodgate on the board")


def test_bribe_edge_must_hold_a_floodgate():
    board = make_board(canals=[straight(H1), straight(H2)], floodgates=[Floodgate(H1, W)])
    rejects(make_state(board), "a", Bribe(H1, E), "no floodgate to bribe")


def test_bribe_rolls_one_die_and_adds_it_to_the_debt():
    board = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, E)])
    state = make_state(board)
    r = random.Random(5)
    expected = random.Random(5).randint(1, 6)
    new = apply(state, "b", Bribe(H1, E), r)
    assert new.player("b").debt == 4 + expected
    assert new.player("a").debt == 0
    ref = random.Random(5)
    ref.randint(1, 6)
    assert r.getstate() == ref.getstate()  # exactly one draw


def test_bribe_die_size_comes_from_the_preset():
    d20 = with_overrides(NORMAL, die_faces=20)
    board = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, E)])
    state = make_state(board, preset=d20)
    r = random.Random(3)
    rolls = [apply(state, "a", Bribe(H1, E), r).player("a").debt for _ in range(200)]
    assert all(1 <= roll <= 20 for roll in rolls)
    assert max(rolls) > 6


def test_bribe_without_a_preset_uses_the_shipped_die():
    board = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, E)])
    state = make_state(board, preset=None)
    r = random.Random(3)
    rolls = [apply(state, "a", Bribe(H1, E), r).player("a").debt for _ in range(200)]
    assert set(rolls) == set(range(1, NORMAL.die_faces + 1))


def test_bribe_remove_takes_the_floodgate_out_of_the_game():
    board = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, E)])
    state = make_state(board, market=(GATE, STRAIGHT), bag=(Y,))
    new = apply(state, "a", Bribe(H2, W), rng())  # named from the other side
    assert new.board.floodgates == ()
    assert new.market == state.market
    assert new.bag == state.bag


def test_bribe_move_goes_to_another_legal_edge():
    board = make_board(canals=[straight(H1), straight(H2)], floodgates=[Floodgate(H1, E)])
    state = make_state(board)
    new = apply(state, "a", Bribe(H1, E, (H2, E)), rng())
    assert new.board.floodgates == (Floodgate(H2, E),)
    rejects(state, "a", Bribe(H1, E, (H1, E)), "another edge")
    rejects(state, "a", Bribe(H1, E, (H2, W)), "another edge")
    rejects(state, "a", Bribe(H1, E, (H1, NE)), "not an open edge of a canal")
    two = make_board(canals=[straight(H1), straight(H2)],
                     floodgates=[Floodgate(H1, E), Floodgate(H1, W)])
    rejects(make_state(two), "a", Bribe(H1, E, (H1, W)), "already has a floodgate")


def test_a_bribe_rewaters_a_vineyard_and_the_briber_claims_it():
    board = make_board(canals=[straight(H1), straight(H2), straight(H3, "b")],
                       floodgates=[Floodgate(H1, E)])
    state = make_state(board)
    assert state.board.claims == ()
    new = apply(state, "b", Bribe(H1, E), rng())
    assert new.board.claimant(V) == "b"
    moved = apply(state, "a", Bribe(H1, E, (H3, W)), rng())
    # Moved onto H2-H3, the vineyard stays dry and is not claimed.
    assert moved.board.claims == ()


# --- Pass --------------------------------------------------------------------


@pytest.mark.parametrize(
    "board, market",
    [
        (make_board(canals=[straight(H1)]), ()),  # empty market
        (make_board(), (GATE, GATE)),  # floodgates only, no canals
        (make_board(river=(), empties=(H2,)), (STRAIGHT, CLAW)),  # nowhere to connect
    ],
    ids=["empty market", "only floodgates", "no legal hex"],
)
def test_pass_when_nothing_can_be_placed(board, market):
    state = make_state(board, market=market, bag=(Y,))
    assert legal_actions(state, "a") == (Pass(),)
    r = rng()
    before = r.getstate()
    new = apply(state, "a", Pass(), r)
    assert new == state
    assert r.getstate() == before


def test_pass_is_illegal_with_a_placement():
    rejects(make_state(), "a", Pass(), "pass is only legal")


def test_bribe_is_never_forced():
    board = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, E)])
    state = make_state(board, market=())
    actions = legal_actions(state, "a")
    assert Pass() in actions
    assert Bribe(H1, E) in actions
    assert actions[-1] == Pass()
    assert apply(state, "a", Pass(), rng()) == state


# --- Randomness --------------------------------------------------------------


def test_only_a_bribe_draws_from_the_rng():
    board = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, W)])
    state = make_state(board, market=(STRAIGHT, GATE))
    for action in (PlaceCanal(STRAIGHT, H2, 0), PlaceFloodgate(H1, E)):
        r = rng()
        before = r.getstate()
        apply(state, "a", action, r)
        assert r.getstate() == before
    r = rng()
    before = r.getstate()
    apply(state, "a", Bribe(H1, W), r)
    assert r.getstate() != before


def test_same_state_action_and_seed_give_the_same_result():
    board = make_board(canals=[straight(H1)], floodgates=[Floodgate(H1, W)])
    state = make_state(board, market=(STRAIGHT, GATE))
    for action in (PlaceCanal(STRAIGHT, H2, 0), Bribe(H1, W), Bribe(H1, W, (H1, E))):
        results = {apply(state, "a", action, random.Random(9)) for _ in range(5)}
        assert len(results) == 1


def test_turn_imports_only_acequias_modules_and_the_standard_library():
    source = Path(__file__).resolve().parent.parent / "acequias" / "turn.py"
    tree = ast.parse(source.read_text("utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            top = node.module.split(".")[0]
            assert top in {"acequias", "__future__", "dataclasses", "random"}, node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name.split(".")[0] in {"random"}, alias.name
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            assert node.value.id != "random" or node.attr == "Random", "global random used"
