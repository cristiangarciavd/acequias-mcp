"""Final scoring: each player's score by term, and the winners.

Rules come from ``README.md`` (End and scoring, Water rights, Bodega bonus).
Each player scores

    vineyard values + bodega bonus - water rights paid
    + water rights collected - bribe debt + season + seat bonus - drought

``season`` is ``Player.season``, the action die's good season gains.
``drought`` is ``Player.drought``, its drought losses, clamped so a drought
never takes a total below 0: a player whose total before the drought is
0 or less loses nothing, one with fewer points than the losses ends at 0.

Only watered claimed vineyards count. Watering and the path the water takes
come from ``acequias.flow.water``; a vineyard's varietal from
``Board.varietal_at`` (its tile, or what the roulette planted there); the
varietal points and the bodega bonus from the game's ``Preset`` in
``acequias.config``.

For each watered claimed vineyard, the claimant pays
``preset.water_right_points`` (1 in the shipped presets) to each distinct
other player who owns a canal on its path, and each of them collects the
same. Unclaimed vineyards score nothing and cause no rights.

The bodega term is ``preset.bodega_points`` times ``Score.bodegas``: 1 or
0 (``bodega_varietals`` distinct watered varietals or not), or, with
``preset.multiple_bodegas``, the largest number of disjoint groups of
``bodega_varietals`` watered vineyards, each of distinct varietals
(``bodega_count``).

The seat bonus is ``preset.seat_bonus[P][k]`` for the player ``k`` seats
after round 1's start player in a ``P``-player game (0 when the preset
gives none for ``P``); round 1's start player is worked out from
``state.start_player`` and ``state.round``, like ``acequias.game.turn_order``.
The drought clamp counts it like any other term.

Vertex vineyards (Rules v3, ``Board.planted``) are scored split (#160):
a vineyard's value is split in thirds among the 3 hexes of its vertex,
and each watered third (``acequias.flow.vertex_thirds``: a canal that
carries water, after floodgates) scores for that canal's owner, whoever
planted the vineyard. A player with ``k`` watered thirds of a vineyard
worth ``V`` scores ``V * k // 3`` (exact for the Rules v3 values,
``acequias.config.V3_POINTS``; other values round each share down). A
third on a river or empty hex, or on a dry canal, scores for nobody.
Vertex vineyards cause no water rights. A player's bodegas count the
varietals of every vineyard with at least one of their watered thirds,
whoever planted it, and so does ``watered`` (the tie-break). Their
``WateredVineyard`` has ``vertex`` set and no ``hex``, and they follow the
hex vineyards in ``Board.planted`` order.

Rules v3 scoring options (#166). With ``preset.varietal_bodega`` off the
bodega term is 0. ``blend`` is the blend (*corte*) bonus: a player holds
a varietal when they have a watered third of a vineyard of it (the
vineyards ``watered_vineyards`` lists), and ``blend_points`` scores the
preset's ``blends`` under its ``blend_rule``: each held blend once, or
the best set of distinct blends that uses no vineyard twice. ``buildings``
is the bodega buildings' points (``Board.bodegas``): each is worth
``preset.bodega_building_points``, split in thirds like a vertex
vineyard; it has no varietal, so it counts for no bodega, blend, or
``watered``. ``total`` adds ``blend + buildings``.

This module is pure: it reads a ``GameState``, changes nothing, and has no
randomness.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from acequias.config import Blend, BlendRule, Preset, preset as preset_for
from acequias.flow import WaterPath, vertex_thirds, water, wet_canals
from acequias.hex import Hex, Vertex
from acequias.model import GameState, Varietal


@dataclass(frozen=True, slots=True)
class WateredVineyard:
    """One watered claimed vineyard of a player.

    ``pays`` holds the rivals the claimant pays ``water_right_points``
    each, once per rival: the path's owners minus the claimant, in seat
    order. ``hex`` is the vineyard's hex, or None for a vertex vineyard
    (Rules v3), whose spot is ``vertex``.

    A vertex vineyard is listed for every player with a watered third of
    it (split scoring, #160): ``planter`` is who planted it, ``thirds``
    the player's watered thirds (1 to 3), ``points`` what they score from
    it, and ``path`` holds the player's watered canals on its vertex, one
    per third, in hex order; ``pays`` is empty. For a hex vineyard
    ``planter`` is None and ``thirds`` and ``points`` are 0 (it scores its
    varietal's points).
    """

    hex: Hex | None
    varietal: Varietal
    path: WaterPath
    pays: tuple[str, ...]
    vertex: Vertex | None = None
    planter: str | None = None
    thirds: int = 0
    points: int = 0


@dataclass(frozen=True, slots=True)
class WateredBodega:
    """A bodega building (#166) with at least one of a player's watered thirds.

    ``builder`` built it, ``thirds`` are the player's watered thirds (1 to
    3), and ``points`` what they score from it.
    """

    vertex: Vertex
    builder: str
    thirds: int
    points: int


@dataclass(frozen=True, slots=True)
class Score:
    """A player's final score, by term.

    ``total == vineyards + bodega + blend + buildings - rights_paid
    + rights_collected - debt + season + seat_bonus - drought``, where ``drought`` is the drought loss actually
    taken (clamped so a drought never takes the total below 0).
    Every term is in points: ``rights_paid`` and ``rights_collected`` are
    the rival-vineyard pairs times the preset's ``water_right_points``.
    ``watered`` is the number of the player's claimed vineyards that are
    watered (the tie-break), and ``watered_vineyards`` lists them in hex
    order. ``bodegas`` is the number of bodega bonuses earned, so
    ``bodega == bodegas * bodega_points``. ``seat_bonus`` is the
    preset's seat bonus for the player's round 1 position. ``blend`` is
    the blend bonus and ``blends`` the names (``Blend.name``) of the blends
    scored, in the preset's order; ``buildings`` the bodega buildings'
    points and ``watered_bodegas`` the buildings they come from, in vertex
    order (#166). The total adds ``blend + buildings``.
    """

    player: str
    seat: int
    vineyards: int
    bodega: int
    rights_paid: int
    rights_collected: int
    debt: int
    total: int
    watered: int
    watered_vineyards: tuple[WateredVineyard, ...]
    season: int = 0
    drought: int = 0
    bodegas: int = 0
    seat_bonus: int = 0
    blend: int = 0
    blends: tuple[str, ...] = ()
    buildings: int = 0
    watered_bodegas: tuple[WateredBodega, ...] = ()


def blend_points(
    varietals: Iterable[Varietal], blends: Sequence[Blend], rule: BlendRule
) -> tuple[int, tuple[Blend, ...]]:
    """The blend bonus of a player's held vineyards, and the blends that score, in table order.

    ``varietals`` holds one item per vineyard the player holds (repeats
    allowed). ``EACH_ONCE``: every blend whose varietals are all held
    scores once. ``DISJOINT``: the set of distinct blends with the most
    points such that no vineyard counts twice (each varietal is used by at
    most as many chosen blends as the player holds vineyards of it); on a
    tie, the set that comes first when the blends are taken in table order.
    """
    counts = Counter(varietals)
    key = tuple(sorted((v.name, n) for v, n in counts.items()))
    return _blend_points(key, tuple(blends), rule)


_BLEND_CACHE: dict[tuple, tuple[int, tuple[Blend, ...]]] = {}
"""``blend_points`` by held counts, blend table and rule: the bots score the same holdings often."""


def _blend_points(
    counts: tuple[tuple[str, int], ...], blends: tuple[Blend, ...], rule: BlendRule
) -> tuple[int, tuple[Blend, ...]]:
    key = (counts, blends, rule)
    found = _BLEND_CACHE.get(key)
    if found is None:
        if len(_BLEND_CACHE) > 8192:
            _BLEND_CACHE.clear()
        found = _BLEND_CACHE[key] = _search_blends(counts, blends, rule)
    return found


def _search_blends(
    counts: tuple[tuple[str, int], ...], blends: tuple[Blend, ...], rule: BlendRule
) -> tuple[int, tuple[Blend, ...]]:
    held = {Varietal[name]: n for name, n in counts}
    usable = [b for b in blends if all(held.get(v, 0) > 0 for v in b.varietals)]
    if rule is BlendRule.EACH_ONCE:
        return sum(b.points for b in usable), tuple(usable)
    best: tuple[int, tuple[Blend, ...]] = (0, ())

    def search(i: int, left: dict[Varietal, int], chosen: list[Blend], points: int) -> None:
        nonlocal best
        if points > best[0]:
            best = (points, tuple(chosen))
        if i == len(usable):
            return
        blend = usable[i]
        if all(left[v] > 0 for v in blend.varietals):
            for v in blend.varietals:
                left[v] -= 1
            chosen.append(blend)
            search(i + 1, left, chosen, points + blend.points)
            chosen.pop()
            for v in blend.varietals:
                left[v] += 1
        search(i + 1, left, chosen, points)

    search(0, dict(held), [], 0)
    return best


def bodega_count(varietals: Iterable[Varietal], size: int) -> int:
    """The largest number of disjoint groups of ``size`` items of ``varietals``,
    each group of ``size`` distinct varietals.

    ``varietals`` holds one item per watered vineyard (repeats allowed).
    ``t`` groups fit exactly when ``sum(min(count, t)) >= size * t`` over
    the varietal counts: each varietal gives at most one vineyard per
    group, and any ``size * t`` vineyards that respect that can be dealt
    into ``t`` groups round-robin. The count is the largest such ``t``.
    """
    if size < 1:
        raise ValueError(f"size must be at least 1, got {size}")
    counts = Counter(varietals).values()
    groups = sum(counts) // size
    while groups > 0 and sum(min(c, groups) for c in counts) < size * groups:
        groups -= 1
    return groups


def split_points(value: int, thirds: int) -> int:
    """What ``thirds`` watered thirds (0 to 3) of a vineyard worth ``value`` score: ``value * thirds // 3``."""
    return value * thirds // 3


def calculate_score(state: GameState, preset: Preset | None = None) -> Mapping[str, Score]:
    """Every player's score on ``state``, keyed by player id, in seat order.

    The state is scored as given, whatever its round. With ``preset=None``
    the scoring values come from ``state.preset`` when it is set, and from
    ``preset(state.mode)`` otherwise; an explicit ``preset`` always wins.
    Raises ``ValueError`` for a watered claimed vineyard with no varietal
    (never planted) or one with no points in the preset.
    """
    if not isinstance(state, GameState):
        raise TypeError(f"calculate_score needs a GameState, got {state!r}")
    if preset is None:
        preset = state.preset if state.preset is not None else preset_for(state.mode)
    elif not isinstance(preset, Preset):
        raise TypeError(f"preset must be a Preset or None, got {preset!r}")

    board = state.board
    players = sorted(state.players, key=lambda p: p.seat)
    seat_of = {p.id: p.seat for p in players}
    bonus_of = _seat_bonuses(state, players, preset)

    owned: dict[str, list[WateredVineyard]] = {p.id: [] for p in players}
    collected: dict[str, int] = {p.id: 0 for p in players}
    for hex, path in sorted(water(board).items()) if board.claims else ():  # only claims score
        claimant = board.claimant(hex)
        if claimant is None:
            continue
        pays = tuple(sorted(path.owners - {claimant}, key=seat_of.__getitem__))
        for rival in pays:
            collected[rival] += preset.water_right_points
        varietal = board.varietal_at(hex)
        if varietal is None:
            raise ValueError(f"the claimed vineyard on {hex} has no varietal planted")
        if varietal not in preset.varietal_points:
            raise ValueError(f"{varietal.display_name} on {hex} has no points in the preset")
        owned[claimant].append(WateredVineyard(hex, varietal, path, pays))
    if board.planted:
        wet = wet_canals(board)
        thirds_at = vertex_thirds(board, wet)
        for vineyard in board.planted:
            vertex = vineyard.vertex
            if vineyard.varietal not in preset.varietal_points:
                raise ValueError(
                    f"{vineyard.varietal.display_name} on {vertex} has no points in the preset"
                )
            value = preset.varietal_points[vineyard.varietal]
            for pid, thirds in thirds_at[vertex].items():
                if pid not in owned:
                    continue  # a canal owner who is not in the game scores nothing
                canals = tuple(
                    board.canal_at(h) for h in vertex.hexes
                    if h in wet and board.canal_at(h).owner == pid
                )
                owned[pid].append(
                    WateredVineyard(
                        None, vineyard.varietal, WaterPath(canals, frozenset({pid})), (), vertex,
                        planter=vineyard.owner, thirds=thirds, points=split_points(value, thirds),
                    )
                )
    built: dict[str, list[WateredBodega]] = {p.id: [] for p in players}
    if board.bodegas:
        wet = wet_canals(board)
        worth = preset.bodega_building_points
        thirds_at = vertex_thirds(board, wet, [b.vertex for b in board.bodegas])
        for bodega in board.bodegas:
            for pid, thirds in thirds_at[bodega.vertex].items():
                if pid in built:
                    built[pid].append(
                        WateredBodega(bodega.vertex, bodega.owner, thirds, split_points(worth, thirds))
                    )

    scores: dict[str, Score] = {}
    for p in players:
        mine = tuple(owned[p.id])
        vineyards = sum(
            v.points if v.vertex is not None else preset.varietal_points[v.varietal] for v in mine
        )
        if preset.varietal_bodega:
            bodegas = bodega_count((v.varietal for v in mine), preset.bodega_varietals)
            if not preset.multiple_bodegas:
                bodegas = min(bodegas, 1)
        else:
            bodegas = 0
        bodega = preset.bodega_points * bodegas
        blend, scored = (
            blend_points((v.varietal for v in mine), preset.blends, preset.blend_rule)
            if preset.blends else (0, ())
        )
        buildings = sum(b.points for b in built[p.id])
        paid = sum(len(v.pays) for v in mine) * preset.water_right_points
        before = (
            vineyards + bodega + blend + buildings - paid + collected[p.id] - p.debt + p.season
            + bonus_of[p.id]
        )
        drought = min(p.drought, max(0, before))
        total = before - drought
        scores[p.id] = Score(
            player=p.id,
            seat=p.seat,
            vineyards=vineyards,
            bodega=bodega,
            rights_paid=paid,
            rights_collected=collected[p.id],
            debt=p.debt,
            total=total,
            watered=len(mine),
            watered_vineyards=mine,
            season=p.season,
            drought=drought,
            bodegas=bodegas,
            seat_bonus=bonus_of[p.id],
            blend=blend,
            blends=tuple(b.name for b in scored),
            buildings=buildings,
            watered_bodegas=tuple(built[p.id]),
        )
    return MappingProxyType(scores)


def _seat_bonuses(state: GameState, players: list, preset: Preset) -> dict[str, int]:
    """Each player's seat bonus, by player id: by their position in round 1's turn order."""
    bonus = preset.seat_bonus.get(len(players))
    if bonus is None:
        return {p.id: 0 for p in players}
    ids = [p.id for p in players]
    first = (ids.index(state.start_player) - (state.round - 1)) % len(ids)
    return {pid: bonus[(k - first) % len(ids)] for k, pid in enumerate(ids)}


def winners(scores: Mapping[str, Score]) -> tuple[str, ...]:
    """The winning player ids from ``calculate_score``, in seat order.

    The highest ``total`` wins; on a tie, the higher ``watered``; if that
    ties too, every tied player wins.
    """
    if not scores:
        return ()
    best = max((s.total, s.watered) for s in scores.values())
    return tuple(
        s.player
        for s in sorted(scores.values(), key=lambda s: s.seat)
        if (s.total, s.watered) == best
    )
