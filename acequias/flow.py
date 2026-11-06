"""Water reach: which vineyards are watered, and the path the water takes.

Rules come from ``README.md`` (Water flow, Floodgate, Water rights):

- Water enters a canal through an open edge facing a river hex.
- It crosses between two neighbouring canals only where both open the
  shared edge, and inside a piece it reaches every open edge.
- A vineyard is watered when a canal carrying water opens an edge facing
  it. Vineyards are end points: water does not pass through them.
- Water never crosses an edge with a floodgate, in either direction.

When a vineyard can be reached by more than one path, the water takes the
cheapest one for the vineyard's claimant: fewest distinct rival owners,
then fewest canals, then the smallest hex sequence (river end first,
compared hex by hex in ``Hex`` order). On an unclaimed vineyard every
owner is a rival.

This module is pure: it reads ``acequias.model`` and ``acequias.hex``,
changes nothing, and has no randomness.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations
from types import MappingProxyType

from acequias.hex import Direction, Hex
from acequias.model import Board, PlacedCanal, Terrain


@dataclass(frozen=True, slots=True)
class WaterPath:
    """The path water takes to one vineyard.

    ``canals`` runs from the river end to the vineyard end, each canal once.
    ``owners`` holds every owner id on those canals, the claimant's own
    included.
    """

    canals: tuple[PlacedCanal, ...]
    owners: frozenset[str]


def water(board: Board) -> Mapping[Hex, WaterPath]:
    """Every watered vineyard on ``board``, mapped to the path its water takes.

    Claimed and unclaimed vineyards are both included; dry ones are not.
    """
    if not isinstance(board, Board):
        raise TypeError(f"water needs a Board, got {board!r}")

    links = _links(board)
    sources = _sources(board)
    feeders = _feeders(board)

    wet = _reach(sources, links, allowed=None)
    result: dict[Hex, WaterPath] = {}
    for vineyard in sorted(feeders):
        ends = {h for h in feeders[vineyard] if h in wet}
        if not ends:
            continue
        path = _choose(board, vineyard, ends, sources, links, wet)
        canals = tuple(board.canal_at(h) for h in path)
        result[vineyard] = WaterPath(canals, frozenset(c.owner for c in canals))
    return MappingProxyType(result)


# --- Graph -------------------------------------------------------------------


def _open_edges(board: Board, canal: PlacedCanal) -> Iterable[Direction]:
    """The canal's open edges that have no floodgate, in ``Direction`` order."""
    for d in Direction:
        if d in canal.edges and not board.has_floodgate(canal.hex, d):
            yield d


def _links(board: Board) -> dict[Hex, tuple[Hex, ...]]:
    """For each canal hex, the neighbouring canal hexes water can cross to."""
    links: dict[Hex, tuple[Hex, ...]] = {}
    for canal in board.canals:
        out = []
        for d in _open_edges(board, canal):
            other = board.canal_at(canal.hex.neighbor(d))
            if other is not None and d.opposite() in other.edges:
                out.append(other.hex)
        links[canal.hex] = tuple(sorted(out))
    return links


def _sources(board: Board) -> frozenset[Hex]:
    """Canal hexes with an open, ungated edge facing a river hex."""
    return frozenset(
        canal.hex
        for canal in board.canals
        if any(_terrain(board, canal.hex.neighbor(d)) is Terrain.RIVER
               for d in _open_edges(board, canal))
    )


def _feeders(board: Board) -> dict[Hex, set[Hex]]:
    """For each vineyard hex, the canal hexes with an open, ungated edge facing it."""
    feeders: dict[Hex, set[Hex]] = {}
    for canal in board.canals:
        for d in _open_edges(board, canal):
            target = canal.hex.neighbor(d)
            if _terrain(board, target) is Terrain.VINEYARD:
                feeders.setdefault(target, set()).add(canal.hex)
    return feeders


def _terrain(board: Board, hex: Hex) -> Terrain | None:
    tile = board.tile_at(hex)
    return None if tile is None else tile.terrain


def _reach(
    starts: Iterable[Hex],
    links: Mapping[Hex, tuple[Hex, ...]],
    allowed: frozenset[Hex] | None,
) -> dict[Hex, int]:
    """BFS from ``starts`` over ``links``, within ``allowed`` (None: every canal).

    Returns each reached hex with its distance in canals, the starts at 1.
    """
    dist: dict[Hex, int] = {}
    queue: deque[Hex] = deque()
    for h in sorted(starts):
        if allowed is None or h in allowed:
            dist[h] = 1
            queue.append(h)
    while queue:
        h = queue.popleft()
        for n in links[h]:
            if n not in dist and (allowed is None or n in allowed):
                dist[n] = dist[h] + 1
                queue.append(n)
    return dist


# --- Path choice -------------------------------------------------------------


def _choose(
    board: Board,
    vineyard: Hex,
    ends: set[Hex],
    sources: frozenset[Hex],
    links: Mapping[Hex, tuple[Hex, ...]],
    wet: Mapping[Hex, int],
) -> tuple[Hex, ...]:
    """The hex sequence of the cheapest path to ``vineyard`` (see module doc).

    Rival subsets are tried in increasing size; the first size that gives a
    path is the fewest rivals possible, and among those subsets the
    shortest, then hex-smallest, path wins.
    """
    claimant = board.claimant(vineyard)
    owner_of = {h: board.canal_at(h).owner for h in wet}
    rivals = sorted({o for o in owner_of.values() if o != claimant})

    for size in range(len(rivals) + 1):
        best: tuple[Hex, ...] | None = None
        for subset in combinations(rivals, size):
            permitted = {claimant, *subset}
            allowed = frozenset(h for h, o in owner_of.items() if o in permitted)
            path = _best_path(sources, ends, links, allowed)
            if path is not None and (best is None or (len(path), path) < (len(best), best)):
                best = path
        if best is not None:
            return best
    raise AssertionError(f"{vineyard} is watered but no path was found")


def _best_path(
    sources: frozenset[Hex],
    ends: set[Hex],
    links: Mapping[Hex, tuple[Hex, ...]],
    allowed: frozenset[Hex],
) -> tuple[Hex, ...] | None:
    """The shortest, then hex-smallest, path from a source to an end within ``allowed``."""
    # Distance from each hex to the vineyard end, so the path can be walked
    # greedily from the river end, always taking the smallest next hex.
    to_end = _reach(ends, links, allowed)
    starts = [h for h in sources if h in to_end]
    if not starts:
        return None
    length = min(to_end[h] for h in starts)
    current = min(h for h in starts if to_end[h] == length)
    path = [current]
    while to_end[current] > 1:
        current = min(n for n in links[current] if to_end.get(n) == to_end[current] - 1)
        path.append(current)
    return tuple(path)
