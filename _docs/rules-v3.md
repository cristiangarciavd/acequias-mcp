# Acequias - Rules v3 (player rules sheet)

Rules v3 (#149) is the redesign of Acequias: every turn starts with a roll of the
action die, and players **plant** their own vineyards where three hexes meet, next to
canals they have brought water to. These are the rules for players. The technical
summary is the README's [Rules v3](../README.md#rules-v3-the-shipped-game) section,
and the engine is `acequias/` (`planting = vertices`, `board_shape = river_strip`).

> **Status:** Rules v3 is the shipped game since #192. Its tuned values are the
> presets `NORMAL_V3` and `FLASH_V3` (`acequias.config.RULES_V3`, #182), which the
> engine and the MCP tools use by default; Rules v2 stays as `NORMAL_V2` / `FLASH_V2`.

## Goal

Build canals that carry water from the river, plant vineyards along them, and score
the most points when the game ends.

## Components

| Component | Detail |
| --- | --- |
| River strip | A short chain of river hexes along the west side of the table. The rest of the table is open: no stones, no printed vineyards |
| Canal pieces (neutral) | Six shapes: straight, gentle curve, sharp curve, symmetric Y, T branch, claw. The bag mix is about 44% straight, 22% gentle curve, 17% sharp curve, 6% Y, 6% T, 5% claw |
| Owner tokens | One on each canal you place, in your color |
| Vineyards | Grape clusters colored by varietal family (violet, red or fluorescent green, with the varietal's initials), taken from the shared vineyard supply and planted on hex corners, with your owner peg on top (see [Planting](#planting)) |
| Floodgates | Small gates that close one opening of a canal; they come only from the action die |
| Action die | Six faces: Floodgate, Release, Resow, Move, Good season, Drought (see [The action die](#1-roll-the-action-die-mandatory) and [`action-die.md`](action-die.md)) |
| Roulette | 14 equal sectors that pick a planted vineyard's varietal (see [Varietals](#varietals-and-points)) |
| Vineyard supply | Shared vineyard pieces per varietal: 2 of each varietal with two roulette sectors and 1 of Bonarda and Cabernet Franc (14 in all), or 3 and 1 (20 in all) in Normal with 4 or 5 players |
| Bodega tokens | One per player (see [Bodega building](#bodega-building)) |
| Debt tokens | Track what each player paid for bribes |

There is no season die and no vineyard tiles under Rules v3.

## Setup

1. **River strip.** Lay the river strip: one segment for 2 players and one more
   segment for each extra player. Each segment has **5 river hexes**, one per row,
   with a slight inward bend. All water comes from the river.
2. **Bag.** Fill the bag with **16 canal pieces per player**, split by the bag mix
   above, and shuffle it. The bag holds no floodgates.
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
| **Floodgate** | Bribe: **2 debt in Normal, 1 in Flash** | You **may** place a floodgate on an open canal opening, anyone's |
| **Release** | Bribe: **2 debt in Normal, 1 in Flash** | You **may** remove one floodgate from the board, anyone's. It leaves the game |
| **Resow** | Free | You **may** spin the roulette again for any planted vineyard, yours or a rival's: first choose the vineyard, then spin. The new result stands, even if it is worse. It stays where it is and keeps its owner |
| **Move** | Free | You **may** move one of **your** vineyards to another corner where you could plant a new one. It keeps its varietal |
| **Good season** | Free | This turn you take **2 actions**: plant + plant, or canal + plant (in either order). Never 2 canals |
| **Drought** | Free | You lose your action this turn |

You pay the bribe only when you place or remove a floodgate; if you decline the face,
or it has no use, it costs nothing.

### 2. Take your action

Unless you rolled a Drought, take **one** action (two after a Good season):

- **Place a canal.** Take a piece from the market and put it on an empty hex with
  your owner token. At least one of its openings must line up with the river or with
  an opening of a canal already on the table (even a dry one or one closed by a
  floodgate). Its other openings may face anything. Refill the market from the bag;
  when the bag is empty the market shrinks.
- **Plant a vineyard** (see [Planting](#planting)).
- **Build a bodega** (see [Bodega building](#bodega-building)).
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
- Spin the roulette: that varietal is planted there, and you take its piece from the
  shared supply. The vineyard is yours. You cannot plant once the supply is empty.
- **Respins:** if the roulette lands on a varietal with no piece left, spin again, up
  to **3 spins** in all. A Resow spins the same way; the resown vineyard's own piece
  goes back to the supply first, so its own varietal always works.
- **Lost turn:** if every spin fails, nothing is planted (a failed resow keeps its
  varietal) and the rest of your turn is lost. It is a lost turn only if nothing was
  planted or resown earlier in the same turn.

## Scoring

### Split vineyard scoring

A vineyard is worth **6** points, or **9** for the rarer Bonarda and Cabernet Franc.
Its value is split in **thirds**, one third for each of the 3 hexes around its
corner:

- A third scores for the **owner of the canal** on that hex, but only if that canal
  carries water at the end of the game. It does not matter who planted the vineyard.
- A third on a river hex, an empty hex, or a dry canal scores for nobody.

A common vineyard pays 2 points per watered third; a rare one pays 3.

**Example.** A Bonarda (9) sits between two of my watered canals and one watered
rival canal: I score 6 and the rival scores 3. If a floodgate dries my two canals, I
score 0 and the rival still scores 3.

There are no water rights under Rules v3.

### Cortes (blends)

You hold a varietal when you own **at least one watered third** of a vineyard of it,
whoever planted it, as it is at the end. Each *corte* whose varietals you all hold
scores once (a vineyard may count for several):

| Corte | Points |
| --- | --- |
| Malbec + Cabernet Sauvignon, Malbec + Bonarda, Malbec + Syrah | 2 each |
| Malbec + Cabernet Franc, Chardonnay + Torrontés, Malbec + Torrontés | 3 each |
| Malbec + Cabernet Sauvignon + Merlot, + Cabernet Franc, or + Bonarda | 4 each |
| Malbec + Cabernet Sauvignon + Merlot + Cabernet Franc | 5 |

### Bodega building

Once per game you may use an action to **build a bodega**: put your bodega token on a
free corner where you could plant a vineyard. You need **2 different red and 1
white** varietal (Torrontés, Chardonnay) among the vineyards you planted. The bodega
is worth **12 points**, split in thirds like a vineyard (4 per watered third, for each
canal owner). It has no varietal and is never moved or resown.

## End of the game

The game ends when the first of three triggers fires:

- **Supply empty:** the last vineyard piece is taken from the shared supply. The
  round is played out.
- **Score target:** a player's total reaches the target score. The round is played
  out.
- **Dead turns:** every player has lost **2 turns in a row** (a lost turn is one where
  every spin failed and nothing was planted). The game ends at once.

| Mode | Players | Supply | Score target | Main end |
| --- | --- | --- | --- | --- |
| **Normal** | 2 | 14 pieces | 50 | Score target |
| **Normal** | 3 | 14 pieces | 50 | Supply |
| **Normal** | 4 | 20 pieces | 55 | Supply |
| **Normal** | 5 | 20 pieces | 40 | Supply |
| **Flash** | 2 | 14 pieces | 30 | Score target |
| **Flash** | 3 | 14 pieces | 35 | Score target |

As a safety net, the game also ends after twice the round count (Normal 2p 20, 3p 30,
4p 24, 5p 20 rounds; Flash 12), which is rarely reached.

**Flash** plays by the same rules with a lower score target, for a quick game of 2 or
3 players.

Final score:

**split vineyard points + cortes + bodega building - debt**

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
- Cortes and the bodega building replace the bodega bonus; the floodgate bribe is
  paid only when used.
- The game ends by the shared supply, a score target or dead turns instead of a fixed
  round count.
