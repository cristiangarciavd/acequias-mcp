"""How many of the Rules v3 markers a set holds, and in which color.

- 20 vineyard clusters: 3 of each common varietal, 1 Bonarda and 1 Cabernet
  Franc, printed in the color of their roulette sector
  (``CLUSTER_COLORS``: violet, red, fluorescent green)
- per player, in the player's color: ``OWNER_PEGS_PER_PLAYER`` owner pegs
  (``owner_token``, spares included) and ``BODEGAS_PER_PLAYER`` bodega

``cluster_entries()`` and ``player_entries(color)`` give those counts as
``build_plate`` entries (``{"piece": ..., "count": ..., "color": ...}``),
pieces at their default sizes. Like ``acequias.cad.footprints`` this module
imports no CAD, so it runs without the ``cad`` extra.
"""

from __future__ import annotations

from typing import Any

from acequias.model import Varietal

CLUSTER_COLORS: dict[str, tuple[Varietal, ...]] = {
    "violet": (Varietal.MALBEC, Varietal.SYRAH, Varietal.BONARDA),
    "red": (Varietal.CABERNET_SAUVIGNON, Varietal.MERLOT, Varietal.CABERNET_FRANC),
    "fluorescent_green": (Varietal.TORRONTES, Varietal.CHARDONNAY),
}
"""The print color of each varietal's clusters (the roulette's sector colors)."""

CLUSTERS_PER_VARIETAL: dict[Varietal, int] = {
    Varietal.MALBEC: 3,
    Varietal.SYRAH: 3,
    Varietal.BONARDA: 1,
    Varietal.CABERNET_SAUVIGNON: 3,
    Varietal.MERLOT: 3,
    Varietal.CABERNET_FRANC: 1,
    Varietal.TORRONTES: 3,
    Varietal.CHARDONNAY: 3,
}
"""Vineyard clusters in a set, per varietal: 20 in all."""

OWNER_PEGS_PER_PLAYER = 28
"""Owner pegs per player, spares for lost pegs included."""

BODEGAS_PER_PLAYER = 1
"""Bodega tokens per player."""


def cluster_entries() -> list[dict[str, Any]]:
    """The ``build_plate`` entries for every vineyard cluster of a set, by color."""
    return [
        {
            "piece": {"type": "vineyard_cluster", "varietal": varietal.name.lower()},
            "count": CLUSTERS_PER_VARIETAL[varietal],
            "color": color,
        }
        for color, varietals in CLUSTER_COLORS.items()
        for varietal in varietals
    ]


def player_entries(color: str) -> list[dict[str, Any]]:
    """The ``build_plate`` entries for one player's owner pegs and bodega in ``color``."""
    return [
        {"piece": {"type": "owner_token"}, "count": OWNER_PEGS_PER_PLAYER, "color": color},
        {"piece": {"type": "bodega_token"}, "count": BODEGAS_PER_PLAYER, "color": color},
    ]
