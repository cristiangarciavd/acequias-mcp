"""The one folder the server writes files into.

Every tool that writes a file (`generate_piece_stl`, `build_plate`) calls
`output_dir()` and writes only directly inside the folder it returns.
"""

from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR_ENV = "ACEQUIAS_OUTPUT_DIR"
"""The environment variable that sets the output folder."""

DEFAULT_OUTPUT_DIR = "output"
"""The output folder when `ACEQUIAS_OUTPUT_DIR` is unset or empty, in the working folder."""


def output_dir() -> Path:
    """The output folder, absolute and resolved, created with its parents if missing.

    Read from `ACEQUIAS_OUTPUT_DIR` on every call; unset or empty means
    `output/` in the working folder, and a relative value is resolved
    against the working folder. Raises `ValueError` naming
    `ACEQUIAS_OUTPUT_DIR` and the path if the path is an existing file or
    the folder cannot be created.
    """
    value = os.environ.get(OUTPUT_DIR_ENV, "") or DEFAULT_OUTPUT_DIR
    folder = (Path.cwd() / value).resolve()
    if folder.exists() and not folder.is_dir():
        raise ValueError(f"{OUTPUT_DIR_ENV} must be a folder, but {str(folder)!r} is a file")
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ValueError(
            f"{OUTPUT_DIR_ENV}: cannot create the output folder {str(folder)!r}: {exc.strerror or exc}"
        ) from exc
    return folder
