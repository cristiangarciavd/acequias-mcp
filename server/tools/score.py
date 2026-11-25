"""The `calculate_score` tool: every player's score on a board state, and the winners.

The tool only checks input, builds the `Board` and `GameState` with
`server.schemas`, calls `acequias.scoring.calculate_score` and `winners`,
and turns the result into JSON. Every check on where pieces may sit and who
owns them comes from the model; every number comes from the library.
`server.app` registers it on the server.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from acequias.config import preset as shipped_preset
from acequias.config import with_overrides
from acequias.model import MAX_PLAYERS, MIN_PLAYERS, Board, GameState
from acequias.scoring import calculate_score as score_state
from acequias.scoring import winners as winners_of
from server.schemas import (
    MODE_PLAYERS,
    CanalJSON,
    ClaimJSON,
    FloodgateJSON,
    HexJSON,
    ModeName,
    PlayerJSON,
    PresetOverridesJSON,
    ScoreJSON,
    canal_from_json,
    claim_from_json,
    floodgate_from_json,
    hexes_to_board,
    mode_from_json,
    mode_to_json,
    overrides_from_json,
    planting_from_json,
    players_from_json,
    score_to_json,
)


class ScoreResult(BaseModel):
    """What `calculate_score` returns."""

    model_config = ConfigDict(extra="forbid", strict=True)

    mode: ModeName = Field(description="Game mode the state was scored in.")
    scores: list[ScoreJSON] = Field(description="One score per player, in seat order.")
    winners: list[str] = Field(
        description=(
            "Winning player ids in seat order: highest total, then most watered "
            "vineyards; more than one only on a shared win."
        )
    )


def calculate_score(
    mode: Annotated[
        ModeName,
        Field(description='Game mode: "normal" or "flash"; sets the bodega bonus.'),
    ],
    hexes: Annotated[
        list[HexJSON],
        Field(description="The board hexes, in the shape generate_board returns them."),
    ],
    players: Annotated[
        list[PlayerJSON],
        Field(
            min_length=MIN_PLAYERS,
            max_length=MAX_PLAYERS,
            description=(
                f"{MIN_PLAYERS} to {MAX_PLAYERS} players in seat order (seats 1 to N; by mode: "
                f"{MODE_PLAYERS}), "
                "each with its id, bribe debt, and optional season and drought points (default 0)."
            ),
        ),
    ],
    canals: Annotated[
        list[CanalJSON],
        Field(description="Canals on the board, each on an empty hex; any order."),
    ] = [],  # Pydantic copies list defaults, and the tool never mutates them.
    floodgates: Annotated[
        list[FloodgateJSON],
        Field(description="Floodgates, each on a canal opening; any order."),
    ] = [],
    claims: Annotated[
        list[ClaimJSON],
        Field(
            description=(
                "Vineyard claims, at most one per vineyard; any order. Under roulette rules "
                "each gives the varietal planted there."
            )
        ),
    ] = [],
    overrides: Annotated[
        PresetOverridesJSON,
        Field(
            description=(
                "Optional preset values to replace (default: none, the mode's shipped "
                "preset), in the shape of simulate_game's preset without mode; e.g. "
                '{"varietal_rules": "roulette", "varietal_points": {...}} scores a '
                "roulette board."
            ),
        ),
    ] = {},  # noqa: B006 - never mutated; overrides_from_json copies it
) -> ScoreResult:
    """Score an Acequias board state: each player's points by term, and the winners.

    Each player scores vineyards + bodega - rights_paid + rights_collected -
    debt + season + seat_bonus - drought (the action die's good season gains and drought
    losses; drought never takes a total below 0; seat_bonus from the preset's seat_bonus,
    seat 1 being round 1's start player); every term is in points, and each rival on a vineyard's water path
    gets water_right_points (3 in the shipped presets). Every watered claimed
    vineyard is listed with the canal path its water takes and the rivals its
    claimant pays, so the water rights can be checked by hand. The state is scored as given, finished or not.
    """
    tiles = hexes_to_board(hexes).tiles
    board = Board(
        tiles=tiles,
        canals=tuple(canal_from_json(item) for item in canals),
        floodgates=tuple(floodgate_from_json(item) for item in floodgates),
        claims=tuple(claim_from_json(item) for item in claims),
        plantings=tuple(
            planting
            for planting in (planting_from_json(item) for item in claims)
            if planting is not None
        ),
    )
    game_mode = mode_from_json(mode)
    preset = with_overrides(shipped_preset(game_mode), **overrides_from_json(overrides))
    game_players = players_from_json(players)
    preset.check_players(len(game_players))
    first = game_players[0].id if game_players else ""
    # Scoring reads only the board, the players, the preset, and round 1's start
    # player (for the seat bonus). The fields the input does not carry get fixed
    # values: round 1, the first player (seat 1) as start and current player, and
    # an empty market and bag.
    state = GameState(
        board=board,
        players=game_players,
        mode=game_mode,
        round=1,
        start_player=first,
        current_player=first,
        market=(),
        bag=(),
        preset=preset,
    )
    scores = score_state(state)
    return ScoreResult.model_validate(
        {
            "mode": mode_to_json(state.mode),
            "scores": [score_to_json(score) for score in scores.values()],
            "winners": list(winners_of(scores)),
        }
    )
