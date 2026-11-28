# Acequias MCP

[![Tests](https://github.com/cristiangarciavd/acequias-mcp/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/cristiangarciavd/acequias-mcp/actions/workflows/tests.yml?query=branch%3Amain)

Acequias is a competitive board game for 2 to 5 players (Flash: 2 or 3) with 3D-printed hex pieces. Players build canals to carry water from the mountains to the vineyards of Mendoza. This repo holds an MCP server that generates balanced boards, scores games, simulates them with bots to tune the rules, and outputs printable STL pieces for a Bambu Lab A1.

> **Status:** the MVP (milestones 1 to 5) is done: the game logic, the MCP server with all 5 tools, the simulation that tuned the rules (#20, [results](#tuning-results)), every MVP piece as STL, and A1 plates as 3MF, confirmed by the first test print (#34, [report](_docs/test-print-1.md)). After the MVP, the `score_aware` and `lookahead` bots (#67, #42) and a parallel, resumable `scripts/tune.py` (#43) are done. The remaining work is milestone 6, After the MVP. Rules v2 (#114) is the shipped game since #126: the varietal roulette, the constructive action die with a season roll, a larger score scale, and multiple bodegas, re-tuned in #103 with Flash limited to 2 or 3 players; its pieces are #113. The Rules v1 values stay in the engine as options (`RULES_V1`). Progress is tracked in the [GitHub issues](../../issues) and [milestones](../../milestones).

This README is the project's specification: game rules, design decisions, architecture, and roadmap. Task details live in the GitHub issues.

Project goals: practice MCP with a real use case (a portfolio project toward AI Solutions Architect), produce something printable on the Bambu Lab A1 and potentially sellable, and apply QA practices (automated tests, plus simulation to balance the game). No deadline: under 1 hour of work per day.

## Game rules

Whoever scores the most points when the harvest ends, after a fixed number of rounds, wins. There are two length modes, **Normal** (2 to 5 players) and **Flash** (2 or 3 players), with the same rules and engine.

### Components

| Component | Detail |
| --- | --- |
| Terrain hexes | River, vineyard, stone, empty |
| Vineyards | Neutral blank plots, planted with one of 8 varietals by the [varietal roulette](#varietal-roulette) when claimed: 6 pts each, 7 for the rarer Bonarda and Cabernet Franc |
| Canal pieces (neutral) | Six shapes: straight, gentle curve, sharp curve, symmetric Y, T branch, claw (see [Water flow](#water-flow)) |
| Floodgates | Small gates that close one opening of a canal piece; they come only from the action die (see [Floodgate](#floodgate)) |
| Owner tokens | One per placed canal, in each player's color |
| Grape clusters | Mark a claimed vineyard, in each player's color |
| Debt tokens | Track each player's debt from action die rolls |
| Action die | Six faces: floodgate, release, resow, resow, good season, drought (see [Action die](#action-die); its printed piece is #113) |
| Season die | A marker for the player who makes the next free [season roll](#season-roll) |
| Roulette | 14 sectors that plant a claimed vineyard (see [Varietal roulette](#varietal-roulette); its printed piece is #113) |

### Setup

1. The MCP generates a balanced map for the number of players and the mode. No vineyard is ever next to the river: each needs at least one canal to be watered.
2. The west edge is the river (the mountains); all water flows from there.
3. The bag holds one canal piece per empty hex (the board's canalizable capacity), split by the bag mix (no floodgates: they come from the action die). It is shuffled and four pieces are placed face up: the market. There is no redraw.
4. A start player is chosen; the start player rotates each round. The start player also takes the season die.

### Turn

On your turn you take **one action**:

- **A. Place a canal.** Take a canal from the market (it is refilled from the bag; when the bag is empty the market shrinks). It goes on an empty hex, with your owner token. At least one of its openings must line up with the river or with an opening of any canal already on the board, even a dry one or one closed by a floodgate. Its other openings may face anything: dead ends are allowed.
- **B. Roll the action die.** Add 1 to your debt and resolve the face (see [Action die](#action-die)).
- **Pass**, only when you have nothing you can place. Rolling is never forced.

Every few rounds a free [season roll](#season-roll) comes before the round's first turn.

Rules note: a small board can lock up. Once every canal opening faces another canal, stone, a vineyard, or the board edge, no canal can be placed anywhere, and you may only roll the die or **Pass** for the rest of the game. This follows the rules as written; the round loop still ends at its round count.

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

After **any** action (a placement or a used die face), the acting player claims **every** unclaimed vineyard that is now watered, and spins the [roulette](#varietal-roulette) for each to plant it. A claim is permanent: once your grape cluster is on a vineyard, nobody else can claim it, even if its water is later cut off. But a vineyard only scores if it is **watered** (connected to the river) on the final board. A claimed vineyard that ends dry scores 0 and pays no water rights. Its owner can water it again by reconnecting it, or by releasing the floodgate that blocks it.

With the [grape-cluster cap](#variants-under-evaluation) (a preset option, off in the shipped game), each player has a limited number of grape clusters. The acting player claims the newly watered vineyards in ascending hex order until their clusters run out; the rest stay unclaimed and watered, and the next player who places a piece or uses a die face (not a pass) and still has clusters claims them. Claims are never given up or moved.

### Turn order (_turnos de riego_)

Each round, every player takes one turn in seat order, starting with the start player and wrapping around. The start player moves to the next seat each round, like the real watering turns of Mendoza's acequias, so no seat keeps the turn-order advantage (target: at most 10%).

### Water rights

If the water reaching your vineyard passes through other players' canals, you pay **3 points to each distinct other player** whose canals are on that path (not per canal). Each vineyard pays separately: two of your vineyards fed through the same rival pay that rival 6. Water rights are settled **at the end of the game**, from the final board. The 3 points are the shipped preset value `water_right_points` (Rules v1's 1 point at the score scale of 3, #111).

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

A floodgate is placed with the action die's **Floodgate** face, on any open opening of any canal on the board, yours or a rival's. Only one floodgate fits on an edge. Once placed, it can be removed only with the **Release** face; it is never moved.

### Action die

On your turn, instead of placing a piece, you may **roll the action die**: add its fixed cost, **1**, to your public **debt**, then roll. Debt is subtracted from your final score. The die has 6 faces: **Floodgate**, **Release**, 2 x **Resow**, **Good season**, **Drought**.

The first three are personal: resolve the face in the same turn, or decline it.

- **Floodgate:** place a floodgate on any open canal edge (see [Floodgate](#floodgate)).
- **Release:** remove one floodgate from the board, anyone's. It leaves the game for good.
- **Resow:** pick any claimed vineyard, yours or a rival's, watered or dry; spin the [roulette](#varietal-roulette) again and replant it. The same varietal may come out again, and the claim does not change.

A face you cannot use (Release with no floodgate on the board) or do not want is lost, and so is its cost: no refund, no re-roll. As after any action, you then claim every newly watered vineyard (a Release can water some).

The season faces apply at once, to every player, and end the roll:

- **Good season:** every player gains one common vineyard plot's value, **6** points.
- **Drought:** every player loses half of that, **3** points. A drought never takes a score below 0: a player at 0 or less loses nothing, and one with fewer points than the loss ends at 0 (applied at final scoring, where the losses are tallied).

### Season roll

At the start of every 3rd round in Normal (rounds 3, 6, 9, ...) and every 2nd round in Flash (rounds 2, 4, 6), before the start player's turn, the holder of the season die rolls the action die for free, without spending their own turn or adding debt. Only a season face counts: a good season or a drought applies to everyone as above, and a floodgate, release or resow face does nothing. Then the round goes on as usual from its start player. The game's first start player holds the season die for the first season roll, and it passes to the left (the next seat) after each season roll, so every seat makes the same number of season rolls, within one.

### Bodega bonus

A player whose watered vineyards include 3 **different** varietals (two Malbecs count once) earns a bodega: **+6** in Normal, **+3** in Flash. A winery wants its blend.

A player earns the bonus once per bodega (**multiple bodegas**, `multiple_bodegas`, #135), and each bodega needs its own 3 watered vineyards of 3 different varietals; no vineyard counts toward two bodegas. The count is the largest number of such disjoint groups: Malbec, Malbec, Bonarda, Bonarda, Torrontés, Torrontés make 2 bodegas, but Malbec ×3, Bonarda ×2, Torrontés make only 1 (there is a single Torrontés). Dry vineyards never count. Resow can target any claimed vineyard, yours or a rival's: replanting a rival's vineyard can break one of their bodegas, and replanting your own can complete one of yours.

### Game modes

| Mode | Players | Rounds | Season roll | Board | Bodega | Target time |
| --- | --- | --- | --- | --- | --- | --- |
| **Normal** | 2 to 5 | 2p 10 · 3p 15 · 4p 12 · 5p 10 | every 3rd round | 18 hexes/player (2p 36 · 3p 54 · 4p 72 · 5p 90) | +6 | ~45–60 min (2p ~20 min) |
| **Flash** | 2 or 3 | 2p 6 · 3p 6 | every 2nd round | 14 hexes/player (2p 28 · 3p 42) | +3 | ~10–20 min |

Flash is shorter because it has fewer rounds. It is for 2 or 3 players only: with 4 or 5 its 4 rounds were biased toward the last seats and ended in too many ties, and no turn-order fix worked (#103, phases E and F of the [tuning results](#tuning-results)); the engine, the MCP tools, and `scripts/tune.py` reject or skip those counts with a clear error. In both modes every vineyard sits 4 hexes from the river, so it connects in 3 pieces: closer vineyards hand the first player most of the wins. Both modes start with 2 vineyards per player and 10% stone hexes. A 2-player Normal game is shorter (about 20 turns) because its board is full by then and more rounds would only add passes. Rounds were tuned in #20 and the rest in #103 ([results](#tuning-results)); the values live in `acequias/config.py` (see [Game config](#game-config)).

Rules v3 has its own opt-in modes, `NORMAL_V3` (2 to 5 players) and `FLASH_V3` (2 or 3), with no fixed round count: the game ends by the shared vineyard supply, a score target, or dead turns (see [Rules v3](#rules-v3-opt-in-not-shipped)). The modes above stay the shipped ones.

### End and scoring

After the last round, each player scores:

**vineyard values + bodega bonuses − water rights paid + water rights collected − die debt + good seasons − droughts**

Only watered vineyards count toward vineyard values, the bodega bonuses, and water rights. Droughts never take a total below 0 (see [Action die](#action-die)).

The highest score wins. On a tie, the tied player with more watered vineyards wins; if that is tied too, the win is shared.

### Variants (under evaluation)

Optional rules, kept only if the simulation shows they help. The rules above are the shipped game (Rules v2, #114, shipped in #126). Flash race end and drought rounds are not implemented yet (#35, #23). The others are preset options (see [Game config](#game-config)), off in the shipped presets.

- **Flash race end:** the first player to claim a 2nd vineyard ends the round; then score.
- **Drought rounds (_sequía_):** in some mid-game rounds part of the river runs dry. It never falls on the last round, so final scoring always uses the full river. (Not the die's Drought face.)
- **More vineyard plots:** more plots per player put more points in play and more routes to block or reopen. `vineyards_per_player` (shipped 2) is raised through `with_overrides`; at `vineyard_distance` (4, 4) each row holds one plot. #103 tried 3 plots (sweep `b4`) and kept 2.
- **Grape-cluster cap:** each player has only `grape_clusters_per_player` grape clusters (claims); see [Claims and watering](#claims-and-watering). The shipped presets have no cap (`None`); #103 tried a cap of 2 (sweep `b4`). Only the vineyards actually claimed get a roulette spin.
- **Seat bonus** (`seat_bonus`, #142): bonus points by round 1 position. #103 tried it for Flash 4-5 players and it overshot (phases E and F).
- **Rules v1** (`RULES_V1`, the presets shipped from #20 until #126): vineyards dealt on the board with fixed varietals (Malbec 3, Bonarda 2, Torrontés 1; `varietal_rules = fixed`), floodgates in the market bag (10%), and the **bribe** instead of the action die (`bribe_rules = d6`): instead of placing a piece, roll a d6, add the roll to your debt, and remove or move one floodgate. One bodega at most, +2 in Normal and +1 in Flash, for all three varietals; water rights 1 point; 15 hexes per player in Normal; Flash for 2 to 5 players (4 rounds at 4p and 5p); no season roll. The other action die options also stay: the 2/2/2 die (`ACTION_DIE_FACES`: 2 x Floodgate, 2 x Release, 2 x Resow), any `action_die_cost` (0 for testing only), explicit `season_points` and `drought_points`, and a season roll whose personal face is the holder's to use (`season_roll_personal_faces = True`).

Gains and losses show in the score as the `season` and `drought` terms (`total = vineyards + bodega - rights_paid + rights_collected - debt + season + seat_bonus - drought`), in `Player.season` and `Player.drought` during the game, and in the MCP player and score JSON. `acequias.game.next_season_roll` gives the round of the next season roll and its holder.

#### Tuning sweeps of the die

`scripts/tune.py --sweep b3b` compares the constructive die at cost 1 and 2 with a season roll every 2, 3 or 4 rounds (Normal) or 2 (Flash), against no die. `--sweep b5` does the same on B4's best board (Normal: 2 plots, 18 hexes/player, distance 4; Flash: its default board) with a season roll every 3 or 4 rounds (Normal) or 2 or 3 (Flash). `--multiple-bodegas` turns on [multiple bodegas](#bodega-bonus) in every b5 candidate (for #103 phase D), and `--season-global-only` turns off `season_roll_personal_faces` in every b5 candidate (combinable with `--multiple-bodegas`). The shipped presets are its candidate "constructive die, cost 1, season roll every 3" (Normal) and "... every 2" (Flash) with `--scale 3 --rare-bonus 1 --multiple-bodegas --season-global-only`, with Flash limited to 2-3 players; `--sweep shipped` runs the shipped presets themselves. Every sweep is defined against the Rules v1 presets, so the commands in the tuning report still play the same games.

#### Rules v3 (opt-in, not shipped)

Rules v3 (#149) is an opt-in preset variant, off in the shipped presets; its tuned values are the opt-in presets `NORMAL_V3` and `FLASH_V3` (#182, below), and it ships as the default only when the owner decides. It is turned on with `planting = vertices` (`PlantingRules.VERTICES`, which needs roulette varietals and action die rules), and optionally the open river strip board with `board_shape = river_strip`. Player documents: the [rules sheet](_docs/rules-v3.md), the [varietal fact card](_docs/varietals.md), and the [action die notes](_docs/action-die.md).

- **Turn:** every turn starts with a **mandatory roll** of the action die. Floodgate and Release cost the bribe (`action_die_cost` in debt, paid even with no use) and must be used when they can (place a floodgate on any open canal edge; remove a floodgate). Resow and Move are free and optional: Resow respins any planted vineyard, yours or a rival's (no moving): the player picks the vineyard first, then spins, and the result stands; Move (#160, the Rules v3 die `V3_DIE_FACES`: floodgate, release, resow, move, good season, drought, one face each, the move icon a moving truck) moves one of your planted vineyards to another empty vertex you may plant on (the same rule as a new vineyard). The old die (2 resows, no move) stays playable for comparison. Good season gives **2 actions** (plant + plant, or canal + plant; never 2 canals); Drought loses the turn. Then take your action: **place a canal**, **plant a vineyard**, or **pass** (always allowed). Optional bribe (#168, opt-in, off by default, `bribe_optional`): Floodgate and Release become optional and the bribe is paid only when the player places or removes a floodgate; declining (or a face with no use) costs nothing; the bots use the face only when its score swing beats the bribe. There is no claim phase, no season roll, and no season or drought points.
- **Planting:** vineyards grow on hex **vertices** (the point where 3 hexes meet), not on vineyard tiles. A player plants on a free vertex next to one of **their own** canals that carries water right now, and spins the roulette for its varietal; planting makes it theirs. A vertex touches a canal when the canal sits on one of its 3 hexes, regardless of openings. Planting next to rivals' canals is allowed. With `vertex_needs_three_canals` (off by default) a vineyard may be planted only on a vertex whose 3 hexes all hold a canal (anyone's, wet or dry); off, a vertex with a river or empty hex may be planted and that third is lost.
- **Split scoring** (#160): a vineyard is worth 6 (common) or 9 (Bonarda, Cabernet Franc; `V3_POINTS`, configurable with `varietal_points`), split in thirds among the 3 hexes of its vertex. A third scores for the owner of its hex only if the hex is a canal that carries water (after floodgates), whoever planted the vineyard; a third on a river hex, an empty hex, or a dry canal scores for nobody. Example: a 9 between two of my watered canals and one rival watered canal gives me 6 and the rival 3; if a floodgate dries my two, I get 0 and the rival still gets 3. A player's share is value x thirds / 3, rounded down for values not divisible by 3. There are no water rights under Rules v3. A player has a bodega when the vineyards with at least one of their watered thirds cover `bodega_varietals` (3) distinct varietals, whoever planted them; a dried or resown vineyard counts as it is now. Score: split vineyard points + bodegas - debt.
- **River strip board** (`board_shape = river_strip`, #154): only a strip of river hexes (`river_hexes_per_segment` per segment, a base segment for 2 players and one more per extra player) with an open, obstacle-free table east of it; the bag (`bag_size` per player count) limits the game.
- **Cortes and bodega buildings** (#166, opt-in, all off by default, values to be tuned): a *corte* (blend, `blends`) is a set of 2 or more varietals worth bonus points at the end; any varietals may blend, red, white or mixed. A player holds a varietal when they have a watered third of a vineyard of it, whoever planted it. `blend_rule` `each_once` scores every held corte once (a vineyard may count for several); `disjoint` scores the best set of distinct cortes that uses no vineyard twice. The default table (`DEFAULT_BLENDS`) is the 10 main cortes of [the blend research](_docs/blends.md) (#165): Malbec with Cabernet Sauvignon, Bonarda or Syrah 2; Malbec + Cabernet Franc, Chardonnay + Torrontés and Malbec + Torrontés 3; Malbec + Cabernet Sauvignon with Merlot, Cabernet Franc or Bonarda 4; Malbec + Cabernet Sauvignon + Merlot + Cabernet Franc 5. `varietal_bodega = false` turns off the 3-varietal bodega bonus so cortes replace it. `bodega_building` adds the action "build a bodega" (one action, any turn, also in a good season's 2): a bodega token on a free vertex the player may plant on (`bodega_placement = new_spot`) or in place of one of their vineyards (`replace`), worth `bodega_building_points` (12) split in thirds like a vineyard (4 per watered third, for each canal owner). It needs `bodega_min_reds` (2) distinct red and `bodega_min_whites` (2) distinct white varietals (Torrontés, Chardonnay) among the vineyards the player planted (`bodega_min_vineyards`, 0 by default, adds a minimum count), at most `bodegas_per_player` (1) each; it has no varietal and is never moved or resown. Score: split vineyard points + bodegas + cortes + bodega buildings - debt.
- **Bots:** `greedy`, `score_aware` and `lookahead` play the v3 turn with split scoring and the move face (`saboteur` plays greedy's v3 choice); resow and move are declined when they gain nothing. `score_aware` adds a planting potential to each player's total (half the roulette's mean, in full at 6 plantable spots), so it opens spots with a canal when it cannot plant, and always plays a mandatory face. `lookahead` plans every later turn as a plain turn (one action, no face). Every score-aware value comes from the scoring, so cortes and bodega buildings are valued as they score (a vineyard not yet spun counts for no corte); `greedy` builds a bodega whenever it may. The bots add a quarter of the building's points times the chance that a player's own planted vineyards meet the requirement (a vineyard not yet spun at the roulette's odds; the full quarter once built), so they resow their own vineyards to complete it when it is close. On the dev machine a 4-player Normal strip game takes about 0.2 s (greedy), 0.7 s (score_aware), and 3 to 5 s (lookahead).
- **MCP:** `generate_board` takes `overrides` and returns a v3 board's planting `spots` (each a vertex as its 3 hexes `[[q, r], [q, r], [q, r]]`) or its river `strip`; `calculate_score` takes `planted` vineyards (`{"hexes", "player", "varietal"}`) and a `strip`, and lists a vertex vineyard under every player with a watered third of it, with `hexes` instead of `q`, `r`, plus `planter`, `thirds` and `points`; `simulate_game` returns the v3 preset keys (`planting`, `vertex_needs_three_canals`, `board_shape`, `river_hexes_per_segment`, `bag_size`, each left out at its default), counts `"plant"` and `"move"` actions, and under v3 counts `"move"` rolls in `die_faces_per_game`. `simulate_game` echoes `bribe_optional` (#168) when true. #166: `calculate_score` takes `bodegas` (`{"hexes", "player"}`) and gives `blend` and `blends` (the cortes scored, by name), `buildings` and `watered_bodegas`, each left out when 0 or empty; the overrides take the corte and bodega building options (`blends` as `[{"varietals", "points"}]`), which `simulate_game` echoes when not at their defaults, and it counts `"bodega"` actions under `bodega_building`.
- **Tuning:** `scripts/tune.py --sweep strip` (river hexes per segment x bag size) `--sweep v3` (one value at a time around a strip base: rounds, die cost, vineyard points, bodega points, the move die, river hexes, bag size; `--v3-river-hexes`, `--v3-bag-per-player` set the base) and `--sweep v3split` (#160: split scoring at 6 / 9; `vertex_needs_three_canals` off / on x the move die / the old die, each around a base of 5 river hexes per segment and a bag of 16 per player, one value at a time: bag 20 and 24, 6 river hexes per segment, bodega 3 / 6 / 9, rounds -2 / +2) play score_aware seats and report plants, canals and passes per game, planted vineyards per player, the bodega rate, die rolls and uses per face (move included), and floodgates placed per game and the most on the board at once (mean / max, to size the physical floodgate supply). `--sweep v3blends` (#166) compares, around the v3split base with the move die, the current bodega bonus, cortes `each_once` and `disjoint` (bodega bonus off), and `each_once` cortes plus the bodega building, each with its points x0.5 / x1 / x1.5 (the building also at 15, and each building row with 2 reds and 2 or 1 whites), and adds corte and building points per player, bodegas built per game, the share of players who meet the requirement, the mean round they first meet it, the share who build, and how often each corte scores. It runs with the round count end condition. `--sweep v3bribe` (#168) plays `bribe_optional` off / on x bribe 1 / 2 / 3 / 4 / 6 around the best #160/#166 setup (`v3_best_base` in `tune.py`: 5 river hexes per segment, bag 16 per player, any-vertex planting, the move die, `each_once` cortes with the bodega bonus off, and the bodega building at 12 points, 2 reds + 1 white, on a new spot) and adds floodgates placed / released per game, the share of floodgate and release rolls used, the mean score swing of a floodgate use, and the mean debt. `--sweep v3end` (#163) plays, around `v3_best_base`, the seat bias diagnosis (seats rotated or shuffled per game, an unlimited bag) and each end condition (`bag_empty`, `vineyards_out`, `score_target` at #160's winning scores x1 / x1.5 / x2) with `finish_round` on and off, and reports the advantage, win rates by position and by seat, length, shared wins, bodega rate, the share of games the round cap ended, which rows bring the advantage under 0.2, and a per-round score trace by position. `--summary PATH` (#179) also writes a short fixed-format summary of each sweep to PATH (one row per candidate: the advantage with pass / FAIL against 0.10, the winning score, turns with pass / FAIL against the target length, and a few figures per sweep), leaving stdout unchanged.
- **End of the game** (#163, opt-in): `end_condition` (`rounds` by default; `bag_empty`: the bag and the market are empty; `vineyards_out`: a player has planted all their `vineyard_markers`, which also cap planting, default Normal 6 / 9 / 7 / 6 and Flash 3; `score_target`: a player's total reaches `score_target`, default Normal 30 / 51 / 43 / 37 and Flash 14) and `finish_round` (on: the round in which the trigger fired is played out; off: the game ends after that turn). A trigger that never fires ends the game after twice the round count (`Preset.round_cap`). `GameState.end_triggered` records the round it fired; `acequias.game.end_fired` checks it after every turn. `unlimited_bag` (off by default) puts each drawn piece back at the bottom of the bag. The MCP overrides take the same keys.
- **Presets** (#182, opt-in): `acequias.config.NORMAL_V3` and `FLASH_V3` (`RULES_V3`) are the shipped Rules v2 presets with the tuned Rules v3 setup (`v3_best_base` in `scripts/tune.py`, which `tests/test_config_v3.py` proves equal): the river strip at 5 river hexes per segment, a bag of 16 pieces per player, vertex planting on any vertex, split scoring at 6 / 9 (`V3_POINTS`), the move die (`V3_DIE_FACES`), `each_once` cortes (`DEFAULT_BLENDS`) with the bodega bonus off, the bodega building on a new spot (12 points, 2 reds + 1 white), and the optional bribe (Normal 2, Flash 1). The end is combined (`supply_empty`, `score_target`, `dead_turns`; the supply and target finish the round) with `max_spins` 3, approved by the owner on #182 from sweep `v3end4` (#188):

  | Mode | Players | Supply m (pieces) | Score target | Main end |
  | --- | --- | --- | --- | --- |
  | Normal | 2 | 1 (14) | 50 | score target |
  | Normal | 3 | 1 (14) | 50 | supply |
  | Normal | 4 | 1.25 (20) | 55 | supply |
  | Normal | 5 | 1.25 (20) | 40 | supply |
  | Flash | 2 | 1 (14) | 30 | score target |
  | Flash | 3 | 1 (14) | 35 | score target |

  The round cap (twice the v2 round count) stays as the safety net. Flash still rejects 4 and 5 players. The shipped presets, the MCP defaults and the golden games are unchanged; making v3 the default is a later task.
- **Shared vineyard supply and combined end** (#181, opt-in, all off by default; the shipped presets do not change): `vineyard_supply` maps a player count to a multiplier m, and the supply holds m pieces per roulette sector of each varietal (14 x m in all; Bonarda and Cabernet Franc have 1 sector, the others 2). Every planted vineyard takes a piece of its varietal; the pieces left are the supply less the vineyards on the board, so no new state is needed. A plant or a resow spins the roulette; a spin on a varietal with no piece left is spun again, up to `max_spins` spins in all (1 by default: no respin). A resown vineyard's own piece goes back first, so its own varietal always works. `Plant` is illegal once the supply is empty. *Lost turn*: when every spin of a plant fails, nothing is planted, no piece is taken and the actions left are gone (canals and bodegas placed earlier in the turn stay); when every spin of a resow fails, the vineyard keeps its varietal and the turn ends before the actions. The turn is lost only if no plant or resow succeeded earlier in it (#184): after a good season, a plant that succeeds and then a plant that fails ends the turn but is not a lost turn, and a successful resow counts as planted. A turn with no spin is never lost. *Dead turns*: each player counts their own lost turns in a row (`Player.dead_turns`), and any other turn of theirs sets it back to 0. *Combined end*: `end_conditions` lists several triggers, and the first to fire ends the game: `supply_empty` (the supply is empty) and `score_target` finish the round (`finish_round`), `dead_turns` (every player has lost 2 turns in a row) ends the game at once, and the round cap (twice the round count) is the safety net. `GameState.end_trigger` records which one ended the game (`rounds` for the cap). `scripts/tune.py --sweep v3end2` plays 3 supply levels x 3 score targets x `max_spins` 2 / 3 around `v3_best_base` and reports the advantage, turns per game and per player against `V3END2_TURN_TARGETS` (total turns per game: Flash 2p 16-24, 3p 24-30; Normal 2p 24-36, 3p 30-40, 4p 36-48, 5p 40-50), minutes at 35 s per turn, the share of games each trigger ended, lost turns per game, the bodega rate and the winning score; `--sweep v3end2c` reruns the 5p rows named in `V3END2_CONFIRM` at 2000 games. The MCP overrides take the same keys.

#### Varietal roulette

The board's vineyards have no varietal. When a player claims a vineyard, they spin the roulette and that varietal is planted there for the rest of the game. The roulette has 14 equal sectors:

| Varietal | Sectors | Points |
| --- | --- | --- |
| Malbec | 2 | 6 |
| Cabernet Sauvignon | 2 | 6 |
| Cabernet Franc | 1 | 7 |
| Syrah | 2 | 6 |
| Merlot | 2 | 6 |
| Bonarda | 1 | 7 |
| Torrontés | 2 | 6 |
| Chardonnay | 2 | 6 |

The rarer Bonarda and Cabernet Franc are worth a bit more; a spin is worth 86/14, about 6.14 points, on average. The bodega bonus needs watered vineyards of 3 **different** varietals. The points are the scale-1 `ROULETTE_POINTS` (2, rare 3) at the score scale of 3 (#111), with a rare bonus of +1 instead of +3, picked in #103 (`SHIPPED_POINTS`).

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

All pieces are parametric build123d models printed on the Bambu Lab A1 (256 × 256 mm plate, 0.4 mm nozzle, PLA). The Rules v2 pieces (action die, season die, roulette) are #113.

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
| `calculate_score` | `mode`, `hexes`, `players` (id and debt), optional `canals`, `floodgates`, `claims`, `overrides` (preset values, as in `simulate_game`; e.g. roulette rules) | `mode`, `scores` per player by term, in points (vineyards + bodega − rights paid + rights collected − debt; rights are `water_right_points` per rival per vineyard) with the number of `bodegas`, the watered vineyards and their paths, and `winners` |
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

`acequias/config.py`: every number the game needs, as one immutable `Preset` per mode, fetched with `preset(mode)`. Board generation, setup, scoring, the round loop, and the simulation read their values from it and hard-code none. Tuning changes the shipped values there; experiments build variants with `with_overrides`, which validates them like the shipped presets. `RULES_V1` holds the Rules v1 presets (shipped until #126), which the tuning sweeps and the engine tests of those rules pin. `RULES_V3` holds the opt-in Rules v3 presets `NORMAL_V3` and `FLASH_V3` (#182), not shipped: `preset(mode)` still returns Rules v2. Shares (stone hexes, bag mix) are whole-number percentages, and rounds are set per player count (they differ since #20). `rounds` also says which player counts a mode is for: its keys (shipped Normal 2 to 5, Flash 2 and 3). `Preset.player_counts` lists them and `check_players(players)` raises `ValueError` for any other count, e.g. "flash mode is for 2 to 3 players, got 4"; `generate_board`, `new_game`, the simulation, and `calculate_score` call it, and `seat_bonus` may list only those counts. `varietal_rules` is `VarietalRules.ROULETTE` (shipped: blank plots, planted on claim from the `roulette` sectors) or `FIXED` (Rules v1: the generator deals the varietals of `varietal_points` onto the board). `varietal_points` maps each varietal in play to its points (shipped `SHIPPED_POINTS`: 6, Bonarda and Cabernet Franc 7); `roulette` lists the sectors in order (`ROULETTE_SECTORS`). `roulette_rules(p)` switches a preset to roulette rules with the scale-1 `ROULETTE_POINTS` (2, rare 3). Validation: under fixed rules `bodega_varietals` is at most the number of varietals in `varietal_points`; under roulette rules every sector needs points, and `bodega_varietals` is at most the number of distinct sector varietals. `vineyards_per_player` is the number of vineyard plots per player. `grape_clusters_per_player` caps each player's claims: `None` (the shipped value) is no cap, otherwise an int of 1 or more. `bribe_rules` is `BribeRules.ACTION_DIE` (shipped) or `D6` (the Rules v1 bribe; `die_faces` is its die); `action_die_cost` (0 or more; 0 is for testing only; shipped `ACTION_DIE_COST = 1`) and `action_die` (the faces in order, not empty; shipped `CONSTRUCTIVE_DIE_FACES`; `ACTION_DIE_FACES` is the 2/2/2 die) are used only under action die rules, which also need a floodgate share of 0 in `bag_mix` and, for a `RESOW` face, roulette rules. `action_die_rules(p)` switches a preset to the action die and sets the floodgate share to 0, rescaling the other shares to 100 by largest remainder (ties in `PieceKind` order); call it on a roulette preset, `action_die_rules(roulette_rules(preset(mode)))`. `water_right_points` (1 or more; shipped 3) is the points a watered claimed vineyard pays each distinct rival on its water path. `season_roll_every` (shipped 3 in Normal, 2 in Flash; `None` is off) starts every X-th round with a [season roll](#season-roll). `season_roll_personal_faces` (a bool; shipped `False`) lets a season roll's personal face apply when `True`; `False` keeps only its season faces. `season_points` and `drought_points` (shipped `None`: one common plot's value, 6, and half of it, 3) are the good season gain and the drought loss. `multiple_bodegas` (a bool; shipped `True`) lets a player earn the bodega bonus once per disjoint group of `bodega_varietals` distinct watered varietals ([Bodega bonus](#bodega-bonus)). `scaled(p, factor)` multiplies every scoring value, each `varietal_points` value, `bodega_points` and `water_right_points`, by an int `factor` of at least 1 and keeps everything else; debt is not scaled (the bribe d6 and `action_die_cost` stay as they are; #103 picks them against the scale).

### Water reach

`acequias/flow.py`: `water(board)` maps every watered vineyard, claimed or not, to the one `WaterPath` its water takes; dry vineyards are absent. A path's `canals` run from the river end to the vineyard, and its `owners` include the claimant's own id, so scoring removes the claimant when it counts water rights. Path choice uses the vineyard's claimant on the board. The module is pure and deterministic.

### Board generator

`acequias/board.py`: `generate_board(players, seed, mode, *, preset=None)` returns a `Board` with tiles only. Equal arguments give an equal board, in any process; all randomness comes from one `random.Random(seed)`. `preset` (from `with_overrides`) replaces the shipped one for the simulation, and must have the same mode. Each row is a river hex on the west followed by an unbroken run of hexes east, and the river zigzags south as one chain, so a hex `k` steps east of its river hex is `k` from the river. Vineyards are placed in the preset's distance range (under fixed rules dealt the varietals of `varietal_points` as evenly as possible; under roulette rules left blank, with the two varietal shuffles skipped) and a layout is kept only if at least as many vineyards as players are reachable through empty hexes; a preset that cannot be met (e.g. a distance range the rows cannot hold, or no layout within the retry cap) raises `ValueError`.

### Assembly instructions

`acequias/assembly.py`: `assembly_instructions(board)` lists one `AssemblyStep` per tile, ignoring canals, floodgates, and claims. Steps go row by row from north to south and west to east; rows and positions count from 1 (row 1 is the northernmost, whatever its `r`). Each step holds `row`, `position`, the axial `hex` for programs, `terrain`, `varietal` (`Board.varietal_at`, so `None` on a blank roulette vineyard), and the `text` a person reads, e.g. `"Row 2, hex 3: vineyard, Malbec"`, or `"Row 2, hex 3: vineyard"` for a blank one. Because rows are staggered, hex 1 of every row after row 1 also names the hex above it that it touches (`"south-east of row 1, hex 1"`, the north-west neighbour preferred); on generated boards that is the river, hex 1 of the row above. A board that cannot be laid out row by row (a skipped `r`, a gap in a row, or a row that does not touch the one above) raises `ValueError` naming the row.

### Scoring

`acequias/scoring.py`: `calculate_score(state, preset=None)` scores a `GameState` as given, whatever its round, and changes nothing; with `preset=None` the varietal points and bodega values come from `state.preset`, or `preset(state.mode)` when that is `None`, and an explicit preset from `with_overrides` replaces them. A vineyard's varietal is `board.varietal_at(hex)` and its points `preset.varietal_points`; a watered claimed vineyard with no varietal (never planted) raises `ValueError`. It returns a read-only mapping of player id → `Score`, in seat order, with the terms `vineyards`, `bodega`, `rights_paid`, `rights_collected`, `debt`, and `total` (the names the MCP tool exposes), all in points: each rival on a vineyard's path gets `preset.water_right_points`, so `rights_paid` and `rights_collected` are rival-vineyard pairs times that value, plus `bodegas` (the number of bodega bonuses: 0 or 1, or under `multiple_bodegas` the largest number of disjoint groups of `bodega_varietals` watered vineyards of distinct varietals, from `bodega_count`; `bodega` is `bodegas × bodega_points`), `watered` (the tie-break count) and `watered_vineyards`: each watered claimed vineyard in hex order, with its varietal, its `WaterPath`, and the rivals it `pays` in seat order. `winners(scores)` returns the winning ids in seat order: highest `total`, then highest `watered`, otherwise a shared win. Debt is only read from `Player.debt`; bribes (or action die rolls) add to it.

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

`acequias/sim.py`: `simulate_game(rules, n, seed)` plays `n` bot games of one mode and returns a `SimResult`. `SimRules` holds `mode`, `players`, `policies` (`policies[k]` plays seat `k + 1`, whatever the start player), and `overrides` for `with_overrides` (`players` must be one of the resulting preset's `player_counts`); the resulting preset is passed only to `new_game`, and every later step reads it from `state.preset`. Game `i` uses `game_seed(seed, i)`, and `play_one(rules, game_seed)` replays any single game of a run. A board the preset cannot satisfy raises `ValueError` naming the game index and seed, with no partial result. A shared win among `k` players gives each `1/k` win credit, so each game hands out exactly 1. Position `j` is the place in round 1's turn order, and `turn_order_advantage` is `max_j |win_rate_by_position[j] − 1/P| × P` (0.10 means a position wins 10% more or less than its fair share). Each statistic is defined in its field's docstring; `SimResult.to_json()` gives plain JSON with the names of `server/schemas.py`. `winner_varietal_rate` has a key only for each varietal in play: those of `varietal_points` under fixed rules (3 keys for Rules v1), the roulette's 8 under roulette rules (the shipped presets). `actions_per_game` also counts `"die"` (rolls), `"release"`, `"resow"`, and `"decline"`; a die floodgate counts as `"floodgate"`, and the counts still add up to `turns_per_game`, which counts log records (a die turn is two). `games_with_die` is the share of games with a roll, `die_faces_per_game` the mean rolls per game of each face, and `die_use_rate` the share of rolls resolved with a use rather than declined (`None` with no rolls).

### Performance

The engine and the bots take fast paths (precomputed tables, boards derived without re-validation) whose results must equal the plain rules. `tests/test_golden_games.py` replays fixed simulation runs against `tests/data/golden_games.json`, recorded before the speed-up, so any change in a log, a final state, a path, or a score fails; re-record it only when the rules change on purpose. The runs pin every Rules v1 value they were recorded with as overrides, so shipping new values (#20, #126) does not change them. `uv run python scripts/bench_sim.py` prints the best wall time of fixed 5-player runs and a SHA-256 of each result (equal digests mean nothing moved); `--profile` lists the hottest functions.

### CAD pieces

`acequias/cad/` holds the build123d models; it is the only code that imports build123d or trimesh, and the game logic and the server never import it at module level, so a plain install stays CAD-free. CAD frame: `x` east, `y` north, `z` up, in mm, each piece centered at `x = y = 0` with its bottom on `z = 0`; outlines come from `Hex.corners`, each corner `(x, y)` used as `(x, -y)`, so each edge faces the same `Direction` as on the board. `hex_tile.py`: `hex_tile(side, height, clearance)` is the terrain prism and `export_stl(shape, path)` writes a binary STL. `channel.py`: `canal_piece(kind)` is the tile with a groove spoke to each edge the kind opens at rotation 0 (players rotate the printed piece) and a hole for the owner token; `floodgate()` is the gate as it sits in the groove: a base that fills the groove, flush with the top, and a grip fin flush with its outer face (the one on the hex edge) that rises to the total `height`; `owner_token()` is a cap with a peg, printed cap down. `tokens.py`: `grape_cluster()` is tiers of grapes on a flat round base, topped by a stem, that rests loose on a vineyard tile (no peg); `debt_token(value)` is a disc worth 1 or 5, marked with die-face pips (no text). Both have circle footprints for the plate layout. `pieces.py`: `build_piece(type, variant, **params)` maps each piece type to its generator, as laid on the plate (the floodgate lies on its flush outer face, so it needs no supports and its layers run along the fin). Defaults are those of the [Geometry profile](#geometry-profile); any size that would leave a wall under 0.8 mm raises `ValueError` naming it.

### Board JSON

`server/schemas.py`: the JSON shapes every tool shares, so a board means the same JSON everywhere. A hex is `q`, `r`, `terrain`, and `varietal` (null except on vineyards, and null on a blank vineyard under roulette rules). Enum strings are lowercase ASCII: terrain `"river"`, `"vineyard"`, `"stone"`, `"empty"`; varietal `"malbec"`, `"cabernet_sauvignon"`, `"cabernet_franc"`, `"syrah"`, `"merlot"`, `"bonarda"`, `"torrontes"`, `"chardonnay"`; varietal rules `"fixed"`, `"roulette"`; canal `kind` `"straight"`, `"gentle_curve"`, `"sharp_curve"`, `"symmetric_y"`, `"t_branch"`, `"claw"` (the floodgate is not a kind). Directions are the case-sensitive names `"E"`, `"NE"`, `"NW"`, `"W"`, `"SW"`, `"SE"`. A canal is `q`, `r`, `kind`, `rotation` (0 to 5), `owner`; a floodgate is the canal's `q`, `r` and the `direction` it closes; a claim is `q`, `r`, `player`, and an optional `varietal` (default null): the varietal the roulette planted there, which becomes a `Board.plantings` entry; a player is `id` and `debt`, and the list order gives seats 1 to N. The preset shape (`simulate_game`'s result `preset`, and `overrides` without `mode` in both `simulate_game` and `calculate_score`) adds `water_right_points`, `varietal_rules`, `varietal_points` keyed by varietal name, `roulette` as a list of names, `grape_clusters_per_player` as an int or null (null means no cap; in `overrides`, null sets no cap and leaving the key out keeps the shipped value), `bribe_rules` (`"d6"` or `"action_die"`), `action_die_cost`, and `action_die` as a list of faces (`"floodgate"`, `"release"`, `"resow"`); `simulate_game` with `overrides={"varietal_rules": "fixed", "varietal_points": {...}, "bribe_rules": "d6", "bag_mix": {..., "floodgate": 10}, "season_roll_every": null}` simulates the Rules v1 bribe; `calculate_score` with `overrides={"water_right_points": 6}` doubles the rights terms (every score term is in points), and without `overrides` uses the shipped preset (roulette rules, so claims give the planted `varietal`). The `players` input of `generate_board` and `simulate_game` describes the counts each mode is for, and a count the preset is not for (Flash with 4 or 5 players) comes back as a tool error with the library's message; `overrides.rounds` sets the counts, e.g. `{"2": 6, "3": 6, "4": 4}` gives Flash a 4-player game for experiments. From a `generate_board` result only `mode` and `hexes` carry over to `calculate_score`: its `players` is a count, not a list, and `seed` and `assembly` are not inputs. Inputs are strict (`"3"`, `3.0`, or `true` is not an int), and the server only maps JSON to `acequias` types; every check comes from the model.

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
| Rules v2 (#114) | Varietal roulette #85, floodgate plate with grip #109, more plots and grape-cluster cap #110, larger score scale #111, action die #112, shipped values #126 (done), their pieces #113 |
| Balance | Re-check with smarter bots #103 (done), seat compensation #104 |
| Tooling | STEP/3MF per piece #37, board picture #39, faster simulation #43 (done), lookahead bot #42 (done), score-aware bot #67 (done) |
| Product | Full game-set piece list #38, rulebook, packaging, and cost #41 |

MVP pieces are plain and functional; the decorative layer below comes after the MVP.

### Quality criteria

- [x] Each tool has unit tests with pytest
- [x] Every generated board has at least one reachable vineyard per player
- [ ] Turn-order advantage is at most 10%, in Normal and in Flash separately: with the shipped Rules v2 and `score_aware` bots, met at Normal 2–4p and Flash 2–3p; Normal 5p is 0.114 ± 0.049, accepted by the owner as within the margin (#103). Flash is limited to 2–3 players because 4–5p failed (follow-up #104)
- [ ] A Normal game takes about 45–60 min and a Flash game 10–20 min, estimated at 1 minute per turn: met at every player count except 2-player Normal, which takes about 20 min by the owner's choice (more rounds would only add passes)
- [x] Each STL is a closed solid and fits with the other pieces

### Tuning results

The shipped values (Rules v2) were tuned in #103 with `scripts/tune.py`, on top of the rounds and board of #20; the full report, with the method, every sweep, and the owner's decisions, is [`_docs/tuning-results.md`](_docs/tuning-results.md). The owner approved candidate B (phases C to F): the constructive die at cost 1, a season roll every 3 rounds (Normal) or 2 (Flash) that applies only season faces, scale 3 with rare +1, multiple bodegas, and Normal's board at 18 hexes per player. Final validation (phase D re-run), seed 103002, 2,000 / 3,200 / 4,800 / 6,400 games for 2 / 3 / 4 / 5 players with `score_aware` and `greedy` (95% margin at most ±0.05), 500 with `lookahead` (±0.09 / 0.12 / 0.15 / 0.18):

| Mode | Players | Advantage (score_aware / greedy / lookahead) |
| --- | --- | --- |
| Normal | 2 | 0.022 / 0.024 / 0.032 |
| Normal | 3 | 0.011 / 0.061 / 0.284 |
| Normal | 4 | 0.054 / 0.107 / 0.177 |
| Normal | 5 | 0.114 / 0.106 / 0.107 |
| Flash | 2 | 0.026 / 0.016 / 0.160 |
| Flash | 3 | 0.081 / 0.063 / 0.114 |

Winning scores run 5.3–9.3 in Normal and 4.1–7.1 in Flash; about a third to a half of the games still end in a shared win. Flash with 4 or 5 players stayed at 0.14–0.38 with every bot and every fix tried (5 rounds, a seat bonus, a tiebreak), so Flash ships for 2 or 3 players only. Normal 5p (0.114 ± 0.049) is accepted as within the margin.

The Rules v1 values were tuned in #20. Final validation, seed 20002, 2,000 / 3,200 / 4,800 / 6,400 games for 2 / 3 / 4 / 5 players (95% margin on the advantage at most ±0.05). Seatings: all `greedy` bots, or `saboteur` and `greedy` alternating (mixed). Minutes assume 1 minute per turn.

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

Bold marks a miss of the 0.10 target. With these one-move-ahead bots scores were very low and about half of the games (more with saboteurs) ended in a shared win, which led to Rules v2 and its re-tuning in #103.

### Open questions

Provisional defaults let work start; the simulation (or CAD, for physical values) settles them. The game values were settled in #20 and, for Rules v2, in #103 ([results](#tuning-results)).

- [x] Normal rounds: 10 / 15 / 12 / 10 for 2 / 3 / 4 / 5 players (#20)
- [x] Flash rounds: 6 / 6 for 2 / 3 players; Flash is for 2 or 3 players only (#20, #103)
- [x] Hexes per player: Normal 18 (#103), Flash 14 (#20)
- [x] Bag mix: straight 44% · gentle curve 22% · sharp curve 17% · symmetric Y 6% · T branch 6% · claw 5%, no floodgates (they come from the action die), sized to board capacity (#103)
- [x] Vineyards per player: 2, both modes; no grape-cluster cap (#103)
- [x] Stone hexes: 10% of the non-river hexes (kept)
- [x] Vineyard distance from the river: 4 hexes (3 canals) in both modes
- [x] Score scale: 3, with a rare bonus of +1: varietals 6, Bonarda and Cabernet Franc 7; water rights 3 (#103)
- [x] Action die: the constructive die (floodgate, release, resow x2, good season, drought) at cost 1; good season +6, drought −3 (#103)
- [x] Season roll: every 3 rounds in Normal, every 2 in Flash; season faces only (#103, #138)
- [x] Bodega bonus: +6 Normal, +3 Flash, once per bodega (multiple bodegas) (#103, #135)
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

`uv run python scripts/tune.py` runs #20's final validation, `--sweep <name>` one sweep, `--candidate <sweep> <label>` the final validation of one candidate (e.g. `--candidate shipped "shipped (Rules v2)"` for the shipped presets), and `--list` lists them (see [Tuning results](#tuning-results)). A player count a candidate's preset is not for is skipped with a note on stderr, and with `--players` it is an argument error. Games run in chunks on `--workers` processes (default 3) at below-normal priority, with progress and an ETA on stderr. Each finished chunk is saved under `output/tune-checkpoints/` (`--checkpoint-dir`), so running the same command again resumes a stopped run; `--fresh` ignores the saved chunks. Neither the worker count nor the chunk size changes any number.

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
- [Rules v3 rules sheet](_docs/rules-v3.md): the Rules v3 rules for players
- [Varietal fact card](_docs/varietals.md): the 8 varietals, print colors, points, and sourced facts
- [Action die](_docs/action-die.md): what each Rules v3 die face means in Mendoza, and its icon
- [Player rulebooks](site/): Spanish (`site/reglas/`) and English (`site/rules/`), published at <https://cristiangarciavd.github.io/acequias-mcp/> with a PDF each, built by `.github/workflows/pages.yml`
- [AGENTS.md](AGENTS.md): instructions for coding agents
- `_docs/outdated/`: superseded documents kept for history only; this README and the GitHub issues replace them

## License

- Code: [PolyForm Noncommercial 1.0.0](LICENSE), © 2026 Cristian García.
- Game content (rules, rulebooks, 3D models, art): [CC BY-NC-SA 4.0](LICENSE-GAME.md), © 2026 Cristian García.
