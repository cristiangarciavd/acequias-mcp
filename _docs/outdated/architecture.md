> **OUTDATED — do not use as context.** This file is kept only for history. `README.md` (specification) and the GitHub issues (tasks) replace it. Agents: do not read further unless the user asked for this file by name.

# Acequias — Architecture

_Snapshot: 2026-11-05, after tasks #1 and #2._

This describes what exists in the repository today, then the module layout the
backlog (GitHub issues) plans to add. Anything under "Planned" is not built yet.

## What exists

### Layout

```
acequias/            game logic, independent of MCP
  __init__.py        package docstring and __version__ ("0.1.0")
  hex.py             axial hex coordinates (task #2)
server/              MCP server package
  __init__.py        package docstring only; no server yet
tests/
  test_package.py    both packages import; version check
  test_hex.py        hex model tests (75 tests)
_docs/               process, PM role, task template, outdated docs
pyproject.toml       project metadata, pytest config
uv.lock              locked dependencies
.python-version      3.12
```

### Tooling

| Item | State |
| --- | --- |
| Environment | uv; `uv sync` installs, `uv run pytest` runs the suite |
| Python | `requires-python >=3.11`, pinned to 3.12 |
| Build backend | hatchling, packaging `acequias` and `server` |
| Runtime dependencies | none |
| Dev dependencies | pytest only |
| Test suite | 77 tests, all passing |
| CI | none yet (#44) |
| Ignored | Python caches, `.venv/`, tool caches, generated `*.stl`, `*.3mf`, `*.step` |

### `acequias/hex.py`

Pure module (standard library only, imports nothing from `acequias`; a test
checks this).

- `Hex(q, r)`: frozen, slotted, hashable dataclass. Non-int coordinates raise
  `TypeError`. Ordered by `(q, r)`, the deterministic tie-break for water paths.
  Supports `+` and `-`.
- Convention: **pointy-top**. `q` grows east, `r` grows south, `s = -q - r`.
  East and west are direct neighbors, so the river can run along the west edge.
- `Direction`: `E, NE, NW, W, SW, SE` (counterclockwise from east), with
  `offset` and `opposite()`.
- `neighbor(d)`, `neighbors()` (in `Direction` order), `distance(other)`.
- `to_cube()` / `from_cube()` (checks the zero sum).
- `to_pixel(size)` / `from_pixel(x, y, size)`: hex centers in the plane, origin
  hex at `(0, 0)`, `x` east, `y` south, in the units of `size` (mm).

Known gaps, tracked in #45: no size check in the pixel conversions, no
direction rotation, no corner points.

### Rules for the code

- Game logic lives in `acequias/` and never imports `server/`, so it is tested
  without MCP.
- Randomness goes through a seeded RNG so games are reproducible.
- Dependencies are added in `pyproject.toml` only after asking.
- Every change goes through a branch and pull request (`_docs/process.md`).

## Planned

Module map from the groomed backlog. Arrows read "uses".

```
                      server/app.py (FastMCP, stdio)  #10
                                 │
   ┌───────────────┬─────────────┼──────────────┬────────────────┐
generate_board  calculate_score  simulate_game  generate_piece_stl  build_plate
   #11             #12             #13            #17               #19
   │               │               │              │                 │
   ▼               ▼               ▼              ▼                 ▼
board.py #4     scoring.py #6   sim.py #9      cad/ #14 #15 #16  plate.py #18
assembly #28       │            bots.py #8 #30     #31 #32       cad/plate_export #33
   │               ▼            game.py #21 #29
   │           flow.py #5       turn.py #7
   └──────┬────────┴──────┬───────┘
          ▼               ▼
     model.py #3     config.py #22
          │
          ▼
       hex.py #2 (#45)
```

| Layer | Modules | Milestone |
| --- | --- | --- |
| Domain | `model.py` (#3), `config.py` (#22) | 1. Game logic |
| Board | `board.py` (#4), assembly steps (#28) | 1. Game logic |
| Water and scoring | `flow.py` (#5), `scoring.py` (#6) | 1. Game logic |
| MCP server | `server/app.py` (#10), tools #11, #12 | 2. MCP server |
| Play | setup (#29), `turn.py` (#7), `game.py` (#21) | 3. Simulation |
| Bots and simulation | `bots.py` (#8, #30), `sim.py` (#9), tool #13, tuning (#20, #35) | 3. Simulation |
| CAD | `cad/hex_tile.py` (#14), `cad/channel.py` (#15), `cad/relief.py` (#16), `cad/tokens.py` (#31), `cad/dem.py` (#32), tool #17 | 4. build123d pieces |
| Printing | `plate.py` (#18), `cad/plate_export.py` (#33), tool #19, first print (#34) | 5. Plate and printing |

Planned dependencies, each needing approval when its task starts: `mcp` (#10),
`build123d` and `trimesh` (#14), `hypothesis` (#44), a GeoTIFF reader (#32).
