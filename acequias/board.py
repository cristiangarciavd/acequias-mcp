"""The balanced board generator.

``generate_board`` lays out the river on the west edge, one river hex per
row, and fills each row eastward with non-river hexes. Vineyards go at the
preset's distance from the river, stones are scattered over the rest, and a
layout is kept only if enough vineyards can be reached through empty hexes.

Layout rules (``README.md``, Setup and Game modes):

- Rows run north (``r = 0``) to south. Each row is its river hex followed by
  an unbroken run of hexes to the east.
- Going one row south, the river hex steps either straight south-east
  (same ``q``) or south-west (``q - 1``), alternating, so the river is one
  chain and stays roughly vertical on the table.
- With that river, a hex ``k`` steps east of its row's river hex is exactly
  ``k`` from the nearest river hex, so vineyards are placed by row offset.

Every size, count, and distance comes from the preset (``acequias.config``).
Under fixed varietal rules the vineyards get the varietals of
``preset.varietal_points``, dealt evenly; under roulette rules they are
blank (no varietal), and are planted when claimed.
Under vertex planting (Rules v3, ``PlantingRules.VERTICES``) no vineyard
tiles are placed: the board's ``spots`` are every vertex that touches at
least one non-river tile (``planting_spots``).
Under the river strip board (Rules v3, ``BoardShape.RIVER_STRIP``) the
board is only the river (``river_strip``): no stones, no vineyards, and an
open table to the east; it does not depend on the seed.
All randomness comes from one ``random.Random(seed)``, and every choice is
made over lists in a fixed order, so the result never depends on hash order.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from fractions import Fraction

from acequias.config import BoardShape, PlantingRules, Preset, VarietalRules, _ceil_share
from acequias.config import preset as shipped_preset
from acequias.hex import Direction, Hex, Vertex
from acequias.model import Board, Mode, RiverStrip, Terrain, Tile, Varietal

# How many layouts the generator tries before it gives up on a preset.
MAX_ATTEMPTS = 200

RIVER_BEND = Fraction(1)
"""How far east, in hex widths, the river strip's two ends sit from its
middle: a slight inward curve (toward the table), the same for every
player count, so a longer strip is flatter (owner, #150)."""


def generate_board(
    players: int, seed: int, mode: Mode, *, preset: Preset | None = None
) -> Board:
    """A deterministic, balanced board for ``players`` players in ``mode``.

    ``preset`` replaces the shipped preset for ``mode`` (for the
    simulation); its mode must be ``mode``. The same arguments always give
    an equal board. Raises ``ValueError`` if the preset cannot be met, or
    if ``players`` is not one of its ``player_counts`` (Flash: 2 or 3).
    """
    _check_int("players", players)
    _check_int("seed", seed)
    if not isinstance(mode, Mode):
        raise TypeError(f"mode must be a Mode, got {mode!r}")
    if preset is None:
        preset = shipped_preset(mode)
    elif not isinstance(preset, Preset):
        raise TypeError(f"preset must be a Preset, got {preset!r}")
    preset.check_players(players)
    if preset.mode is not mode:
        raise ValueError(
            f"preset is for mode {preset.mode.name}, but mode is {mode.name}"
        )

    hexes = players * preset.hexes_per_player
    vineyards = players * preset.vineyard_tiles_per_player
    stones = _ceil_share(preset.stone_share, hexes)
    low, high = preset.vineyard_distance
    lengths = _even_lengths(hexes, high)
    candidates = sum(max(0, min(n, high) - low + 1) for n in lengths)
    vertices = preset.planting is PlantingRules.VERTICES
    if not vertices and candidates < vineyards:
        raise ValueError(
            f"cannot place {vineyards} vineyards (vineyards_per_player="
            f"{preset.vineyards_per_player}) at vineyard_distance {preset.vineyard_distance} "
            f"on {hexes} hexes (hexes_per_player={preset.hexes_per_player}); "
            f"only {candidates} hexes are at that distance from the river"
        )

    if preset.board_shape is BoardShape.RIVER_STRIP:
        strip = river_strip(players, preset.river_hexes_per_segment)
        return Board(tiles=tuple(Tile(h, Terrain.RIVER) for h in strip.river), strip=strip)

    rng = random.Random(seed)
    for _ in range(MAX_ATTEMPTS):
        tiles = _layout(rng, players, hexes, vineyards, stones, preset)
        if tiles is not None:
            if vertices:
                return Board(tiles=tiles, spots=planting_spots(tiles))
            return Board(tiles=tiles)
    raise ValueError(
        f"no layout in {MAX_ATTEMPTS} tries lets {players} vineyards be reached: "
        f"hexes_per_player={preset.hexes_per_player}, "
        f"vineyards_per_player={preset.vineyards_per_player}, "
        f"stone_share={preset.stone_share}, vineyard_distance={preset.vineyard_distance}"
    )


def river_strip(players: int, hexes_per_segment: int) -> RiverStrip:
    """The river strip for ``players`` players: one segment for 2, one more per extra player.

    Each segment has ``hexes_per_segment`` river hexes, one per row from
    row 0 southward. The river bends slightly inward: its column follows a
    parabola whose ends are ``RIVER_BEND`` hex widths east of its middle,
    so the bend flattens as the strip gets longer. Each row the river steps
    half a hex east or west (south-east or south-west), whichever lands
    nearer the curve (west on a tie), so it stays one chain of hexes and
    its east side keeps the hex outline. Deterministic: no seed.
    """
    _check_int("players", players)
    _check_int("hexes_per_segment", hexes_per_segment)
    if players < 2:
        raise ValueError(f"players must be at least 2, got {players}")
    if hexes_per_segment < 1:
        raise ValueError(f"hexes_per_segment must be at least 1, got {hexes_per_segment}")
    rows = (players - 1) * hexes_per_segment
    middle = Fraction(rows - 1, 2)

    def curve(r: int) -> Fraction:
        # x of the row's river hex, in hex widths (x = q + r / 2).
        return RIVER_BEND * ((r - middle) / middle) ** 2 if middle else Fraction(0)

    half = Fraction(1, 2)
    x = Fraction(round(curve(0)))
    river = [Hex(int(x), 0)]
    for r in range(1, rows):
        east, west = x + half, x - half
        x = east if abs(east - curve(r)) < abs(west - curve(r)) else west
        river.append(Hex(int(x - Fraction(r, 2)), r))
    segments = tuple(
        tuple(river[i : i + hexes_per_segment]) for i in range(0, rows, hexes_per_segment)
    )
    return RiverStrip(segments)


def planting_spots(tiles: Sequence[Tile]) -> tuple[Vertex, ...]:
    """Every vertex of ``tiles`` that touches at least one non-river tile, in vertex order.

    These are a Rules v3 board's planting spots; one vineyard fits on each.
    """
    return tuple(
        sorted({v for t in tiles if t.terrain is not Terrain.RIVER for v in t.hex.vertices()})
    )


def reachable_vineyards(board: Board) -> list[Hex]:
    """The vineyards that a chain of empty hexes links to the river, in hex order.

    A vineyard is reachable when some chain of neighbouring empty hexes
    starts next to a river hex and ends next to the vineyard.
    """
    return [Hex(q, r) for q, r in _reachable(board.tiles)]


def _reachable(tiles: Sequence[Tile]) -> list[tuple[int, int]]:
    """``reachable_vineyards`` on plain ``(q, r)`` pairs, which is much faster
    than building ``Hex`` neighbours."""
    cells = {(t.hex.q, t.hex.r): t.terrain for t in tiles}

    def around(cell: tuple[int, int]) -> list[tuple[int, int]]:
        return [(cell[0] + dq, cell[1] + dr) for dq, dr in _OFFSETS]

    start = [
        c
        for c in sorted(cells)
        if cells[c] is Terrain.EMPTY and any(cells.get(n) is Terrain.RIVER for n in around(c))
    ]
    seen = set(start)
    stack = list(start)
    while stack:
        for n in around(stack.pop()):
            if n not in seen and cells.get(n) is Terrain.EMPTY:
                seen.add(n)
                stack.append(n)
    return [
        c
        for c in sorted(cells)
        if cells[c] is Terrain.VINEYARD and any(n in seen for n in around(c))
    ]


_OFFSETS = tuple(d.value for d in Direction)


# --- Layout ----------------------------------------------------------------


def _layout(
    rng: random.Random,
    players: int,
    hexes: int,
    vineyards: int,
    stones: int,
    preset: Preset,
) -> list[Tile] | None:
    """One random layout, or None if too few vineyards are reachable."""
    low, high = preset.vineyard_distance
    lengths = _jitter(rng, _even_lengths(hexes, high), high)
    rows = _rows(rng, lengths)

    # Vineyards: round-robin over the rows in a random order, so they spread
    # across the board; each row takes a random free offset in range.
    open_offsets = [list(range(low, min(len(row), high) + 1)) for row in rows]
    order = list(range(len(rows)))
    rng.shuffle(order)
    vineyard_hexes: list[Hex] = []
    while len(vineyard_hexes) < vineyards:
        if not any(open_offsets):
            return None
        for i in order:
            if len(vineyard_hexes) == vineyards:
                break
            if open_offsets[i]:
                offset = open_offsets[i].pop(rng.randrange(len(open_offsets[i])))
                vineyard_hexes.append(rows[i][offset - 1])

    taken = set(vineyard_hexes)
    rest = [h for row in rows for h in row if h not in taken]
    stone_hexes = rng.sample(rest, stones)

    grapes: list[Varietal | None]
    if preset.varietal_rules is VarietalRules.FIXED:
        # Deal the varietals in play as evenly as possible, in random order.
        varietals = list(preset.varietal_points)
        rng.shuffle(varietals)
        grapes = [varietals[i % len(varietals)] for i in range(vineyards)]
        rng.shuffle(grapes)
    else:
        # Roulette rules: blank plots, planted when claimed (acequias.turn).
        grapes = [None] * vineyards

    stone_set = set(stone_hexes)
    tiles = [Tile(river, Terrain.RIVER) for river in _river(rows)]
    tiles += [Tile(h, Terrain.VINEYARD, g) for h, g in zip(vineyard_hexes, grapes)]
    tiles += [Tile(h, Terrain.STONE if h in stone_set else Terrain.EMPTY) for h in rest]
    if preset.planting is PlantingRules.HEXES and len(_reachable(tiles)) < players:
        return None
    return tiles


def _even_lengths(hexes: int, high: int) -> list[int]:
    """Row lengths about ``high + 1`` each, as even as possible, summing to ``hexes``."""
    count = max(1, hexes // (high + 1))
    base, extra = divmod(hexes, count)
    return [base + 1 if i < extra else base for i in range(count)]


def _jitter(rng: random.Random, lengths: list[int], high: int) -> list[int]:
    """Move single hexes between rows at random, keeping every row at least
    ``high`` long (or as long as it already is, if shorter), so the edge of
    the board is ragged but every row still reaches the far vineyard distance.
    """
    lengths = list(lengths)
    floor = min(high, min(lengths))
    for _ in range(len(lengths)):
        i = rng.randrange(len(lengths))
        j = rng.randrange(len(lengths))
        if i != j and lengths[i] - 1 >= floor:
            lengths[i] -= 1
            lengths[j] += 1
    return lengths


def _rows(rng: random.Random, lengths: Sequence[int]) -> list[list[Hex]]:
    """The non-river hexes of each row, west to east.

    Row ``r``'s river hex sits just west of its first hex. Going one row
    south, the river keeps its ``q`` or moves to ``q - 1``, alternately,
    starting on a random phase.
    """
    phase = rng.randrange(2)
    rows = []
    q = 0
    for r, length in enumerate(lengths):
        if r > 0 and (r + phase) % 2 == 0:
            q -= 1
        rows.append([Hex(q + k, r) for k in range(1, length + 1)])
    return rows


def _river(rows: Sequence[Sequence[Hex]]) -> list[Hex]:
    """The river hex just west of each row."""
    return [Hex(row[0].q - 1, row[0].r) for row in rows]


def _check_int(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an int, got {value!r}")
