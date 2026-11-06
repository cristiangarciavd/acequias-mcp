"""Assembly instructions: how a person lays out a board's printed terrain hexes.

``assembly_instructions`` turns a ``Board`` into one step per tile, row by
row from north to south and west to east within a row. Rows and positions
are numbered from 1 for people; each step also keeps the axial ``Hex`` for
programs. Only tiles matter: canals, floodgates, and claims are ignored.

Rows are staggered (the river steps south-east or south-west from row to
row, see ``acequias.board``), so hex 1 of every row after the first also
says which hex of the row above it touches.

This module depends on nothing in ``acequias`` except ``acequias.model`` and
``acequias.hex``.
"""

from __future__ import annotations

from dataclasses import dataclass

from acequias.hex import Direction, Hex
from acequias.model import Board, Terrain, Tile, Varietal


@dataclass(frozen=True, slots=True)
class AssemblyStep:
    """One tile to place: where it goes, what it is, and the sentence to read."""

    row: int
    position: int
    hex: Hex
    terrain: Terrain
    varietal: Varietal | None
    text: str


def assembly_instructions(board: Board) -> list[AssemblyStep]:
    """The ordered steps to lay out ``board``'s tiles, one per tile.

    Raises ``ValueError`` naming the row if the board cannot be laid out
    row by row: its rows skip an ``r``, a row has a gap in ``q``, or hex 1
    of a row after row 1 touches no hex of the row above.
    """
    if not isinstance(board, Board):
        raise TypeError(f"board must be a Board, got {board!r}")

    by_r: dict[int, list[Tile]] = {}
    for tile in board.tiles:
        by_r.setdefault(tile.hex.r, []).append(tile)
    if not by_r:
        return []

    rs = sorted(by_r)
    first_r = rs[0]
    for row, r in enumerate(rs, start=1):
        if r != first_r + row - 1:
            raise ValueError(
                f"row {row} is at r={r}, but the row above is at r={rs[row - 2]}; "
                "rows must not skip an r"
            )

    steps: list[AssemblyStep] = []
    # Hex -> its position in its row, for the row above the current one.
    above: dict[Hex, int] = {}
    for row, r in enumerate(rs, start=1):
        tiles = sorted(by_r[r], key=lambda t: t.hex.q)
        for prev, tile in zip(tiles, tiles[1:]):
            if tile.hex.q != prev.hex.q + 1:
                raise ValueError(
                    f"row {row} (r={r}) has a gap between q={prev.hex.q} and q={tile.hex.q}"
                )

        current: dict[Hex, int] = {}
        for position, tile in enumerate(tiles, start=1):
            text = f"Row {row}, hex {position}: {_describe(tile)}"
            if position == 1 and row > 1:
                text += ", " + _anchor(tile.hex, row, above)
            steps.append(
                AssemblyStep(
                    row=row,
                    position=position,
                    hex=tile.hex,
                    terrain=tile.terrain,
                    varietal=tile.varietal,
                    text=text,
                )
            )
            current[tile.hex] = position
        above = current
    return steps


def _describe(tile: Tile) -> str:
    if tile.varietal is not None:
        return f"{tile.terrain.value}, {tile.varietal.display_name}"
    return tile.terrain.value


def _anchor(hex: Hex, row: int, above: dict[Hex, int]) -> str:
    """Where hex 1 of ``row`` sits against the row above it."""
    north_west = hex.neighbor(Direction.NW)
    if north_west in above:
        return f"south-east of row {row - 1}, hex {above[north_west]}"
    north_east = hex.neighbor(Direction.NE)
    if north_east in above:
        return f"south-west of row {row - 1}, hex {above[north_east]}"
    raise ValueError(
        f"row {row} (r={hex.r}): hex 1 at {hex} touches no hex of row {row - 1}"
    )
