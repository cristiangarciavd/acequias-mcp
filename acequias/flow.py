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

Rules v3 (vertex planting) adds vineyards on vertices
(``Board.planted``). A vertex vineyard touches the canals on its (up to)
3 hexes; it is watered when any of them carries water, whatever edges
the canal opens, and its water takes the cheapest path, as above, to any
of those watered canals (``vertex_water``). A player may plant on a free
vertex that touches one of their own canals carrying water
(``can_plant``, ``plantable_spots``). Such a vertex always touches the
canal's own hex, so it is a planting spot; legality is worked out from
the canals alone, not from ``Board.spots``, the board's bounds, or its
stone and empty hexes, so it also fits a board without fixed bounds.
With ``three_canals`` (``Preset.vertex_needs_three_canals``, #160) the
vertex must also have a canal, any owner's, wet or dry, on each of its 3
hexes. ``vertex_thirds`` gives the split scoring's watered thirds
(``acequias.scoring``).

This module is pure: it reads ``acequias.model`` and ``acequias.hex``,
changes nothing, and has no randomness.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations
from types import MappingProxyType

from acequias.hex import Direction, Hex, Vertex
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
        path = _choose(vineyard, board.claimant(vineyard), ends, sources, links, owner_of)
        canals = tuple(board.canal_at(h) for h in path)
        result[vineyard] = WaterPath(canals, frozenset(c.owner for c in canals))
    return MappingProxyType(result)


def vertex_water(board: Board) -> Mapping[Vertex, WaterPath]:
    """Every watered planted vertex vineyard on ``board``, mapped to the path its water takes.

    The path ends at one of the watered canals the vertex touches; it is the
    cheapest for the vineyard's owner (fewest rivals, then fewest canals,
    then hex order). Dry vineyards are left out.
    """
    if not isinstance(board, Board):
        raise TypeError(f"vertex_water needs a Board, got {board!r}")
    if not board.planted:
        return MappingProxyType({})
    links, sources, _ = _graph(board)
    wet = _reach(sources, links, allowed=None)
    owner_of = {h: board.canal_at(h).owner for h in wet}
    result: dict[Vertex, WaterPath] = {}
    for vineyard in board.planted:
        ends = {h for h in vineyard.vertex.hexes if h in wet}
        if not ends:
            continue
        path = _choose(vineyard.vertex, vineyard.owner, ends, sources, links, owner_of)
        canals = tuple(board.canal_at(h) for h in path)
        result[vineyard.vertex] = WaterPath(canals, frozenset(c.owner for c in canals))
    return MappingProxyType(result)


def wet_canals(board: Board) -> frozenset[Hex]:
    """The hexes of every canal on ``board`` that carries water right now."""
    if not isinstance(board, Board):
        raise TypeError(f"wet_canals needs a Board, got {board!r}")
    links, sources, _ = _graph(board)
    return frozenset(_reach(sources, links, allowed=None))


def vertex_thirds(
    board: Board, wet: frozenset[Hex] | None = None, vertices: Iterable[Vertex] | None = None
) -> Mapping[Vertex, Mapping[str, int]]:
    """Each planted vertex's watered thirds by canal owner (Rules v3 split scoring, #160).

    A vertex has 3 hexes, one third each; a third is watered, and belongs to
    the canal's owner, when its hex holds a canal that carries water. A
    river or empty hex, or a dry canal, gives a third to nobody. Every
    planted vertex is a key, in ``Board.planted`` order; a vertex with no
    watered third maps to an empty mapping. ``wet`` is ``wet_canals(board)``
    when known. ``vertices`` gives other vertices to split instead, such as
    the bodegas' (``Board.bodegas``, #166).
    """
    if not isinstance(board, Board):
        raise TypeError(f"vertex_thirds needs a Board, got {board!r}")
    if wet is None:
        wet = wet_canals(board)
    canal_at = board._canal_index.get
    result: dict[Vertex, Mapping[str, int]] = {}
    if vertices is None:
        vertices = [v.vertex for v in board.planted]
    for vertex in vertices:
        thirds: dict[str, int] = {}
        for h in vertex.hexes:
            if h in wet:
                owner = canal_at(h).owner
                thirds[owner] = thirds.get(owner, 0) + 1
        result[vertex] = MappingProxyType(thirds)
    return MappingProxyType(result)


def plantable_spots(board: Board, player: str, three_canals: bool = False) -> tuple[Vertex, ...]:
    """The spots ``player`` may plant on now, in vertex order (Rules v3).

    A vertex is plantable when nothing is planted or built on it and it touches a
    canal of ``player``'s that carries water: the vertices of their wet
    canals, minus the planted ones. With ``three_canals`` each of its 3
    hexes must also hold a canal.
    """
    if not isinstance(board, Board):
        raise TypeError(f"plantable_spots needs a Board, got {board!r}")
    if not isinstance(player, str):
        raise TypeError(f"player must be a str, got {player!r}")
    own = [h for h in wet_canals(board) if board.canal_at(h).owner == player]
    found = {v for h in own for v in h.vertices() if not board.is_occupied(v)}
    if three_canals:
        canals = board._canal_index
        found = {v for v in found if all(h in canals for h in v.hexes)}
    return tuple(sorted(found))


def can_plant(board: Board, player: str, vertex: Vertex, three_canals: bool = False) -> bool:
    """Whether ``player`` may plant a vineyard on ``vertex`` now (see ``plantable_spots``)."""
    if not isinstance(vertex, Vertex):
        raise TypeError(f"vertex must be a Vertex, got {vertex!r}")
    if not isinstance(player, str):
        raise TypeError(f"player must be a str, got {player!r}")
    if not isinstance(board, Board):
        raise TypeError(f"can_plant needs a Board, got {board!r}")
    if board.is_occupied(vertex):
        return False
    if three_canals and not all(h in board._canal_index for h in vertex.hexes):
        return False
    wet = wet_canals(board)
    return any(
        h in wet and board.canal_at(h).owner == player for h in vertex.hexes
    )


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
    vineyard: Hex | Vertex,
    claimant: str | None,
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
