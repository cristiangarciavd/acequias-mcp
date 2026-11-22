"""Final scoring: each player's score by term, and the winners.

Rules come from ``README.md`` (End and scoring, Water rights, Bodega bonus).
Each player scores

    vineyard values + bodega bonus - water rights paid
    + water rights collected - bribe debt + season - drought

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

This module is pure: it reads a ``GameState``, changes nothing, and has no
randomness.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from acequias.config import Preset, preset as preset_for
from acequias.flow import WaterPath, water
from acequias.hex import Hex
from acequias.model import GameState, Varietal


@dataclass(frozen=True, slots=True)
class WateredVineyard:
    """One watered claimed vineyard of a player.

    ``pays`` holds the rivals the claimant pays ``water_right_points``
    each, once per rival: the path's owners minus the claimant, in seat
    order.
    """

    hex: Hex
    varietal: Varietal
    path: WaterPath
    pays: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Score:
    """A player's final score, by term.

    ``total == vineyards + bodega - rights_paid + rights_collected - debt
    + season - drought``, where ``drought`` is the drought loss actually
    taken (clamped so a drought never takes the total below 0).
    Every term is in points: ``rights_paid`` and ``rights_collected`` are
    the rival-vineyard pairs times the preset's ``water_right_points``.
    ``watered`` is the number of the player's claimed vineyards that are
    watered (the tie-break), and ``watered_vineyards`` lists them in hex
    order.
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

    points = preset.varietal_points
    scores: dict[str, Score] = {}
    for p in players:
        mine = tuple(owned[p.id])
        vineyards = sum(points[v.varietal] for v in mine)
        varietals = {v.varietal for v in mine}
        bodega = preset.bodega_points if len(varietals) >= preset.bodega_varietals else 0
        paid = sum(len(v.pays) for v in mine) * preset.water_right_points
        before = vineyards + bodega - paid + collected[p.id] - p.debt + p.season
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
        )
    return MappingProxyType(scores)


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
