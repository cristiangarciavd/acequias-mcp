"""Every printable piece by type: the dispatch from a piece type to its generator.

``build_piece(piece_type, variant, **params)`` builds one piece at the
origin, as its generator lays it on the print plate. The piece types and
their variants:

- ``"terrain"``: a ``Terrain``. For the MVP every terrain is the plain
  ``hex_tile`` (decorative relief comes after the MVP), so the four are
  identical
- ``"canal"``: a canal ``PieceKind`` (not the floodgate), ``canal_piece``
- ``"floodgate"``: no variant, ``floodgate`` laid on its flush outer face
  (``printed_floodgate``), so it needs no supports
- ``"owner_token"``: no variant, ``owner_token``
- ``"grape_cluster"``: no variant, ``grape_cluster``
- ``"debt_token"``: the token value, 1 or 5, ``debt_token``
- ``"qr_plate"``: the rulebook language, ``"reglas"`` or ``"rules"``,
  ``qr_plate``
- ``"vineyard_cluster"``: the ``Varietal``, ``vineyard_cluster`` (Rules v3)
- ``"bodega_token"``: no variant, ``bodega_token`` (Rules v3)

``params`` are the generator's keyword arguments; any left out keep the
generator's default. The generators check every value and raise
``ValueError`` naming the parameter.

Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from build123d import Axis, Solid

from acequias.cad.channel import canal_piece, floodgate, owner_token
from acequias.cad.hex_tile import hex_tile
from acequias.cad.markers import bodega_token, vineyard_cluster
from acequias.cad.qr_plate import qr_plate
from acequias.cad.tokens import debt_token, grape_cluster
from acequias.model import PieceKind, Terrain


def terrain_piece(terrain: Terrain, **params: Any) -> Solid:
    """The terrain piece for ``terrain``: for the MVP, the plain ``hex_tile``.

    Raises ``TypeError`` if ``terrain`` is not a ``Terrain``.
    """
    if not isinstance(terrain, Terrain):
        raise TypeError(f"terrain must be a Terrain, got {terrain!r}")
    return hex_tile(**params)


def _canal(kind: PieceKind, **params: Any) -> Solid:
    return canal_piece(kind, **params)


def printed_floodgate(**params: Any) -> Solid:
    """``floodgate(**params)`` as printed: lying on its flush outer face.

    The outer face (``+y`` in ``floodgate``) goes down onto the bed, so the
    fin lies flat and its layers run along its height. The plate outline is
    ``groove_width - 2 * tolerance`` in ``x`` by ``height`` in ``y``, the
    print is ``thickness`` high, bottom on ``z = 0``, centered at
    ``x = y = 0``.
    """
    gate = floodgate(**params).rotate(Axis.X, -90)
    box = gate.bounding_box()
    return gate.translate(
        (-(box.min.X + box.max.X) / 2, -(box.min.Y + box.max.Y) / 2, -box.min.Z)
    )


def _debt_token(value: int, **params: Any) -> Solid:
    return debt_token(value, **params)


# Piece type -> (generator, takes a variant).
GENERATORS: dict[str, tuple[Callable[..., Solid], bool]] = {
    "terrain": (terrain_piece, True),
    "canal": (_canal, True),
    "floodgate": (printed_floodgate, False),
    "owner_token": (owner_token, False),
    "grape_cluster": (grape_cluster, False),
    "debt_token": (_debt_token, True),
    "qr_plate": (qr_plate, True),
    "vineyard_cluster": (vineyard_cluster, True),
    "bodega_token": (bodega_token, False),
}

PIECE_TYPES: tuple[str, ...] = tuple(GENERATORS)
"""Every piece type, in the order above."""


def build_piece(piece_type: str, variant: object = None, **params: Any) -> Solid:
    """One piece of ``piece_type``: its ``variant``, if it has one, and its sizes.

    Raises ``ValueError`` for an unknown type, a variant given to a type
    without one or missing from a type that needs one, and whatever the
    generator raises for a bad value.
    """
    if piece_type not in GENERATORS:
        allowed = ", ".join(f'"{name}"' for name in PIECE_TYPES)
        raise ValueError(f"type must be one of {allowed}, got {piece_type!r}")
    generator, has_variant = GENERATORS[piece_type]
    if has_variant:
        if variant is None:
            raise ValueError(f"a {piece_type} piece needs its variant")
        return generator(variant, **params)
    if variant is not None:
        raise ValueError(f"a {piece_type} piece has no variant, got {variant!r}")
    return generator(**params)
