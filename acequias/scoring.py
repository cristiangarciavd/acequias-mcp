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

Vertex vineyards (Rules v3, ``Board.planted``) score the same way: a
watered one scores its varietal's points for its owner, counts toward
their bodegas, and pays the rights of its path (``acequias.flow.vertex_water``);
a dry one scores 0. Their ``WateredVineyard`` has ``vertex`` set and no
``hex``, and they follow the hex vineyards in vertex order.

This module is pure: it reads a ``GameState``, changes nothing, and has no
randomness.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from acequias.config import Preset, preset as preset_for
from acequias.flow import WaterPath, vertex_water, water
from acequias.hex import Hex, Vertex
from acequias.model import GameState, Varietal


@dataclass(frozen=True, slots=True)
class WateredVineyard:
    """One watered claimed vineyard of a player.

    ``pays`` holds the rivals the claimant pays ``water_right_points``
    each, once per rival: the path's owners minus the claimant, in seat
    order. ``hex`` is the vineyard's hex, or None for a vertex vineyard
    (Rules v3), whose spot is ``vertex``.
    """

    hex: Hex | None
    varietal: Varietal
    path: WaterPath
    pays: tuple[str, ...]
    vertex: Vertex | None = None


@dataclass(frozen=True, slots=True)
class Score:
    """A player's final score, by term.

    ``total == vineyards + bodega - rights_paid + rights_collected - debt
    + season + seat_bonus - drought``, where ``drought`` is the drought loss actually
    taken (clamped so a drought never takes the total below 0).
    Every term is in points: ``rights_paid`` and ``rights_collected`` are
    the rival-vineyard pairs times the preset's ``water_right_points``.
    ``watered`` is the number of the player's claimed vineyards that are
    watered (the tie-break), and ``watered_vineyards`` lists them in hex
    order. ``bodegas`` is the number of bodega bonuses earned, so
    ``bodega == bodegas * bodega_points``. ``seat_bonus`` is the
    preset's seat bonus for the player's round 1 position.
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
    for hex, path in sorted(water(board).items()):
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
    for vertex, path in vertex_water(board).items():
        vineyard = board.planted_at(vertex)
        owner = vineyard.owner
        pays = tuple(sorted(path.owners - {owner}, key=seat_of.__getitem__))
        for rival in pays:
            collected[rival] += preset.water_right_points
        if vineyard.varietal not in preset.varietal_points:
            raise ValueError(
                f"{vineyard.varietal.display_name} on {vertex} has no points in the preset"
            )
        owned[owner].append(WateredVineyard(None, vineyard.varietal, path, pays, vertex))

    points = preset.varietal_points
    scores: dict[str, Score] = {}
    for p in players:
        mine = tuple(owned[p.id])
        vineyards = sum(points[v.varietal] for v in mine)
        bodegas = bodega_count((v.varietal for v in mine), preset.bodega_varietals)
        if not preset.multiple_bodegas:
            bodegas = min(bodegas, 1)
        bodega = preset.bodega_points * bodegas
        paid = sum(len(v.pays) for v in mine) * preset.water_right_points
        before = vineyards + bodega - paid + collected[p.id] - p.debt + p.season + bonus_of[p.id]
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
