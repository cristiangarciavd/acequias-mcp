"""The `simulate_game` tool: many bot games and their balance statistics.

The tool only checks input, builds `SimRules`, calls
`acequias.sim.simulate_game(rules, games, seed).to_json()`, and returns that
JSON unchanged. Statistics come only from `acequias.sim`, and every value
check from `SimRules`, `policy`, and `Preset`. `server.app` registers it.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from acequias.bots import POLICIES
from acequias.model import MAX_PLAYERS, MIN_PLAYERS
from acequias.sim import SimRules
from acequias.sim import simulate_game as run_simulation
from server.schemas import (
    ModeName,
    PresetJSON,
    PresetOverridesJSON,
    VarietalName,
    mode_from_json,
    overrides_from_json,
)
from server.tools.board import MAX_SEED, pick_seed

# The most games one call plays. It keeps one call well inside the client's
# timeout; #43 raises it (progress updates, parallel games). Planned as 1,000,
# but a 5-player Normal game of greedy bots takes about 2 s on the dev
# machine, so 1,000 games would take over 30 minutes; 10 games fit in 30 s.
MAX_GAMES = 10
# Planned as 100; it cannot be above MAX_GAMES.
DEFAULT_GAMES = min(100, MAX_GAMES)
DEFAULT_POLICY = "greedy"

# Built from `POLICIES` at import time, so a policy added there is listed here.
PolicyName = Literal[tuple(POLICIES)]  # type: ignore[valid-type]

ActionName = Literal["canal", "floodgate", "bribe", "pass"]
ScoreTermName = Literal["vineyards", "bodega", "rights_paid", "rights_collected", "debt", "total"]


class SpreadJSON(BaseModel):
    """A mean and its population standard deviation."""

    model_config = ConfigDict(extra="forbid")

    mean: float = Field(description="The mean.")
    stdev: float = Field(description="The population standard deviation.")


class SimResultJSON(BaseModel):
    """What `simulate_game` returns: `SimResult.to_json()` of `acequias.sim`, unchanged."""

    model_config = ConfigDict(extra="forbid")

    mode: ModeName = Field(description="The mode simulated.")
    players: int = Field(description="The player count P.")
    policies: list[str] = Field(description="The policy of each seat, seat 1 first.")
    n: int = Field(description="The number of games played.")
    seed: int = Field(description="The run seed; pass it again to get the same result.")
    preset: PresetJSON = Field(description="Every preset value used, after overrides.")
    win_rate_by_position: list[float] = Field(
        description=(
            "Entry j-1: win credit of the player in turn position j (position 1 starts "
            "round 1) / n. A shared win gives each winner 1/k. Adds up to 1."
        )
    )
    win_rate_by_seat: list[float] = Field(
        description="Entry s-1: win credit of the seat-s player / n. Adds up to 1."
    )
    win_rate_by_policy: dict[str, float] = Field(
        description="Policy name: win credit of the seats with that policy / n. Adds up to 1."
    )
    turn_order_advantage: float = Field(
        description="max over positions of |win rate - 1/P| * P; 0.10 means 10% off the fair share."
    )
    shared_win_rate: float = Field(description="Share of games with more than one winner.")
    score_terms: dict[ScoreTermName, SpreadJSON] = Field(
        description="Mean and stdev of each score term over all player-games."
    )
    mean_total_by_position: list[float] = Field(
        description="Entry j-1: mean total score of position-j players."
    )
    winning_score: SpreadJSON = Field(description="Mean and stdev of each game's highest total.")
    turns_per_game: float = Field(description="Mean number of turns per game (rounds * P).")
    actions_per_game: dict[ActionName, float] = Field(
        description="Mean number of each action per game; they add up to turns_per_game."
    )
    games_with_bribe: float = Field(description="Share of games with at least one bribe.")
    games_with_floodgate: float = Field(description="Share of games with at least one floodgate.")
    win_rate_bribers: float | None = Field(
        description="Mean win credit of player-games with a bribe; null if there are none."
    )
    win_rate_non_bribers: float | None = Field(
        description="Mean win credit of player-games without a bribe; null if there are none."
    )
    bodega_rate: float = Field(description="Share of player-games with a bodega bonus.")
    winner_varietal_rate: dict[VarietalName, float] = Field(
        description="Varietal: share of games where a winner watered a vineyard of it."
    )


def simulate_game(
    mode: Annotated[
        ModeName,
        Field(description='Game mode: "normal" (full game) or "flash" (short game).'),
    ],
    players: Annotated[
        int,
        Field(
            strict=True,
            ge=MIN_PLAYERS,
            le=MAX_PLAYERS,
            description=f"Number of players, {MIN_PLAYERS} to {MAX_PLAYERS}.",
        ),
    ],
    games: Annotated[
        int,
        Field(
            strict=True,
            ge=1,
            le=MAX_GAMES,
            description=f"Number of games to play, 1 to {MAX_GAMES}. Default {DEFAULT_GAMES}.",
        ),
    ] = DEFAULT_GAMES,
    seed: Annotated[
        Annotated[int, Field(strict=True, ge=0, le=MAX_SEED)] | None,
        Field(
            description=(
                "Optional run seed, 0 to 2^53 - 1. The same input and seed always give the "
                "same result. Omit it and the server picks one and returns it."
            ),
        ),
    ] = None,
    policies: Annotated[
        list[PolicyName] | None,
        Field(
            description=(
                "Optional bot policy per seat, seat 1 first; its length must equal players. "
                f'Default: "{DEFAULT_POLICY}" in every seat.'
            ),
        ),
    ] = None,
    overrides: Annotated[
        PresetOverridesJSON,
        Field(
            description=(
                "Optional preset values to replace (default: none), in the shape of the "
                "result's preset without mode, so a preset from one result can be passed back."
            ),
        ),
    ] = {},  # noqa: B006 - never mutated; overrides_from_json copies it
) -> SimResultJSON:
    """Simulate many Acequias games between bots and return balance statistics.

    Plays `games` complete games of one mode with the bot policies given
    (default all "greedy") and the mode's preset with any `overrides`, and
    returns win rates by turn position, seat, and policy, the turn-order
    advantage, score spreads, action counts, and the inputs used (including
    every preset value and the seed). The same input and seed always give the
    same result.
    """
    if seed is None:
        seed = pick_seed()
    if policies is None:
        policies = [DEFAULT_POLICY] * players
    rules = SimRules(
        mode=mode_from_json(mode),
        players=players,
        policies=tuple(policies),
        overrides=overrides_from_json(overrides),
    )
    return SimResultJSON.model_validate(run_simulation(rules, games, seed).to_json())
