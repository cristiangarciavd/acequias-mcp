> **OUTDATED — do not use as context.** This file is kept only for history. `README.md` (specification) and the GitHub issues (tasks) replace it. Agents: do not read further unless the user asked for this file by name.

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
Description: Define in `acequias/model.py` the terrain types (river, vineyard, stone, empty), the varietals with their score (Malbec 3, Bonarda 2, Torrontés 1), the canal pieces (straight, gentle curve, sharp curve, Y-junction, floodgate), the game mode (normal/flash), and the board and player state structures, including each player's accumulated bribe debt. Only dataclasses/enums and their invariants, with tests that verify the score values and the validity of the types.

## 4. Balanced board generator
Goal: `generate_board(players, seed, mode)`, deterministic.
Description: In `acequias/board.py`, generate a hex map based on the number of players and the mode (normal/flash), with the west edge as the river and neutral vineyards distributed across it. The mode controls size and density: normal is ~12 hexes/player; flash is ~7 hexes/player with the river one row closer to the vineyards. It must be reproducible by seed and guarantee at least one vineyard reachable per player. Include tests for determinism (same seed → same map), the reachability invariant, and that flash boards are smaller/denser than normal.

## 5. Water reach and canal path
Goal: Which vineyards reach the river, and through which canals.
Description: In `acequias/flow.py`, given a board and the placed canal pieces, compute which vineyards are connected to the river and the list of canals (with their owner) each connection passes through. It is a pure graph traversal, feeding scoring and water rights. Tests with hand-built cases, including a floodgate block.

## 6. Scoring with water rights, bodega bonus, and bribe debt
Goal: `calculate_score(state)` with points per player.
Description: In `acequias/scoring.py`, from the final board state, compute each player's score as vineyard values + bodega bonus − water rights paid + water rights collected − bribe debt. Water rights pay 1 point to each distinct other player whose canals are on the water path. The bodega bonus is +2 for holding at least one vineyard of each varietal (reduced in flash mode). Return the score per player. Include tests with hand-worked examples covering each term.

## 7. Turn engine and move validation
Goal: Apply a legal action to the state.
Description: In `acequias/turn.py`, validate and apply a turn action, which is one of: (a) place a piece — pick from the market, place it connected to the network, slot in the owner token, claim a vineyard if applicable, and replenish the market; or (b) bribe — roll a d6 via the seeded RNG, add the result to the player's debt, and remove or move an existing floodgate to a legal position. Reject illegal actions with a clear error. Tests for valid placements, invalid placements, market replenishment, and a bribe that moves/removes a floodgate and accrues debt.

## 8. Simple-policy bots
Goal: Bots that choose legal moves.
Description: In `acequias/bots.py`, implement a `decide(state) -> move` interface with at least two policies: a random one and a greedy one (prioritizes claiming higher-value vineyards). They feed the simulation. Tests that verify each bot always produces a legal move.

## 9. Simulation engine and balance statistics
Goal: `simulate_game(rules, n)` with balance metrics.
Description: In `acequias/sim.py`, run N games with bots across the fixed rounds and collect balance statistics (turn-order advantage, distribution of winning varietals, average score, average turns). All randomness (board, bots, the bribe d6) runs through a seeded RNG so runs are reproducible. It must support both modes and report stats per mode. Tests for determinism and for the shape of the statistics.

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
Goal: Fix rounds, board size, bag mix, and die for both modes.
Description: Use the simulation engine to resolve the plan's open questions for Normal and Flash (rounds per mode, hexes per number of players, pieces of each type in the bag, whether the d6 bribe cost is balanced, and the flash bodega bonus), aiming for no turn order exceeding 10% advantage in either mode and the target play times (Normal ~45–60 min, Flash ~10–20 min by turn count). Record the chosen values in `plan.md`. Adds no features: it calibrates and documents.

## 21. Rotating start player (turnos de riego)
Goal: Start player rotates each round.
Description: In the game/round loop (`acequias/turn.py` or a small `acequias/game.py`), rotate which player goes first each round so no seat keeps the first-move edge. Expose the per-round turn order so the simulation can measure turn-order advantage. Tests that over a full game each player leads a fair share of rounds and the order is deterministic given a seed.

## 22. Game mode presets and config
Goal: One place that defines Normal and Flash.
Description: In `acequias/config.py`, define the Normal and Flash presets (rounds, hexes per player, flash river offset, flash bodega value) that board generation, scoring, and the simulation read from. Wire the mode through so a full game runs end-to-end in each mode. Keep values provisional, to be tuned by task 20. Tests that each mode loads a coherent preset and that a full game completes in both.

## 23. Drought event (Sequía) — later
Goal: Optional event that tightens the water supply.
Description: Later/optional. Add an event where, in one or more rounds, the river feeds fewer edges and competition for water rises. It touches `acequias/flow.py` (restricted sources) and the round loop (event timing). Gate it behind a rule flag so Normal and Flash are unaffected unless enabled, and evaluate its balance in the simulation before making it default.
