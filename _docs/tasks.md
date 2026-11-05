# Acequias — Task backlog

_Updated: 2026-11-05_

Each task is scoped to finish in one session (under 1 hour) and to be handed off
on its own: the description names its module and interface, so whoever picks it
up doesn't need to have read the others. The order is a suggested build path,
not a hard dependency: each task states what it takes in and what it produces.

The stack is fixed in `plan.md` (FastMCP + uv + build123d + trimesh + pytest).

---

## 1. Empty project with a passing test
Goal: Repo installable with `uv` and a green `pytest`.
Description: Create the base structure (`acequias/` for the logic, `server/` for the MCP, `tests/`), the `pyproject.toml` managed with uv, and the pytest configuration. Add a single trivial test (for example, that the package imports) that passes, to leave the scaffolding ready. No game or geometry logic included.

## 2. Hex model (axial coordinates)
Goal: A hex coordinate type with basic operations.
Description: Implement in `acequias/hex.py` an axial coordinate type (q, r) with neighbors, distance, equality, and conversion helpers. It is a pure module, with no dependency on the rest of the game. Include unit tests for neighbors and distance.

## 3. Game domain types
Goal: The game's data model, with no logic.
Description: Define in `acequias/model.py` the terrain types (river, vineyard, stone, empty), the varietals with their score (Malbec 3, Bonarda 2, Torrontés 1), the canal pieces (straight, gentle curve, sharp curve, Y-junction, floodgate), and the board and player state structures. Only dataclasses/enums and their invariants, with tests that verify the score values and the validity of the types.

## 4. Balanced board generator
Goal: `generate_board(players, seed)`, deterministic.
Description: In `acequias/board.py`, generate a hex map based on the number of players, with the west edge as the river and neutral vineyards distributed across it. It must be reproducible by seed and guarantee at least one vineyard reachable per player. Include tests for determinism (same seed → same map) and for the reachability invariant.

## 5. Water reach and canal path
Goal: Which vineyards reach the river, and through which canals.
Description: In `acequias/flow.py`, given a board and the placed canal pieces, compute which vineyards are connected to the river and the list of canals (with their owner) each connection passes through. It is a pure graph traversal, feeding scoring and water rights. Tests with hand-built cases, including a floodgate block.

## 6. Scoring with water rights
Goal: `calculate_score(state)` with points per player.
Description: In `acequias/scoring.py`, from the final board state, add up the value of the vineyards claimed by each player and apply water rights (subtract what is paid, add what is collected) using the canal path. Return the score per player. Include tests with hand-worked examples.

## 7. Turn engine and move validation
Goal: Apply a legal move to the state.
Description: In `acequias/turn.py`, validate and apply a move (pick a piece from the market, place it connected to the network, slot in the owner token, claim a vineyard if applicable) and replenish the market. Reject illegal moves with a clear error. Tests for valid moves, invalid moves, and market replenishment.

## 8. Simple-policy bots
Goal: Bots that choose legal moves.
Description: In `acequias/bots.py`, implement a `decide(state) -> move` interface with at least two policies: a random one and a greedy one (prioritizes claiming higher-value vineyards). They feed the simulation. Tests that verify each bot always produces a legal move.

## 9. Simulation engine and balance statistics
Goal: `simulate_game(rules, n)` with balance metrics.
Description: In `acequias/sim.py`, run N games with bots across the fixed rounds and collect balance statistics (turn-order advantage, distribution of winning varietals, average score). It must be reproducible by seed. Tests for determinism and for the shape of the statistics.

## 10. MCP server skeleton (FastMCP)
Goal: A FastMCP server that boots and lists tools.
Description: In `server/app.py`, stand up the server with FastMCP (official SDK) exposing a trivial test tool (for example, `ping`). Leave the entry point and configuration ready to add the real tools. Include an integration test that connects an in-process client and lists the tools.

## 11. MCP tool: generate_board
Goal: Expose `generate_board` as an MCP tool.
Description: Wrap the board generation function (`acequias/board.py`) as a FastMCP tool, with an input schema (players, seed) and an output schema (map + assembly instructions). It reimplements no logic: it only adapts and serializes. A test that invokes the tool and validates the response schema.

## 12. MCP tool: calculate_score
Goal: Expose `calculate_score` as an MCP tool.
Description: Wrap the scoring function (`acequias/scoring.py`) as a FastMCP tool, taking the final board state and returning the score per player with water rights. Adaptation and serialization only. A test that invokes the tool with a known state and verifies the points.

## 13. MCP tool: simulate_game
Goal: Expose `simulate_game` as an MCP tool.
Description: Wrap the simulation engine (`acequias/sim.py`) as a FastMCP tool, taking rules and a number of games and returning the balance statistics. Adaptation and serialization only. A test that invokes the tool with few games and a fixed seed.

## 14. build123d: parametric terrain hex
Goal: A hexagonal prism exported to STL.
Description: In `acequias/cad/hex_tile.py`, model a parametric hexagonal prism (side, height) with build123d and export it to STL. It is the functional base of every terrain piece. A QA test that validates the STL is a closed solid (`trimesh.is_watertight`).

## 15. build123d: canal with groove, fit, and owner token
Goal: A canal piece + token that fit together with tolerance.
Description: In `acequias/cad/channel.py`, model a canal piece (hexagon with a groove) and a central hole for the owner token, plus the token that fits with a parameterizable tolerance. Export both STLs. QA tests: both are closed solids, and the relief/groove does not intrude into the fit area.

## 16. Decorative layer: relief from a height map
Goal: Turn a height map into relief over the base.
Description: In `acequias/cad/relief.py`, with trimesh and numpy, turn a grayscale height map (generated by noise/patterns or from a DEM) into a relief mesh and fuse it onto a functional hex. Intended for mountains, water ripples, and vineyard furrows. QA tests: closed mesh and minimum printable thickness (0.4 mm nozzle) respected.

## 17. MCP tool: generate_piece_stl
Goal: Expose STL generation as an MCP tool.
Description: Wrap the build123d generators (tasks 14–16) in a FastMCP tool that, given a piece type and parameters, produces the STL files and returns their paths. Dispatch and serialization only. A test that invokes the tool for each type and verifies the files are created and are closed solids.

## 18. Plate layout logic (256 × 256)
Goal: Place pieces on the bed without overlap.
Description: In `acequias/plate.py`, given a list of pieces, distribute them on a deterministic hex grid over the A1's 256 × 256 mm build plate, producing one or more plates if they don't fit on one. Return the positions per piece. Tests that no piece overlaps another or exceeds the bed.

## 19. MCP tool: build_plate
Goal: Expose `build_plate` as an MCP tool.
Description: Wrap the plate layout logic (`acequias/plate.py`) as a FastMCP tool, taking the list of pieces and returning the print plates with positions. Adaptation and serialization only. A test that invokes the tool with a known list and verifies the number of plates and positions.

## 20. Tune open parameters with the simulation
Goal: Fix rounds, board size, and bag mix.
Description: Use the simulation engine to resolve the plan's open questions (number of harvest rounds, hexes per number of players, pieces of each type in the bag), aiming for no turn order exceeding 10% advantage. Record the chosen values in `plan.md`. Adds no features: it calibrates and documents.
