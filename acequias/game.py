"""The round loop: whose turn it is, the rotating start player, and the end of the game.

Rules come from ``README.md`` (Turn, Turn order). A turn is one action. In
every round each player acts once, in seat order (players sorted by
``Player.seat``, the lowest seat following the highest), starting from that
round's start player. The start player rotates to the next seat each round,
like Mendoza's *turnos de riego*. The game ends after the preset's round
count: the state after the last turn has ``round == rounds + 1``.

``act`` checks the turn and applies one action through
``acequias.turn.apply``; ``play_game`` asks bots for actions until the game
is over and logs every turn; ``replay`` plays a log again. Dice and bots use
separate RNGs (``game_rngs``), so a game is identified by its setup
arguments, its seed, and its bot policies. This module draws no random
numbers itself. Standard library only.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from acequias.config import preset as shipped_preset
from acequias.model import GameState
from acequias.turn import Action, apply

__all__ = [
    "Bot",
    "TurnRecord",
    "turn_order",
    "act",
    "game_over",
    "play_game",
    "replay",
    "game_rngs",
]

Bot = Callable[[GameState, str, random.Random], Action]
"""A bot policy: ``decide(state, player, rng)`` returns the action to take."""


@dataclass(frozen=True)
class TurnRecord:
    """One turn of a game: the round it was in, who acted, and the action."""

    round: int
    player: str
    action: Action


def _round_count(state: GameState) -> int:
    """The game's round count, from its preset (the shipped one when ``state.preset`` is None)."""
    _check_state(state)
    p = state.preset or shipped_preset(state.mode)
    return p.rounds_for(len(state.players))


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
    """Whether every round has been played: ``state.round`` is past the round count."""
    return state.round > _round_count(state)


def act(state: GameState, player: str, action: Action, rng: random.Random) -> GameState:
    """The state after ``player`` takes ``action`` on their turn; ``state`` is never changed.

    Raises ``ValueError`` when the game is over or it is not ``player``'s
    turn (both checked before ``apply``, so ``rng`` is untouched), and the
    ``ValueError`` from ``apply`` for an illegal action. After the last
    player of a round acts, the round goes up by one and the start player
    moves to the next seat, who acts first.
    """
    if game_over(state):
        raise ValueError(f"the game is over: all {_round_count(state)} rounds have been played")
    if player != state.current_player:
        raise ValueError(f"it is {state.current_player}'s turn, not {player!r}'s")
    after = apply(state, player, action, rng)

    order = turn_order(state, state.round)
    position = order.index(player)
    if position + 1 < len(order):
        return replace(after, current_player=order[position + 1])
    seats = _seat_order(state)
    start = seats[(seats.index(state.start_player) + 1) % len(seats)]
    return replace(after, round=state.round + 1, start_player=start, current_player=start)


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
        record = TurnRecord(state.round, player, action)
        state = act(state, player, action, dice_rng)
        log.append(record)
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
