"""The `generate_board` tool: a balanced board and its assembly instructions.

The tool only checks input, calls `acequias.board.generate_board` and
`acequias.assembly.assembly_instructions`, and turns the result into JSON
with `server.schemas`. `server.app` registers it on the server.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from acequias.assembly import assembly_instructions
from acequias.board import generate_board as build_board
from acequias.model import MAX_PLAYERS, MIN_PLAYERS
from server.schemas import (
    AssemblyStepJSON,
    HexJSON,
    ModeName,
    assembly_to_json,
    board_to_hexes,
    mode_from_json,
    mode_to_json,
)

# The largest integer a JSON client (an IEEE double) holds exactly.
MAX_SEED = 2**53 - 1
# A seed the server picks when the client gives none: 0 to 2^31 - 1.
MAX_PICKED_SEED = 2**31 - 1


class BoardResult(BaseModel):
    """What `generate_board` returns."""

    model_config = ConfigDict(extra="forbid", strict=True)

    players: int = Field(description="Number of players the board is for.")
    mode: ModeName = Field(description="Game mode.")
    seed: int = Field(description="The seed used; pass it again to get the same board.")
    hexes: list[HexJSON] = Field(
        description="One object per board hex, sorted by q, then r."
    )
    assembly: list[AssemblyStepJSON] = Field(
        description="Steps to lay out the printed hexes, row by row from north to south."
    )


def pick_seed() -> int:
    """A fresh seed from 0 to 2^31 - 1, the only randomness in the tool."""
    return secrets.randbelow(MAX_PICKED_SEED + 1)


def generate_board(
    players: Annotated[
        int,
        Field(
            strict=True,
            ge=MIN_PLAYERS,
            le=MAX_PLAYERS,
            description=f"Number of players, {MIN_PLAYERS} to {MAX_PLAYERS}.",
        ),
    ],
    mode: Annotated[
        ModeName,
        # A Literal only matches the exact strings, so it needs no strict flag.
        Field(description='Game mode: "normal" (full game) or "flash" (short game).'),
    ],
    seed: Annotated[
        Annotated[int, Field(strict=True, ge=0, le=MAX_SEED)] | None,
        Field(
            description=(
                "Optional seed, 0 to 2^53 - 1. The same players, mode, and seed always "
                "give the same board. Omit it and the server picks one and returns it."
            ),
        ),
    ] = None,
) -> BoardResult:
    """Generate a balanced Acequias board and its assembly instructions.

    Returns the players, mode, and seed used, the board hexes (terrain, and
    varietal on vineyards), and the steps to lay the printed hexes out on the
    table. The same players, mode, and seed always give the same board.
    """
    if seed is None:
        seed = pick_seed()
    game_mode = mode_from_json(mode)
    board = build_board(players, seed, game_mode)
    return BoardResult.model_validate(
        {
            "players": players,
            "mode": mode_to_json(game_mode),
            "seed": seed,
            "hexes": board_to_hexes(board),
            "assembly": assembly_to_json(assembly_instructions(board)),
        }
    )
