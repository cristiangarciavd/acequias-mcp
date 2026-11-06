# Acequias MCP

Acequias is a competitive board game for 2 to 5 players with 3D-printed hex pieces. Players build canals to carry water from the mountains to the vineyards of Mendoza. This repo holds an MCP server that generates balanced boards, scores games, simulates them with bots to tune the rules, and outputs printable STL pieces for a Bambu Lab A1.

> **Status:** early development. The project scaffolding and the hex coordinate model are in place; the game logic comes next. Progress is tracked in the [GitHub issues](../../issues) and [milestones](../../milestones).

This README is the project's specification: game rules, design decisions, architecture, and roadmap. Task details live in the GitHub issues.

Project goals: practice MCP with a real use case (a portfolio project toward AI Solutions Architect), produce something printable on the Bambu Lab A1 and potentially sellable, and apply QA practices (automated tests, plus simulation to balance the game). No deadline: under 1 hour of work per day.

## Game rules

Whoever scores the most points when the harvest ends, after a fixed number of rounds, wins. There are two length modes, **Normal** and **Flash**, with the same rules and engine.

### Components

| Component | Detail |
| --- | --- |
| Terrain hexes | River, vineyard, stone, empty |
| Vineyards | Neutral, valued by varietal: Malbec 3 pts, Bonarda 2 pts, Torrontés 1 pt |
| Canal pieces (neutral) | Straight, gentle curve, sharp curve, Y-junction, floodgate |
| Owner tokens | One per placed canal, in each player's color |
| Grape clusters | Mark a claimed vineyard, in each player's color |
| Debt tokens | Track each player's accumulated bribe debt |
| Die (external) | One standard d6, provided by the players, used by the bribe action |

### Setup

1. The MCP generates a balanced map for the number of players and the mode.
2. The west edge is the river (the mountains); all water flows from there.
3. Four canal pieces are placed face up: the market.
4. A start player is chosen; the start player rotates each round.

### Turn

On your turn you take **one action**:

- **A. Place a piece.** Take a piece from the market (it is refilled from the bag), place it connected to the existing network, and slot in your owner token. If the move connects an unclaimed vineyard to the river, claim it with your grape cluster.
- **B. Bribe (_coima_).** See [Bribe](#bribe-coima).

### Claims and watering

A claim is permanent: once your grape cluster is on a vineyard, nobody else can claim it, even if its water is later cut off. But a vineyard only scores if it is **watered** (connected to the river) on the final board. A claimed vineyard that ends dry scores 0 and pays no water rights. Its owner can water it again by reconnecting it, or by bribing away the floodgate that blocks it.

### Turn order (_turnos de riego_)

The start player rotates each round, like the real watering turns of Mendoza's acequias, so no seat keeps the turn-order advantage (target: at most 10%).

### Water rights

If the water reaching your vineyard passes through other players' canals, you pay **1 point to each distinct other player** whose canals are on that path (not per canal). Water rights are settled **at the end of the game**, from the final board.

When a vineyard can be reached by more than one path, the water takes the **cheapest path for the vineyard's owner**:

1. Fewest distinct rival owners on the path.
2. Tie: the shortest path, counted in canals.
3. Still tied: a fixed deterministic order (hex coordinate order), so scoring is reproducible.

This rewards building your own bypass: a longer route of your own canals stops you paying water rights.

### Floodgate

The attack-and-defense piece: it blocks or diverts water. It is placed like any canal piece and can later be removed or moved only by a bribe.

### Bribe (coima)

Instead of placing a piece, you may bribe to remove or move one floodgate on the board, yours or an opponent's:

1. Roll the d6 and add the result to your public **debt**.
2. **Remove** the floodgate (back to the supply) or **move** it to another legal, connected position.
3. Water re-flows immediately.

Debt is subtracted from your final score, so a bribe is a gamble (it costs 1 to 6), and the growing cost keeps floodgate wars in check.

### Bodega bonus

A player whose watered vineyards include **each** varietal (Malbec, Bonarda, Torrontés) earns **+2**: a winery wants its blend. Flash reduces it (see Game modes).

### Game modes

| Mode | Rounds | Board | Target time |
| --- | --- | --- | --- |
| **Normal** | ~12 | ~12 hexes/player (2p 24 · 3p 36 · 4p 48 · 5p 60) | ~45–60 min |
| **Flash** | ~5 | ~7 hexes/player, river one row closer to the vineyards | ~10–20 min |

Flash is shorter in two ways: fewer rounds, and a denser board where vineyards connect in 1–2 pieces instead of 3–4. Its bodega bonus is reduced (+1, or only 2 varietals required). All values are provisional and tuned by the simulation.

### End and scoring

After the last round, each player scores:

**vineyard values + bodega bonus − water rights paid + water rights collected − bribe debt**

Only watered vineyards count toward vineyard values, the bodega bonus, and water rights.

## Physical pieces

All pieces are parametric build123d models printed on the Bambu Lab A1 (256 × 256 mm plate, 0.4 mm nozzle, PLA). The d6 is not printed.

- **Terrain hexes:** hexagonal prism, with relief depending on type
- **Canal pieces:** hexagon with a groove; neutral, single-color
- **Owner tokens:** small marker that fits a hole in the canal; in each player's color
- **Grape clusters:** figure that rests on the claimed vineyard
- **Debt tokens:** small markers, printed in small batches

### Geometry profile

| Parameter | Value |
| --- | --- |
| Hex side | 16 mm (~32 mm corner to corner); fallback 18 mm if the groove or fit is too tight |
| Tile height (functional) | 4 mm, plus decorative relief on top |
| Board footprint (4p) | ~18–20 cm across |
| Print estimate (4p set, ~50–70 hexes) | ~150–200 g PLA, ~8–12 h; rough until the real STL is sliced |

The bag of canal pieces is sized to the board's canalizable capacity, which caps how many canals need printing. Groove size and fit tolerance are still to be validated against the 0.4 mm nozzle.

### Aesthetics

Each piece has two layers, so it doesn't look "all vectors":

- **Functional** (hexagon, groove, fit): build123d, precise and repeatable.
- **Decorative** (mountain, water, vineyard): mesh relief with trimesh + numpy on top of the functional base; Blender later for organic shapes.

Relief comes from real elevation data (SRTM / Copernicus DEM) for mountain hexes, and from height maps generated in code for water ripples, vineyard furrows, and stones. QA checks: closed mesh, minimum printable thickness, and no relief in the fit area.

### Plate layout

Pieces are placed on a deterministic hex grid on the 256 × 256 mm plate, spilling onto more plates when needed.

## MCP architecture

A Python server with FastMCP (official SDK). The game logic lives in `acequias/`, independent of the server in `server/`, so it can be tested without MCP. All randomness (dice, board generation, bots) goes through a seeded RNG, so games are reproducible.

| Tool | Input | Output |
| --- | --- | --- |
| `generate_board` | Number of players, seed, mode | Balanced map and assembly instructions |
| `calculate_score` | Final board state | Points per player (vineyards + bodega − water rights − debt) |
| `simulate_game` | Rules (incl. mode), number of games | Balance statistics (turn-order advantage, varietals) |
| `generate_piece_stl` | Piece type, parameters | STL files |
| `build_plate` | List of pieces | Print plates for the A1 |

### Hex convention

`acequias/hex.py`: hexes are **pointy-top**, so east and west are direct neighbors and the river runs along the west edge. `q` grows east and `r` south (`s = -q - r`). Pixel/mm positions put the origin hex at `(0, 0)`, with `x` east and `y` south. Hexes sort by `(q, r)`, the deterministic tie-break of the water-path rule.

### Tech stack

| Layer | Tool |
| --- | --- |
| MCP server | [FastMCP](https://github.com/modelcontextprotocol/python-sdk) (official Python SDK) |
| Environment and dependencies | [uv](https://docs.astral.sh/uv/) (fallback: conda-forge if OpenCASCADE fails on Windows) |
| Logic and simulation | Pure Python, axial hex coordinates |
| Functional geometry | [build123d](https://github.com/gumyr/build123d) (OpenCASCADE; STL/STEP/3MF export), chosen over CadQuery for its API; reversible |
| Decorative relief | trimesh + numpy; Blender/bpy later |
| Elevation data | SRTM / Copernicus DEM |
| Tests and QA | pytest + hypothesis; `trimesh.is_watertight` for STL |

## Roadmap

One milestone per phase, worked in order; 4 to 6 weeks at under 1 hour per day.

1. **Game logic:** hex model, board generation with modes, scoring with bodega bonus and bribe debt.
2. **MCP server:** expose those tools with FastMCP and test them from Claude.
3. **Simulation:** bots and `simulate_game` to tune points, rounds, market, dice, and both modes.
4. **build123d pieces:** `generate_piece_stl`, with elevation relief and height maps.
5. **Plate and printing:** `build_plate` and the first print on the A1.

### Quality criteria

- [ ] Each tool has unit tests with pytest
- [ ] Every generated board has at least one reachable vineyard per player
- [ ] Turn-order advantage is at most 10%, in Normal and in Flash separately
- [ ] A Normal game takes about 45–60 min and a Flash game 10–20 min (by turn count)
- [ ] Each STL is a closed solid and fits with the other pieces

### Open questions

Provisional defaults let work start; the simulation (or CAD, for physical values) settles them.

- [ ] Normal rounds: default 12
- [ ] Flash rounds per player count: default ~5, aiming at 10–20 min
- [ ] Hexes per player: Normal ~12, Flash ~7
- [ ] Bag mix: straight 40% · gentle curve 20% · sharp curve 15% · Y-junction 15% · floodgate 10%, sized to board capacity
- [ ] Die: is the d6 (average bribe cost 3.5) balanced against vineyard values, or should it be a d8 or a success threshold?
- [ ] Flash bodega bonus: +1, or only 2 varietals required?
- [ ] Hex side: 16 mm, or the 18 mm fallback (validated in CAD and by printing)
- [ ] Flash race-end variant ("first to claim a 2nd vineyard ends the round, then score"): evaluate in the simulation before committing

## Development

```sh
uv sync          # install dependencies
uv run pytest    # run the test suite
```

## Documents

- [Process](_docs/process.md): how work is organized
- [Task template](_docs/task-template.md): the shape every issue follows
- [AGENTS.md](AGENTS.md): instructions for coding agents
- `_docs/outdated/`: superseded documents kept for history only; this README and the GitHub issues replace them
