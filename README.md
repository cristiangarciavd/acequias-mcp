# Acequias MCP

[![Tests](https://github.com/cristiangarciavd/acequias-mcp/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/cristiangarciavd/acequias-mcp/actions/workflows/tests.yml?query=branch%3Amain)

Acequias is a competitive board game for 2 to 5 players with 3D-printed hex pieces. Players build canals to carry water from the mountains to the vineyards of Mendoza. This repo holds an MCP server that generates balanced boards, scores games, simulates them with bots to tune the rules, and outputs printable STL pieces for a Bambu Lab A1.

> **Status:** early development. Milestones 1 (game logic) and 2 (MCP server) are done. Milestone 3 (simulation) is nearly done: the turn engine, the round loop, the random, greedy, and saboteur bots, and the faster simulation are in, and the server exposes `generate_board`, `calculate_score`, and `simulate_game`; only tuning the open parameters with it (#20) is left. Milestone 4 (pieces) has the terrain hex (#14) and the canal pieces, floodgate, and owner token (#15); milestone 5 has the plate layout (#18). Progress is tracked in the [GitHub issues](../../issues) and [milestones](../../milestones).

This README is the project's specification: game rules, design decisions, architecture, and roadmap. Task details live in the GitHub issues.

Project goals: practice MCP with a real use case (a portfolio project toward AI Solutions Architect), produce something printable on the Bambu Lab A1 and potentially sellable, and apply QA practices (automated tests, plus simulation to balance the game). No deadline: under 1 hour of work per day.

## Game rules

Whoever scores the most points when the harvest ends, after a fixed number of rounds, wins. There are two length modes, **Normal** and **Flash**, with the same rules and engine.

### Components

| Component | Detail |
| --- | --- |
| Terrain hexes | River, vineyard, stone, empty |
| Vineyards | Neutral, valued by varietal: Malbec 3 pts, Bonarda 2 pts, Torrontés 1 pt |
| Canal pieces (neutral) | Six shapes: straight, gentle curve, sharp curve, symmetric Y, T branch, claw (see [Water flow](#water-flow)) |
| Floodgates | Small gates that close one opening of a canal piece (see [Floodgate](#floodgate)) |
| Owner tokens | One per placed canal, in each player's color |
| Grape clusters | Mark a claimed vineyard, in each player's color |
| Debt tokens | Track each player's accumulated bribe debt |
| Die (external) | One standard d6, provided by the players, used by the bribe action |

### Setup

1. The MCP generates a balanced map for the number of players and the mode. No vineyard is ever next to the river: each needs at least one canal to be watered.
2. The west edge is the river (the mountains); all water flows from there.
3. The bag holds one piece per empty hex (the board's canalizable capacity), split by the bag mix. It is shuffled and four pieces are placed face up: the market. There is no redraw, even if the market holds only floodgates.
4. A start player is chosen; the start player rotates each round.

### Turn

On your turn you take **one action**:

- **A. Place a piece.** Take a piece from the market (it is refilled from the bag; when the bag is empty the market shrinks).
  - A **canal** goes on an empty hex, with your owner token. At least one of its openings must line up with the river or with an opening of any canal already on the board, even a dry one or one closed by a floodgate. Its other openings may face anything: dead ends are allowed.
  - A **floodgate** goes on any open opening of any canal on the board, yours or a rival's (see [Floodgate](#floodgate)).
- **B. Bribe (_coima_).** See [Bribe](#bribe-coima).
- **Pass**, only when you have nothing you can place. Bribing is never forced.

Rules note: a small board can lock up. Once every canal opening faces another canal, stone, a vineyard, or the board edge, no canal can be placed anywhere; if no floodgate can be placed or bribed either, **Pass** is the only legal action for the rest of the game. This follows the rules as written; the round loop still ends at its round count.

### Water flow

- Water enters a canal through an opening that faces the river.
- Water crosses between two neighbouring canals only where **both** have an opening facing each other.
- Inside a piece, water reaches all of its openings.
- A vineyard is watered when a canal carrying water has an opening facing it. Vineyards are **end points**: water does not pass through them.

Canal shapes, by the hex edges they open (pointy-top hexes, so the edges face E, NE, NW, W, SW, SE; rotate a piece to point it any way):

| Shape | Openings at rotation 0 |
| --- | --- |
| Straight | E, W (opposite edges) |
| Gentle curve | E, NW (two edges apart) |
| Sharp curve | E, NE (neighbouring edges) |
| Symmetric Y | E, NW, SW (every other edge) |
| T branch | E, W, NE (a straight line with one side branch) |
| Claw | E, NE, NW (three neighbouring edges) |

### Claims and watering

After **any** action (a placement or a bribe), the acting player claims **every** unclaimed vineyard that is now watered. A claim is permanent: once your grape cluster is on a vineyard, nobody else can claim it, even if its water is later cut off. But a vineyard only scores if it is **watered** (connected to the river) on the final board. A claimed vineyard that ends dry scores 0 and pays no water rights. Its owner can water it again by reconnecting it, or by bribing away the floodgate that blocks it.

### Turn order (_turnos de riego_)

Each round, every player takes one turn in seat order, starting with the start player and wrapping around. The start player moves to the next seat each round, like the real watering turns of Mendoza's acequias, so no seat keeps the turn-order advantage (target: at most 10%).

### Water rights

If the water reaching your vineyard passes through other players' canals, you pay **1 point to each distinct other player** whose canals are on that path (not per canal). Each vineyard pays separately: two of your vineyards fed through the same rival pay that rival 2. Water rights are settled **at the end of the game**, from the final board.

When a vineyard can be reached by more than one path, the water takes the **cheapest path for the vineyard's owner**:

1. Fewest distinct rival owners on the path (on an unclaimed vineyard, every owner counts as a rival).
2. Tie: the shortest path, counted in canals.
3. Still tied: the path whose hexes, from the river end, come first in hex coordinate order, so scoring is reproducible.

This rewards building your own bypass: a longer route of your own canals stops you paying water rights.

### Floodgate

The attack-and-defense piece. A floodgate is a small gate placed on **one opening** of a canal piece (any player's), and water cannot cross that edge in either direction:

- On a piece's **entrance**, it blocks all the water coming in, so that piece and everything downstream go dry.
- On one **exit**, it blocks only that way onward; the piece's other exits keep flowing.
- On an opening facing the river it closes that intake; on one facing a vineyard it cuts that vineyard off.

Only one floodgate fits on an edge. Once placed, it can be removed or moved only by a bribe.

### Bribe (coima)

Instead of placing a piece, you may bribe to remove or move one floodgate on the board, yours or an opponent's:

1. Roll the d6 and add the result to your public **debt**.
2. **Remove** the floodgate (it leaves the game for good) or **move** it to another open edge of a canal.
3. Water re-flows immediately.

Debt is subtracted from your final score, so a bribe is a gamble (it costs 1 to 6), and the growing cost keeps floodgate wars in check.

### Bodega bonus

A player whose watered vineyards include **each** varietal (Malbec, Bonarda, Torrontés) earns **+2**: a winery wants its blend. In Flash it is **+1**, still for all three.

### Game modes

| Mode | Rounds | Board | Target time |
| --- | --- | --- | --- |
| **Normal** | ~12 | ~12 hexes/player (2p 24 · 3p 36 · 4p 48 · 5p 60) | ~45–60 min |
| **Flash** | ~5 | ~7 hexes/player, river one row closer to the vineyards | ~10–20 min |

Flash is shorter in two ways: fewer rounds, and a denser board where vineyards connect in 1–2 pieces instead of 3–4. Its bodega bonus is reduced to +1. Both modes start with 2 vineyards per player and 10% stone hexes. All values are provisional and tuned by the simulation; they live in `acequias/config.py` (see [Game config](#game-config)).

### End and scoring

After the last round, each player scores:

**vineyard values + bodega bonus − water rights paid + water rights collected − bribe debt**

Only watered vineyards count toward vineyard values, the bodega bonus, and water rights.

The highest score wins. On a tie, the tied player with more watered vineyards wins; if that is tied too, the win is shared.

### Variants (under evaluation)

Optional rules, off by default, kept only if the simulation shows they help:

- **Flash race end:** the first player to claim a 2nd vineyard ends the round; then score.
- **Drought (_sequía_):** in some mid-game rounds part of the river runs dry. It never falls on the last round, so final scoring always uses the full river.

## Physical pieces

All pieces are parametric build123d models printed on the Bambu Lab A1 (256 × 256 mm plate, 0.4 mm nozzle, PLA). The d6 is not printed.

- **Terrain hexes:** hexagonal prism, with relief depending on type
- **Canal pieces:** hexagon with a groove; neutral, single-color
- **Floodgates:** small gates that slot into the groove at one opening
- **Owner tokens:** small marker that fits a hole in the canal; in each player's color
- **Grape clusters:** figure that rests on the claimed vineyard
- **Debt tokens:** small markers, printed in small batches

### Geometry profile

| Parameter | Value |
| --- | --- |
| Hex side | 16 mm (~32 mm corner to corner); fallback 18 mm if the groove or fit is too tight |
| Tile height (functional) | 4 mm, plus decorative relief on top |
| Canal groove | 6 mm wide, 1.5 mm deep |
| Owner token | hole 4 mm across, 2 mm deep; cap 7 mm across, 1.2 mm high |
| Floodgate | 5.70 × 2.00 × 1.50 mm (groove width minus a 0.15 mm fit tolerance per side, flush with the top) |
| Thinnest wall | 0.8 mm (two widths of the 0.4 mm nozzle) |
| Board footprint (4p) | ~18–20 cm across |
| Print estimate (4p set, ~50–70 hexes) | ~150–200 g PLA, ~8–12 h; rough until the real STL is sliced |

The bag of canal pieces is sized to the board's canalizable capacity, which caps how many canals need printing. The piece sizes are the code's defaults and stay provisional until the first test print (#34) validates the groove and the fit tolerance.

### Aesthetics

Each piece has two layers, so it doesn't look "all vectors":

- **Functional** (hexagon, groove, fit): build123d, precise and repeatable.
- **Decorative** (mountain, water, vineyard): mesh relief with trimesh + numpy on top of the functional base; Blender later for organic shapes.

Relief comes from real elevation data (SRTM / Copernicus DEM) for mountain hexes, and from height maps generated in code for water ripples, vineyard furrows, and stones. QA checks: closed mesh, minimum printable thickness, and no relief in the fit area. The decorative layer comes after the MVP (see [MVP](#mvp)); MVP pieces are functional only.

### Plate layout

Pieces are placed on a deterministic hex grid on the 256 × 256 mm plate, spilling onto more plates when needed.

`acequias/plate.py` (pure layout math, standard library only): `layout_plates(pieces)` takes `Piece`s with a footprint (`HexFootprint`, `CircleFootprint`, or `RectFootprint`, in mm) and a color group, and returns numbered `Plate`s of `Placement`s: each footprint's center from the bed's front-left corner, rotation always 0. Hexes go on a honeycomb grid spaced so neighbours are exactly `gap` apart; circles and rectangles go on a square grid of bounding-box cells. Each plate holds one color group and one grid type, so it prints with one filament; within a group every cell is sized to the largest piece and plates fill in input order. With the defaults (256 × 256 bed, 5 mm margin, 3 mm gap) a plate holds 68 hexes of 16 mm, 52 of 18 mm, or 256 circles of 12 mm.

## MCP architecture

A Python server built on `MCPServer` from the official `mcp` SDK (formerly FastMCP). The game logic lives in `acequias/`, independent of the server in `server/`, so it can be tested without MCP. All randomness (dice, board generation, bots) goes through a seeded RNG, so games are reproducible.

| Tool | Input | Output |
| --- | --- | --- |
| `generate_board` | `players` (2 to 5), `mode`, optional `seed` | `players`, `mode`, the `seed` used, `hexes`, and `assembly` instructions |
| `calculate_score` | `mode`, `hexes`, `players` (id and debt), optional `canals`, `floodgates`, `claims` | `mode`, `scores` per player by term (vineyards + bodega − rights paid + rights collected − debt) with the watered vineyards and their paths, and `winners` |
| `simulate_game` | `mode`, `players`, optional `games` (1 to `MAX_GAMES`, default 10), `policies` (one per seat, default all `"greedy"`), `overrides` (preset values, in the shape of the result's `preset` without `mode`), `seed` | `SimResult.to_json()` unchanged: the statistics, plus the inputs, the `seed` used, and every preset value after overrides |
| `generate_piece_stl` | Piece type, parameters | STL files |
| `build_plate` | List of pieces | Print plates for the A1 |

`simulate_game` caps `games` at `MAX_GAMES = 10`, set when a 5-player Normal game of greedy bots took about 2 s, so 10 games kept one call within a 30-second client timeout; since #84 such a game takes under 0.1 s. Raising the cap is #43.

### Hex convention

`acequias/hex.py`: hexes are **pointy-top**, so east and west are direct neighbors and the river runs along the west edge. `q` grows east and `r` south (`s = -q - r`). Pixel/mm positions put the origin hex at `(0, 0)`, with `x` east and `y` south. Hexes sort by `(q, r)`, the deterministic tie-break of the water-path rule. Sizes must be finite and greater than 0, or the conversions raise `ValueError`. `Direction.rotated(steps)` turns a direction `steps` × 60° counterclockwise, in `Direction` order (E → NE → NW → W → SW → SE); negative steps turn clockwise. `Hex.corners(size)` gives the 6 corner points in the same plane, counterclockwise from just below east (ESE, ENE, N, WNW, WSW, S), so the edge from corner `i` to `i + 1` faces the `i`-th `Direction`.

### Domain model

`acequias/model.py`: types and their invariants, no game logic. Every value is immutable, so an update builds a new one, and collections are kept in hex order, so two boards with the same contents are equal whatever order they were built in. Players are referenced by string id: canal owners, claims, and the start and current player. Claims live on the board as vineyard hex → player id; a vineyard with no claim is unclaimed. A canal's openings at a rotation (0 to 5, each 60° counterclockwise) are a `frozenset` of `Direction`s, so rotations that open the same edges compare equal. A floodgate sits on an edge, not a hex: it is identified by that edge, so the same gate given from either side is equal, and an edge holds at most one. `Board` checks where pieces may sit; `GameState` checks that every id belongs to one of its 2 to 5 players.

### Game config

`acequias/config.py`: every number the game needs, as one immutable `Preset` per mode, fetched with `preset(mode)`. Board generation, setup, scoring, the round loop, and the simulation read their values from it and hard-code none. Tuning changes the shipped values there; experiments build variants with `with_overrides`, which validates them like the shipped presets. Shares (stone hexes, bag mix) are whole-number percentages, and rounds are set per player count so they can differ later.

### Water reach

`acequias/flow.py`: `water(board)` maps every watered vineyard, claimed or not, to the one `WaterPath` its water takes; dry vineyards are absent. A path's `canals` run from the river end to the vineyard, and its `owners` include the claimant's own id, so scoring removes the claimant when it counts water rights. Path choice uses the vineyard's claimant on the board. The module is pure and deterministic.

### Board generator

`acequias/board.py`: `generate_board(players, seed, mode, *, preset=None)` returns a `Board` with tiles only. Equal arguments give an equal board, in any process; all randomness comes from one `random.Random(seed)`. `preset` (from `with_overrides`) replaces the shipped one for the simulation, and must have the same mode. Each row is a river hex on the west followed by an unbroken run of hexes east, and the river zigzags south as one chain, so a hex `k` steps east of its river hex is `k` from the river. Vineyards are placed in the preset's distance range and a layout is kept only if at least as many vineyards as players are reachable through empty hexes; a preset that cannot be met (e.g. a distance range the rows cannot hold, or no layout within the retry cap) raises `ValueError`.

### Assembly instructions

`acequias/assembly.py`: `assembly_instructions(board)` lists one `AssemblyStep` per tile, ignoring canals, floodgates, and claims. Steps go row by row from north to south and west to east; rows and positions count from 1 (row 1 is the northernmost, whatever its `r`). Each step holds `row`, `position`, the axial `hex` for programs, `terrain`, `varietal` (vineyards only), and the `text` a person reads, e.g. `"Row 2, hex 3: vineyard, Malbec"`. Because rows are staggered, hex 1 of every row after row 1 also names the hex above it that it touches (`"south-east of row 1, hex 1"`, the north-west neighbour preferred); on generated boards that is the river, hex 1 of the row above. A board that cannot be laid out row by row (a skipped `r`, a gap in a row, or a row that does not touch the one above) raises `ValueError` naming the row.

### Scoring

`acequias/scoring.py`: `calculate_score(state, preset=None)` scores a `GameState` as given, whatever its round, and changes nothing; with `preset=None` the bodega values come from `state.preset`, or `preset(state.mode)` when that is `None`, and an explicit preset from `with_overrides` replaces them. It returns a read-only mapping of player id → `Score`, in seat order, with the terms `vineyards`, `bodega`, `rights_paid`, `rights_collected`, `debt`, and `total` (the names the MCP tool exposes), plus `watered` (the tie-break count) and `watered_vineyards`: each watered claimed vineyard in hex order, with its varietal, its `WaterPath`, and the rivals it `pays` in seat order. `winners(scores)` returns the winning ids in seat order: highest `total`, then highest `watered`, otherwise a shared win. Debt is only read from `Player.debt`; bribes add to it.

### Game setup

`acequias/setup.py`: `new_game(players, seed, mode, *, preset=None)` returns the starting `GameState`: the board from `generate_board` with the same arguments, players `"p1"` to `"pN"` in seats 1 to N with no debt, round 1, and `current_player` equal to `start_player`. It always sets `GameState.preset` to the preset it used (the shipped one when none is passed); every later step (turn engine, round loop, scoring, simulation) reads the game's numbers from `state.preset` and keeps it in every state it builds. `GameState.preset` may be `None` only on hand-built states, which then fall back to `preset(state.mode)`. `bag_counts(total, preset)` splits the bag by `bag_mix` with the largest remainder method (ties in `PieceKind` order). One `random.Random(seed)` shuffles the pieces and then picks the start player; the market is the first `market_size` pieces and the bag the rest, with `bag[0]` the next piece drawn.

### Turn engine

`acequias/turn.py`: the actions are frozen dataclasses `PlaceCanal(kind, hex, rotation)`, `PlaceFloodgate(hex, direction)`, `Bribe(hex, direction, to=None)` (`to=(hex, direction)` moves the floodgate, `None` removes it), and `Pass()`. `apply(state, player, action, rng)` returns a new state and never changes its input; it leaves `current_player`, `start_player`, and `round` untouched, since turn order belongs to the round loop. The caller owns `rng`: only a legal bribe draws from it, with exactly one `rng.randint(1, die_faces)` after every check, so replaying a game needs the same `rng` stream. A placement takes the first copy of its kind from the market and appends `bag[0]`. An illegal action raises `IllegalAction` (a `ValueError`) naming the broken rule; an unknown player raises `ValueError` and a non-action `TypeError`. `legal_actions(state, player)` returns every legal action once, in a fixed order (canals, floodgates, bribes, then pass), in a canonical spelling: the smallest rotation that opens the same edges, and a floodgate edge named from the canal side with the smaller hex. `apply` accepts any equivalent spelling and gives the same state.

### Round loop

`acequias/game.py`: a turn is one action, through `act(state, player, action, rng)`, which checks that it is `state.current_player`'s turn and that the game is not over (before `apply`, so `rng` is untouched on a refusal), then advances the turn. `turn_order(state, round)` gives the acting order of any round: seat order (by `Player.seat`, wrapping), from that round's start player, which moves to the next seat each round. The round count is `rounds_for(len(players))` from `state.preset` (or `preset(state.mode)`); after the last turn the state has `round == rounds + 1`, which is what `game_over(state)` checks, so no `GameState` field marks the end. `play_game(state, bots, dice_rng, bot_rng)` plays to the end and returns the final state and a log of `TurnRecord(round, player, action)`; a bot's illegal action raises, it never becomes a pass. Dice and bots draw from separate RNGs, so the dice stream does not depend on how many numbers the bots draw: `replay(state, log, dice_rng)` rebuilds the final state from the log with a same-seeded `dice_rng` and no bots. `game_rngs(seed)` returns `(dice_rng, bot_rng)`, seeded from strings so both differ from `new_game`'s `random.Random(seed)`; a game is identified by `new_game`'s arguments, the seed, and the bot policies.

### Bots

`acequias/bots.py`: a bot is a plain function `decide(state, player, rng)` (the `Bot` type in `game.py`) that returns one element of `legal_actions(state, player)`, keeps no state, and draws only from `rng`. `POLICIES` maps names to bots (read-only) and `policy(name)` looks one up, listing the valid names when it is unknown. `random` picks with one `rng.choice` over every legal action. `greedy` weighs only this move and only vineyard points, with no lookahead: the canal that claims the most points now, else the one nearest the most valuable unclaimed vineyard, else a floodgate on a rival's canal; it never bribes, passing instead, and breaks ties with `rng.choice`. `saboteur` values each non-pass action by its swing in watered vineyard points (own minus rivals'), minus the expected bribe cost `(die_faces + 1) / 2` for a bribe; it plays the best action worth more than 0 and otherwise falls back to `greedy`.

### Simulation

`acequias/sim.py`: `simulate_game(rules, n, seed)` plays `n` bot games of one mode and returns a `SimResult`. `SimRules` holds `mode`, `players`, `policies` (`policies[k]` plays seat `k + 1`, whatever the start player), and `overrides` for `with_overrides`; the resulting preset is passed only to `new_game`, and every later step reads it from `state.preset`. Game `i` uses `game_seed(seed, i)`, and `play_one(rules, game_seed)` replays any single game of a run. A board the preset cannot satisfy raises `ValueError` naming the game index and seed, with no partial result. A shared win among `k` players gives each `1/k` win credit, so each game hands out exactly 1. Position `j` is the place in round 1's turn order, and `turn_order_advantage` is `max_j |win_rate_by_position[j] − 1/P| × P` (0.10 means a position wins 10% more or less than its fair share). Each statistic is defined in its field's docstring; `SimResult.to_json()` gives plain JSON with the names of `server/schemas.py`.

### Performance

The engine and the bots take fast paths (precomputed tables, boards derived without re-validation) whose results must equal the plain rules. `tests/test_golden_games.py` replays fixed simulation runs against `tests/data/golden_games.json`, recorded before the speed-up, so any change in a log, a final state, a path, or a score fails; re-record it only when the rules change on purpose. `uv run python scripts/bench_sim.py` prints the best wall time of fixed 5-player runs and a SHA-256 of each result (equal digests mean nothing moved); `--profile` lists the hottest functions.

### CAD pieces

`acequias/cad/` holds the build123d models; it is the only code that imports build123d or trimesh, and the game logic and the server never import it at module level, so a plain install stays CAD-free. CAD frame: `x` east, `y` north, `z` up, in mm, each piece centered at `x = y = 0` with its bottom on `z = 0`; outlines come from `Hex.corners`, each corner `(x, y)` used as `(x, -y)`, so each edge faces the same `Direction` as on the board. `hex_tile.py`: `hex_tile(side, height, clearance)` is the terrain prism and `export_stl(shape, path)` writes a binary STL. `channel.py`: `canal_piece(kind)` is the tile with a groove spoke to each edge the kind opens at rotation 0 (players rotate the printed piece) and a hole for the owner token; `floodgate()` is the gate as it sits in the groove; `owner_token()` is a cap with a peg, printed cap down. Defaults are those of the [Geometry profile](#geometry-profile); any size that would leave a wall under 0.8 mm raises `ValueError` naming it.

### Board JSON

`server/schemas.py`: the JSON shapes every tool shares, so a board means the same JSON everywhere. A hex is `q`, `r`, `terrain`, and `varietal` (null except on vineyards). Enum strings are lowercase ASCII: terrain `"river"`, `"vineyard"`, `"stone"`, `"empty"`; varietal `"malbec"`, `"bonarda"`, `"torrontes"`; canal `kind` `"straight"`, `"gentle_curve"`, `"sharp_curve"`, `"symmetric_y"`, `"t_branch"`, `"claw"` (the floodgate is not a kind). Directions are the case-sensitive names `"E"`, `"NE"`, `"NW"`, `"W"`, `"SW"`, `"SE"`. A canal is `q`, `r`, `kind`, `rotation` (0 to 5), `owner`; a floodgate is the canal's `q`, `r` and the `direction` it closes; a claim is `q`, `r`, `player`; a player is `id` and `debt`, and the list order gives seats 1 to N. From a `generate_board` result only `mode` and `hexes` carry over to `calculate_score`: its `players` is a count, not a list, and `seed` and `assembly` are not inputs. Inputs are strict (`"3"`, `3.0`, or `true` is not an int), and the server only maps JSON to `acequias` types; every check comes from the model.

### Tech stack

| Layer | Tool |
| --- | --- |
| MCP server | [`mcp`](https://github.com/modelcontextprotocol/python-sdk) 2.x (official Python SDK), class `MCPServer` (formerly FastMCP) |
| Environment and dependencies | [uv](https://docs.astral.sh/uv/) (fallback: conda-forge if OpenCASCADE fails on Windows) |
| Logic and simulation | Pure Python, axial hex coordinates |
| Functional geometry | [build123d](https://github.com/gumyr/build123d) (OpenCASCADE; STL/STEP/3MF export), chosen over CadQuery for its API; reversible. In the optional `cad` extra |
| Decorative relief | trimesh + numpy, in the optional `cad` extra; Blender/bpy later |
| Elevation data | SRTM / Copernicus DEM |
| Tests and QA | pytest + hypothesis; `trimesh.is_watertight` for STL |

## Roadmap

One milestone per phase, worked in order; 4 to 6 weeks at under 1 hour per day. Milestones 1 to 5 are the MVP; milestone 6 holds everything after it.

1. **Game logic:** hex model, board generation with modes, scoring with bodega bonus and bribe debt.
2. **MCP server:** expose those tools with FastMCP and test them from Claude.
3. **Simulation:** bots and `simulate_game` to tune points, rounds, market, dice, and both modes.
4. **build123d pieces:** `generate_piece_stl` for plain functional pieces: terrain hexes, the six canal shapes, floodgates, and tokens.
5. **Plate and printing:** `build_plate`, 3MF plates, and the first print on the A1.
6. **After the MVP (lower priority):** decorative relief, variants, and extras; started only once milestones 1 to 5 are closed.

### MVP

The MVP is a **playable, printable Acequias set** for 2 to 5 players, in Normal and Flash, run from Claude through the 5 MCP tools, with rules balanced by simulation.

It is done when:

- [ ] All 5 MCP tools work from Claude: `generate_board`, `calculate_score`, `simulate_game`, `generate_piece_stl`, `build_plate`
- [ ] The full rules above play end to end in the engine, in both modes, with bots
- [ ] Turn-order advantage is at most 10% in both modes, and the tuned values are recorded here
- [ ] Every piece needed to play (terrain hexes, six canal shapes, floodgates, owner tokens, grape clusters, debt tokens) is generated as a closed STL and laid out on A1 plates as 3MF
- [ ] The first test print passes its fit check (#34)
- [ ] CI runs the whole suite on every pull request (#44)

**In the MVP** (milestones 1–5): #3–#15, #17–#22, #28–#31, #33, #34, #44, #45.

**After the MVP** (milestone 6, lower priority), each with its own issue:

| Area | Issues |
| --- | --- |
| Looks | Height-map relief #16, real elevation relief #32, Blender shapes #36 |
| Rule variants | Drought #23 and its marker #40, Flash race end #35 |
| Tooling | STEP/3MF per piece #37, board picture #39, faster simulation #43, lookahead bot #42 |
| Product | Full game-set piece list #38, rulebook, packaging, and cost #41 |

MVP pieces are plain and functional; the decorative layer below comes after the MVP.

### Quality criteria

- [ ] Each tool has unit tests with pytest
- [ ] Every generated board has at least one reachable vineyard per player
- [ ] Turn-order advantage is at most 10%, in Normal and in Flash separately
- [ ] A Normal game takes about 45–60 min and a Flash game 10–20 min, estimated at 1 minute per turn
- [ ] Each STL is a closed solid and fits with the other pieces

### Open questions

Provisional defaults let work start; the simulation (or CAD, for physical values) settles them.

- [ ] Normal rounds: default 12
- [ ] Flash rounds per player count: default ~5, aiming at 10–20 min
- [ ] Hexes per player: Normal ~12, Flash ~7
- [ ] Bag mix: straight 40% · gentle curve 20% · sharp curve 15% · symmetric Y 5% · T branch 5% · claw 5% · floodgate 10%, sized to board capacity
- [ ] Vineyards per player: default 2, both modes
- [ ] Stone hexes: default 10% of the non-river hexes
- [ ] Vineyard distance from the river: Normal 4–5 hexes (3–4 canals), Flash 2–3 (1–2 canals)
- [ ] Die: is the d6 (average bribe cost 3.5) balanced against vineyard values, or should it be a d8 or a success threshold?
- [ ] Flash bodega bonus: default +1 for all three varietals
- [ ] Hex side: 16 mm, or the 18 mm fallback (validated in CAD and by printing)
- [ ] Flash race-end variant: evaluate in the simulation before committing (see [Variants](#variants-under-evaluation))

## Development

```sh
uv sync              # install dependencies (game logic and server)
uv sync --extra cad  # also install build123d and trimesh, for the CAD pieces
uv run pytest        # run the test suite
```

Without the `cad` extra the CAD tests are skipped; CI installs it, so they run there.

### Running the MCP server

`uv run acequias-server` starts the server over stdio (`server/app.py`). It exposes `generate_board`, `calculate_score`, `simulate_game`, and `ping`, which returns `"pong"` as a connection check.

Claude Code (replace the path with your checkout):

```sh
claude mcp add acequias -- uv run --directory /path/to/ProyAcequiasMCP acequias-server
```

Claude Desktop, in `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "acequias": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/ProyAcequiasMCP", "acequias-server"]
    }
  }
}
```

Then ask Claude to "call the acequias ping tool"; it should answer `pong`. Next, ask it to generate a 3-player Flash board and score it with no pieces placed: every player scores 0 and shares the win. In Claude Code, `/mcp` shows whether the server is connected.

Each tool lives in `server/tools/` and is registered in `server/app.py` on the module-level `app`, as `app.tool()` over `tool_errors`: a `ValueError` or `TypeError` from `acequias` comes back as a tool error with its message, and any other exception as a tool error with a generic message. Tests connect `mcp.Client(app)` in-process (`tests/test_server.py`).

## Documents

- [Process](_docs/process.md): how work is organized
- [Task template](_docs/task-template.md): the shape every issue follows
- [AGENTS.md](AGENTS.md): instructions for coding agents
- `_docs/outdated/`: superseded documents kept for history only; this README and the GitHub issues replace them
