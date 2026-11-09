# Test print 1: fit check

This is the report for issue #34, the first real print of the MVP pieces on
the Bambu Lab A1. It has three parts:

1. **What to print** (filled in by the agent): the plates, where every piece
   sits on them, and where the files are
2. **What to check and record** (filled in by the owner): every blank field
   and empty checkbox below
3. **Decisions** (filled in by the owner): one chosen value per row, which
   the agent then applies in part B of #34

Nothing in this report changes the code. Every piece is printed at today's
default sizes, except where a row below says otherwise.

## Contents

- [Before you start](#before-you-start)
- [The files](#the-files)
- [Plate 1: neutral hexes](#plate-1-neutral-hexes)
- [Plate 2: neutral small pieces](#plate-2-neutral-small-pieces)
- [Plate 3: red player pieces](#plate-3-red-player-pieces)
- [Estimate set (slice only, do not print)](#estimate-set-slice-only-do-not-print)
- [Owner: check the plates in Bambu Studio](#owner-check-the-plates-in-bambu-studio)
- [Owner: setup](#owner-setup)
- [Owner: time and weight](#owner-time-and-weight)
- [Owner: fit checks](#owner-fit-checks)
- [Owner: measurements](#owner-measurements)
- [Decisions](#decisions)
- [Reprint at 18 mm (only if D1 is 18 mm)](#reprint-at-18-mm-only-if-d1-is-18-mm)
- [How to regenerate the files](#how-to-regenerate-the-files)

## Before you start

- **Three files, not two.** The issue asks for "plate 1" (all neutral pieces)
  and "plate 2" (the red player pieces). The `build_plate` tool never mixes
  hexes and small round or flat pieces on one plate, so the issue's plate 1
  comes out as two files: **plate 1** (the hexes) and **plate 2** (floodgates
  and debt tokens). Both print in the same neutral filament. The issue's
  plate 2 is **plate 3** here (red).
- **Look-alike pieces.** Several pieces look the same but differ by a few
  tenths of a millimetre (the clearance of a hex, the tolerance of a
  floodgate or owner token). The plate maps below say which is which by its
  place on the bed. **Before you take each group off the bed, put it in its
  own labelled bag or mark it with a pen** (for example "T0", "T0.2",
  "F0.10", "O0.25"). The "Label" column in each map is a suggestion.
- **How to read positions.** `x` and `y` are the center of each piece in mm,
  measured from the **front-left corner of the bed**: `x` grows to the right,
  `y` grows toward the back of the printer. Pieces fill rows from left to
  right, starting at the front.
- **Piece ids.** Each piece has an id such as `terrain-empty-04`. It is the
  object's name inside the 3MF file, so Bambu Studio shows it in the object
  list.

## The files

Generated on 2026-11-08 by calling `build_plate` with the inputs in
[How to regenerate the files](#how-to-regenerate-the-files). The 3MF files are
not in the repo (they are git-ignored); they were written here:

Test print (job `3da015ded30f`), folder
`C:\Users\user\AppData\Local\Temp\claude\d16f78fbdea62aa0\8f447e24-6b4c-45bd-93ac-cbc876f3ac62\scratchpad\print34\plates-3da015ded30f\`:

| File | Plate | Color | Pieces | Print it? |
| --- | --- | --- | --- | --- |
| `plate-1-neutral.3mf` | 1 | neutral | 14 hexes | Yes |
| `plate-2-neutral.3mf` | 2 | neutral | 4 floodgates, 2 debt tokens | Yes |
| `plate-3-red.3mf` | 3 | red (any player color) | 8 owner tokens, 2 grape clusters | Yes |

Estimate set (job `87f58eaa41bf`), folder
`C:\Users\user\AppData\Local\Temp\claude\d16f78fbdea62aa0\8f447e24-6b4c-45bd-93ac-cbc876f3ac62\scratchpad\print34\plates-87f58eaa41bf\`:

| File | Plate | Color | Pieces | Print it? |
| --- | --- | --- | --- | --- |
| `plate-1-neutral.3mf` | 1 | neutral | 68 hexes | No, slice only |
| `plate-2-neutral.3mf` | 2 | neutral | 28 hexes | No, slice only |
| `plate-3-neutral.3mf` | 3 | neutral | 5 floodgates, 8 debt tokens | No, slice only |
| `plate-4-red.3mf` | 4 | red | 12 owner tokens, 2 grape clusters | No, slice only |
| `plate-5-blue.3mf` | 5 | blue | 12 owner tokens, 2 grape clusters | No, slice only |
| `plate-6-yellow.3mf` | 6 | yellow | 12 owner tokens, 2 grape clusters | No, slice only |
| `plate-7-green.3mf` | 7 | green | 12 owner tokens, 2 grape clusters | No, slice only |

That folder is temporary. Copy both `plates-...` folders somewhere safe
before you start; if they are gone, regenerate them (same input, same files).

## Plate 1: neutral hexes

File `plate-1-neutral.3mf`. All hexes: side 16 mm, height 4 mm. Canal pieces:
groove 6 mm wide, 1.5 mm deep, owner-token hole 4 mm across, 2 mm deep.
Two rows: front row `y = 21.00`, second row `y = 47.60`.

| Piece id | What it is | Differs by | Label | x (mm) | y (mm) |
| --- | --- | --- | --- | --- | --- |
| `terrain-empty-01` | terrain hex | clearance 0 | T0 | 18.86 | 21.00 |
| `terrain-empty-02` | terrain hex | clearance 0 | T0 | 49.57 | 21.00 |
| `terrain-empty-03` | terrain hex | clearance 0 | T0 | 80.28 | 21.00 |
| `terrain-empty-04` | terrain hex | clearance 0.2 | T0.2 | 110.99 | 21.00 |
| `terrain-empty-05` | terrain hex | clearance 0.2 | T0.2 | 141.71 | 21.00 |
| `terrain-empty-06` | terrain hex | clearance 0.2 | T0.2 | 172.42 | 21.00 |
| `canal-straight-01` | canal, straight | clearance 0 | C0 | 203.13 | 21.00 |
| `canal-gentle_curve-01` | canal, gentle curve | clearance 0 | C0 | 233.85 | 21.00 |
| `canal-sharp_curve-01` | canal, sharp curve | clearance 0 | C0 | 34.21 | 47.60 |
| `canal-symmetric_y-01` | canal, symmetric Y | clearance 0 | C0 | 64.93 | 47.60 |
| `canal-t_branch-01` | canal, T branch | clearance 0 | C0 | 95.64 | 47.60 |
| `canal-claw-01` | canal, claw | clearance 0 | C0 | 126.35 | 47.60 |
| `canal-straight-02` | canal, straight | clearance 0.2 | C0.2 | 157.06 | 47.60 |
| `canal-straight-03` | canal, straight | clearance 0.2 | C0.2 | 187.78 | 47.60 |

In words: the front row is three T0 hexes, then three T0.2 hexes, then two
canals (straight, gentle curve). The second row is four canals (sharp curve,
Y, T, claw), then the two straight canals at clearance 0.2 on the right.
The two straight canals look alike: `canal-straight-01` (front row, C0) and
`canal-straight-02`/`-03` (second row, right, C0.2).

## Plate 2: neutral small pieces

File `plate-2-neutral.3mf`. One row at `y = 11.00`, left to right.
Floodgates: groove 6 mm, depth 1.5 mm, thickness 2 mm. Debt tokens: 12 mm
across, 2 mm thick.

| Piece id | What it is | Differs by | Label | x (mm) | y (mm) |
| --- | --- | --- | --- | --- | --- |
| `floodgate-01` | floodgate | tolerance 0.10 | F0.10 | 11.00 | 11.00 |
| `floodgate-02` | floodgate | tolerance 0.15 (default) | F0.15 | 26.00 | 11.00 |
| `floodgate-03` | floodgate | tolerance 0.20 | F0.20 | 41.00 | 11.00 |
| `floodgate-04` | floodgate | tolerance 0.25 | F0.25 | 56.00 | 11.00 |
| `debt_token-1-01` | debt token | value 1 | D1 | 71.00 | 11.00 |
| `debt_token-5-01` | debt token | value 5 | D5 | 86.00 | 11.00 |

The four floodgates look almost the same: bag each one on its own as it
comes off, from left to right.

## Plate 3: red player pieces

File `plate-3-red.3mf`. One row at `y = 12.00`, left to right. Owner tokens:
cap 7 mm across, 1.2 mm high, printed cap down with the peg up. Grape
clusters: 14 mm base, 15 mm high.

| Piece id | What it is | Differs by | Label | x (mm) | y (mm) |
| --- | --- | --- | --- | --- | --- |
| `owner_token-01` | owner token | tolerance 0.10 | O0.10 | 12.00 | 12.00 |
| `owner_token-02` | owner token | tolerance 0.10 | O0.10 | 29.00 | 12.00 |
| `owner_token-03` | owner token | tolerance 0.15 (default) | O0.15 | 46.00 | 12.00 |
| `owner_token-04` | owner token | tolerance 0.15 (default) | O0.15 | 63.00 | 12.00 |
| `owner_token-05` | owner token | tolerance 0.20 | O0.20 | 80.00 | 12.00 |
| `owner_token-06` | owner token | tolerance 0.20 | O0.20 | 97.00 | 12.00 |
| `owner_token-07` | owner token | tolerance 0.25 | O0.25 | 114.00 | 12.00 |
| `owner_token-08` | owner token | tolerance 0.25 | O0.25 | 131.00 | 12.00 |
| `grape_cluster-01` | grape cluster | - | G | 148.00 | 12.00 |
| `grape_cluster-02` | grape cluster | - | G | 165.00 | 12.00 |

The owner tokens come in pairs, left to right: 0.10, 0.15, 0.20, 0.25. Bag
each pair on its own.

## Estimate set (slice only, do not print)

This is a deliberately large 4-player Normal set, used only to get a sliced
time and weight (D11). It is an upper bound, not the real piece list (that is
issue #38). Assumptions:

- 48 terrain hexes: 4 players x 12 hexes each (12 of each terrain; all
  terrains are the same plain tile in the MVP)
- 48 canal pieces, one per hex: 8 of each of the six shapes
- 5 floodgates
- 12 owner tokens and 2 grape clusters per player, 4 players (red, blue,
  yellow, green)
- 8 debt tokens: 4 of value 1 and 4 of value 5
- Every size at today's default

That is 165 pieces on 7 plates (listed in [The files](#the-files)). Open each
of the 7 files in Bambu Studio, slice it with the same settings as the test
print, and write the time and weight in [Owner: time and
weight](#owner-time-and-weight). The `build_plate` input is in [How to
regenerate the files](#how-to-regenerate-the-files).

## Owner: check the plates in Bambu Studio

Before slicing: open each test-print file in Bambu Studio. **Do not press
"Arrange" and do not move any piece.** Check that every piece is already on
the bed, and that each piece id sits where the plate map above says (same id,
same x and y from the bed's front-left corner). If a plate is wrong, answer
No, write what is different, and attach a screenshot to a comment on #34.

| Plate | Every piece on the bed, in the right place? (Yes / No) | Note if No | Screenshot link |
| --- | --- | --- | --- |
| 1 (`plate-1-neutral.3mf`) | | | |
| 2 (`plate-2-neutral.3mf`) | | | |
| 3 (`plate-3-red.3mf`) | | | |

## Owner: setup

Fill in once per plate where it differs (D10). Supports: none.

| Field | Plate 1 | Plate 2 | Plate 3 |
| --- | --- | --- | --- |
| Printer | | | |
| Nozzle | | | |
| Filament brand | | | |
| Filament type | | | |
| Filament color | | | |
| Bambu Studio version | | | |
| Printer / filament / process profile | | | |
| Layer height (mm) | | | |
| Infill (% and pattern) | | | |
| Wall count | | | |
| Brim (yes / no) | | | |
| Supports | none | none | none |

## Owner: time and weight

Test print (D11):

| Plate | Sliced time | Sliced weight (g) | Actual time | Actual weight (g) |
| --- | --- | --- | --- | --- |
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |

Estimate set, sliced only (D11):

| Plate | Sliced time | Sliced weight (g) |
| --- | --- | --- |
| 1 (neutral hexes) | | |
| 2 (neutral hexes) | | |
| 3 (neutral floodgates and debt tokens) | | |
| 4 (red) | | |
| 5 (blue) | | |
| 6 (yellow) | | |
| 7 (green) | | |
| **Total** | | |

## Owner: fit checks

Answer each with Yes or No, and add a note when No. Attach photos to a
comment on #34 and paste the links in the "Photo" column.

| # | Check | Yes / No | Note | Photo |
| --- | --- | --- | --- | --- |
| 1 | Nothing needed supports, and every piece came off the bed whole | | | |
| 2 | Tile to tile, clearance 0 (T0 and C0): neighboring hexes sit flush on a table, no gap you can see through, no forcing (D2) | | | |
| 3 | Tile to tile, clearance 0.2 (T0.2 and C0.2): same check (D2) | | | |
| 4 | Elephant's foot: no flared bottom edge that stops tiles sitting flush (D3) | | | |
| 5 | Canal grooves line up across every shared edge when neighboring canal pieces are turned to connect, at clearance 0 (D4) | | | |
| 6 | Same, with the two C0.2 straight canals next to each other and next to a C0 canal (D2, D4) | | | |
| 7 | Owner token cap lies flat on the piece and does not cover the groove | | | |
| 8 | Grape cluster stays upright on a terrain hex and does not slide off when the tile is nudged (D8) | | | |
| 9 | Debt tokens: 1 and 5 can be told apart at arm's length (D9) | | | |
| 10 | Debt tokens: the two tokens stack flat (D9) | | | |

Floodgate in a canal groove, one row per tolerance (D7). Try each floodgate
in a C0 canal piece:

| Floodgate | Slots in by hand? | Closes the opening fully? | Neighbors still sit flush? | Lifts out by hand, no tools? | Note |
| --- | --- | --- | --- | --- | --- |
| F0.10 (`floodgate-01`) | | | | | |
| F0.15 (`floodgate-02`) | | | | | |
| F0.20 (`floodgate-03`) | | | | | |
| F0.25 (`floodgate-04`) | | | | | |

Owner token in a canal piece's hole, one row per tolerance (D5, D6). Try both
tokens of each pair:

| Owner token | Goes in by hand? | Stays in when the piece is turned over? | Comes out by hand? | Note |
| --- | --- | --- | --- | --- |
| O0.10 (`owner_token-01`, `-02`) | | | | |
| O0.15 (`owner_token-03`, `-04`) | | | | |
| O0.20 (`owner_token-05`, `-06`) | | | | |
| O0.25 (`owner_token-07`, `-08`) | | | | |

## Owner: measurements

With calipers if you have them; otherwise write `n/a`.

| What | Nominal (mm) | Measured (mm) |
| --- | --- | --- |
| Terrain hex T0, flat to flat | 27.71 | |
| Terrain hex T0, corner to corner | 32.00 | |
| Terrain hex T0.2, flat to flat | 27.31 | |
| Terrain hex T0.2, corner to corner | 31.54 | |
| Canal groove width (C0 straight) | 6.00 | |
| Floodgate F0.10 width | 5.80 | |
| Floodgate F0.15 width | 5.70 | |
| Floodgate F0.20 width | 5.60 | |
| Floodgate F0.25 width | 5.50 | |
| Owner token O0.10 peg diameter | 3.80 | |
| Owner token O0.15 peg diameter | 3.70 | |
| Owner token O0.20 peg diameter | 3.60 | |
| Owner token O0.25 peg diameter | 3.50 | |

## Decisions

For each row, write the value you choose or "keep default", and your
initials. The agent applies every changed value in part B of #34.

| # | Decision | Current default | Values printed | Chosen value | Initials |
| --- | --- | --- | --- | --- | --- |
| D1 | Hex side: 16 mm, or the 18 mm fallback | 16 mm | 16 mm | | |
| D2 | Tile clearance (gap between neighboring tiles) | 0 mm | 0, 0.2 mm | | |
| D3 | Bottom chamfer against elephant's foot: needed or not | none | none | | |
| D4 | Groove width and depth | 6 mm x 1.5 mm | 6 mm x 1.5 mm | | |
| D5 | Owner-token hole size (`hole_diameter`, `hole_depth`) | 4 mm x 2 mm | 4 mm x 2 mm | | |
| D6 | Owner-token tolerance | 0.15 mm | 0.10, 0.15, 0.20, 0.25 mm | | |
| D7 | Floodgate tolerance, and whether it needs a grip to lift it out | 0.15 mm, no grip | 0.10, 0.15, 0.20, 0.25 mm, no grip | | |
| D8 | Grape cluster size, and whether it needs a peg or hole to stay put | base 14 mm, height 15 mm, rests loose | base 14 mm, height 15 mm, loose | | |
| D9 | Debt token size and pip depth (legibility of 1 and 5) | 12 mm x 2 mm, pips 2 mm x 0.6 mm | 12 mm x 2 mm, pips 2 mm x 0.6 mm | | |
| D10 | Slicer settings (layer height, infill, walls, filament profile) | not recorded | see [Owner: setup](#owner-setup) | | |
| D11 | Sliced weight and time for a 4-player set | ~150-200 g, ~8-12 h (rough) | see [Owner: time and weight](#owner-time-and-weight) | | |

## Reprint at 18 mm (only if D1 is 18 mm)

Leave empty unless D1 is "18 mm". If it is, the agent prepares the same
plates at side 18 mm and adds them here; the owner then fills in the same
plate check, setup, time and weight, fit checks, and measurements for the
reprint before part B starts.

- Reprint files: 
- Reprint results: 

## How to regenerate the files

Running the same input again gives the same plates, the same piece
positions, and the same file names (the folder name comes from the input).

**Where the files go.** `build_plate` writes into the folder named by the
`ACEQUIAS_OUTPUT_DIR` environment variable. If it is not set, it writes into
an `output` folder inside the project folder (git-ignored). The test print
lands in `plates-3da015ded30f` and the estimate set in
`plates-87f58eaa41bf` inside that folder.

**The easy way.** In Claude Code, with the `acequias` MCP server connected
(see `README.md`, Running the MCP server), say: "Call the acequias
`build_plate` tool with exactly the test-print input from
`_docs/test-print-1.md`", and the same for the estimate-set input. Every
other `build_plate` setting stays at its default (bed 256 x 256 mm, margin
5 mm, gap 3 mm).

**Test-print input:**

```json
{
  "entries": [
    {"piece": {"type": "terrain", "terrain": "empty", "clearance": 0.0}, "count": 3, "color": "neutral"},
    {"piece": {"type": "terrain", "terrain": "empty", "clearance": 0.2}, "count": 3, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "straight", "clearance": 0.0}, "count": 1, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "gentle_curve", "clearance": 0.0}, "count": 1, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "sharp_curve", "clearance": 0.0}, "count": 1, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "symmetric_y", "clearance": 0.0}, "count": 1, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "t_branch", "clearance": 0.0}, "count": 1, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "claw", "clearance": 0.0}, "count": 1, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "straight", "clearance": 0.2}, "count": 2, "color": "neutral"},
    {"piece": {"type": "floodgate", "tolerance": 0.1}, "count": 1, "color": "neutral"},
    {"piece": {"type": "floodgate", "tolerance": 0.15}, "count": 1, "color": "neutral"},
    {"piece": {"type": "floodgate", "tolerance": 0.2}, "count": 1, "color": "neutral"},
    {"piece": {"type": "floodgate", "tolerance": 0.25}, "count": 1, "color": "neutral"},
    {"piece": {"type": "debt_token", "value": 1}, "count": 1, "color": "neutral"},
    {"piece": {"type": "debt_token", "value": 5}, "count": 1, "color": "neutral"},
    {"piece": {"type": "owner_token", "tolerance": 0.1}, "count": 2, "color": "red"},
    {"piece": {"type": "owner_token", "tolerance": 0.15}, "count": 2, "color": "red"},
    {"piece": {"type": "owner_token", "tolerance": 0.2}, "count": 2, "color": "red"},
    {"piece": {"type": "owner_token", "tolerance": 0.25}, "count": 2, "color": "red"},
    {"piece": {"type": "grape_cluster"}, "count": 2, "color": "red"}
  ]
}
```

**Estimate-set input:**

```json
{
  "entries": [
    {"piece": {"type": "terrain", "terrain": "river"}, "count": 12, "color": "neutral"},
    {"piece": {"type": "terrain", "terrain": "vineyard"}, "count": 12, "color": "neutral"},
    {"piece": {"type": "terrain", "terrain": "stone"}, "count": 12, "color": "neutral"},
    {"piece": {"type": "terrain", "terrain": "empty"}, "count": 12, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "straight"}, "count": 8, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "gentle_curve"}, "count": 8, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "sharp_curve"}, "count": 8, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "symmetric_y"}, "count": 8, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "t_branch"}, "count": 8, "color": "neutral"},
    {"piece": {"type": "canal", "kind": "claw"}, "count": 8, "color": "neutral"},
    {"piece": {"type": "floodgate"}, "count": 5, "color": "neutral"},
    {"piece": {"type": "debt_token", "value": 1}, "count": 4, "color": "neutral"},
    {"piece": {"type": "debt_token", "value": 5}, "count": 4, "color": "neutral"},
    {"piece": {"type": "owner_token"}, "count": 12, "color": "red"},
    {"piece": {"type": "owner_token"}, "count": 12, "color": "blue"},
    {"piece": {"type": "owner_token"}, "count": 12, "color": "yellow"},
    {"piece": {"type": "owner_token"}, "count": 12, "color": "green"},
    {"piece": {"type": "grape_cluster"}, "count": 2, "color": "red"},
    {"piece": {"type": "grape_cluster"}, "count": 2, "color": "blue"},
    {"piece": {"type": "grape_cluster"}, "count": 2, "color": "yellow"},
    {"piece": {"type": "grape_cluster"}, "count": 2, "color": "green"}
  ]
}
```

**For a developer**, the same call in-process from the project folder (after
`uv sync --extra cad`), with `ACEQUIAS_OUTPUT_DIR` set to the folder you want:

```python
import asyncio
from mcp import Client
from server.app import app

async def main(request):
    async with Client(app) as client:
        result = await client.call_tool("build_plate", request)
    print(result.structured_content["folder"])

asyncio.run(main({"entries": [...]}))  # paste one of the inputs above
```
