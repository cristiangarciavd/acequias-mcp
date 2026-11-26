"""The round loop: whose turn it is, the rotating start player, and the end of the game.

Rules come from ``README.md`` (Turn, Turn order). A turn is one action. In
every round each player acts once, in seat order (players sorted by
``Player.seat``, the lowest seat following the highest), starting from that
round's start player. The start player rotates to the next seat each round,
like Mendoza's *turnos de riego*. Under action die rules a die turn is two
actions by the same player: the roll, then the face's use or
``DeclineFace``; the turn moves on only once no face is pending. A
rolled season face (good season, drought) applies at once and ends the
turn. With ``Preset.season_roll_every`` X, every X-th round starts with a
free season roll (``GameState.season_roll``) by the season die's holder
(``season_holder``): the k-th season roll of the game is made by the seat
k-1 places after the game's first start player (the season die passes to
the next seat after each season roll), so every seat makes the same number
of season rolls, within one, whatever X and the player count. While the
roll is due or its face pending, ``current_player`` is the holder; the
roll, and the use or decline of a personal face, do not spend a turn;
then the round's start player takes their turn. ``next_season_roll``
says when the next season roll is due and who makes it. The game ends after the preset's round
count: the state after the last turn has ``round == rounds + 1``.

End conditions (#163, opt-in, ``Preset.end_condition``): when a turn ends
(``_next_turn``) and the preset's trigger holds (the bag and the market are
empty, a player has planted all their vineyard markers, or a player's
total reaches the target), ``GameState.end_triggered`` records the round.
With ``Preset.finish_round`` the round is played out and the game ends
after it; without, the game ends at once, after that turn. A game whose
trigger never fires ends after ``Preset.round_cap`` rounds.

Combined end (#181, ``Preset.end_conditions``): the first trigger to hold
when a turn ends (in the preset's order, ``fired_trigger``) ends the game,
as above; ``SUPPLY_EMPTY`` fires once the shared vineyard supply is empty
and ``DEAD_TURNS`` once every player's ``Player.dead_turns`` is at least
``DEAD_TURN_LIMIT``, and ``DEAD_TURNS`` always ends the game at once.
``GameState.end_trigger`` records the trigger that ended the game, or
``ROUNDS`` when a preset with triggers reaches its round cap. When a Rules
v3 turn ends, the player's ``dead_turns`` goes up by one after a lost
turn (``ActionsLeft.lost``, also counted in ``lost_turns``) and back to 0
after any other turn.

Under Rules v3 (vertex planting) a turn is the mandatory roll, the
face's use if one is pending, then the player's actions (one, two after a
good season, none after a drought) or a pass; the turn moves on once no
face is pending and ``GameState.actions_left`` has no action left, and
``actions_left`` goes back to None for the next player. There is no
season roll.

``act`` checks the turn and applies one action through
``acequias.turn.apply``; ``play_game`` asks bots for actions until the game
is over and logs every action (a die turn is two records); ``replay`` plays a log again. Dice and bots use
separate RNGs (``game_rngs``), so a game is identified by its setup
arguments, its seed, and its bot policies. This module draws no random
numbers itself. Standard library only.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from acequias.config import DEAD_TURN_LIMIT, EndCondition, PlantingRules
from acequias.config import preset as shipped_preset
from acequias.model import DieFace, GameState, SeasonRoll
from acequias.turn import Action, RollActionDie, apply, roll_face, supply_left

__all__ = [
    "Bot",
    "TurnRecord",
    "turn_order",
    "act",
    "game_over",
    "end_fired",
    "fired_trigger",
    "play_game",
    "replay",
    "game_rngs",
    "season_holder",
    "next_season_roll",
]

Bot = Callable[[GameState, str, random.Random], Action]
"""A bot policy: ``decide(state, player, rng)`` returns the action to take."""


@dataclass(frozen=True)
class TurnRecord:
    """One action of a game: the round it was in, who acted, and the action.

    ``face`` is the face rolled, for a ``RollActionDie`` logged by
    ``play_game`` (a season face included); ``None`` otherwise. ``replay`` ignores it (the dice rng
    rolls it again).
    """

    round: int
    player: str
    action: Action
    face: DieFace | None = None


def _round_count(state: GameState) -> int:
    """The game's last possible round, from its preset (the shipped one when ``state.preset`` is
    None): the round count, or the cap under an end condition (``Preset.round_cap``)."""
    _check_state(state)
    p = state.preset or shipped_preset(state.mode)
    return p.round_cap(len(state.players))


def turn_order(state: GameState, round: int) -> tuple[str, ...]:
    """The player ids in acting order for ``round``, 1 to the round count.

    Worked out from ``state.start_player`` and ``state.round``, so every
    state of the same game gives the same answer. Raises ``ValueError``
    for a round outside the game.
    """
    total = _round_count(state)
    if not isinstance(round, int) or isinstance(round, bool):
        raise TypeError(f"round must be an int, got {round!r}")
    if not 1 <= round <= total:
        raise ValueError(f"round must be 1 to {total}, got {round}")
    seats = _seat_order(state)
    first = (seats.index(state.start_player) + round - state.round) % len(seats)
    return seats[first:] + seats[:first]


def game_over(state: GameState) -> bool:
    """Whether the game is over: ``state.round`` is past the round count (the cap under an end
    condition), or the end condition fired (``GameState.end_triggered``) and, with
    ``Preset.finish_round``, its round is over; ``DEAD_TURNS`` (#181) ends it at once."""
    if state.round > _round_count(state):
        return True
    fired = state.end_triggered
    if fired is None:
        return False
    p = state.preset or shipped_preset(state.mode)
    if state.end_trigger is EndCondition.DEAD_TURNS:
        return True
    return not p.finish_round or state.round > fired


def end_fired(state: GameState) -> bool:
    """Whether one of the preset's end triggers (#163, #181) holds on ``state``; always False
    under the round count end. See ``fired_trigger``."""
    return fired_trigger(state) is not None


def fired_trigger(state: GameState) -> EndCondition | None:
    """The first of the preset's triggers (``Preset.triggers``) that holds on ``state``, or None.

    ``BAG_EMPTY``: the bag and the market are empty. ``VINEYARDS_OUT``: a player
    holds ``Preset.markers_for`` vineyards. ``SCORE_TARGET``: a player's total
    (``calculate_score``) is at least ``Preset.target_for``. ``SUPPLY_EMPTY``:
    the shared vineyard supply has no piece left. ``DEAD_TURNS``: every
    player's ``dead_turns`` is at least ``DEAD_TURN_LIMIT``.
    """
    p = state.preset or shipped_preset(state.mode)
    for end in p.triggers:
        if _holds(state, p, end):
            return end
    return None


def _holds(state: GameState, p, end: EndCondition) -> bool:
    players = len(state.players)
    if end is EndCondition.SUPPLY_EMPTY:
        left = supply_left(state)
        return left is not None and not any(n > 0 for n in left.values())
    if end is EndCondition.DEAD_TURNS:
        return all(pl.dead_turns >= DEAD_TURN_LIMIT for pl in state.players)
    if end is EndCondition.BAG_EMPTY:
        return not state.bag and not state.market
    if end is EndCondition.VINEYARDS_OUT:
        markers = p.markers_for(players)
        held = {}
        for v in state.board.planted:
            held[v.owner] = held.get(v.owner, 0) + 1
        return any(n >= markers for n in held.values())
    from acequias.scoring import calculate_score  # local: scoring is heavy and only needed here

    target = p.target_for(players)
    return any(s.total >= target for s in calculate_score(state).values())


def act(state: GameState, player: str, action: Action, rng: random.Random) -> GameState:
    """The state after ``player`` takes ``action`` on their turn; ``state`` is never changed.

    Raises ``ValueError`` when the game is over or it is not ``player``'s
    turn (both checked before ``apply``, so ``rng`` is untouched), and the
    ``ValueError`` from ``apply`` for an illegal action. After the last
    player of a round acts, the round goes up by one and the start player
    moves to the next seat, who acts first. While ``apply`` leaves a die
    face pending, the turn does not move: the same player acts again.
    After the season roll (or its face) the round's start player takes
    their turn. A new round that is a season round
    (``Preset.is_season_round``) starts with ``season_roll`` ``DUE`` and
    the season die's holder (``season_holder``) as ``current_player``.
    """
    if game_over(state):
        if state.end_triggered is not None:
            raise ValueError(f"the game is over: its end condition fired in round {state.end_triggered}")
        raise ValueError(f"the game is over: all {_round_count(state)} rounds have been played")
    if player != state.current_player:
        raise ValueError(f"it is {state.current_player}'s turn, not {player!r}'s")
    return _next_turn(state, apply(state, player, action, rng), player)


def _next_turn(state: GameState, after: GameState, player: str) -> GameState:
    """``after`` (``player``'s action on ``state``) with the turn moved on, if it ends one.

    The bots use this to plan a season face without rolling.
    """
    if after.pending_face is not None:
        return after
    p = state.preset or shipped_preset(state.mode)
    if p.planting is PlantingRules.VERTICES:  # Rules v3: the turn lasts until no action is left
        if after.actions_left is None or after.actions_left.actions > 0:
            return after
        after = replace(after, actions_left=None, players=_dead_counted(after, player))
    if after.end_triggered is None and end_fired(after):
        trigger = fired_trigger(after) or p.triggers[0]
        after = replace(after, end_triggered=state.round, end_trigger=trigger)
        if not p.finish_round or trigger is EndCondition.DEAD_TURNS:
            return after
    if state.season_roll is not None:  # the season roll is done: the start player's turn
        return replace(after, current_player=after.start_player)

    order = turn_order(state, state.round)
    position = order.index(player)
    if position + 1 < len(order):
        return replace(after, current_player=order[position + 1])
    seats = _seat_order(state)
    start = seats[(seats.index(state.start_player) + 1) % len(seats)]
    round = state.round + 1
    if after.end_triggered is None and p.triggers and round > _round_count(state):
        after = replace(after, end_trigger=EndCondition.ROUNDS)  # the round cap ends the game
    if round <= _round_count(state) and p.is_season_round(round):
        return replace(
            after, round=round, start_player=start,
            current_player=season_holder(state, round), season_roll=SeasonRoll.DUE,
        )
    return replace(after, round=round, start_player=start, current_player=start, season_roll=None)


def season_holder(state: GameState, round: int) -> str:
    """Who makes the season roll of season round ``round`` (``Preset.is_season_round``).

    The k-th season roll (round k * X, X the preset's ``season_roll_every``)
    is made by the seat k-1 places after the game's first start player, in
    seat order: the season die passes to the next seat after each season
    roll. Worked out from ``state.start_player`` and ``state.round``, like
    ``turn_order``, so every state of the same game gives the same answer.
    Raises ``ValueError`` for a round outside the game or not a season round.
    """
    turn_order(state, round)  # checks the round
    p = state.preset or shipped_preset(state.mode)
    if not p.is_season_round(round):
        raise ValueError(f"round {round} has no season roll")
    seats = _seat_order(state)
    first = seats.index(state.start_player) - (state.round - 1)
    k = round // p.season_roll_every
    return seats[(first + k - 1) % len(seats)]


def next_season_roll(state: GameState) -> tuple[int, str] | None:
    """The round of the next season roll and the player who holds the season die for it.

    While a season roll is due or its face pending, that is the current
    round and ``current_player``; otherwise the next season round after
    ``state.round``. ``None`` when the game has no season roll left.
    """
    if state.season_roll is not None:
        return state.round, state.current_player
    p = state.preset or shipped_preset(state.mode)
    every = p.season_roll_every
    if every is None:
        return None
    round = (state.round // every + 1) * every
    if round > _round_count(state):
        return None
    return round, season_holder(state, round)


def play_game(
    state: GameState,
    bots: Mapping[str, Bot],
    dice_rng: random.Random,
    bot_rng: random.Random,
) -> tuple[GameState, tuple[TurnRecord, ...]]:
    """Play from ``state`` to the end of the game; return the final state and the turn log.

    ``bots`` maps every player id to a ``decide(state, player, rng)``
    callable, which draws only from ``bot_rng``; bribe rolls draw only from
    ``dice_rng``. A missing or unknown id raises ``ValueError`` before any
    turn; a bot's illegal action raises the ``ValueError`` from ``apply``.
    """
    _check_bots(state, bots)
    log: list[TurnRecord] = []
    while not game_over(state):
        player = state.current_player
        action = bots[player](state, player, bot_rng)
        round = state.round
        face = _rolled_face(state, dice_rng) if isinstance(action, RollActionDie) else None
        state = act(state, player, action, dice_rng)
        log.append(TurnRecord(round, player, action, face))
    return state, tuple(log)


def replay(state: GameState, log: Iterable[TurnRecord], dice_rng: random.Random) -> GameState:
    """The state after playing every record of ``log`` from ``state`` with ``act``.

    Raises ``ValueError`` for a record whose round or player does not match
    the state when it is reached.
    """
    for i, record in enumerate(log):
        if not isinstance(record, TurnRecord):
            raise TypeError(f"log[{i}] must be a TurnRecord, got {record!r}")
        if record.round != state.round:
            raise ValueError(
                f"log[{i}] is for round {record.round}, but the game is in round {state.round}"
            )
        if record.player != state.current_player:
            raise ValueError(
                f"log[{i}] is a turn of {record.player!r}, but it is "
                f"{state.current_player}'s turn"
            )
        state = act(state, record.player, record.action, dice_rng)
    return state


def game_rngs(seed: int) -> tuple[random.Random, random.Random]:
    """The ``(dice_rng, bot_rng)`` pair for the game with ``seed``.

    Seeded from strings, which ``random`` hashes the same way in every
    process, so the two streams differ from each other and from the
    ``random.Random(seed)`` that ``new_game`` uses.
    """
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError(f"seed must be an int, got {seed!r}")
    return random.Random(f"dice:{seed}"), random.Random(f"bots:{seed}")


# --- Helpers -----------------------------------------------------------------


def _rolled_face(state: GameState, dice_rng: random.Random) -> DieFace:
    """The face a ``RollActionDie`` on ``state`` will roll with ``dice_rng``; ``dice_rng`` is untouched.

    The roll is the dice rng's first draw (``acequias.turn.roll_face``), so
    a copy of the rng rolls the same face; this also names a personal face
    that a season roll ignores (``Preset.season_roll_personal_faces`` off).
    """
    copy = random.Random()
    copy.setstate(dice_rng.getstate())
    return roll_face(state.preset or shipped_preset(state.mode), copy)


def _dead_counted(after: GameState, player: str):
    """``after``'s players with ``player``'s dead-turn counters updated at the end of their turn
    (#181): up by one after a lost turn, back to 0 after any other. Unchanged when nothing moves."""
    lost = after.actions_left is not None and after.actions_left.lost
    players = after.players
    for i, pl in enumerate(players):
        if pl.id != player:
            continue
        if lost:
            pl = replace(pl, dead_turns=pl.dead_turns + 1, lost_turns=pl.lost_turns + 1)
        elif pl.dead_turns:
            pl = replace(pl, dead_turns=0)
        else:
            return players
        return players[:i] + (pl,) + players[i + 1:]
    return players


def _seat_order(state: GameState) -> tuple[str, ...]:
    return tuple(p.id for p in sorted(state.players, key=lambda p: p.seat))


def _check_bots(state: GameState, bots: Mapping[str, Bot]) -> None:
    if not isinstance(bots, Mapping):
        raise TypeError(f"bots must be a mapping of player id to bot, got {bots!r}")
    ids = {p.id for p in state.players}
    missing = sorted(ids - set(bots))
    if missing:
        raise ValueError(f"bots has no bot for players {missing}")
    unknown = sorted(map(repr, set(bots) - ids))
    if unknown:
        raise ValueError(f"bots names players not in the game: {', '.join(unknown)}")
    for player_id, bot in bots.items():
        if not callable(bot):
            raise TypeError(f"the bot for {player_id} must be callable, got {bot!r}")


def _check_state(state: object) -> None:
    if not isinstance(state, GameState):
        raise TypeError(f"state must be a GameState, got {state!r}")
