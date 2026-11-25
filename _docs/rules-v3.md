# Acequias - Rules v3 (player rules sheet)

Rules v3 (#149) is the redesign of Acequias: every turn starts with a roll of the
action die, and players **plant** their own vineyards where three hexes meet, next to
canals they have brought water to. These are the rules for players. The technical
summary is the README's [Rules v3](../README.md#rules-v3-opt-in-not-shipped) section,
and the engine is `acequias/` (`planting = vertices`, `board_shape = river_strip`).

> **Status:** Rules v3 is an opt-in rules option, not the shipped game yet. It ships
> only after tuning and the owner's approval. Values marked **(to be tuned)** show the
> current test value from the tuning sweeps (#149, #160).

## Goal

Build canals that carry water from the river, plant vineyards along them, and score
the most points when the last round ends.

## Components

| Component | Detail |
| --- | --- |
| River strip | A short chain of river hexes along the west side of the table. The rest of the table is open: no stones, no printed vineyards |
| Canal pieces (neutral) | Six shapes: straight, gentle curve, sharp curve, symmetric Y, T branch, claw. The bag mix is about 44% straight, 22% gentle curve, 17% sharp curve, 6% Y, 6% T, 5% claw |
| Owner tokens | One on each canal you place, in your color |
| Vineyards | Grape clusters in your color, planted on hex corners (see [Planting](#planting)) |
| Floodgates | Small gates that close one opening of a canal; they come only from the action die |
| Action die | Six faces: Floodgate, Release, Resow, Move, Good season, Drought (see [The action die](#1-roll-the-action-die-mandatory) and [`action-die.md`](action-die.md)) |
| Roulette | 14 equal sectors that pick a planted vineyard's varietal (see [Varietals](#varietals-and-points)) |
| Debt tokens | Track what each player paid for bribes |

There is no season die and no vineyard tiles under Rules v3.

## Setup

1. **River strip.** Lay the river strip: one segment for 2 players and one more
   segment for each extra player. Each segment has **5 river hexes (to be tuned;
   6 also tested)**, one per row, with a slight inward bend. All water comes from
   the river.
2. **Bag.** Fill the bag with **16 canal pieces per player (to be tuned; 20 and 24
   also tested)**, split by the bag mix above, and shuffle it. The bag holds no
   floodgates.
3. **Market.** Draw 4 pieces and lay them face up: the market.
4. **Start player.** Choose a start player. The start player moves to the next seat
   every round, like the *turnos de riego* (watering turns) of Mendoza's *acequias*.

## Turn

Each round, every player takes one turn in seat order, starting with the round's
start player. A turn has two steps.

### 1. Roll the action die (mandatory)

Every turn starts with a roll. Resolve the face first:

| Face | Cost | Effect |
| --- | --- | --- |
| **Floodgate** | Bribe: **1 debt (to be tuned)** | You **must** place a floodgate on an open canal opening, anyone's, if there is one |
| **Release** | Bribe: **1 debt (to be tuned)** | You **must** remove one floodgate from the board, anyone's, if there is one. It leaves the game |
| **Resow** | Free | You **may** spin the roulette again for any planted vineyard, yours or a rival's: first choose the vineyard, then spin. The new result stands, even if it is worse. It stays where it is and keeps its owner |
| **Move** | Free | You **may** move one of **your** vineyards to another corner where you could plant a new one. It keeps its varietal |
| **Good season** | Free | This turn you take **2 actions**: plant + plant, or canal + plant (in either order). Never 2 canals |
| **Drought** | Free | You lose your action this turn |

The bribe of Floodgate and Release is paid even when the face has no use (no open
opening, or no floodgate to release). The tuning also compares an older die with two
Resow faces and no Move face **(to be tuned)**.

### 2. Take your action

Unless you rolled a Drought, take **one** action (two after a Good season):

- **Place a canal.** Take a piece from the market and put it on an empty hex with
  your owner token. At least one of its openings must line up with the river or with
  an opening of a canal already on the table (even a dry one or one closed by a
  floodgate). Its other openings may face anything. Refill the market from the bag;
  when the bag is empty the market shrinks.
- **Plant a vineyard** (see [Planting](#planting)).
- **Pass.** Always allowed.

## Water

- Water enters a canal through an opening that faces the river.
- Water crosses between two neighbouring canals only where **both** have an opening
  facing each other.
- Inside a piece, water reaches all of its openings.
- A **floodgate** closes one opening: water cannot cross that edge in either
  direction. On a piece's entrance it dries that piece and everything downstream;
  on one exit it blocks only that way onward. Only one floodgate fits on an edge.

A canal **carries water** when water reaches it from the river after floodgates.

## Planting

Vineyards grow on the **corners** of hexes (the point where 3 hexes meet), not on
hexes.

- You may plant on a free corner (no vineyard on it) that touches one of **your own**
  canals that carries water right now. A corner touches a canal when the canal sits
  on one of its 3 hexes, whichever way the canal's openings point.
- The other two hexes of the corner may be anything: rivals' canals, the river, or
  empty table. Planting next to rivals' canals is allowed.
- Spin the roulette: that varietal is planted there. The vineyard is yours.
- **Option (to be tuned; off for now):** with *three canals*, you may plant only on a
  corner whose 3 hexes all hold a canal (anyone's, wet or dry).

## Scoring

### Split vineyard scoring

A vineyard is worth **6** points, or **9** for the rarer Bonarda and Cabernet Franc
**(to be tuned)**. Its value is split in **thirds**, one third for each of the 3
hexes around its corner:

- A third scores for the **owner of the canal** on that hex, but only if that canal
  carries water at the end of the game. It does not matter who planted the vineyard.
- A third on a river hex, an empty hex, or a dry canal scores for nobody.

A common vineyard pays 2 points per watered third; a rare one pays 3.

**Example.** A Bonarda (9) sits between two of my watered canals and one watered
rival canal: I score 6 and the rival scores 3. If a floodgate dries my two canals, I
score 0 and the rival still scores 3.

There are no water rights under Rules v3.

### Bodega

Count the vineyards where you own **at least one watered third**, whoever planted
them, as they are at the end (a dried or resown vineyard counts as it is now). Each
group of **3 vineyards of 3 different varietals** is a bodega, and no vineyard counts
toward two bodegas. Each bodega scores **6 points in Normal, 3 in Flash (to be tuned;
3, 6 and 9 tested)**.

Example: Malbec, Malbec, Bonarda, Bonarda, Torrontés, Torrontés make 2 bodegas;
Malbec x3, Bonarda x2, Torrontés make only 1.

## End of the game

The game ends after a fixed number of rounds **(to be tuned)**:

| Mode | Players | Rounds (current test value) | Bodega |
| --- | --- | --- | --- |
| **Normal** | 2, 3, 4, 5 | 10, 15, 12, 10 | 6 |
| **Flash** | 2, 3 | 6, 6 | 3 |

**Flash** plays by the same rules with fewer rounds and a smaller bodega, for a quick
game of 2 or 3 players.

Final score:

**split vineyard points + bodegas - debt**

The highest score wins. On a tie, the tied player with more watered vineyards (those
with at least one watered third of theirs) wins; if that is tied too, the win is
shared.

## Varietals and points

The roulette has 14 equal sectors. Bonarda and Cabernet Franc have one sector each
and are worth 9; the others have two each and are worth 6. Their print colors and
short facts are on the [varietal fact card](varietals.md).

| Varietal | Sectors | Points | Print color |
| --- | --- | --- | --- |
| Malbec | 2 | 6 | Violet |
| Cabernet Sauvignon | 2 | 6 | Red |
| Cabernet Franc | 1 | 9 | Red |
| Syrah | 2 | 6 | Violet |
| Merlot | 2 | 6 | Red |
| Bonarda | 1 | 9 | Violet |
| Torrontés | 2 | 6 | Fluorescent green |
| Chardonnay | 2 | 6 | Fluorescent green |

## What changed from Rules v2

- The die roll is mandatory every turn; the season roll and the season die are gone.
- Players plant vineyards on hex corners instead of claiming printed vineyards.
- Vineyard points are split by thirds among the canals around them; water rights are
  gone.
- Good season and Drought change your actions instead of giving or taking points.
- The Move face replaces one of the two Resow faces.
- The board is an open table with a river strip.
