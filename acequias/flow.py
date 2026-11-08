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
from acequias.model import Board, PlacedCanal

_OPPOSITE = {d: d.opposite() for d in Direction}


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

    links, sources, feeders = _graph(board)
    wet = _reach(sources, links, allowed=None)
    owner_of = {h: board.canal_at(h).owner for h in wet}
    result: dict[Hex, WaterPath] = {}
    for vineyard in sorted(feeders):
        ends = {h for h in feeders[vineyard] if h in wet}
        if not ends:
            continue
        path = _choose(board, vineyard, ends, sources, links, owner_of)
        canals = tuple(board.canal_at(h) for h in path)
        result[vineyard] = WaterPath(canals, frozenset(c.owner for c in canals))
    return MappingProxyType(result)


def _watered(board: Board) -> list[Hex]:
    """The vineyards ``water(board)`` maps, in hex order, without choosing their paths.

    Whether a vineyard is watered does not depend on who claimed it, so this
    is all that claiming needs.
    """
    links, sources, feeders = _graph(board)
    wet = _reach(sources, links, allowed=None)
    return [v for v in sorted(feeders) if any(h in wet for h in feeders[v])]


# --- Graph -------------------------------------------------------------------


def _graph(
    board: Board,
) -> tuple[dict[Hex, tuple[Hex, ...]], frozenset[Hex], dict[Hex, set[Hex]]]:
    """``(links, sources, feeders)`` of ``board``, in one pass over its canals.

    - ``links``: for each canal hex, the neighbouring canal hexes water can
      cross to (both open the shared edge and it has no floodgate)
    - ``sources``: canal hexes with an open, ungated edge facing a river hex
    - ``feeders``: for each vineyard hex, the canal hexes with an open,
      ungated edge facing it
    """
    statics = board._static()
    canal_at = board._canal_index.get
    gated: set[tuple[Hex, Direction]] = set()
    for gate in board.floodgates:
        gated.add((gate.hex, gate.direction))
        gated.add((gate.hex.neighbor(gate.direction), _OPPOSITE[gate.direction]))

    links: dict[Hex, tuple[Hex, ...]] = {}
    sources = []
    feeders: dict[Hex, set[Hex]] = {}
    for canal in board.canals:
        hex = canal.hex
        around = statics.neighbors[hex]
        river = statics.river_dirs[hex]
        vineyards = statics.vineyard_dirs[hex]
        out = []
        source = False
        for d in canal.edges:
            if gated and (hex, d) in gated:
                continue
            if d in river:
                source = True
            elif d in vineyards:
                feeders.setdefault(vineyards[d], set()).add(hex)
            else:
                target = around[d]
                other = canal_at(target)
                if other is not None and _OPPOSITE[d] in other.edges:
                    out.append(target)
        links[hex] = tuple(out)
        if source:
            sources.append(hex)
    return links, frozenset(sources), feeders


def _reach(
    starts: Iterable[Hex],
    links: Mapping[Hex, tuple[Hex, ...]],
    allowed: frozenset[Hex] | None,
) -> dict[Hex, int]:
    """BFS from ``starts`` over ``links``, within ``allowed`` (None: every canal).

    Returns each reached hex with its distance in canals, the starts at 1.
    The distances do not depend on the order of ``starts`` or of the links.
    """
    dist: dict[Hex, int] = {}
    queue: deque[Hex] = deque()
    for h in starts:
        if allowed is None or h in allowed:
            dist[h] = 1
            queue.append(h)
    while queue:
        h = queue.popleft()
        step = dist[h] + 1
        for n in links[h]:
            if n not in dist and (allowed is None or n in allowed):
                dist[n] = step
                queue.append(n)
    return dist


# --- Path choice -------------------------------------------------------------


def _choose(
    board: Board,
    vineyard: Hex,
    ends: set[Hex],
    sources: frozenset[Hex],
    links: Mapping[Hex, tuple[Hex, ...]],
    owner_of: Mapping[Hex, str],
) -> tuple[Hex, ...]:
    """The hex sequence of the cheapest path to ``vineyard`` (see module doc).

    First the shortest, then hex-smallest, path over every wet canal; say it
    has ``k`` rivals. No path has a smaller (length, hexes) key, so it is
    also the best path among those with ``k`` rivals, and it is the answer
    unless a path with fewer rivals exists. Those are looked for as before:
    rival subsets in increasing size below ``k``; the first size that gives
    a path is the fewest rivals possible, and among those subsets the
    shortest, then hex-smallest, path wins.
    """
    claimant = board.claimant(vineyard)
    overall = _best_path(sources, ends, links, frozenset(owner_of))
    if overall is None:
        raise AssertionError(f"{vineyard} is watered but no path was found")
    fewest = len({owner_of[h] for h in overall} - {claimant})
    if fewest == 0:
        return overall
    rivals = sorted({o for o in owner_of.values() if o != claimant})

    for size in range(fewest):
        best: tuple[Hex, ...] | None = None
        for subset in combinations(rivals, size):
            permitted = {claimant, *subset}
            allowed = frozenset(h for h, o in owner_of.items() if o in permitted)
            path = _best_path(sources, ends, links, allowed)
            if path is not None and (best is None or (len(path), path) < (len(best), best)):
                best = path
        if best is not None:
            return best
    return overall


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
