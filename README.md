# Acequias MCP

[![Tests](https://github.com/cristiangarciavd/acequias-mcp/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/cristiangarciavd/acequias-mcp/actions/workflows/tests.yml?query=branch%3Amain)

Acequias is a competitive board game for 2 to 5 players with 3D-printed hex pieces. Players build canals to carry water from the mountains to the vineyards of Mendoza. This repo holds an MCP server that generates balanced boards, scores games, simulates them with bots to tune the rules, and outputs printable STL pieces for a Bambu Lab A1.

> **Status:** the MVP (milestones 1 to 5) is done: the game logic, the MCP server with all 5 tools, the simulation that tuned the rules (#20, [results](#tuning-results)), every MVP piece as STL, and A1 plates as 3MF, confirmed by the first test print (#34, [report](_docs/test-print-1.md)). After the MVP, the `score_aware` and `lookahead` bots (#67, #42) and a parallel, resumable `scripts/tune.py` (#43) are done. The remaining work is milestone 6, After the MVP: Rules v2 (#114) adds opt-in rule options (varietal roulette, more plots, grape-cluster cap, action die, larger score scale) to the engine, off in the shipped presets until the re-tuning in #103; its pieces are #113. Progress is tracked in the [GitHub issues](../../issues) and [milestones](../../milestones).

This README is the project's specification: game rules, design decisions, architecture, and roadmap. Task details live in the GitHub issues.

Project goals: practice MCP with a real use case (a portfolio project toward AI Solutions Architect), produce something printable on the Bambu Lab A1 and potentially sellable, and apply QA practices (automated tests, plus simulation to balance the game). No deadline: under 1 hour of work per day.

## Game rules

Whoever scores the most points when the harvest ends, after a fixed number of rounds, wins. There are two length modes, **Normal** and **Flash**, with the same rules and engine.

### Components

| Component | Detail |
| --- | --- |
| Terrain hexes | River, vineyard, stone, empty |
| Vineyards | Neutral, valued by varietal: Malbec 3 pts, Bonarda 2 pts, Torrontés 1 pt (the default fixed rules; the [varietal roulette](#varietal-roulette) variant plants 8 varietals on claim instead) |
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

With the [grape-cluster cap](#variants-under-evaluation) (a preset option, off in the shipped game), each player has a limited number of grape clusters. The acting player claims the newly watered vineyards in ascending hex order until their clusters run out; the rest stay unclaimed and watered, and the next player who places a piece or bribes (not a pass) and still has clusters claims them. Claims are never given up or moved.

### Turn order (_turnos de riego_)

Each round, every player takes one turn in seat order, starting with the start player and wrapping around. The start player moves to the next seat each round, like the real watering turns of Mendoza's acequias, so no seat keeps the turn-order advantage (target: at most 10%).

### Water rights

If the water reaching your vineyard passes through other players' canals, you pay **1 point to each distinct other player** whose canals are on that path (not per canal). Each vineyard pays separately: two of your vineyards fed through the same rival pay that rival 2. Water rights are settled **at the end of the game**, from the final board. The 1 point is the shipped preset value `water_right_points`; a larger score scale (#111, `scaled`) raises it with the other points.

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

The bribe is the default rule. The [action die](#action-die) variant replaces it (a preset option, off in the shipped game).

### Bodega bonus

A player whose watered vineyards include **each** varietal (Malbec, Bonarda, Torrontés) earns **+2**: a winery wants its blend. In Flash it is **+1**, still for all three. These are the default fixed rules; under the [varietal roulette](#varietal-roulette) the bonus needs watered vineyards of any 3 **different** varietals (two Malbecs count once).

### Game modes

| Mode | Rounds | Board | Target time |
| --- | --- | --- | --- |
| **Normal** | 2p 10 · 3p 15 · 4p 12 · 5p 10 | 15 hexes/player (2p 30 · 3p 45 · 4p 60 · 5p 75) | ~45–60 min (2p ~20 min) |
| **Flash** | 2p 6 · 3p 6 · 4p 4 · 5p 4 | 14 hexes/player (2p 28 · 3p 42 · 4p 56 · 5p 70) | ~10–20 min |

Flash is shorter because it has fewer rounds. In both modes every vineyard sits 4 hexes from the river, so it connects in 3 pieces: closer vineyards hand the first player most of the wins. Flash's bodega bonus is reduced to +1. Both modes start with 2 vineyards per player and 10% stone hexes. A 2-player Normal game is shorter (about 20 turns) because its board is full by then and more rounds would only add passes. The values were tuned by the simulation (#20, [results](#tuning-results)); they live in `acequias/config.py` (see [Game config](#game-config)).

### End and scoring

After the last round, each player scores:

**vineyard values + bodega bonus − water rights paid + water rights collected − bribe debt**

Only watered vineyards count toward vineyard values, the bodega bonus, and water rights.

The highest score wins. On a tie, the tied player with more watered vineyards wins; if that is tied too, the win is shared.

### Variants (under evaluation)

Optional rules, off by default, kept only if the simulation shows they help. The rules above are the shipped game. Flash race end and drought are not implemented yet (#35, #23). The other options are Rules v2 (#114): implemented as preset options (see [Game config](#game-config)), while the shipped Normal and Flash presets keep the rules above until #103.

- **Flash race end:** the first player to claim a 2nd vineyard ends the round; then score.
- **Drought (_sequía_):** in some mid-game rounds part of the river runs dry. It never falls on the last round, so final scoring always uses the full river.
- **Varietal roulette:** vineyards start as blank plots and are planted by a roulette spin when claimed (below). It is implemented as a preset option (`varietal_rules = roulette`, see [Game config](#game-config)); the shipped Normal and Flash presets keep the fixed rules until #103.
- **More vineyard plots:** more plots per player put more points in play and more routes to block or reopen. `vineyards_per_player` (today 2) is raised through `with_overrides`; at `vineyard_distance` (4, 4) each row holds one plot, so Normal's 15 hexes per player fit at most 3 plots per player, and more plots also need more hexes per player (e.g. 4 plots with 20 hexes) or a wider distance. Values to be tuned in #103.
- **Grape-cluster cap:** each player has only `grape_clusters_per_player` grape clusters (claims); see [Claims and watering](#claims-and-watering). The shipped presets have no cap (`None`); the cap is to be tuned in #103. Under the roulette, only the vineyards actually claimed get a spin.
- **Action die:** replaces the [bribe](#bribe-coima) with a custom die that everyone can use to get back into the game (below). It is a preset option (`bribe_rules = action_die`, see [Game config](#game-config)) and needs the varietal roulette for its Resow face; the shipped presets keep the bribe until #103.

#### Action die

On your turn, instead of placing a piece, you may **roll the action die**: add its fixed cost to your debt, then roll. The cost is **2** for now, to be tuned in #103 (2 or 3). The die has 6 faces: 2 x **Floodgate**, 2 x **Release**, 2 x **Resow**. Resolve the face in the same turn:

- **Floodgate:** place a floodgate on any open canal edge (the same edges as a market floodgate). It comes from the die, not the market.
- **Release:** remove one floodgate from the board, anyone's. It is only removed, never moved.
- **Resow:** pick any claimed vineyard, yours or a rival's, watered or dry; spin the [roulette](#varietal-roulette) again and replant it. The same varietal may come out again, and the claim does not change.

You may **decline** the face. A face you cannot use (Release with no floodgate on the board) or do not want is lost, and so is its cost: no refund, no re-roll. As after any action, you then claim every newly watered vineyard (a Release can water some). Under these rules **floodgates come only from the die**: they leave the market bag, and the other pieces share the bag (`action_die_rules` rescales the shipped mix to straight 44, gentle curve 22, sharp curve 17, symmetric Y 6, T branch 6, claw 5). There is no bribe action.

#### Constructive die and season roll

Two more opt-in options of the action die (#130), off in the shipped presets; values to be tuned in #126 after #103.

- **Constructive die** (`action_die = CONSTRUCTIVE_DIE_FACES`): 1 x Floodgate, 1 x Release, 2 x Resow, 1 x **Good season**, 1 x **Drought**. The 2/2/2 die (`ACTION_DIE_FACES`) stays the default. Floodgate, Release and Resow are personal, as above: you may decline them, and an unusable one does nothing. Good season and drought always apply, to every player, as soon as they are rolled, and end the roll:
  - **Good season:** every player gains `season_points` (default: one common vineyard plot's value, the most frequent plot value, 2 under the roulette; it follows `scaled()`).
  - **Drought:** every player loses `drought_points` (default: half of the good season gain, rounded down, at least 1). A drought never takes a score below 0: a player at 0 or less loses nothing, and one with fewer points than the loss ends at 0 (applied at final scoring, where the losses are tallied).
- **Season roll** (`season_roll_every = X`, default off): at the start of every X-th round, before the start player's turn, the holder of the season die rolls the action die for free, without spending their own turn. A season face applies to everyone as above; a personal face is the holder's to use or decline, and an unusable or declined one does nothing. Then the round goes on as usual from its start player. The game's first start player holds the season die for the first season roll, and it passes to the left (the next seat) after each season roll, so the k-th season roll is made by the seat k-1 places after the first start player and every seat makes the same number of season rolls, within one, whatever X and the player count. `acequias.game.next_season_roll` gives the round of the next season roll and its holder.

A voluntary roll is unchanged: it costs `action_die_cost` and the turn, and a declined or unusable face loses the cost. Gains and losses show in the score as the `season` and `drought` terms (`total = vineyards + bodega - rights_paid + rights_collected - debt + season - drought`), in `Player.season` and `Player.drought` during the game, and in the MCP player and score JSON. `scripts/tune.py --sweep b3b` compares the constructive die at cost 1 and 2 with a season roll every 2, 3 or 4 rounds (Normal) or 2 (Flash), against no die. `--sweep b5` does the same on B4's best board (Normal: 2 plots, 18 hexes/player, distance 4; Flash: its default board) with a season roll every 3 or 4 rounds (Normal) or 2 or 3 (Flash).

#### Varietal roulette

The board's vineyards have no varietal. When a player claims a vineyard, they spin the roulette and that varietal is planted there for the rest of the game. The roulette has 14 equal sectors:

| Varietal | Sectors | Points (provisional, to be tuned in #103) |
| --- | --- | --- |
| Malbec | 2 | 2 |
| Cabernet Sauvignon | 2 | 2 |
| Cabernet Franc | 1 | 3 |
| Syrah | 2 | 2 |
| Merlot | 2 | 2 |
| Bonarda | 1 | 3 |
| Torrontés | 2 | 2 |
| Chardonnay | 2 | 2 |

The rarer Bonarda and Cabernet Franc are worth a bit more; a spin is worth 30/14, about 2.14 points, on average. The bodega bonus needs watered vineyards of 3 **different** varietals. The point values are provisional until the re-tuning in #103 (with the scale from #111).

The varietals, for the printed roulette and the rules sheet (research notes, figures and sources in [`_docs/varietals.md`](_docs/varietals.md)):

- **Malbec:** Argentina's flagship red, brought from France in 1853; one vine in four in the country is Malbec.
- **Cabernet Sauvignon:** Bordeaux's noble red; before Malbec's rise it was Argentina's prestige grape. Firm, cassis-scented, long-lived.
- **Cabernet Franc:** The rising star: Argentina's plantings more than doubled in a decade, led by high Uco vineyards.
- **Syrah:** Spicy Rhône red that loves the hot eastern plains; Mendoza grows three-quarters of Argentina's Syrah.
- **Merlot:** Bordeaux's soft, plummy red; a quiet blending partner that shines in cool Uco and Patagonia.
- **Bonarda:** A juicy East-side red with a mistaken identity: not Italian at all, but France's Douce Noir.
- **Torrontés:** Argentina's own white, born from Muscat and a mission grape; smells sweet, tastes dry.
- **Chardonnay:** Burgundy's white goes high: crisp Chardonnay from Tupungato, and the base of Mendoza's sparkling wine.

## Physical pieces

All pieces are parametric build123d models printed on the Bambu Lab A1 (256 × 256 mm plate, 0.4 mm nozzle, PLA). The d6 is not printed.

- **Terrain hexes:** hexagonal prism, with relief depending on type
- **Canal pieces:** hexagon with a groove; neutral, single-color
- **Floodgates:** small L-shaped gates: a base that slots into the groove at one opening, flush with the top, and a grip fin on the outer edge to place and lift it
- **Owner tokens:** small marker that fits a hole in the canal; in each player's color
- **Grape clusters:** figure that rests on the claimed vineyard
- **Debt tokens:** small markers, printed in small batches

### Geometry profile

| Parameter | Value |
| --- | --- |
| Hex side | 16 mm (~32 mm corner to corner); final, confirmed by test print 1 (#34, D1) |
| Tile clearance | 0 mm: tiles print at full size, one size for all hexes (#34, D2) |
| Tile height (functional) | 4 mm, plus decorative relief on top |
| Canal groove | 6 mm wide, 1.5 mm deep |
| Owner token | hole 4 mm across, 2 mm deep; peg 3.60 mm across (0.20 mm fit tolerance per side); cap 7 mm across, 1.2 mm high |
| Floodgate | 5.70 × 3.00 mm base (groove width minus a 0.15 mm fit tolerance per side, flush with the top), grip fin 1.6 mm thick, 7 mm total height; printed on its side, no supports |
| Grape cluster | 14 mm base, 15 mm high, grapes at least 2 mm across |
| Debt token | 12 mm across, 2 mm thick; pips 2 mm across, 1.0 mm deep |
| Thinnest wall | 0.8 mm (two widths of the 0.4 mm nozzle) |
| Board footprint (4p) | ~18–20 cm across |
| Print estimate (4p set) | ~190–200 g PLA, ~7 h of printing, scaled from test print 1 (about 1.94 g and 4 min per hex); not yet confirmed by slicing the full set |

The bag of canal pieces is sized to the board's canalizable capacity, which caps how many canals need printing. The piece sizes are the code's defaults; test print 1 (#34, [`_docs/test-print-1.md`](_docs/test-print-1.md)) confirmed them, raising the owner-token tolerance to 0.20 mm and the pip depth to 1.0 mm.

### Aesthetics

Each piece has two layers, so it doesn't look "all vectors":

- **Functional** (hexagon, groove, fit): build123d, precise and repeatable.
- **Decorative** (mountain, water, vineyard): mesh relief with trimesh + numpy on top of the functional base; Blender later for organic shapes.

Relief comes from real elevation data (SRTM / Copernicus DEM) for mountain hexes, and from height maps generated in code for water ripples, vineyard furrows, and stones. QA checks: closed mesh, minimum printable thickness, and no relief in the fit area. The decorative layer comes after the MVP (see [MVP](#mvp)); MVP pieces are functional only.

### Plate layout

Pieces are placed on a deterministic hex grid on the 256 × 256 mm plate, spilling onto more plates when needed.

`acequias/plate.py` (pure layout math, standard library only): `layout_plates(pieces)` takes `Piece`s with a footprint (`HexFootprint`, `CircleFootprint`, or `RectFootprint`, in mm) and a color group, and returns numbered `Plate`s of `Placement`s: each footprint's center from the bed's front-left corner, rotation always 0. Hexes go on a honeycomb grid spaced so neighbours are exactly `gap` apart; circles and rectangles go on a square grid of bounding-box cells. Each plate holds one color group and one grid type, so it prints with one filament; within a group every cell is sized to the largest piece and plates fill in input order. With the defaults (256 × 256 bed, 5 mm margin, 3 mm gap) a plate holds 68 hexes of 16 mm, 52 of 18 mm, or 256 circles of 12 mm.

`acequias/cad/footprints.py`: `piece_footprint(type, variant, **params)` gives each piece's footprint from its sizes without importing build123d (terrain and canal: the hex shrunk by `clearance`; floodgate: a rectangle, its width by its `height`, as it lies on its side; tokens and grape cluster: a circle), and a test checks it against the built solid.

### Plate export

`acequias/cad/plate_export.py`: `export_plate(plate, solids, path, bed=...)` writes one laid-out plate as a 3MF file in mm through build123d's `Mesher`: one separate object per placement, in placement order, named after its piece id, rotated by its `rotation` and moved to its `x`, `y` with its lowest point at z = 0. The plate number and color group go in as metadata (`acequias:plate`, `acequias:color_group`); no 3MF colors or filament assignments are written yet (#76), so the filament is picked in the slicer. UUIDs come from the piece ids, so the same plate exports to the same objects. A piece outside the bed, a missing solid, or a path not ending in `.3mf` raises `ValueError`, and a failed export leaves no file behind and any existing file unchanged.

### Printing

Profile used for test print 1 (#34): Bambu Lab A1, 0.4 mm nozzle, PLA; 0.2 mm layers (first layer too), Classic wall generator, 2 wall loops, Monotonic top surface, 15% Grid infill, no supports. For the debt tokens, add one extra top layer or turn on ironing in the slicer: with the default top the face around the pips looks scratched.

## MCP architecture

A Python server built on `MCPServer` from the official `mcp` SDK (formerly FastMCP). The game logic lives in `acequias/`, independent of the server in `server/`, so it can be tested without MCP. All randomness (dice, board generation, bots) goes through a seeded RNG, so games are reproducible.

| Tool | Input | Output |
| --- | --- | --- |
| `generate_board` | `players` (2 to 5), `mode`, optional `seed` | `players`, `mode`, the `seed` used, `hexes`, and `assembly` instructions |
| `calculate_score` | `mode`, `hexes`, `players` (id and debt), optional `canals`, `floodgates`, `claims`, `overrides` (preset values, as in `simulate_game`; e.g. roulette rules) | `mode`, `scores` per player by term, in points (vineyards + bodega − rights paid + rights collected − debt; rights are `water_right_points` per rival per vineyard) with the watered vineyards and their paths, and `winners` |
| `simulate_game` | `mode`, `players`, optional `games` (1 to `MAX_GAMES`, default 10), `policies` (one per seat, default all `"greedy"`), `overrides` (preset values, in the shape of the result's `preset` without `mode`; e.g. roulette rules or the action die), `seed` | `SimResult.to_json()` unchanged: the statistics (action die ones included), plus the inputs, the `seed` used, and every preset value after overrides |
| `generate_piece_stl` | `piece`: one `PieceJSON` object, chosen by `type` (`terrain`, `canal`, `floodgate`, `owner_token`, `grape_cluster`, `debt_token`), with optional sizes in mm | `path` of the STL written, `piece` with every default filled in, and the mesh's `size`, `volume`, `triangles`, and `watertight` |
| `build_plate` | `entries`: 1 to 50 `{piece, count, color}` (`piece` as in `generate_piece_stl`, `color` the plate's color group and filament, at most 500 pieces in total), optional `bed_width`, `bed_depth`, `margin`, `gap` in mm | `folder` and `job`, `plates` (each with `number`, `color`, the 3MF `path`, and `placements` giving every piece id, its entry, its full `piece`, and `x`, `y`, `rotation`), and a `summary` of pieces and plates per color |

`simulate_game` caps `games` at `MAX_GAMES = 10`, set when a 5-player Normal game of greedy bots took about 2 s, so 10 games kept one call within a 30-second client timeout; since #84 such a game takes under 0.1 s. Long runs use `scripts/tune.py` (see [Tuning](#tuning)).

`generate_piece_stl` writes into one output folder, set by `ACEQUIAS_OUTPUT_DIR` (default `output/` in the server's working folder, git-ignored), and takes no path. The file name is built from the type, the variant, and every parameter, so the same request overwrites the same file. `build_plate` writes into the same folder, one subfolder per request: `plates-<job>/plate-<n>-<color>.3mf`, where `<job>` is the first 12 hex digits of the SHA-256 of the input with every default filled in, so the same request overwrites its own plates and different requests never share a folder. Every piece gets an id like `canal-straight-03` (numbered per type and variant in input order), and equal pieces are built once. All errors are found before any file is written. Without the `cad` extra the server still starts, and both CAD tools return an error naming the extra and `uv sync --extra cad`.

### Hex convention

`acequias/hex.py`: hexes are **pointy-top**, so east and west are direct neighbors and the river runs along the west edge. `q` grows east and `r` south (`s = -q - r`). Pixel/mm positions put the origin hex at `(0, 0)`, with `x` east and `y` south. Hexes sort by `(q, r)`, the deterministic tie-break of the water-path rule. Sizes must be finite and greater than 0, or the conversions raise `ValueError`. `Direction.rotated(steps)` turns a direction `steps` × 60° counterclockwise, in `Direction` order (E → NE → NW → W → SW → SE); negative steps turn clockwise. `Hex.corners(size)` gives the 6 corner points in the same plane, counterclockwise from just below east (ESE, ENE, N, WNW, WSW, S), so the edge from corner `i` to `i + 1` faces the `i`-th `Direction`.

### Domain model

`acequias/model.py`: types and their invariants, no game logic. Every value is immutable, so an update builds a new one, and collections are kept in hex order, so two boards with the same contents are equal whatever order they were built in. Players are referenced by string id: canal owners, claims, and the start and current player. Claims live on the board as vineyard hex → player id; a vineyard with no claim is unclaimed. A vineyard tile has a varietal under fixed rules and none under roulette rules; `Board.plantings` holds vineyard hex → the varietal the roulette planted on a claimed blank vineyard, and `Board.varietal_at(hex)` reads the tile's varietal, else the planting, else `None`. A canal's openings at a rotation (0 to 5, each 60° counterclockwise) are a `frozenset` of `Direction`s, so rotations that open the same edges compare equal. A floodgate sits on an edge, not a hex: it is identified by that edge, so the same gate given from either side is equal, and an edge holds at most one. `Board` checks where pieces may sit (a planting only on a claimed vineyard with a blank tile); `GameState` checks that every id belongs to one of its 2 to 5 players, and that the varietals fit its preset's rules: under fixed rules every vineyard tile has a varietal with points and nothing is planted, under roulette rules no vineyard tile has one. With a `grape_clusters_per_player` cap, no player holds more claims than the cap. `GameState.pending_face` is the [action die](#action-die) face (`DieFace.FLOODGATE`, `RELEASE`, or `RESOW`) that `current_player` rolled and has not resolved; it is set only under action die rules, and only to a face on the preset's die.

### Game config

`acequias/config.py`: every number the game needs, as one immutable `Preset` per mode, fetched with `preset(mode)`. Board generation, setup, scoring, the round loop, and the simulation read their values from it and hard-code none. Tuning changes the shipped values there; experiments build variants with `with_overrides`, which validates them like the shipped presets. Shares (stone hexes, bag mix) are whole-number percentages, and rounds are set per player count (they differ since #20). `varietal_rules` is `VarietalRules.FIXED` (the shipped default: the generator deals the varietals of `varietal_points` onto the board) or `ROULETTE` (blank plots, planted on claim from the `roulette` sectors). `varietal_points` maps each varietal in play to its points (shipped: Malbec 3, Bonarda 2, Torrontés 1); `roulette` lists the sectors in order (`ROULETTE_SECTORS`). `roulette_rules(p)` switches a preset to roulette rules with the provisional `ROULETTE_POINTS`. Validation: under fixed rules `bodega_varietals` is at most the number of varietals in `varietal_points`; under roulette rules every sector needs points, and `bodega_varietals` is at most the number of distinct sector varietals. `vineyards_per_player` is the number of vineyard plots per player. `grape_clusters_per_player` caps each player's claims: `None` (the shipped value) is no cap, otherwise an int of 1 or more. `bribe_rules` is `BribeRules.D6` (the shipped bribe; `die_faces` is its die) or `ACTION_DIE`; `action_die_cost` (0 or more; 0 is for testing only; shipped `ACTION_DIE_COST = 2`, provisional until #103) and `action_die` (the faces in order, not empty; shipped `ACTION_DIE_FACES`, two of each) are used only under action die rules, which also need a floodgate share of 0 in `bag_mix` and, for a `RESOW` face, roulette rules. `action_die_rules(p)` switches a preset to the action die and sets the floodgate share to 0, rescaling the other shares to 100 by largest remainder (ties in `PieceKind` order); call it on a roulette preset, `action_die_rules(roulette_rules(preset(mode)))`. `water_right_points` (1 or more; shipped 1) is the points a watered claimed vineyard pays each distinct rival on its water path. `scaled(p, factor)` multiplies every scoring value, each `varietal_points` value, `bodega_points` and `water_right_points`, by an int `factor` of at least 1 and keeps everything else; debt is not scaled (the bribe d6 and `action_die_cost` stay as they are; #103 picks them against the scale).

### Water reach

`acequias/flow.py`: `water(board)` maps every watered vineyard, claimed or not, to the one `WaterPath` its water takes; dry vineyards are absent. A path's `canals` run from the river end to the vineyard, and its `owners` include the claimant's own id, so scoring removes the claimant when it counts water rights. Path choice uses the vineyard's claimant on the board. The module is pure and deterministic.

### Board generator

`acequias/board.py`: `generate_board(players, seed, mode, *, preset=None)` returns a `Board` with tiles only. Equal arguments give an equal board, in any process; all randomness comes from one `random.Random(seed)`. `preset` (from `with_overrides`) replaces the shipped one for the simulation, and must have the same mode. Each row is a river hex on the west followed by an unbroken run of hexes east, and the river zigzags south as one chain, so a hex `k` steps east of its river hex is `k` from the river. Vineyards are placed in the preset's distance range (under fixed rules dealt the varietals of `varietal_points` as evenly as possible; under roulette rules left blank, with the two varietal shuffles skipped) and a layout is kept only if at least as many vineyards as players are reachable through empty hexes; a preset that cannot be met (e.g. a distance range the rows cannot hold, or no layout within the retry cap) raises `ValueError`.

### Assembly instructions

`acequias/assembly.py`: `assembly_instructions(board)` lists one `AssemblyStep` per tile, ignoring canals, floodgates, and claims. Steps go row by row from north to south and west to east; rows and positions count from 1 (row 1 is the northernmost, whatever its `r`). Each step holds `row`, `position`, the axial `hex` for programs, `terrain`, `varietal` (`Board.varietal_at`, so `None` on a blank roulette vineyard), and the `text` a person reads, e.g. `"Row 2, hex 3: vineyard, Malbec"`, or `"Row 2, hex 3: vineyard"` for a blank one. Because rows are staggered, hex 1 of every row after row 1 also names the hex above it that it touches (`"south-east of row 1, hex 1"`, the north-west neighbour preferred); on generated boards that is the river, hex 1 of the row above. A board that cannot be laid out row by row (a skipped `r`, a gap in a row, or a row that does not touch the one above) raises `ValueError` naming the row.

### Scoring

`acequias/scoring.py`: `calculate_score(state, preset=None)` scores a `GameState` as given, whatever its round, and changes nothing; with `preset=None` the varietal points and bodega values come from `state.preset`, or `preset(state.mode)` when that is `None`, and an explicit preset from `with_overrides` replaces them. A vineyard's varietal is `board.varietal_at(hex)` and its points `preset.varietal_points`; a watered claimed vineyard with no varietal (never planted) raises `ValueError`. It returns a read-only mapping of player id → `Score`, in seat order, with the terms `vineyards`, `bodega`, `rights_paid`, `rights_collected`, `debt`, and `total` (the names the MCP tool exposes), all in points: each rival on a vineyard's path gets `preset.water_right_points`, so `rights_paid` and `rights_collected` are rival-vineyard pairs times that value, plus `watered` (the tie-break count) and `watered_vineyards`: each watered claimed vineyard in hex order, with its varietal, its `WaterPath`, and the rivals it `pays` in seat order. `winners(scores)` returns the winning ids in seat order: highest `total`, then highest `watered`, otherwise a shared win. Debt is only read from `Player.debt`; bribes (or action die rolls) add to it.

### Game setup

`acequias/setup.py`: `new_game(players, seed, mode, *, preset=None)` returns the starting `GameState`: the board from `generate_board` with the same arguments, players `"p1"` to `"pN"` in seats 1 to N with no debt, round 1, and `current_player` equal to `start_player`. It always sets `GameState.preset` to the preset it used (the shipped one when none is passed); every later step (turn engine, round loop, scoring, simulation) reads the game's numbers from `state.preset` and keeps it in every state it builds. `GameState.preset` may be `None` only on hand-built states, which then fall back to `preset(state.mode)`. `bag_counts(total, preset)` splits the bag by `bag_mix` with the largest remainder method (ties in `PieceKind` order). One `random.Random(seed)` shuffles the pieces and then picks the start player; the market is the first `market_size` pieces and the bag the rest, with `bag[0]` the next piece drawn.

### Turn engine

`acequias/turn.py`: the actions are frozen dataclasses `PlaceCanal(kind, hex, rotation)`, `PlaceFloodgate(hex, direction)`, `Bribe(hex, direction, to=None)` (`to=(hex, direction)` moves the floodgate, `None` removes it), and `Pass()`. `apply(state, player, action, rng)` returns a new state and never changes its input; it leaves `current_player`, `start_player`, and `round` untouched, since turn order belongs to the round loop. The caller owns `rng`, drawn from only after every check has passed, so a rejected action leaves it untouched and replaying a game needs the same `rng` stream. A bribe first rolls `rng.randint(1, die_faces)`. Then, under roulette rules only, each vineyard the action newly claims gets one `rng.choice(preset.roulette)`, in ascending hex order, recorded in `Board.plantings`; under fixed rules nothing else is drawn, so fixed-rules games draw exactly as before. After a placement or a bribe the acting player claims the unclaimed watered vineyards in ascending hex order; with a `grape_clusters_per_player` cap they stop at the cap, the rest stay unclaimed (and draw no spin), and the next player who places or bribes claims them. A placement takes the first copy of its kind from the market and appends `bag[0]`. An illegal action raises `IllegalAction` (a `ValueError`) naming the broken rule; an unknown player raises `ValueError` and a non-action `TypeError`. `legal_actions(state, player)` returns every legal action once, in a fixed order (canals, floodgates, bribes, then pass), in a canonical spelling: the smallest rotation that opens the same edges, and a floodgate edge named from the canal side with the smaller hex. `apply` accepts any equivalent spelling and gives the same state.

Under [action die](#action-die) rules there are four more actions: `RollActionDie()`, `Release(hex, direction)`, `Resow(hex)`, and `DeclineFace()`; the floodgate face reuses `PlaceFloodgate`, which then takes nothing from the market and leaves the market and bag unchanged. `Bribe` is illegal under these rules and `RollActionDie` under d6 rules. A roll is legal whenever the player could take a turn, even when no face would be usable, and it is not a placement (`Pass` keeps its rule). It adds `action_die_cost` to the roller's debt and sets `pending_face`. While a face is pending only `current_player` may act, only with that face's uses or `DeclineFace()`, and either clears it; a declined face keeps its cost. The rng order: a roll draws one `rng.choice(preset.action_die)` and nothing else; a `Resow` draws one `rng.choice(preset.roulette)` for its new planting; `Release` and the die floodgate draw nothing of their own; then the claim spins run as above (a used face claims like any action); `DeclineFace` draws nothing. `legal_actions` lists canals, floodgates, bribes (d6 only), `RollActionDie()` (action die only), then pass; with a pending face, its uses (floodgate edges or releases in the bribe edge order, or resows by hex) then `DeclineFace()`, and nothing for any other player.

### Round loop

`acequias/game.py`: a turn is one action, through `act(state, player, action, rng)`, which checks that it is `state.current_player`'s turn and that the game is not over (before `apply`, so `rng` is untouched on a refusal), then advances the turn. `turn_order(state, round)` gives the acting order of any round: seat order (by `Player.seat`, wrapping), from that round's start player, which moves to the next seat each round. The round count is `rounds_for(len(players))` from `state.preset` (or `preset(state.mode)`); after the last turn the state has `round == rounds + 1`, which is what `game_over(state)` checks, so no `GameState` field marks the end. Under [action die](#action-die) rules a die turn is two actions by the same player: `act` does not move the turn on while a face is pending, so the roll and its resolution are two log records in the same round. `play_game(state, bots, dice_rng, bot_rng)` plays to the end and returns the final state and a log of `TurnRecord(round, player, action, face)` (`face` is the face rolled for a `RollActionDie`, else `None`; `replay` ignores it); a bot's illegal action raises, it never becomes a pass. Dice and bots draw from separate RNGs, so the dice stream does not depend on how many numbers the bots draw: `replay(state, log, dice_rng)` rebuilds the final state from the log with a same-seeded `dice_rng` and no bots. `game_rngs(seed)` returns `(dice_rng, bot_rng)`, seeded from strings so both differ from `new_game`'s `random.Random(seed)`; a game is identified by `new_game`'s arguments, the seed, and the bot policies.

### Bots

`acequias/bots.py`: a bot is a plain function `decide(state, player, rng)` (the `Bot` type in `game.py`) that returns one element of `legal_actions(state, player)`, keeps no state, and draws only from `rng`. `POLICIES` maps names to bots (read-only) and `policy(name)` looks one up, listing the valid names when it is unknown. `random` picks with one `rng.choice` over every legal action. `greedy` weighs only this move and only vineyard points, with no lookahead: the canal that claims the most points now, else the one nearest the most valuable unclaimed vineyard, else a floodgate on a rival's canal; it never bribes, passing instead, and breaks ties with `rng.choice`. A vineyard is worth the points of `board.varietal_at`; under roulette rules one with no varietal yet (unclaimed, or newly claimed on the board a move would give, before its spin) is worth the roulette's mean points. `saboteur` values each non-pass action by its swing in watered vineyard points (own minus rivals'), minus the expected bribe cost `(die_faces + 1) / 2` for a bribe; it plays the best action worth more than 0 and otherwise falls back to `greedy`. Under a `grape_clusters_per_player` cap, a player with no clusters left values every unclaimed vineyard at 0: greedy skips its canal step (no steering toward a vineyard it cannot claim) and places a floodgate as above, or any canal when it has no floodgate; the saboteur's swing counts only vineyards the move lets it claim. With no cap every bot chooses as before. Under [action die](#action-die) rules `random` rolls and resolves like any legal action; `greedy` and `saboteur` never roll (`score_aware` and `lookahead` weigh the roll), and when handed a pending face they play its use with the best swing above 0, else `DeclineFace()`. A `Resow` is weighed with that vineyard blank (the roulette's mean points). Under d6 rules their choices are unchanged.

`score_aware` (#67) values every action by its effect on the full score of `calculate_score` (vineyards, bodega, water rights, debt), as if the game ended on the board the action gives: the change in its own total minus the change in the best rival's. Chance counts by expectation, never by sampling: a new claim with no varietal yet counts at the roulette's mean points (and adds nothing to the bodega until it is planted, an approximation), a d6 bribe adds `(die_faces + 1) / 2` debt, and a `Resow` counts the vineyard at the roulette's mean. `RollActionDie` is worth `-action_die_cost` plus the mean, over the die's faces, of the best use of that face (at least 0, since a face can be declined). It plays the highest value even below 0 (a `Pass`, legal only with nothing to place, is weighed at 0), never falling back to `greedy`; handed a pending face, it plays the best use, or `DeclineFace()` when none is worth more than 0. Values are exact fractions, and ties go to one `rng.choice` in `legal_actions` order, its only draw. Claims follow the cluster cap, so a vineyard it cannot claim is worth nothing to it. It looks one move ahead only (`lookahead` searches deeper), at under 2 s per Normal 5-player game.

`lookahead` (#42, `lookahead_bot(state, player, rng, *, depth=2, beam=3)`) plans `depth` of its own moves (`depth=1` is `score_aware`'s choice). At each own move it keeps the `beam` best actions by `score_aware`'s one-move value (ties in `legal_actions` order); after each, the rivals reply in turn order with `score_aware`'s choice made without rng (ties to the first legal action), then it plays its next move, and the leaf value is `score_aware`'s: its own expected total minus the best rival's. The end of the game cuts the search. Chance counts by expectation, never by sampling: the d6 at its mean, new claims at the roulette's mean, and `RollActionDie` (its own or a rival's) as the mean, over the die's faces, of the best line for that face (declining allowed); a die turn is one own move, and a pending face no use beats is declined. It never reads the bag: planned moves see only the visible market, less the pieces taken, with no refill. Planned boards come from `_board_after` (turn order from `act` on a private fixed-seed rng whose draws are discarded), so no rule is reimplemented; its only draw from `rng` is one `rng.choice` over tied root actions. The default `beam` is 3, not 5, to stay under 5 s per Normal 5-player game (B4).

### Simulation

`acequias/sim.py`: `simulate_game(rules, n, seed)` plays `n` bot games of one mode and returns a `SimResult`. `SimRules` holds `mode`, `players`, `policies` (`policies[k]` plays seat `k + 1`, whatever the start player), and `overrides` for `with_overrides`; the resulting preset is passed only to `new_game`, and every later step reads it from `state.preset`. Game `i` uses `game_seed(seed, i)`, and `play_one(rules, game_seed)` replays any single game of a run. A board the preset cannot satisfy raises `ValueError` naming the game index and seed, with no partial result. A shared win among `k` players gives each `1/k` win credit, so each game hands out exactly 1. Position `j` is the place in round 1's turn order, and `turn_order_advantage` is `max_j |win_rate_by_position[j] − 1/P| × P` (0.10 means a position wins 10% more or less than its fair share). Each statistic is defined in its field's docstring; `SimResult.to_json()` gives plain JSON with the names of `server/schemas.py`. `winner_varietal_rate` has a key only for each varietal in play: those of `varietal_points` under fixed rules (3 keys for the shipped presets), the roulette's 8 under roulette rules. `actions_per_game` also counts `"die"` (rolls), `"release"`, `"resow"`, and `"decline"`; a die floodgate counts as `"floodgate"`, and the counts still add up to `turns_per_game`, which counts log records (a die turn is two). `games_with_die` is the share of games with a roll, `die_faces_per_game` the mean rolls per game of each face, and `die_use_rate` the share of rolls resolved with a use rather than declined (`None` with no rolls).

### Performance

The engine and the bots take fast paths (precomputed tables, boards derived without re-validation) whose results must equal the plain rules. `tests/test_golden_games.py` replays fixed simulation runs against `tests/data/golden_games.json`, recorded before the speed-up, so any change in a log, a final state, a path, or a score fails; re-record it only when the rules change on purpose. `uv run python scripts/bench_sim.py` prints the best wall time of fixed 5-player runs and a SHA-256 of each result (equal digests mean nothing moved); `--profile` lists the hottest functions.

### CAD pieces

`acequias/cad/` holds the build123d models; it is the only code that imports build123d or trimesh, and the game logic and the server never import it at module level, so a plain install stays CAD-free. CAD frame: `x` east, `y` north, `z` up, in mm, each piece centered at `x = y = 0` with its bottom on `z = 0`; outlines come from `Hex.corners`, each corner `(x, y)` used as `(x, -y)`, so each edge faces the same `Direction` as on the board. `hex_tile.py`: `hex_tile(side, height, clearance)` is the terrain prism and `export_stl(shape, path)` writes a binary STL. `channel.py`: `canal_piece(kind)` is the tile with a groove spoke to each edge the kind opens at rotation 0 (players rotate the printed piece) and a hole for the owner token; `floodgate()` is the gate as it sits in the groove: a base that fills the groove, flush with the top, and a grip fin flush with its outer face (the one on the hex edge) that rises to the total `height`; `owner_token()` is a cap with a peg, printed cap down. `tokens.py`: `grape_cluster()` is tiers of grapes on a flat round base, topped by a stem, that rests loose on a vineyard tile (no peg); `debt_token(value)` is a disc worth 1 or 5, marked with die-face pips (no text). Both have circle footprints for the plate layout. `pieces.py`: `build_piece(type, variant, **params)` maps each piece type to its generator, as laid on the plate (the floodgate lies on its flush outer face, so it needs no supports and its layers run along the fin). Defaults are those of the [Geometry profile](#geometry-profile); any size that would leave a wall under 0.8 mm raises `ValueError` naming it.

### Board JSON

`server/schemas.py`: the JSON shapes every tool shares, so a board means the same JSON everywhere. A hex is `q`, `r`, `terrain`, and `varietal` (null except on vineyards, and null on a blank vineyard under roulette rules). Enum strings are lowercase ASCII: terrain `"river"`, `"vineyard"`, `"stone"`, `"empty"`; varietal `"malbec"`, `"cabernet_sauvignon"`, `"cabernet_franc"`, `"syrah"`, `"merlot"`, `"bonarda"`, `"torrontes"`, `"chardonnay"`; varietal rules `"fixed"`, `"roulette"`; canal `kind` `"straight"`, `"gentle_curve"`, `"sharp_curve"`, `"symmetric_y"`, `"t_branch"`, `"claw"` (the floodgate is not a kind). Directions are the case-sensitive names `"E"`, `"NE"`, `"NW"`, `"W"`, `"SW"`, `"SE"`. A canal is `q`, `r`, `kind`, `rotation` (0 to 5), `owner`; a floodgate is the canal's `q`, `r` and the `direction` it closes; a claim is `q`, `r`, `player`, and an optional `varietal` (default null): the varietal the roulette planted there, which becomes a `Board.plantings` entry; a player is `id` and `debt`, and the list order gives seats 1 to N. The preset shape (`simulate_game`'s result `preset`, and `overrides` without `mode` in both `simulate_game` and `calculate_score`) adds `water_right_points`, `varietal_rules`, `varietal_points` keyed by varietal name, `roulette` as a list of names, `grape_clusters_per_player` as an int or null (null means no cap; in `overrides`, null sets no cap and leaving the key out keeps the shipped value), `bribe_rules` (`"d6"` or `"action_die"`), `action_die_cost`, and `action_die` as a list of faces (`"floodgate"`, `"release"`, `"resow"`); `simulate_game` with `overrides={"varietal_rules": "roulette", "varietal_points": {...}, "bribe_rules": "action_die", "bag_mix": {..., "floodgate": 0}}` simulates the action die; `calculate_score` with `overrides={"varietal_rules": "roulette", "varietal_points": {...}}` scores a roulette board with planted claims, `overrides={"water_right_points": 2}` doubles the rights terms (every score term is in points), and without `overrides` uses the shipped preset. From a `generate_board` result only `mode` and `hexes` carry over to `calculate_score`: its `players` is a count, not a list, and `seed` and `assembly` are not inputs. Inputs are strict (`"3"`, `3.0`, or `true` is not an int), and the server only maps JSON to `acequias` types; every check comes from the model.

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

- [x] All 5 MCP tools work from Claude: `generate_board`, `calculate_score`, `simulate_game`, `generate_piece_stl`, `build_plate`
- [x] The full rules above play end to end in the engine, in both modes, with bots
- [ ] Turn-order advantage is at most 10% in both modes, and the tuned values are recorded here: values recorded; the 10% bound is met in 10 of 16 configurations (see Quality criteria, follow-ups #103, #104)
- [x] Every piece needed to play (terrain hexes, six canal shapes, floodgates, owner tokens, grape clusters, debt tokens) is generated as a closed STL and laid out on A1 plates as 3MF
- [x] The first test print passes its fit check (#34)
- [x] CI runs the whole suite on every pull request (#44)

**In the MVP** (milestones 1–5): #3–#15, #17–#22, #28–#31, #33, #34, #44, #45.

**After the MVP** (milestone 6, lower priority), each with its own issue:

| Area | Issues |
| --- | --- |
| Looks | Height-map relief #16, real elevation relief #32, Blender shapes #36 |
| Rule variants | Drought #23 and its marker #40, Flash race end #35 |
| Rules v2 (#114) | Varietal roulette #85, floodgate plate with grip #109, more plots and grape-cluster cap #110, larger score scale #111, action die #112, their pieces #113 |
| Balance | Re-check with smarter bots #103, seat compensation #104 |
| Tooling | STEP/3MF per piece #37, board picture #39, faster simulation #43 (done), lookahead bot #42 (done), score-aware bot #67 (done) |
| Product | Full game-set piece list #38, rulebook, packaging, and cost #41 |

MVP pieces are plain and functional; the decorative layer below comes after the MVP.

### Quality criteria

- [x] Each tool has unit tests with pytest
- [x] Every generated board has at least one reachable vineyard per player
- [ ] Turn-order advantage is at most 10%, in Normal and in Flash separately: met in 10 of 16 simulated configurations; missed by all-greedy tables at Normal 4–5p and Flash 3–5p, and by Flash 5p with saboteurs (follow-ups #103, #104)
- [ ] A Normal game takes about 45–60 min and a Flash game 10–20 min, estimated at 1 minute per turn: met at every player count except 2-player Normal, which takes about 20 min by the owner's choice (more rounds would only add passes)
- [x] Each STL is a closed solid and fits with the other pieces

### Tuning results

The values above were tuned in #20 with `scripts/tune.py`; the full report, with the method, every sweep, and the owner's decisions, is [`_docs/tuning-results.md`](_docs/tuning-results.md). Final validation, seed 20002, 2,000 / 3,200 / 4,800 / 6,400 games for 2 / 3 / 4 / 5 players (95% margin on the advantage at most ±0.05). Seatings: all `greedy` bots, or `saboteur` and `greedy` alternating (mixed). Minutes assume 1 minute per turn.

| Mode | Players | Advantage (greedy / mixed) | Turns (minutes) | Average winning score (greedy / mixed) |
| --- | --- | --- | --- | --- |
| Normal | 2 | 0.02 / 0.01 | 20 | 0.75 / 0.53 |
| Normal | 3 | 0.07 / 0.01 | 45 | 1.14 / 0.41 |
| Normal | 4 | **0.12** / 0.03 | 48 | 1.25 / 0.30 |
| Normal | 5 | **0.15** / 0.05 | 50 | 1.59 / 0.35 |
| Flash | 2 | 0.00 / 0.01 | 12 | 0.70 / 0.47 |
| Flash | 3 | **0.12** / 0.01 | 18 | 0.98 / 0.34 |
| Flash | 4 | **0.18** / 0.07 | 16 | 1.58 / 0.51 |
| Flash | 5 | **0.29** / **0.15** | 20 | 2.06 / 0.60 |

Bold marks a miss of the 0.10 target. With these one-move-ahead bots scores are very low and about half of the games (more with saboteurs) end in a shared win; #103 re-measures balance with the stronger bots (#42, #67) before any rule change (#104).

### Open questions

Provisional defaults let work start; the simulation (or CAD, for physical values) settles them. The game values were settled in #20 ([results](#tuning-results)).

- [x] Normal rounds: 10 / 15 / 12 / 10 for 2 / 3 / 4 / 5 players
- [x] Flash rounds per player count: 6 / 6 / 4 / 4 for 2 / 3 / 4 / 5 players
- [x] Hexes per player: Normal 15, Flash 14
- [x] Bag mix: straight 40% · gentle curve 20% · sharp curve 15% · symmetric Y 5% · T branch 5% · claw 5% · floodgate 10%, sized to board capacity (kept)
- [x] Vineyards per player: 2, both modes (kept)
- [x] Stone hexes: 10% of the non-river hexes (kept)
- [x] Vineyard distance from the river: 4 hexes (3 canals) in both modes
- [x] Die: the d6 is kept (a d4 makes bribes common, a d8 nearly removes them); a success threshold waits for smarter bots (#42, #67)
- [x] Flash bodega bonus: +1 for all three varietals (kept)
- [x] Hex side: 16 mm, settled by test print 1 (#34, D1); the 18 mm fallback is not needed
- [ ] Flash race-end variant: evaluate in the simulation before committing (see [Variants](#variants-under-evaluation))

## Development

```sh
uv sync              # install dependencies (game logic and server)
uv sync --extra cad  # also install build123d and trimesh, for the CAD pieces
uv run pytest        # run the test suite
```

Without the `cad` extra the CAD tests are skipped; CI installs it, so they run there.

### Tuning

`uv run python scripts/tune.py` runs the final validation, `--sweep <name>` one sweep, and `--list` lists them (see [Tuning results](#tuning-results)). Games run in chunks on `--workers` processes (default 3) at below-normal priority, with progress and an ETA on stderr. Each finished chunk is saved under `output/tune-checkpoints/` (`--checkpoint-dir`), so running the same command again resumes a stopped run; `--fresh` ignores the saved chunks. Neither the worker count nor the chunk size changes any number.

### Running the MCP server

`uv run acequias-server` starts the server over stdio (`server/app.py`). It exposes `generate_board`, `calculate_score`, `simulate_game`, `generate_piece_stl` and `build_plate` (both need the `cad` extra), and `ping`, which returns `"pong"` as a connection check.

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
