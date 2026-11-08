"""Export one laid-out plate as a printable 3MF file.

``export_plate(plate, solids, path)`` takes a ``Plate`` from
``acequias.plate.layout_plates`` and the build123d solid of every piece on
it, and writes one 3MF file in mm with every piece already in place on the
bed, ready to open in the slicer:

- one separate mesh object per placement, in placement order, named after
  its piece id
- each piece rotated by its placement's ``rotation`` (degrees about z,
  around the solid's own origin), then moved so that origin sits at the
  placement's ``x``, ``y`` (mm from the bed's front-left corner) and its
  lowest point at ``z = 0``
- the plate's number and color group as model metadata
  (``acequias:plate`` and ``acequias:color_group``)

No 3MF colors or filament assignments are written: each plate is one color
group, and the filament is picked in the slicer.

The file is written and read back with build123d's ``Mesher`` (lib3mf).
Every UUID in the file comes from the piece ids and the plate number, so
exporting the same plate twice gives the same objects.

Needs the optional ``cad`` extra (``uv sync --extra cad``).
"""

from __future__ import annotations

import math
import os
import tempfile
import uuid
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path

from build123d import Location, Mesher, Solid, Unit

from acequias.plate import DEFAULT_BED, Placement, Plate

METADATA_NAMESPACE = "acequias"
"""Namespace of the plate metadata: ``acequias:plate``, ``acequias:color_group``."""

TESSELLATION_TOLERANCE = 0.05
"""Largest gap in mm between a curved surface and its triangles.

The bounding box of a curved piece (owner token, grape cluster, debt token)
in the file matches the solid's within this; flat-sided pieces (hexes,
canals, floodgate) match exactly.
"""

LINEAR_DEFLECTION = 0.01
"""``Mesher.add_shape`` linear deflection, relative to each edge's size."""

ANGULAR_DEFLECTION = 0.2
"""``Mesher.add_shape`` angular deflection in radians.

Each chord of a curved edge of radius ``r`` turns by at most this, so it is
at most ``r * (1 - cos(0.1))``, about ``0.005 * r``, from the surface: under
``TESSELLATION_TOLERANCE`` for every radius up to 10 mm.
"""

# Slack for floating-point error when checking that a piece is on the bed.
_BED_EPS = 1e-6

# Fixed namespace for the UUIDs derived from piece ids.
_UUID_NAMESPACE = uuid.UUID("6b1d9a52-3f0e-4f43-9a55-0c3a5e1c7a33")


def export_plate(
    plate: Plate,
    solids: Mapping[str, Solid],
    path: str | os.PathLike[str],
    *,
    bed: tuple[float, float] = DEFAULT_BED,
) -> Path:
    """Write ``plate`` as one 3MF file at ``path`` and return the path.

    ``solids`` maps each piece id to its build123d solid, modeled at the
    origin as its generator lays it on the plate; it may hold ids the plate
    does not use, and the same solid may serve many ids. The solids are not
    changed. ``bed`` is the bed's (width, depth) in mm.

    Creates the parent folder if missing and overwrites an existing file;
    the file only appears once it is complete.

    Raises ``ValueError``, writing nothing, for a ``path`` that does not end
    in ``.3mf``, a bad bed, a plate with no placements, a piece id used twice
    on the plate, a placement whose id has no solid in ``solids`` (or whose
    solid is not a ``Solid``), and a piece that, once placed, sticks out of
    the bed.
    """
    out = Path(path)
    if out.suffix.lower() != ".3mf":
        raise ValueError(f"path must end in .3mf, got {str(path)!r}")
    bed_w, bed_d = _check_bed(bed)
    if not plate.placements:
        raise ValueError(f"plate {plate.number} has no placements")

    placed: list[tuple[str, Solid]] = []
    seen: set[str] = set()
    for placement in plate.placements:
        piece_id = placement.piece_id
        if piece_id in seen:
            raise ValueError(f"piece id {piece_id!r} is on plate {plate.number} twice")
        seen.add(piece_id)
        if piece_id not in solids:
            raise ValueError(f"no solid for piece {piece_id!r}")
        solid = solids[piece_id]
        if not isinstance(solid, Solid):
            raise ValueError(
                f"the solid for piece {piece_id!r} must be a build123d Solid, "
                f"got {type(solid).__name__}"
            )
        shape = _place(solid, placement)
        box = shape.bounding_box()
        if (
            box.min.X < -_BED_EPS
            or box.min.Y < -_BED_EPS
            or box.max.X > bed_w + _BED_EPS
            or box.max.Y > bed_d + _BED_EPS
        ):
            raise ValueError(
                f"piece {piece_id!r} sticks out of the {bed_w:g} x {bed_d:g} mm bed: "
                f"once placed it spans x {box.min.X:.2f} to {box.max.X:.2f} and "
                f"y {box.min.Y:.2f} to {box.max.Y:.2f} mm"
            )
        placed.append((piece_id, shape))

    mesher = Mesher(unit=Unit.MM)
    for piece_id, shape in placed:
        before = len(mesher.meshes)
        mesher.add_shape(
            shape,
            linear_deflection=LINEAR_DEFLECTION,
            angular_deflection=ANGULAR_DEFLECTION,
            uuid_value=_uuid(piece_id, "object"),
        )
        if len(mesher.meshes) != before + 1:
            raise ValueError(f"piece {piece_id!r} did not give exactly one mesh")
    mesher.add_meta_data(METADATA_NAMESPACE, "plate", str(plate.number), "xs:integer", True)
    mesher.add_meta_data(METADATA_NAMESPACE, "color_group", plate.color_group, "xs:string", True)
    _set_uuids(mesher, plate, [piece_id for piece_id, _ in placed])

    buffer = BytesIO()
    mesher.write_stream(buffer, "3mf")
    _write_atomic(out, buffer.getvalue())
    return out


def _check_bed(bed: object) -> tuple[float, float]:
    try:
        width, depth = bed  # type: ignore[misc]
    except (TypeError, ValueError):
        raise ValueError(f"bed must be a (width, depth) pair, got {bed!r}") from None
    for name, value in (("bed width", width), ("bed depth", depth)):
        if (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError(f"{name} must be a finite number > 0, got {value!r}")
    return float(width), float(depth)


def _place(solid: Solid, placement: Placement) -> Solid:
    """A copy of ``solid`` rotated, moved onto the bed, and named; ``solid`` is unchanged."""
    # A rotation about z keeps the lowest point, so the source's min z holds.
    lowest = solid.bounding_box().min.Z
    location = Location(
        (placement.x, placement.y, -lowest), (0, 0, placement.rotation)
    )
    shape = solid.moved(location)
    shape.label = placement.piece_id
    return shape


def _uuid(piece_id: str, role: str) -> uuid.UUID:
    return uuid.uuid5(_UUID_NAMESPACE, f"{role}/{piece_id}")


def _set_uuids(mesher: Mesher, plate: Plate, piece_ids: list[str]) -> None:
    """Replace the random UUIDs lib3mf gives the build, its items, and the components.

    ``Mesher.add_shape`` adds, per shape, a mesh object (its UUID is set
    from the piece id), a build item, and a components object wrapping the
    mesh; lib3mf gives the last two random UUIDs, set here from the piece id.
    """
    model = mesher.model
    by_resource = {
        mesh.GetResourceID(): piece_id for mesh, piece_id in zip(mesher.meshes, piece_ids)
    }
    model.SetBuildUUID(str(_uuid(f"plate-{plate.number}", "build")))

    items = model.GetBuildItems()
    while items.MoveNext():
        item = items.GetCurrent()
        item.SetUUID(str(_uuid(by_resource[item.GetObjectResourceID()], "item")))

    groups = model.GetComponentsObjects()
    while groups.MoveNext():
        group = groups.GetCurrentComponentsObject()
        for index in range(group.GetComponentCount()):
            component = group.GetComponent(index)
            piece_id = by_resource[component.GetObjectResourceID()]
            component.SetUUID(str(_uuid(piece_id, f"component-{index}")))
            if index == 0:
                group.SetUUID(str(_uuid(piece_id, "components")))


def _write_atomic(path: Path, data: bytes) -> None:
    """Write ``data`` to a temporary file beside ``path``, then move it into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
