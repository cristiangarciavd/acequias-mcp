"""The plate footprint of every printable piece, from its sizes.

``piece_footprint(piece_type, variant, **params)`` takes the same arguments
as ``acequias.cad.pieces.build_piece`` and returns the outline the piece
covers on the print plate, for ``acequias.plate.layout_plates``:

- ``"terrain"`` and ``"canal"``: ``HexFootprint(side - 2 * clearance / sqrt(3))``,
  the hex outline shrunk by ``clearance`` on every edge
- ``"floodgate"``: ``RectFootprint(groove_width - 2 * tolerance, height)``,
  the gate lying on its flush outer face, as it is printed
- ``"owner_token"``: ``CircleFootprint(cap_diameter)``
- ``"grape_cluster"``: ``CircleFootprint(base_diameter)``
- ``"debt_token"``: ``CircleFootprint(diameter)``
- ``"qr_plate"``: ``RectFootprint(size, size + label_band)``
- ``"vineyard_cluster"``: ``RectFootprint(base_diameter, 0.75 * base_diameter)``,
  the round cluster cut by its two flat sides (``CLUSTER_FLAT_RATIO``)
- ``"bodega_token"``: ``CircleFootprint(base_diameter)``

Unlike ``acequias.cad.pieces`` this module imports neither build123d nor
trimesh, so the layout needs no CAD. It reads only the sizes that set the
outline and fills in no defaults: pass every one of them (a test checks
each footprint against the built solid's bounding box).
"""

from __future__ import annotations

from typing import Any

from acequias.hex import SQRT3
from acequias.plate import CircleFootprint, Footprint, HexFootprint, RectFootprint

CLUSTER_FLAT_RATIO = 0.75
"""``acequias.cad.markers.CLUSTER_FLAT_RATIO``, repeated so no CAD is imported."""


def piece_footprint(piece_type: str, variant: object = None, **params: Any) -> Footprint:
    """The plate footprint of one piece of ``piece_type`` with sizes ``params`` (mm).

    ``variant`` is accepted so the call matches ``build_piece``; no variant
    changes a footprint. ``params`` may hold sizes the footprint does not use.

    Raises ``ValueError`` for an unknown type, a missing size, or a
    footprint that is not positive (for example a clearance that eats the
    whole hex).
    """
    if piece_type in ("terrain", "canal"):
        side = _size(piece_type, params, "side")
        clearance = _size(piece_type, params, "clearance")
        return HexFootprint(side - 2 * clearance / SQRT3)
    if piece_type == "floodgate":
        groove_width = _size(piece_type, params, "groove_width")
        tolerance = _size(piece_type, params, "tolerance")
        return RectFootprint(groove_width - 2 * tolerance, _size(piece_type, params, "height"))
    if piece_type == "owner_token":
        return CircleFootprint(_size(piece_type, params, "cap_diameter"))
    if piece_type == "grape_cluster":
        return CircleFootprint(_size(piece_type, params, "base_diameter"))
    if piece_type == "debt_token":
        return CircleFootprint(_size(piece_type, params, "diameter"))
    if piece_type == "qr_plate":
        size = _size(piece_type, params, "size")
        return RectFootprint(size, size + _size(piece_type, params, "label_band"))
    if piece_type == "vineyard_cluster":
        base = _size(piece_type, params, "base_diameter")
        return RectFootprint(base, CLUSTER_FLAT_RATIO * base)
    if piece_type == "bodega_token":
        return CircleFootprint(_size(piece_type, params, "base_diameter"))
    raise ValueError(f"no footprint for piece type {piece_type!r}")


def _size(piece_type: str, params: dict[str, Any], name: str) -> Any:
    if name not in params:
        raise ValueError(f"the footprint of a {piece_type} piece needs {name!r}")
    return params[name]
