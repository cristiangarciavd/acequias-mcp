# Tuning results (issue #20)

The simulation (`acequias/sim.py`) run against the open parameters of
`README.md` (Open questions), for Normal and Flash and every player count from 2 to 5.
`scripts/tune.py` produces every number below.

**Status: final.** The owner decided on #20 (see [Approved values](#approved-values)):
Normal uses 15 hexes per player (at most 75 terrain hexes) and 10 rounds at
2 players, and the rest of the proposal was accepted. The final validation
below was re-run with those values, and they are in `acequias/config.py`
and `README.md`. Follow-ups for the missed targets: #103 and #104.

## Summary

| Parameter | Mode | Before #20 | Final | Main evidence |
| --- | --- | --- | --- | --- |
| Rounds (2/3/4/5 players) | Normal | 12/12/12/12 | 10/15/12/10 | 3-5p: 45/48/50 turns, inside 45-60, a whole number of start-player rotations. 2p: the owner chose a shorter game (20 turns); the 2p board is full by about 8 rounds, so more rounds only add passes (sweep `rounds2p`) |
| Rounds (2/3/4/5 players) | Flash | 5/5/5/5 | 6/6/4/4 | Length target 10-20 turns met (12/18/16/20). The target's low end (rounds 5/4/3/2) pushes 4p and 5p advantage to 0.38 and 0.54 |
| Hexes per player | Normal | 12 | 15 (owner) | The sweeps favoured 24 (fewer passes, lower advantage), but that needs 120 terrain hexes at 5p. The owner capped it at about 75 |
| Hexes per player | Flash | 7 | 14 | 7 cannot hold vineyards at distance 4. 14 gives fewer passes than 10 |
| Vineyard distance | Normal | 4-5 | 4-4 | 3-4 gives seat 2 a large edge (advantage 0.16-0.61). 4-4 and 4-5 are close; 4-4 scores higher with fewer ties |
| Vineyard distance | Flash | 2-3 | 4-4 (owner) | 2-3 hands seat 1 most wins (advantage 0.37-1.73). 3-4 gives seat 2 a large edge (0.09-0.75). Only 4-4 is near balance |
| Vineyards per player | both | 2 | 2 (kept) | 3 gives no consistent gain in Normal and is infeasible in Flash at distance 4 |
| Stone share | both | 10% | 10% (kept) | 0% and 15% move advantage up or down within the noise and in no consistent direction |
| Bag mix | both | 40/20/15/5/5/5/10 | kept | Branchier bags raise scores and cut ties, but worsen advantage at 3p and 5p in the combined sweep |
| Market size | both | 4 | 4 (kept) | 3 and 5 differ from 4 only within the noise |
| Bribe die | both | d6 | d6 (kept, owner) | d4 makes bribes frequent and ruinous for the briber. d8 nearly removes them. See [Bribe die](#bribe-die-d4-d6-d8) |
| Bodega bonus | Normal | +2 for 3 varietals | kept | Earned by 0.0-0.2% of players. See [Bodega](#flash-bodega-bonus) |
| Bodega bonus | Flash | +1 for 3 varietals | kept (owner) | Earned by 0.0-0.4% of players. +2 for 2 varietals raises that to 1-5% |

Targets at the final validation (all 16 configurations, 2,000-6,400 games each):

- **Length (45-60 turns in Normal, 10-20 in Flash): met in 14 of 16
  configurations.** Missed by 2-player Normal (both seatings): 20 turns,
  about 20 minutes, a gap the owner accepted (see
  [Length vs board size](#length-vs-board-size)).
- **Turn-order advantage at most 0.10: met in 10 of 16, missed in 6.** It is
  met at every 2-player count, at Normal 3p, and in the mixed seating
  everywhere except Flash 5p. It is missed by all-greedy tables at Normal
  4-5p (0.122 / 0.154) and Flash 3-5p (0.119 / 0.182 / 0.286), and by
  Flash 5p mixed (0.147). No sweep candidate fixed this. Follow-ups: #103
  (re-check with smarter bots) and #104 (a seat-compensation rule). See
  [Gaps](#gaps-and-follow-ups).

## Method

- **Runner:** `scripts/tune.py` only calls `simulate_game`, `SimRules` and
  `SimResult` (#9). Each experiment is passed as `overrides` (`Preset` field
  names, #22). The script reimplements no rule and no statistic. It is not
  collected by pytest.
- **Configurations:** mode × player count (2-5) × seating. In the `greedy`
  seating every seat plays the `greedy` bot. In the `mixed` seating, seats
  alternate `saboteur` and `greedy`, with seat 1 a saboteur, so floodgate
  wars and bribes actually happen (#30).
- **Sweeps:** each sweep changes one or two parameters from a base
  (`SWEEP_BASE` in the script), with 500 games per configuration and
  run seed **20001**. Most sweeps use the greedy seating. The die sweep
  uses mixed, and the bodega sweep uses both. With 500 games, the 95% margin on the
  advantage is ±0.088 / ±0.124 / ±0.152 / ±0.175 for 2 / 3 / 4 / 5
  players. So sweeps rank candidates roughly, and only the final validation
  decides.
- **Final validation:** the final values (`PROPOSED` in the script),
  all 16 configurations, `max(2000, 1600 × (P − 1))` games (2,000 / 3,200 /
  4,800 / 6,400), and run seed **20002**, which no sweep uses. The 95%
  margin `1.96 × sqrt((P − 1) / n)` is printed next to each advantage (at
  most 0.049).
- **Length:** turns per game × `MINUTES_PER_TURN` = 1 minute per turn (an
  assumption from `README.md` > Quality criteria; #70 measures it at the
  table). A pass counts as a full turn.
- **Commands** (from the repo root):
  - `uv run python scripts/tune.py`: the final validation (every number in
    [Final validation](#final-validation)). Wall time here: 6,776 s
    (1 h 53 min) on 12 cores; 5p Normal mixed alone took 1.9 h of one core.
    The first run, at 24 Normal hexes/player, took 4 h 35 min.
  - `uv run python scripts/tune.py --sweep <name>`: one sweep (`board`,
    `stone`, `vineyards`, `bag`, `market`, `rounds`, `die`, `bodega`,
    `combined`, `rounds2p`). `--sweep all` runs all of them. The sweeps below took about
    1 h (256 jobs) plus the combined and `rounds2p` sweeps.
  - `uv run python scripts/tune.py --mode flash --players 3 --seating mixed`:
    one configuration of the final validation.
- Numbers are identical between runs. `--jobs` changes only the wall time,
  and wall times go to stderr. (Since #43 the flag is `--workers`, and runs
  save resumable checkpoints; see `README.md` > Development > Tuning.)

## Final validation

Seed 20002; games per configuration: 2p 2000, 3p 3200, 4p 4800, 5p 6400. Minutes assume 1 minute per turn.

- Normal: rounds=10/15/12/10, hexes_per_player=15, stone_share=10, vineyard_distance=4-4
- Flash: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4

These are the shipped presets; every other field is the preset's value
(vineyards 2, market 4, bag 40/20/15/5/5/5/10, d6, bodega +2/3 Normal and
+1/3 Flash).

### Balance and length

| Mode | P | Seating | Games | Advantage ± 95% | At most 0.10 | Win rate by position | Win rate by policy | Shared wins | Turns | Minutes | In length target | Pass share |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| normal | 2 | greedy | 2000 | 0.023 ± 0.044 | yes | 0.51 / 0.49 | greedy 1.000 | 0.543 | 20 | 20 | no | 0.47 |
| normal | 2 | mixed | 2000 | 0.014 ± 0.044 | yes | 0.51 / 0.49 | saboteur 0.544, greedy 0.456 | 0.659 | 20 | 20 | no | 0.47 |
| normal | 3 | greedy | 3200 | 0.069 ± 0.049 | yes | 0.31 / 0.33 / 0.36 | greedy 1.000 | 0.501 | 45 | 45 | yes | 0.64 |
| normal | 3 | mixed | 3200 | 0.006 ± 0.049 | yes | 0.33 / 0.33 / 0.34 | saboteur 0.613, greedy 0.387 | 0.777 | 45 | 45 | yes | 0.62 |
| normal | 4 | greedy | 4800 | 0.122 ± 0.049 | no | 0.22 / 0.23 / 0.28 / 0.27 | greedy 1.000 | 0.606 | 48 | 48 | yes | 0.52 |
| normal | 4 | mixed | 4800 | 0.025 ± 0.049 | yes | 0.25 / 0.25 / 0.25 / 0.24 | saboteur 0.457, greedy 0.543 | 0.914 | 48 | 48 | yes | 0.51 |
| normal | 5 | greedy | 6400 | 0.154 ± 0.049 | no | 0.18 / 0.18 / 0.23 / 0.21 / 0.20 | greedy 1.000 | 0.568 | 50 | 50 | yes | 0.42 |
| normal | 5 | mixed | 6400 | 0.054 ± 0.049 | yes | 0.21 / 0.21 / 0.20 / 0.19 / 0.19 | saboteur 0.530, greedy 0.470 | 0.912 | 50 | 50 | yes | 0.40 |
| flash | 2 | greedy | 2000 | 0.000 ± 0.044 | yes | 0.50 / 0.50 | greedy 1.000 | 0.601 | 12 | 12 | yes | 0.27 |
| flash | 2 | mixed | 2000 | 0.008 ± 0.044 | yes | 0.50 / 0.50 | saboteur 0.536, greedy 0.464 | 0.711 | 12 | 12 | yes | 0.27 |
| flash | 3 | greedy | 3200 | 0.119 ± 0.049 | no | 0.31 / 0.32 / 0.37 | greedy 1.000 | 0.567 | 18 | 18 | yes | 0.22 |
| flash | 3 | mixed | 3200 | 0.006 ± 0.049 | yes | 0.34 / 0.33 / 0.33 | saboteur 0.636, greedy 0.364 | 0.823 | 18 | 18 | yes | 0.22 |
| flash | 4 | greedy | 4800 | 0.182 ± 0.049 | no | 0.22 / 0.22 / 0.26 / 0.30 | greedy 1.000 | 0.507 | 16 | 16 | yes | 0.01 |
| flash | 4 | mixed | 4800 | 0.072 ± 0.049 | yes | 0.26 / 0.25 / 0.23 / 0.26 | saboteur 0.486, greedy 0.514 | 0.869 | 16 | 16 | yes | 0.01 |
| flash | 5 | greedy | 6400 | 0.286 ± 0.049 | no | 0.16 / 0.16 / 0.20 / 0.26 / 0.22 | greedy 1.000 | 0.458 | 20 | 20 | yes | 0.00 |
| flash | 5 | mixed | 6400 | 0.147 ± 0.049 | no | 0.21 / 0.20 / 0.17 / 0.21 / 0.21 | saboteur 0.570, greedy 0.430 | 0.870 | 20 | 20 | yes | 0.01 |

### Actions, floodgates, and bribes

| Mode | P | Seating | Canal | Floodgate | Bribe | Pass | Games with floodgate | Games with bribe | Win rate bribers | Win rate non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| normal | 2 | greedy | 9.47 | 1.22 | 0.00 | 9.31 | 0.828 | 0.000 | n/a | 0.500 | 0.00 |
| normal | 2 | mixed | 9.45 | 1.21 | 0.00 | 9.33 | 0.828 | 0.004 | 0.000 | 0.501 | 0.01 |
| normal | 3 | greedy | 14.62 | 1.74 | 0.00 | 28.64 | 0.907 | 0.000 | n/a | 0.333 | 0.00 |
| normal | 3 | mixed | 14.58 | 1.74 | 0.99 | 27.69 | 0.907 | 0.114 | 0.007 | 0.355 | 1.16 |
| normal | 4 | greedy | 20.22 | 2.85 | 0.00 | 24.93 | 0.976 | 0.000 | n/a | 0.250 | 0.00 |
| normal | 4 | mixed | 19.97 | 2.82 | 0.69 | 24.52 | 0.976 | 0.119 | 0.002 | 0.262 | 0.61 |
| normal | 5 | greedy | 25.44 | 3.35 | 0.00 | 21.20 | 0.986 | 0.000 | n/a | 0.200 | 0.00 |
| normal | 5 | mixed | 25.26 | 3.33 | 1.42 | 19.98 | 0.986 | 0.215 | 0.001 | 0.218 | 0.99 |
| flash | 2 | greedy | 7.71 | 1.08 | 0.00 | 3.21 | 0.770 | 0.000 | n/a | 0.500 | 0.00 |
| flash | 2 | mixed | 7.67 | 1.11 | 0.00 | 3.22 | 0.787 | 0.003 | 0.167 | 0.501 | 0.00 |
| flash | 3 | greedy | 12.43 | 1.56 | 0.00 | 4.01 | 0.865 | 0.000 | n/a | 0.333 | 0.00 |
| flash | 3 | mixed | 12.28 | 1.62 | 0.20 | 3.90 | 0.897 | 0.084 | 0.024 | 0.347 | 0.24 |
| flash | 4 | greedy | 15.48 | 0.31 | 0.00 | 0.21 | 0.222 | 0.000 | n/a | 0.250 | 0.00 |
| flash | 4 | mixed | 14.49 | 1.19 | 0.10 | 0.22 | 0.848 | 0.067 | 0.000 | 0.255 | 0.09 |
| flash | 5 | greedy | 19.62 | 0.28 | 0.00 | 0.10 | 0.203 | 0.000 | n/a | 0.200 | 0.00 |
| flash | 5 | mixed | 18.11 | 1.53 | 0.26 | 0.10 | 0.919 | 0.149 | 0.001 | 0.209 | 0.18 |

### Scores

| Mode | P | Seating | Total (mean ± sd) | Winning score (mean ± sd) | Vineyard points | Bodega points | Bodega rate | Rights paid | Winner has Malbec / Bonarda / Torrontés |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| normal | 2 | greedy | 0.58 ± 0.83 | 0.75 ± 0.96 | 0.58 | 0.002 | 0.001 | 0.28 | 0.20 / 0.16 / 0.02 |
| normal | 2 | mixed | 0.41 ± 0.71 | 0.53 ± 0.84 | 0.41 | 0.002 | 0.001 | 0.20 | 0.14 / 0.12 / 0.01 |
| normal | 3 | greedy | 0.73 ± 0.92 | 1.14 ± 1.02 | 0.72 | 0.004 | 0.002 | 0.54 | 0.30 / 0.14 / 0.02 |
| normal | 3 | mixed | -0.89 ± 5.09 | 0.41 ± 0.75 | 0.27 | 0.002 | 0.001 | 0.21 | 0.06 / 0.04 / 0.01 |
| normal | 4 | greedy | 0.68 ± 0.96 | 1.25 ± 0.97 | 0.68 | 0.003 | 0.001 | 0.70 | 0.24 / 0.03 / 0.00 |
| normal | 4 | mixed | -0.45 ± 3.35 | 0.30 ± 0.63 | 0.16 | 0.001 | 0.000 | 0.17 | 0.02 / 0.01 / 0.00 |
| normal | 5 | greedy | 0.72 ± 1.12 | 1.59 ± 1.06 | 0.71 | 0.003 | 0.002 | 0.83 | 0.22 / 0.04 / 0.00 |
| normal | 5 | mixed | -0.84 ± 4.06 | 0.35 ± 0.71 | 0.15 | 0.001 | 0.000 | 0.18 | 0.01 / 0.00 / 0.00 |
| flash | 2 | greedy | 0.54 ± 0.85 | 0.70 ± 1.00 | 0.54 | 0.002 | 0.002 | 0.25 | 0.20 / 0.13 / 0.02 |
| flash | 2 | mixed | 0.36 ± 0.70 | 0.47 ± 0.83 | 0.36 | 0.002 | 0.002 | 0.17 | 0.13 / 0.09 / 0.01 |
| flash | 3 | greedy | 0.63 ± 0.88 | 0.98 ± 1.01 | 0.63 | 0.001 | 0.001 | 0.48 | 0.27 / 0.11 / 0.02 |
| flash | 3 | mixed | -0.01 ± 1.33 | 0.34 ± 0.69 | 0.22 | 0.000 | 0.000 | 0.18 | 0.07 / 0.03 / 0.01 |
| flash | 4 | greedy | 0.88 ± 1.05 | 1.58 ± 0.99 | 0.88 | 0.002 | 0.002 | 0.89 | 0.28 / 0.04 / 0.00 |
| flash | 4 | mixed | 0.18 ± 0.93 | 0.51 ± 0.78 | 0.27 | 0.000 | 0.000 | 0.28 | 0.07 / 0.01 / 0.00 |
| flash | 5 | greedy | 0.97 ± 1.29 | 2.06 ± 1.09 | 0.96 | 0.004 | 0.004 | 1.11 | 0.26 / 0.06 / 0.01 |
| flash | 5 | mixed | 0.07 ± 1.27 | 0.60 ± 0.87 | 0.26 | 0.000 | 0.000 | 0.30 | 0.05 / 0.01 / 0.00 |

### First run (the proposal, before the owner's decisions)

The first final validation (same seed and game counts) used the proposal:
Normal rounds 24/15/12/10 at 24 hexes/player. Flash had the same values as
now, and its numbers were identical. Normal then gave:

| P | Seating | Advantage ± 95% | Turns | Pass share | Winning score |
| --- | --- | --- | --- | --- | --- |
| 2 | greedy / mixed | 0.004 / 0.015 ± 0.044 | 48 | 0.63 | 1.00 / 0.62 |
| 3 | greedy / mixed | 0.122 / 0.011 ± 0.049 | 45 | 0.38 / 0.36 | 1.29 / 0.25 |
| 4 | greedy / mixed | 0.147 / 0.031 ± 0.049 | 48 | 0.20 / 0.19 | 1.60 / 0.25 |
| 5 | greedy / mixed | 0.138 / 0.048 ± 0.049 | 50 | 0.06 / 0.05 | 2.10 / 0.31 |

At 15 hexes/player the advantage moves within about one margin (3p greedy
0.122 → 0.069 now meets the target; 5p greedy 0.138 → 0.154), but the
3-5p pass share rises from 0.06-0.38 to 0.40-0.64, and winning scores
drop a little.

## Findings and the owner's choices

### Length vs board size

Turns are rounds × players, so any length is reachable by choosing rounds.
The real question is how many of those turns are actual moves. A player
passes when no market piece can be placed. The bag holds one piece per
empty hex, so a small board runs out of useful moves early.

- **Extra rounds on a full board add only passes.** In the `rounds` sweep (Normal, 18
  hexes/player), 2p games with 12, 23, 24 and 30 rounds place the same
  11.4 canals and 1.8 floodgates, with identical win rates and scores. Only the pass
  count changes (10.8 → 46.8). 3p and 4p behave the same way.
- **Pass share at the first proposal (24 hexes/player):** 0.63 / 0.38 /
  0.20 / 0.06 for 2 / 3 / 4 / 5 players. In 2p Normal, about 18 of the 48
  turns are real moves. Pass share falls with board size: 2p is 0.85 / 0.72 /
  0.64 at 12 / 18 / 24 hexes/player (board sweep, distance 4-4).
- **Flash:** pass share 0.27 / 0.22 / 0.01 / 0.00. 4p and 5p use almost
  all their turns.
- **The choices put to the owner for 2-player Normal:**
  1. **Keep the length (proposed): 24 rounds, about 48 minutes, but about two
     thirds of the turns are passes.**
  2. **Shorter game:** about 10-12 rounds (20-24 turns, about 20-24 min).
     The sweeps suggest it plays the same moves: at 18 hexes/player, 12
     rounds gave identical outcomes to 24. At 24 hexes/player 2p makes
     about 18 moves per game, so 12 rounds should leave about a quarter of
     turns as passes. That figure is an estimate and was not run at 24 hexes. This misses the 45-60 min target
     for 2p.
  3. **Bigger board:** the trend (0.85 → 0.72 → 0.64 for 12 → 18 → 24
     hexes) suggests even about 40 hexes/player would leave about half the
     turns as passes. That figure is an extrapolation and was not run. It would also mean far more
     printed hexes.
- **Physical cost of the proposal:** at 24 hexes/player, Normal needs up to
  **120 terrain hexes** (5p), against 60 before #20. Flash at 14 hexes/player needs
  up to 70. The printed set must cover the largest Normal board.
- **The owner's decision:** option 2 for 2-player Normal (10-12 rounds),
  and at most about 75 terrain hexes for 5-player Normal, so **15
  hexes/player**. Sweep `rounds2p` (15 hexes/player, 500 games) shows that
  2p places the same 9.5 canals and 1.2 floodgates with identical win rates
  at 8, 10, 12 and 24 rounds: the board is full by about 8 rounds. **10
  rounds** is the shortest game in the owner's range with every real move,
  so it was chosen: 20 turns, pass share 0.47 (against 0.56 at 12 rounds).
  3-5p keep 15 / 12 / 10 rounds (45 / 48 / 50 turns, inside the target).
- **Recorded gap:** 2-player Normal takes about **20 minutes**, below the
  45-60 minute target. Reaching it would only add passes on this board.
- **Cost of the smaller board:** Normal at 15 hexes/player passes more at
  3-5 players: 0.64 / 0.52 / 0.42 (greedy), against 0.38 / 0.20 / 0.06 at 24.
  Normal needs up to 75 terrain hexes (5p) and Flash up to 70.

### Vineyard distance (and what it does to Flash)

Distance is the strongest lever on turn order:

- Normal 3-4: seat 2 wins far more often (advantage 0.16-0.61 across sizes).
  4-4 and 4-5 are close to balance. 4-4 gives higher scores and fewer
  ties than 4-5 (shared wins 0.44-0.54 vs 0.53-0.69 at 24 hexes/player).
- Flash 2-3 (current): seat 1 wins 45-72% of games against a fair share of
  20-50% (advantage 0.37-1.73). Flash 3-4: seat 2 dominates (0.09-0.75). Flash 4-4 is the only tested range near
  balance. At 7 hexes/player, 4-4 is infeasible ("only 2 hexes are at
  that distance from the river"), so 4-4 needs 10 or 14 hexes/player.
- **The owner decides:** `README.md` describes Flash as "a denser board where
  vineyards connect in 1-2 pieces". The proposed distance 4-4 means 3 canals,
  the same as Normal's minimum. Flash would then be shorter only through fewer rounds, not through a denser board.
  Keeping 2-3 means a large first-player advantage with these bots.
- **The owner's decision:** distance 4 in Flash (accepted).

### Bribe die (d4, d6, d8)

The die sweep uses the mixed seating, 500 games per configuration, seed 20001.

| Mode | P | Die | Bribes / game | Games with bribe | Mean debt | Win rate bribers / non-bribers | Advantage ± 95% |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Normal | 2 | d4 / d6 / d8 | 0.08 / 0.00 / 0.00 | 0.07 / 0.00 / 0.00 | 0.09 / 0.00 / 0.00 | 0.257 / 0.509 · 0.000 / 0.501 · n/a / 0.500 | 0.000 / 0.006 / 0.004 ± 0.088 |
| Normal | 3 | d4 / d6 / d8 | 4.03 / 1.10 / 0.53 | 0.33 / 0.12 / 0.07 | 3.37 / 1.28 / 0.82 | 0.005 / 0.421 · 0.019 / 0.356 · 0.000 / 0.346 | 0.021 / 0.033 / 0.044 ± 0.124 |
| Normal | 4 | d4 / d6 / d8 | 3.97 / 0.73 / 0.31 | 0.42 / 0.13 / 0.07 | 2.47 / 0.63 / 0.31 | 0.000 / 0.310 · 0.000 / 0.264 · 0.000 / 0.256 | 0.084 / 0.049 / 0.081 ± 0.152 |
| Normal | 5 | d4 / d6 / d8 | 6.20 / 1.64 / 0.99 | 0.59 / 0.28 / 0.19 | 3.10 / 1.15 / 0.92 | 0.000 / 0.285 · 0.000 / 0.224 · 0.000 / 0.215 | 0.172 / 0.068 / 0.061 ± 0.175 |
| Flash | 2 | d4 / d6 / d8 | 0.04 / 0.01 / 0.00 | 0.04 / 0.01 / 0.00 | 0.05 / 0.01 / 0.00 | 0.136 / 0.508 · 0.000 / 0.502 · 0.000 / 0.501 | 0.048 / 0.060 / 0.056 ± 0.088 |
| Flash | 3 | d4 / d6 / d8 | 0.76 / 0.17 / 0.08 | 0.26 / 0.08 / 0.04 | 0.64 / 0.21 / 0.12 | 0.014 / 0.388 · 0.034 / 0.345 · 0.000 / 0.340 | 0.012 / 0.028 / 0.034 ± 0.124 |
| Flash | 4 | d4 / d6 / d8 | 0.45 / 0.10 / 0.06 | 0.25 / 0.07 / 0.05 | 0.28 / 0.09 / 0.07 | 0.000 / 0.273 · 0.000 / 0.255 · 0.000 / 0.254 | 0.043 / 0.059 / 0.057 ± 0.152 |
| Flash | 5 | d4 / d6 / d8 | 1.08 / 0.26 / 0.16 | 0.44 / 0.15 / 0.10 | 0.52 / 0.18 / 0.14 | 0.000 / 0.233 · 0.000 / 0.209 · 0.000 / 0.205 | 0.143 / 0.138 / 0.164 ± 0.175 |

"Mean debt" is per player (all players, bribers or not). At the final
validation count with the d6, games with a bribe are 0.004 / 0.114 /
0.119 / 0.215 (Normal) and 0.003 / 0.084 / 0.067 / 0.149 (Flash), and
bribers win 0-2.4% against 21-50% for non-bribers (16.7% in Flash 2p, from a
handful of bribes).

- **The bot's caution:** the saboteur bribes only when the swing in
  watered vineyard points beats the expected cost `(faces + 1) / 2`. That
  means a swing of 3+ with a d4, 4+ with a d6, and 5+ with a d8. A low bribe count is
  partly this caution, not only the die.
- **Bribers almost never win, with any die.** With 0-1 points per player at
  the end (see [Score spread](#score-spread-and-shared-wins)), a debt of
  1-6 sinks the briber. A d4 makes bribes common (up to 6 per game, in
  up to 59% of games) but still ruinous. A d8 makes them rare.
- **Decision: keep the d6** (the owner accepted the proposal). Advantage does not separate the dice within
  the noise. The d6 keeps bribes present but uncommon. It also needs no
  special die.
- **Success-threshold bribe: not recommended now.** These results come from a
  one-move-ahead bot in games that score almost nothing. A stronger bot
  (#42, #67) should re-check the bribe before any rule change, which #103
  includes. So no separate issue is filed for it.

### Flash bodega bonus

Bodega sweep: Flash, 500 games per configuration, seed 20001.

| P | Seating | +1 for 3 (current): bodega rate / mean bodega points / advantage | +2 for 2: bodega rate / mean bodega points / advantage | Winner has Malbec / Bonarda / Torrontés (current → +2 for 2) |
| --- | --- | --- | --- | --- |
| 2 | greedy | 0.005 / 0.005 / 0.038 | 0.022 / 0.044 / 0.026 | 0.20/0.17/0.03 → 0.20/0.18/0.03 |
| 2 | mixed | 0.001 / 0.001 / 0.060 | 0.012 / 0.024 / 0.056 | 0.12/0.11/0.01 → 0.12/0.12/0.01 |
| 3 | greedy | 0.001 / 0.001 / 0.182 | 0.029 / 0.059 / 0.221 | 0.27/0.14/0.02 → 0.30/0.16/0.04 |
| 3 | mixed | 0.000 / 0.000 / 0.028 | 0.008 / 0.016 / 0.031 | 0.07/0.04/0.00 → 0.07/0.05/0.00 |
| 4 | greedy | 0.003 / 0.003 / 0.187 | 0.051 / 0.102 / 0.275 | 0.28/0.03/0.00 → 0.37/0.11/0.03 |
| 4 | mixed | 0.001 / 0.001 / 0.059 | 0.013 / 0.026 / 0.053 | 0.07/0.02/0.00 → 0.08/0.02/0.01 |
| 5 | greedy | 0.001 / 0.001 / 0.287 | 0.052 / 0.105 / 0.328 | 0.29/0.06/0.01 → 0.36/0.12/0.04 |
| 5 | mixed | 0.000 / 0.000 / 0.138 | 0.012 / 0.023 / 0.115 | 0.05/0.02/0.00 → 0.06/0.02/0.01 |

(Advantage margins: ±0.088 / 0.124 / 0.152 / 0.175 for 2-5 players.)

- **Normal's bodega rate** (final validation): 0.000-0.002. The +2 for all
  three varietals is earned by fewer than 1 player in 500.
- **Flash's current bonus is almost never earned** (0.0-0.5% of players).
  Changing it to +2 for 2 varietals raises that to 0.8-5.2% of players. It is still rare,
  but it pulls winners toward Bonarda and Torrontés. Its greedy advantage at 3-5p is higher
  (0.221 / 0.275 / 0.328 against 0.182 / 0.187 / 0.287). That is within the
  sweep's noise, but it never helps.
- **Decision: keep +1 for 3 in Flash** (the owner accepted the proposal). No balance gain was
  shown for the change. Either way, the bodega bonus hardly matters with these bots.

### Score spread and shared wins

`README.md` sets no target for these, so this section reports numbers and invents no threshold.

- Winning scores are tiny: mean 0.7-2.1 points (greedy) and 0.3-0.6 (mixed),
  with standard deviation about 1. Most players end with 0 or 1 watered vineyard
  points.
- **Shared wins: 46-61% of games (greedy) and 66-91% (mixed).** Most of these are ties at
  very low scores, often 0-0. In mixed games, saboteurs with debt drag the mean total below 0
  (Normal 3p: −0.89 ± 5.09).
- The branchy bag (10/10/5/25/20/20/10) halves the ties and doubles scores
  (combined sweep, Normal 24 hexes: shared wins 0.44 → 0.26 at 2p, winning
  score 1.01 → 1.94). It raised 3p and 5p advantage, though (0.036 → 0.169,
  0.143 → 0.245, 500 games), so it is not proposed. Removing stone as well
  pushes 4p and 5p advantage higher still.
- **Decision: not targeted for now** (the owner, for ties, scores, bribes and passes).
  The low scores look mostly like a bot limit: greedy and saboteur look one move
  ahead. #103 re-measures them with #42 / #67 before the bag or the scoring is
  changed for them.

### Pass share

The pass share is shown for every configuration above. At the final values it is
0.47 / 0.64 / 0.52 / 0.42 (Normal, greedy) and 0.27 / 0.22 / 0.01 / 0.00 (Flash).
There is no README target, and the owner set none. Normal passes a lot at every
player count because the owner capped the board at 15 hexes/player. See
[Length vs board size](#length-vs-board-size).

### Gaps and follow-ups

The turn-order target (0.10) is missed in 6 of 16 configurations at the final count:

| Mode | P | Seating | Advantage ± 95% | Gap | Pattern | Best sweep candidate (500 games, not validated) |
| --- | --- | --- | --- | --- | --- | --- |
| Normal | 4 | greedy | 0.122 ± 0.049 | 0.022 | Seats 3-4 win 27-28% | stone 15%: 0.089 ± 0.152 (at 18 hexes/player) |
| Normal | 5 | greedy | 0.154 ± 0.049 | 0.054 | Seat 3 wins 23% | bag 35/20/15/5/5/5/15: 0.077 ± 0.175 (at 18 hexes/player) |
| Flash | 3 | greedy | 0.119 ± 0.049 | 0.019 | Seat 3 wins 37% | bag 20/15/10/15/15/15/10: 0.039 ± 0.124 |
| Flash | 4 | greedy | 0.182 ± 0.049 | 0.082 | Seat 4 wins 30% | rounds 5 (20 turns): 0.071 ± 0.152 |
| Flash | 5 | greedy | 0.286 ± 0.049 | 0.186 | Seat 4 wins 26%, seats 1-2 16% | branchy bag, no stone: 0.107 ± 0.175 |
| Flash | 5 | mixed | 0.147 ± 0.049 | 0.047 | Seat 3 wins 17% | only the die and bodega sweeps ran mixed: 0.115-0.164 |

Also missed: the **length target for 2-player Normal** (20 turns, about 20
minutes, against 45-60), by the owner's choice; see
[Length vs board size](#length-vs-board-size).

- With all-greedy tables, the **later seats in round 1 win more**: they react
  to more of the board before it fills. Mixed tables (where the saboteur
  disrupts the leader) stay within 0.10 except Flash 5p.
- The "best candidates" above are single 500-game results with margins of
  ±0.12-0.18, so they are not reliable. In the first run, the proposal's own
  3p and 4p sweep values (0.036, 0.059) became 0.122 and 0.147 at the full
  count, and the combined sweep did not reproduce the bag gains.
- **Follow-ups filed (milestone 6):**
  1. #103: re-check balance with the look-ahead bot (#42) and the
     rights/bodega/debt-aware bot (#67), since the current gaps may come
     from the bots. It also re-checks the bribe die.
  2. #104: a rule that compensates the disadvantaged seats, compared in the
     simulation, after #103 says whether the gaps remain.

### Kept parameters (details)

- **Vineyards per player (2):** 3 lowers 3p and 4p greedy advantage at 18
  hexes (0.192 → 0.121, 0.185 → 0.112), but at 24 hexes it raised it (4p
  0.059 → 0.191, 5p 0.143 → 0.253). In Flash at distance 4 it is
  infeasible for every player count ("only 5 hexes are at that distance" at
  2p).
- **Stone share (10%):** 0% scores higher and passes less, but advantage
  moves both ways (Flash 4p 0.187 → 0.233, Normal 5p 0.189 → 0.096). 15%
  raises shared wins. No consistent gain, so it is kept.
- **Market size (4):** 3 and 5 move advantage within the noise in both
  directions, and other numbers barely change.
- **Bag mix (current):** see [Score spread](#score-spread-and-shared-wins).
  Fewer floodgates (5%) raised Normal 4-5p advantage (0.261, 0.308). More
  floodgates (15%) raised ties (shared wins up to 0.71).

## Approved values

The owner's decisions on #20 (2026-11-09):

1. 2-player Normal: 10-12 rounds, a shorter game with the same real moves;
   the 2-player time target is recorded as a known gap. **10 rounds** was
   picked from that range (sweep `rounds2p`).
2. Flash vineyards at distance 4 (proposal accepted).
3. Keep the d6 and the Flash bodega bonus of +1 for all three varietals
   (proposal accepted).
4. Board size: at most about 75 terrain hexes for 5-player Normal, so
   **15 hexes/player** instead of the proposed 24. Flash stays at 14.
5. Ties, scores, bribes and passes are not targeted for now.
6. Both follow-ups for the missed turn-order targets are filed: #103 and #104.

Shipped in `acequias/config.py`:

| Field | Normal | Flash |
| --- | --- | --- |
| `rounds` (2/3/4/5 players) | 10 / 15 / 12 / 10 | 6 / 6 / 4 / 4 |
| `hexes_per_player` | 15 | 14 |
| `vineyards_per_player` | 2 | 2 |
| `stone_share` | 10 | 10 |
| `vineyard_distance` | (4, 4) | (4, 4) |
| `market_size` | 4 | 4 |
| `bag_mix` (straight/gentle/sharp/Y/T/claw/floodgate) | 40/20/15/5/5/5/10 | 40/20/15/5/5/5/10 |
| `die_faces` | 6 | 6 |
| `bodega_points` / `bodega_varietals` | 2 / 3 | 1 / 3 |

## Sweeps

Every sweep below: 500 games per row and run seed 20001. Each one changes
only the named parameters from the base shown above its table. Columns: advantage ±
95% margin; win rate by position; share of shared wins; turns (minutes at
1/turn); pass share; mean canal / floodgate / bribe / pass actions per
game; winning score and per-player total (mean ± sd); bodega rate and
mean bodega points; share of winners with each varietal watered; share of
games with a bribe; win rate of bribers / non-bribers; mean debt per
player. "infeasible" rows are candidates the board generator or `Preset`
rejected, with the error.

### Sweep `board`: Vineyard distance x hexes per player (stone share from the base)

Command: `uv run python scripts/tune.py --sweep board`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| distance 3-4, 12 hexes/player | 2 | greedy | 0.176 ± 0.088 | 0.41 / 0.59 | 0.48 | 48 (48) | 0.86 | 5.3 / 1.19 / 0.00 / 41.5 | 0.96 ± 1.07 | 0.69 ± 0.91 | 0.000 | 0.000 | 0.26 / 0.15 / 0.06 | 0.00 | n/a / 0.500 | 0.00 |
| distance 3-4, 12 hexes/player | 3 | greedy | 0.341 ± 0.124 | 0.22 / 0.44 / 0.34 | 0.35 | 45 (45) | 0.75 | 9.7 / 1.69 / 0.00 / 33.6 | 1.36 ± 1.10 | 0.81 ± 0.95 | 0.001 | 0.001 | 0.36 / 0.24 / 0.04 | 0.00 | n/a / 0.333 | 0.00 |
| distance 3-4, 12 hexes/player | 4 | greedy | 0.494 ± 0.152 | 0.13 / 0.35 / 0.31 / 0.21 | 0.26 | 48 (48) | 0.70 | 12.7 / 1.49 / 0.00 / 33.8 | 1.87 ± 1.10 | 1.00 ± 1.07 | 0.003 | 0.006 | 0.44 / 0.27 / 0.09 | 0.00 | n/a / 0.250 | 0.00 |
| distance 3-4, 12 hexes/player | 5 | greedy | 0.612 ± 0.175 | 0.08 / 0.29 / 0.25 / 0.20 / 0.19 | 0.22 | 50 (50) | 0.61 | 17.4 / 2.08 / 0.00 / 30.5 | 2.16 ± 1.01 | 1.01 ± 1.11 | 0.003 | 0.006 | 0.51 / 0.28 / 0.09 | 0.00 | n/a / 0.200 | 0.00 |
| distance 3-4, 18 hexes/player | 2 | greedy | 0.164 ± 0.088 | 0.42 / 0.58 | 0.32 | 48 (48) | 0.74 | 10.6 / 1.64 / 0.00 / 35.7 | 1.44 ± 1.24 | 1.11 ± 1.12 | 0.002 | 0.004 | 0.35 / 0.27 / 0.11 | 0.00 | n/a / 0.500 | 0.00 |
| distance 3-4, 18 hexes/player | 3 | greedy | 0.286 ± 0.124 | 0.24 / 0.43 / 0.33 | 0.27 | 45 (45) | 0.62 | 14.9 / 1.97 / 0.00 / 28.1 | 1.74 ± 1.15 | 1.08 ± 1.09 | 0.003 | 0.007 | 0.41 / 0.24 / 0.07 | 0.00 | n/a / 0.333 | 0.00 |
| distance 3-4, 18 hexes/player | 4 | greedy | 0.456 ± 0.152 | 0.15 / 0.36 / 0.26 / 0.23 | 0.26 | 48 (48) | 0.48 | 22.2 / 3.04 / 0.00 / 22.8 | 2.10 ± 1.13 | 1.12 ± 1.15 | 0.003 | 0.006 | 0.44 / 0.26 / 0.11 | 0.00 | n/a / 0.250 | 0.00 |
| distance 3-4, 18 hexes/player | 5 | greedy | 0.537 ± 0.175 | 0.11 / 0.31 / 0.27 / 0.17 / 0.15 | 0.19 | 50 (50) | 0.35 | 29.1 / 3.56 / 0.00 / 17.3 | 2.55 ± 1.13 | 1.24 ± 1.31 | 0.005 | 0.010 | 0.53 / 0.30 / 0.09 | 0.00 | n/a / 0.200 | 0.00 |
| distance 3-4, 24 hexes/player | 2 | greedy | 0.198 ± 0.088 | 0.40 / 0.60 | 0.26 | 48 (48) | 0.66 | 14.4 / 1.99 / 0.00 / 31.6 | 1.57 ± 1.27 | 1.19 ± 1.15 | 0.004 | 0.008 | 0.36 / 0.28 / 0.11 | 0.00 | n/a / 0.500 | 0.00 |
| distance 3-4, 24 hexes/player | 3 | greedy | 0.258 ± 0.124 | 0.25 / 0.41 / 0.35 | 0.26 | 45 (45) | 0.42 | 23.1 / 3.03 / 0.00 / 18.9 | 1.90 ± 1.19 | 1.18 ± 1.12 | 0.005 | 0.011 | 0.44 / 0.31 / 0.09 | 0.00 | n/a / 0.333 | 0.00 |
| distance 3-4, 24 hexes/player | 4 | greedy | 0.467 ± 0.152 | 0.13 / 0.36 / 0.27 / 0.24 | 0.22 | 48 (48) | 0.25 | 31.9 / 3.99 / 0.00 / 12.1 | 2.26 ± 1.16 | 1.26 ± 1.22 | 0.005 | 0.010 | 0.47 / 0.31 / 0.12 | 0.00 | n/a / 0.250 | 0.00 |
| distance 3-4, 24 hexes/player | 5 | greedy | 0.506 ± 0.175 | 0.10 / 0.28 / 0.27 / 0.18 / 0.18 | 0.19 | 50 (50) | 0.09 | 41.1 / 4.35 / 0.00 / 4.5 | 2.78 ± 1.19 | 1.37 ± 1.39 | 0.006 | 0.012 | 0.52 / 0.28 / 0.11 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-4, 12 hexes/player | 2 | greedy | 0.030 ± 0.088 | 0.52 / 0.48 | 0.72 | 48 (48) | 0.85 | 5.9 / 1.27 / 0.00 / 40.9 | 0.45 ± 0.80 | 0.34 ± 0.67 | 0.000 | 0.000 | 0.13 / 0.09 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-4, 12 hexes/player | 3 | greedy | 0.133 ± 0.124 | 0.31 / 0.32 / 0.38 | 0.62 | 45 (45) | 0.72 | 10.8 / 1.82 / 0.00 / 32.3 | 0.80 ± 0.88 | 0.51 ± 0.75 | 0.001 | 0.003 | 0.23 / 0.10 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-4, 12 hexes/player | 4 | greedy | 0.105 ± 0.152 | 0.22 / 0.25 / 0.27 / 0.26 | 0.66 | 48 (48) | 0.67 | 14.4 / 1.68 / 0.00 / 31.9 | 1.15 ± 0.96 | 0.60 ± 0.93 | 0.003 | 0.005 | 0.20 / 0.02 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-4, 12 hexes/player | 5 | greedy | 0.230 ± 0.175 | 0.17 / 0.19 / 0.25 / 0.23 / 0.17 | 0.59 | 50 (50) | 0.57 | 19.3 / 2.24 / 0.00 / 28.4 | 1.43 ± 1.05 | 0.63 ± 1.07 | 0.002 | 0.004 | 0.23 / 0.03 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-4, 18 hexes/player | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 48 (48) | 0.72 | 11.4 / 1.79 / 0.00 / 34.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-4, 18 hexes/player | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-4, 18 hexes/player | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-4, 18 hexes/player | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 50 (50) | 0.29 | 31.6 / 3.81 / 0.00 / 14.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-4, 24 hexes/player | 2 | greedy | 0.032 ± 0.088 | 0.52 / 0.48 | 0.44 | 48 (48) | 0.64 | 15.4 / 2.08 / 0.00 / 30.6 | 1.01 ± 1.08 | 0.81 ± 0.95 | 0.004 | 0.008 | 0.27 / 0.22 / 0.05 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-4, 24 hexes/player | 3 | greedy | 0.036 ± 0.124 | 0.33 / 0.32 / 0.34 | 0.46 | 45 (45) | 0.37 | 24.9 / 3.25 / 0.00 / 16.8 | 1.29 ± 1.07 | 0.83 ± 1.00 | 0.002 | 0.004 | 0.33 / 0.15 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-4, 24 hexes/player | 4 | greedy | 0.059 ± 0.152 | 0.24 / 0.24 / 0.26 / 0.26 | 0.54 | 48 (48) | 0.19 | 34.6 / 4.24 / 0.00 / 9.2 | 1.62 ± 1.10 | 0.87 ± 1.14 | 0.004 | 0.009 | 0.24 / 0.04 / 0.01 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-4, 24 hexes/player | 5 | greedy | 0.143 ± 0.175 | 0.19 / 0.18 / 0.23 / 0.22 / 0.19 | 0.49 | 50 (50) | 0.06 | 43.2 / 4.01 / 0.00 / 2.8 | 2.08 ± 1.21 | 0.94 ± 1.35 | 0.004 | 0.009 | 0.21 / 0.05 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-5, 12 hexes/player | 2 | greedy | 0.022 ± 0.088 | 0.51 / 0.49 | 0.77 | 48 (48) | 0.85 | 6.1 / 1.29 / 0.00 / 40.6 | 0.36 ± 0.73 | 0.28 ± 0.61 | 0.000 | 0.000 | 0.10 / 0.08 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-5, 12 hexes/player | 3 | greedy | 0.125 ± 0.124 | 0.29 / 0.35 / 0.35 | 0.77 | 45 (45) | 0.75 | 9.6 / 1.68 / 0.00 / 33.8 | 0.48 ± 0.73 | 0.30 ± 0.62 | 0.000 | 0.000 | 0.15 / 0.05 / 0.00 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-5, 12 hexes/player | 4 | greedy | 0.143 ± 0.152 | 0.22 / 0.23 / 0.29 / 0.27 | 0.76 | 48 (48) | 0.70 | 13.0 / 1.54 / 0.00 / 33.5 | 0.82 ± 0.83 | 0.44 ± 0.80 | 0.000 | 0.000 | 0.17 / 0.01 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-5, 12 hexes/player | 5 | greedy | 0.227 ± 0.175 | 0.15 / 0.19 / 0.23 / 0.22 / 0.20 | 0.76 | 50 (50) | 0.62 | 16.8 / 2.03 / 0.00 / 31.1 | 1.08 ± 0.89 | 0.47 ± 0.94 | 0.000 | 0.001 | 0.13 / 0.02 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-5, 18 hexes/player | 2 | greedy | 0.022 ± 0.088 | 0.51 / 0.49 | 0.59 | 48 (48) | 0.75 | 10.3 / 1.64 / 0.00 / 36.1 | 0.66 ± 0.90 | 0.51 ± 0.77 | 0.000 | 0.000 | 0.16 / 0.14 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-5, 18 hexes/player | 3 | greedy | 0.136 ± 0.124 | 0.29 / 0.33 / 0.38 | 0.64 | 45 (45) | 0.61 | 15.6 / 2.05 / 0.00 / 27.4 | 0.86 ± 0.94 | 0.54 ± 0.82 | 0.000 | 0.000 | 0.22 / 0.09 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-5, 18 hexes/player | 4 | greedy | 0.174 ± 0.152 | 0.21 / 0.24 / 0.29 / 0.27 | 0.70 | 48 (48) | 0.50 | 21.2 / 2.94 / 0.00 / 23.8 | 1.08 ± 1.00 | 0.59 ± 0.94 | 0.002 | 0.003 | 0.18 / 0.04 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-5, 18 hexes/player | 5 | greedy | 0.190 ± 0.175 | 0.17 / 0.20 / 0.24 / 0.20 / 0.19 | 0.68 | 50 (50) | 0.39 | 27.0 / 3.36 / 0.00 / 19.7 | 1.44 ± 1.01 | 0.62 ± 1.13 | 0.001 | 0.002 | 0.17 / 0.02 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-5, 24 hexes/player | 2 | greedy | 0.014 ± 0.088 | 0.49 / 0.51 | 0.53 | 48 (48) | 0.66 | 14.4 / 2.02 / 0.00 / 31.6 | 0.78 ± 0.98 | 0.59 ± 0.85 | 0.000 | 0.000 | 0.21 / 0.14 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-5, 24 hexes/player | 3 | greedy | 0.095 ± 0.124 | 0.30 / 0.34 / 0.35 | 0.61 | 45 (45) | 0.45 | 21.8 / 2.91 / 0.00 / 20.3 | 0.93 ± 0.89 | 0.58 ± 0.82 | 0.001 | 0.001 | 0.23 / 0.08 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-5, 24 hexes/player | 4 | greedy | 0.117 ± 0.152 | 0.22 / 0.22 / 0.28 / 0.28 | 0.69 | 48 (48) | 0.30 | 30.0 / 3.82 / 0.00 / 14.2 | 1.19 ± 1.03 | 0.62 ± 0.99 | 0.001 | 0.002 | 0.18 / 0.02 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-5, 24 hexes/player | 5 | greedy | 0.206 ± 0.175 | 0.17 / 0.20 / 0.24 / 0.20 / 0.20 | 0.64 | 50 (50) | 0.15 | 37.9 / 4.35 / 0.00 / 7.7 | 1.62 ± 1.13 | 0.70 ± 1.24 | 0.001 | 0.002 | 0.13 / 0.03 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| distance 2-3, 7 hexes/player | 2 | greedy | 0.440 ± 0.088 | 0.72 / 0.28 | 0.19 | 12 (12) | 0.72 | 2.6 / 0.82 / 0.00 / 8.6 | 1.99 ± 1.19 | 1.22 ± 1.26 | 0.000 | 0.000 | 0.40 / 0.30 / 0.22 | 0.00 | n/a / 0.500 | 0.00 |
| distance 2-3, 7 hexes/player | 3 | greedy | 1.092 ± 0.124 | 0.70 / 0.24 / 0.06 | 0.15 | 18 (18) | 0.72 | 4.4 / 0.66 / 0.00 / 12.9 | 2.97 ± 1.21 | 1.68 ± 1.41 | 0.001 | 0.001 | 0.67 / 0.38 / 0.28 | 0.00 | n/a / 0.333 | 0.00 |
| distance 2-3, 7 hexes/player | 4 | greedy | 1.409 ± 0.152 | 0.60 / 0.29 / 0.08 / 0.03 | 0.17 | 16 (16) | 0.49 | 6.7 / 1.38 / 0.00 / 7.9 | 3.21 ± 1.06 | 1.69 ± 1.40 | 0.001 | 0.001 | 0.73 / 0.38 / 0.27 | 0.00 | n/a / 0.250 | 0.00 |
| distance 2-3, 7 hexes/player | 5 | greedy | 1.728 ± 0.175 | 0.55 / 0.29 / 0.12 / 0.04 / 0.01 | 0.24 | 20 (20) | 0.57 | 7.5 / 1.18 / 0.00 / 11.4 | 3.38 ± 1.00 | 1.66 ± 1.38 | 0.001 | 0.001 | 0.79 / 0.39 / 0.20 | 0.00 | n/a / 0.200 | 0.00 |
| distance 2-3, 10 hexes/player | 2 | greedy | 0.368 ± 0.088 | 0.68 / 0.32 | 0.10 | 12 (12) | 0.50 | 5.4 / 0.64 / 0.00 / 6.0 | 2.94 ± 1.21 | 2.15 ± 1.41 | 0.004 | 0.004 | 0.58 / 0.45 / 0.33 | 0.00 | n/a / 0.500 | 0.00 |
| distance 2-3, 10 hexes/player | 3 | greedy | 0.904 ± 0.124 | 0.63 / 0.25 / 0.11 | 0.11 | 18 (18) | 0.51 | 7.6 / 1.17 / 0.00 / 9.3 | 3.21 ± 1.00 | 2.03 ± 1.34 | 0.005 | 0.005 | 0.74 / 0.39 / 0.29 | 0.00 | n/a / 0.333 | 0.00 |
| distance 2-3, 10 hexes/player | 4 | greedy | 1.137 ± 0.152 | 0.53 / 0.30 / 0.11 / 0.06 | 0.17 | 16 (16) | 0.21 | 11.0 / 1.58 / 0.00 / 3.4 | 3.48 ± 1.06 | 2.05 ± 1.40 | 0.005 | 0.005 | 0.75 / 0.43 / 0.32 | 0.00 | n/a / 0.250 | 0.00 |
| distance 2-3, 10 hexes/player | 5 | greedy | 1.259 ± 0.175 | 0.45 / 0.29 / 0.16 / 0.07 / 0.03 | 0.21 | 20 (20) | 0.26 | 13.2 / 1.56 / 0.00 / 5.3 | 3.86 ± 1.02 | 2.15 ± 1.44 | 0.007 | 0.007 | 0.84 / 0.46 / 0.28 | 0.00 | n/a / 0.200 | 0.00 |
| distance 2-3, 14 hexes/player | 2 | greedy | 0.378 ± 0.088 | 0.69 / 0.31 | 0.05 | 12 (12) | 0.20 | 8.5 / 1.06 / 0.00 / 2.4 | 3.12 ± 1.25 | 2.29 ± 1.46 | 0.010 | 0.010 | 0.59 / 0.48 / 0.34 | 0.00 | n/a / 0.500 | 0.00 |
| distance 2-3, 14 hexes/player | 3 | greedy | 0.757 ± 0.124 | 0.59 / 0.31 / 0.11 | 0.12 | 18 (18) | 0.25 | 12.0 / 1.47 / 0.00 / 4.6 | 3.47 ± 1.20 | 2.24 ± 1.46 | 0.015 | 0.015 | 0.71 / 0.50 / 0.34 | 0.00 | n/a / 0.333 | 0.00 |
| distance 2-3, 14 hexes/player | 4 | greedy | 1.121 ± 0.152 | 0.53 / 0.29 / 0.11 / 0.07 | 0.14 | 16 (16) | 0.01 | 15.4 / 0.39 / 0.00 / 0.2 | 3.96 ± 1.02 | 2.54 ± 1.41 | 0.015 | 0.015 | 0.85 / 0.46 / 0.36 | 0.00 | n/a / 0.250 | 0.00 |
| distance 2-3, 14 hexes/player | 5 | greedy | 1.324 ± 0.175 | 0.46 / 0.27 / 0.14 / 0.08 / 0.04 | 0.18 | 20 (20) | 0.01 | 19.3 / 0.52 / 0.00 / 0.2 | 4.25 ± 1.06 | 2.57 ± 1.43 | 0.020 | 0.020 | 0.87 / 0.49 / 0.33 | 0.00 | n/a / 0.200 | 0.00 |
| distance 3-4, 7 hexes/player | 2 | greedy | 0.092 ± 0.088 | 0.45 / 0.55 | 0.79 | 12 (12) | 0.75 | 2.2 / 0.78 / 0.00 / 9.0 | 0.31 ± 0.66 | 0.22 ± 0.53 | 0.000 | 0.000 | 0.09 / 0.05 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| distance 3-4, 7 hexes/player | 3 | greedy | 0.495 ± 0.124 | 0.17 / 0.50 / 0.33 | 0.42 | 18 (18) | 0.70 | 4.7 / 0.68 / 0.00 / 12.7 | 1.04 ± 0.99 | 0.57 ± 0.81 | 0.001 | 0.001 | 0.29 / 0.20 / 0.04 | 0.00 | n/a / 0.333 | 0.00 |
| distance 3-4, 7 hexes/player | 4 | greedy | 0.687 ± 0.152 | 0.12 / 0.42 / 0.25 / 0.21 | 0.37 | 16 (16) | 0.51 | 6.4 / 1.36 / 0.00 / 8.2 | 1.27 ± 0.99 | 0.60 ± 0.83 | 0.001 | 0.001 | 0.36 / 0.20 / 0.05 | 0.00 | n/a / 0.250 | 0.00 |
| distance 3-4, 7 hexes/player | 5 | greedy | 0.752 ± 0.175 | 0.07 / 0.35 / 0.24 / 0.20 / 0.14 | 0.30 | 20 (20) | 0.50 | 8.7 / 1.28 / 0.00 / 10.0 | 1.44 ± 0.89 | 0.60 ± 0.82 | 0.000 | 0.000 | 0.42 / 0.27 / 0.06 | 0.00 | n/a / 0.200 | 0.00 |
| distance 3-4, 10 hexes/player | 2 | greedy | 0.250 ± 0.088 | 0.38 / 0.62 | 0.38 | 12 (12) | 0.49 | 5.4 / 0.67 / 0.00 / 5.9 | 1.29 ± 1.23 | 0.94 ± 1.09 | 0.003 | 0.003 | 0.34 / 0.19 / 0.12 | 0.00 | n/a / 0.500 | 0.00 |
| distance 3-4, 10 hexes/player | 3 | greedy | 0.319 ± 0.124 | 0.23 / 0.44 / 0.33 | 0.32 | 18 (18) | 0.47 | 8.3 / 1.23 / 0.00 / 8.5 | 1.39 ± 1.04 | 0.84 ± 0.93 | 0.001 | 0.001 | 0.39 / 0.25 / 0.06 | 0.00 | n/a / 0.333 | 0.00 |
| distance 3-4, 10 hexes/player | 4 | greedy | 0.496 ± 0.152 | 0.13 / 0.37 / 0.27 / 0.22 | 0.28 | 16 (16) | 0.21 | 11.0 / 1.66 / 0.00 / 3.3 | 1.67 ± 1.05 | 0.85 ± 0.98 | 0.001 | 0.001 | 0.42 / 0.20 / 0.06 | 0.00 | n/a / 0.250 | 0.00 |
| distance 3-4, 10 hexes/player | 5 | greedy | 0.631 ± 0.175 | 0.07 / 0.31 / 0.28 / 0.17 / 0.16 | 0.25 | 20 (20) | 0.22 | 13.9 / 1.60 / 0.00 / 4.5 | 2.05 ± 1.09 | 0.96 ± 1.08 | 0.003 | 0.003 | 0.51 / 0.26 / 0.09 | 0.00 | n/a / 0.200 | 0.00 |
| distance 3-4, 14 hexes/player | 2 | greedy | 0.180 ± 0.088 | 0.41 / 0.59 | 0.37 | 12 (12) | 0.32 | 7.1 / 1.06 / 0.00 / 3.9 | 1.27 ± 1.20 | 0.93 ± 1.06 | 0.002 | 0.002 | 0.31 / 0.24 / 0.11 | 0.00 | n/a / 0.500 | 0.00 |
| distance 3-4, 14 hexes/player | 3 | greedy | 0.318 ± 0.124 | 0.23 / 0.44 / 0.33 | 0.26 | 18 (18) | 0.28 | 11.5 / 1.48 / 0.00 / 5.0 | 1.76 ± 1.19 | 1.07 ± 1.09 | 0.003 | 0.003 | 0.47 / 0.28 / 0.05 | 0.00 | n/a / 0.333 | 0.00 |
| distance 3-4, 14 hexes/player | 4 | greedy | 0.509 ± 0.152 | 0.14 / 0.38 / 0.23 / 0.25 | 0.21 | 16 (16) | 0.03 | 15.0 / 0.61 / 0.00 / 0.4 | 2.27 ± 1.12 | 1.28 ± 1.17 | 0.004 | 0.004 | 0.49 / 0.26 / 0.12 | 0.00 | n/a / 0.250 | 0.00 |
| distance 3-4, 14 hexes/player | 5 | greedy | 0.532 ± 0.175 | 0.09 / 0.30 / 0.24 / 0.22 / 0.14 | 0.18 | 20 (20) | 0.01 | 19.2 / 0.50 / 0.00 / 0.3 | 2.69 ± 1.07 | 1.35 ± 1.30 | 0.006 | 0.006 | 0.57 / 0.29 / 0.10 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-4, 7 hexes/player | 2 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 4 vineyards (vineyards_per_player=2) at vineyard_distance (4, 4) on 14 hexes (hexes_per_player=7); only 2 hexes are at that distance from the river | | | | | | | | | | | | | |
| distance 4-4, 7 hexes/player | 3 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 6 vineyards (vineyards_per_player=2) at vineyard_distance (4, 4) on 21 hexes (hexes_per_player=7); only 4 hexes are at that distance from the river | | | | | | | | | | | | | |
| distance 4-4, 7 hexes/player | 4 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 8 vineyards (vineyards_per_player=2) at vineyard_distance (4, 4) on 28 hexes (hexes_per_player=7); only 5 hexes are at that distance from the river | | | | | | | | | | | | | |
| distance 4-4, 7 hexes/player | 5 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 10 vineyards (vineyards_per_player=2) at vineyard_distance (4, 4) on 35 hexes (hexes_per_player=7); only 7 hexes are at that distance from the river | | | | | | | | | | | | | |
| distance 4-4, 10 hexes/player | 2 | greedy | 0.016 ± 0.088 | 0.49 / 0.51 | 0.59 | 12 (12) | 0.43 | 6.1 / 0.71 / 0.00 / 5.1 | 0.68 ± 0.92 | 0.53 ± 0.79 | 0.000 | 0.000 | 0.20 / 0.14 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-4, 10 hexes/player | 3 | greedy | 0.129 ± 0.124 | 0.29 / 0.34 / 0.37 | 0.63 | 18 (18) | 0.42 | 9.2 / 1.30 / 0.00 / 7.5 | 0.73 ± 0.87 | 0.44 ± 0.73 | 0.000 | 0.000 | 0.22 / 0.08 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-4, 10 hexes/player | 4 | greedy | 0.249 ± 0.152 | 0.20 / 0.21 / 0.31 / 0.28 | 0.64 | 16 (16) | 0.12 | 12.6 / 1.48 / 0.00 / 2.0 | 1.15 ± 1.00 | 0.62 ± 0.92 | 0.001 | 0.001 | 0.21 / 0.01 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-4, 10 hexes/player | 5 | greedy | 0.244 ± 0.175 | 0.16 / 0.17 / 0.25 / 0.22 / 0.20 | 0.61 | 20 (20) | 0.13 | 15.9 / 1.49 / 0.00 / 2.6 | 1.57 ± 1.10 | 0.71 ± 1.14 | 0.002 | 0.002 | 0.21 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| distance 4-4, 14 hexes/player | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| distance 4-4, 14 hexes/player | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| distance 4-4, 14 hexes/player | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| distance 4-4, 14 hexes/player | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |

### Sweep `stone`: Stone share (percent of non-river hexes)

Command: `uv run python scripts/tune.py --sweep stone`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stone_share = 0 | 2 | greedy | 0.018 ± 0.088 | 0.49 / 0.51 | 0.32 | 48 (48) | 0.66 | 14.4 / 1.80 / 0.00 / 31.8 | 1.35 ± 1.23 | 1.06 ± 1.09 | 0.002 | 0.004 | 0.33 / 0.26 / 0.04 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 0 | 3 | greedy | 0.137 ± 0.124 | 0.29 / 0.33 / 0.38 | 0.39 | 45 (45) | 0.46 | 21.2 / 2.86 / 0.00 / 20.9 | 1.58 ± 1.13 | 1.01 ± 1.06 | 0.003 | 0.007 | 0.39 / 0.16 / 0.04 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 0 | 4 | greedy | 0.171 ± 0.152 | 0.24 / 0.25 / 0.29 / 0.22 | 0.46 | 48 (48) | 0.31 | 29.7 / 3.51 / 0.00 / 14.8 | 1.81 ± 1.04 | 1.01 ± 1.17 | 0.003 | 0.006 | 0.33 / 0.07 / 0.02 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 0 | 5 | greedy | 0.096 ± 0.175 | 0.20 / 0.19 / 0.22 / 0.20 / 0.19 | 0.40 | 50 (50) | 0.13 | 38.9 / 4.56 / 0.00 / 6.6 | 2.41 ± 1.21 | 1.13 ± 1.44 | 0.004 | 0.009 | 0.28 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| stone_share = 5 | 2 | greedy | 0.058 ± 0.088 | 0.53 / 0.47 | 0.43 | 48 (48) | 0.70 | 12.7 / 1.73 / 0.00 / 33.5 | 0.97 ± 1.05 | 0.75 ± 0.92 | 0.003 | 0.006 | 0.24 / 0.21 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 5 | 3 | greedy | 0.110 ± 0.124 | 0.30 / 0.32 / 0.37 | 0.46 | 45 (45) | 0.53 | 18.5 / 2.71 / 0.00 / 23.8 | 1.22 ± 1.01 | 0.80 ± 0.92 | 0.001 | 0.001 | 0.31 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 5 | 4 | greedy | 0.205 ± 0.152 | 0.22 / 0.24 / 0.30 / 0.24 | 0.50 | 48 (48) | 0.38 | 26.6 / 3.31 / 0.00 / 18.0 | 1.65 ± 0.96 | 0.90 ± 1.08 | 0.002 | 0.003 | 0.28 / 0.07 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 5 | 5 | greedy | 0.184 ± 0.175 | 0.17 / 0.17 / 0.24 / 0.22 / 0.21 | 0.45 | 50 (50) | 0.22 | 35.1 / 3.95 / 0.00 / 10.9 | 2.01 ± 1.10 | 0.93 ± 1.30 | 0.003 | 0.006 | 0.27 / 0.05 / 0.02 | 0.00 | n/a / 0.200 | 0.00 |
| stone_share = 10 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 48 (48) | 0.72 | 11.4 / 1.79 / 0.00 / 34.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 10 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 10 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 10 | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 50 (50) | 0.29 | 31.6 / 3.81 / 0.00 / 14.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| stone_share = 15 | 2 | greedy | 0.022 ± 0.088 | 0.49 / 0.51 | 0.60 | 48 (48) | 0.76 | 9.9 / 1.73 / 0.00 / 36.3 | 0.63 ± 0.88 | 0.48 ± 0.75 | 0.000 | 0.000 | 0.16 / 0.13 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 15 | 3 | greedy | 0.097 ± 0.124 | 0.30 / 0.34 / 0.36 | 0.63 | 45 (45) | 0.63 | 14.4 / 2.00 / 0.00 / 28.6 | 0.78 ± 0.88 | 0.49 ± 0.78 | 0.002 | 0.004 | 0.21 / 0.10 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 15 | 4 | greedy | 0.089 ± 0.152 | 0.23 / 0.23 / 0.27 / 0.27 | 0.59 | 48 (48) | 0.49 | 21.8 / 2.66 / 0.00 / 23.5 | 1.23 ± 1.01 | 0.67 ± 0.97 | 0.000 | 0.000 | 0.25 / 0.04 / 0.01 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 15 | 5 | greedy | 0.180 ± 0.175 | 0.19 / 0.16 / 0.23 / 0.21 / 0.20 | 0.60 | 50 (50) | 0.37 | 27.8 / 3.76 / 0.00 / 18.4 | 1.42 ± 1.00 | 0.64 ± 1.06 | 0.002 | 0.003 | 0.25 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| stone_share = 0 | 2 | greedy | 0.000 ± 0.088 | 0.50 / 0.50 | 0.40 | 12 (12) | 0.15 | 9.3 / 0.87 / 0.00 / 1.8 | 1.10 ± 1.18 | 0.86 ± 1.02 | 0.004 | 0.004 | 0.25 / 0.25 / 0.04 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 0 | 3 | greedy | 0.150 ± 0.124 | 0.30 / 0.32 / 0.38 | 0.38 | 18 (18) | 0.05 | 15.8 / 1.28 / 0.00 / 0.9 | 1.75 ± 1.20 | 1.16 ± 1.14 | 0.006 | 0.006 | 0.43 / 0.18 / 0.06 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 0 | 4 | greedy | 0.233 ± 0.152 | 0.23 / 0.23 / 0.24 / 0.31 | 0.37 | 16 (16) | 0.00 | 15.9 / 0.08 / 0.00 / 0.0 | 2.11 ± 1.02 | 1.21 ± 1.20 | 0.004 | 0.004 | 0.33 / 0.08 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 0 | 5 | greedy | 0.185 ± 0.175 | 0.16 / 0.18 / 0.20 / 0.24 / 0.22 | 0.36 | 20 (20) | 0.00 | 19.8 / 0.18 / 0.00 / 0.0 | 2.54 ± 1.06 | 1.25 ± 1.41 | 0.006 | 0.006 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| stone_share = 5 | 2 | greedy | 0.084 ± 0.088 | 0.54 / 0.46 | 0.52 | 12 (12) | 0.23 | 8.2 / 0.98 / 0.00 / 2.8 | 0.83 ± 1.04 | 0.65 ± 0.90 | 0.002 | 0.002 | 0.21 / 0.17 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 5 | 3 | greedy | 0.149 ± 0.124 | 0.29 / 0.33 / 0.38 | 0.46 | 18 (18) | 0.15 | 14.0 / 1.39 / 0.00 / 2.6 | 1.29 ± 1.08 | 0.83 ± 1.00 | 0.003 | 0.003 | 0.32 / 0.13 / 0.03 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 5 | 4 | greedy | 0.182 ± 0.152 | 0.21 / 0.22 / 0.27 / 0.30 | 0.48 | 16 (16) | 0.00 | 15.8 / 0.18 / 0.00 / 0.0 | 1.76 ± 1.02 | 0.97 ± 1.12 | 0.001 | 0.001 | 0.28 / 0.05 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 5 | 5 | greedy | 0.190 ± 0.175 | 0.16 / 0.16 / 0.21 / 0.24 / 0.23 | 0.41 | 20 (20) | 0.00 | 19.7 / 0.27 / 0.00 / 0.0 | 2.24 ± 1.11 | 1.06 ± 1.36 | 0.003 | 0.003 | 0.29 / 0.07 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| stone_share = 10 | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 10 | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 10 | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 10 | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| stone_share = 15 | 2 | greedy | 0.022 ± 0.088 | 0.51 / 0.49 | 0.68 | 12 (12) | 0.36 | 6.5 / 1.16 / 0.00 / 4.3 | 0.53 ± 0.88 | 0.41 ± 0.75 | 0.000 | 0.000 | 0.15 / 0.11 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| stone_share = 15 | 3 | greedy | 0.095 ± 0.124 | 0.31 / 0.33 / 0.37 | 0.61 | 18 (18) | 0.29 | 11.2 / 1.62 / 0.00 / 5.2 | 0.76 ± 0.87 | 0.47 ± 0.75 | 0.000 | 0.000 | 0.21 / 0.11 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| stone_share = 15 | 4 | greedy | 0.205 ± 0.152 | 0.21 / 0.23 / 0.26 / 0.30 | 0.61 | 16 (16) | 0.04 | 14.7 / 0.69 / 0.00 / 0.6 | 1.29 ± 0.99 | 0.68 ± 0.98 | 0.002 | 0.002 | 0.22 / 0.02 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| stone_share = 15 | 5 | greedy | 0.301 ± 0.175 | 0.17 / 0.15 / 0.22 / 0.26 / 0.20 | 0.59 | 20 (20) | 0.02 | 18.8 / 0.71 / 0.00 / 0.5 | 1.58 ± 1.03 | 0.73 ± 1.11 | 0.002 | 0.002 | 0.23 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

### Sweep `vineyards`: Vineyards per player

Command: `uv run python scripts/tune.py --sweep vineyards`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vineyards_per_player = 2 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 48 (48) | 0.72 | 11.4 / 1.79 / 0.00 / 34.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| vineyards_per_player = 2 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| vineyards_per_player = 2 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| vineyards_per_player = 2 | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 50 (50) | 0.29 | 31.6 / 3.81 / 0.00 / 14.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| vineyards_per_player = 3 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.49 | 48 (48) | 0.74 | 10.8 / 1.82 / 0.00 / 35.3 | 0.93 ± 1.11 | 0.73 ± 0.94 | 0.003 | 0.006 | 0.26 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| vineyards_per_player = 3 | 3 | greedy | 0.121 ± 0.124 | 0.30 / 0.33 / 0.37 | 0.42 | 45 (45) | 0.60 | 15.8 / 2.17 / 0.00 / 27.0 | 1.37 ± 1.11 | 0.88 ± 1.02 | 0.001 | 0.003 | 0.37 / 0.17 / 0.04 | 0.00 | n/a / 0.333 | 0.00 |
| vineyards_per_player = 3 | 4 | greedy | 0.112 ± 0.152 | 0.23 / 0.23 / 0.28 / 0.26 | 0.41 | 48 (48) | 0.47 | 22.8 / 2.73 / 0.00 / 22.5 | 1.80 ± 1.12 | 0.98 ± 1.16 | 0.003 | 0.006 | 0.30 / 0.04 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| vineyards_per_player = 3 | 5 | greedy | 0.176 ± 0.175 | 0.18 / 0.17 / 0.21 / 0.21 / 0.24 | 0.43 | 50 (50) | 0.33 | 29.6 / 3.93 / 0.00 / 16.5 | 1.96 ± 1.11 | 0.93 ± 1.22 | 0.004 | 0.007 | 0.29 / 0.03 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| vineyards_per_player = 2 | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| vineyards_per_player = 2 | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| vineyards_per_player = 2 | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| vineyards_per_player = 2 | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| vineyards_per_player = 3 | 2 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 6 vineyards (vineyards_per_player=3) at vineyard_distance (4, 4) on 28 hexes (hexes_per_player=14); only 5 hexes are at that distance from the river | | | | | | | | | | | | | |
| vineyards_per_player = 3 | 3 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 9 vineyards (vineyards_per_player=3) at vineyard_distance (4, 4) on 42 hexes (hexes_per_player=14); only 8 hexes are at that distance from the river | | | | | | | | | | | | | |
| vineyards_per_player = 3 | 4 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 12 vineyards (vineyards_per_player=3) at vineyard_distance (4, 4) on 56 hexes (hexes_per_player=14); only 11 hexes are at that distance from the river | | | | | | | | | | | | | |
| vineyards_per_player = 3 | 5 | greedy | infeasible: game 0 (game seed 3001947593271002930) cannot be set up: cannot place 15 vineyards (vineyards_per_player=3) at vineyard_distance (4, 4) on 70 hexes (hexes_per_player=14); only 14 hexes are at that distance from the river | | | | | | | | | | | | | |

### Sweep `bag`: Bag mix (straight/gentle/sharp/Y/T/claw/floodgate, percent)

Command: `uv run python scripts/tune.py --sweep bag`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bag 40/20/15/5/5/5/10 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 48 (48) | 0.72 | 11.4 / 1.79 / 0.00 / 34.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| bag 40/20/15/5/5/5/10 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| bag 40/20/15/5/5/5/10 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| bag 40/20/15/5/5/5/10 | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 50 (50) | 0.29 | 31.6 / 3.81 / 0.00 / 14.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| bag 20/15/10/15/15/15/10 | 2 | greedy | 0.008 ± 0.088 | 0.50 / 0.50 | 0.41 | 48 (48) | 0.70 | 12.5 / 1.90 / 0.00 / 33.6 | 1.26 ± 1.28 | 1.01 ± 1.13 | 0.003 | 0.006 | 0.32 / 0.21 / 0.07 | 0.00 | n/a / 0.500 | 0.00 |
| bag 20/15/10/15/15/15/10 | 3 | greedy | 0.217 ± 0.124 | 0.26 / 0.36 / 0.38 | 0.41 | 45 (45) | 0.55 | 18.1 / 2.29 / 0.00 / 24.6 | 1.64 ± 1.21 | 1.06 ± 1.15 | 0.007 | 0.015 | 0.38 / 0.16 / 0.05 | 0.00 | n/a / 0.333 | 0.00 |
| bag 20/15/10/15/15/15/10 | 4 | greedy | 0.191 ± 0.152 | 0.20 / 0.26 / 0.27 / 0.27 | 0.47 | 48 (48) | 0.37 | 26.5 / 3.60 / 0.00 / 17.9 | 1.90 ± 1.25 | 1.00 ± 1.27 | 0.005 | 0.011 | 0.25 / 0.07 / 0.01 | 0.00 | n/a / 0.250 | 0.00 |
| bag 20/15/10/15/15/15/10 | 5 | greedy | 0.193 ± 0.175 | 0.19 / 0.19 / 0.24 / 0.19 / 0.19 | 0.38 | 50 (50) | 0.19 | 36.1 / 4.18 / 0.00 / 9.7 | 2.78 ± 1.33 | 1.28 ± 1.63 | 0.008 | 0.015 | 0.23 / 0.07 / 0.02 | 0.00 | n/a / 0.200 | 0.00 |
| bag 10/10/5/25/20/20/10 | 2 | greedy | 0.050 ± 0.088 | 0.53 / 0.47 | 0.21 | 48 (48) | 0.66 | 14.3 / 2.11 / 0.00 / 31.5 | 1.97 ± 1.43 | 1.58 ± 1.31 | 0.017 | 0.034 | 0.49 / 0.29 / 0.16 | 0.00 | n/a / 0.500 | 0.00 |
| bag 10/10/5/25/20/20/10 | 3 | greedy | 0.115 ± 0.124 | 0.29 / 0.35 / 0.36 | 0.32 | 45 (45) | 0.47 | 21.1 / 2.55 / 0.00 / 21.3 | 2.37 ± 1.40 | 1.62 ± 1.40 | 0.020 | 0.040 | 0.43 / 0.21 / 0.08 | 0.00 | n/a / 0.333 | 0.00 |
| bag 10/10/5/25/20/20/10 | 4 | greedy | 0.175 ± 0.152 | 0.22 / 0.25 / 0.29 / 0.24 | 0.32 | 48 (48) | 0.32 | 29.6 / 3.21 / 0.00 / 15.2 | 2.88 ± 1.39 | 1.59 ± 1.61 | 0.015 | 0.029 | 0.31 / 0.11 / 0.05 | 0.00 | n/a / 0.250 | 0.00 |
| bag 10/10/5/25/20/20/10 | 5 | greedy | 0.151 ± 0.175 | 0.17 / 0.21 / 0.23 / 0.21 / 0.18 | 0.29 | 50 (50) | 0.12 | 39.7 / 4.19 / 0.00 / 6.1 | 3.66 ± 1.54 | 1.72 ± 2.02 | 0.018 | 0.037 | 0.26 / 0.10 / 0.03 | 0.00 | n/a / 0.200 | 0.00 |
| bag 40/20/15/10/5/5/5 | 2 | greedy | 0.084 ± 0.088 | 0.54 / 0.46 | 0.29 | 48 (48) | 0.75 | 11.5 / 0.54 / 0.00 / 35.9 | 1.37 ± 1.20 | 1.07 ± 1.07 | 0.007 | 0.014 | 0.34 / 0.26 / 0.05 | 0.00 | n/a / 0.500 | 0.00 |
| bag 40/20/15/10/5/5/5 | 3 | greedy | 0.061 ± 0.124 | 0.34 / 0.31 / 0.35 | 0.37 | 45 (45) | 0.60 | 16.9 / 0.99 / 0.00 / 27.1 | 1.57 ± 1.12 | 1.02 ± 1.05 | 0.003 | 0.007 | 0.36 / 0.19 / 0.04 | 0.00 | n/a / 0.333 | 0.00 |
| bag 40/20/15/10/5/5/5 | 4 | greedy | 0.261 ± 0.152 | 0.22 / 0.23 / 0.32 / 0.23 | 0.42 | 48 (48) | 0.46 | 24.3 / 1.51 / 0.00 / 22.2 | 1.94 ± 1.09 | 1.06 ± 1.20 | 0.005 | 0.011 | 0.27 / 0.08 / 0.01 | 0.00 | n/a / 0.250 | 0.00 |
| bag 40/20/15/10/5/5/5 | 5 | greedy | 0.308 ± 0.175 | 0.17 / 0.20 / 0.26 / 0.20 / 0.17 | 0.34 | 50 (50) | 0.33 | 31.9 / 1.56 / 0.00 / 16.6 | 2.49 ± 1.17 | 1.16 ± 1.43 | 0.008 | 0.015 | 0.23 / 0.09 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| bag 35/20/15/5/5/5/15 | 2 | greedy | 0.026 ± 0.088 | 0.49 / 0.51 | 0.62 | 48 (48) | 0.71 | 11.3 / 2.43 / 0.00 / 34.3 | 0.60 ± 0.88 | 0.46 ± 0.75 | 0.001 | 0.002 | 0.15 / 0.13 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| bag 35/20/15/5/5/5/15 | 3 | greedy | 0.052 ± 0.124 | 0.32 / 0.33 / 0.35 | 0.62 | 45 (45) | 0.56 | 16.5 / 3.35 / 0.00 / 25.1 | 0.81 ± 0.92 | 0.52 ± 0.80 | 0.001 | 0.001 | 0.23 / 0.10 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| bag 35/20/15/5/5/5/15 | 4 | greedy | 0.170 ± 0.152 | 0.23 / 0.23 / 0.29 / 0.25 | 0.71 | 48 (48) | 0.40 | 24.1 / 4.64 / 0.00 / 19.2 | 1.04 ± 0.92 | 0.54 ± 0.90 | 0.001 | 0.002 | 0.17 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| bag 35/20/15/5/5/5/15 | 5 | greedy | 0.077 ± 0.175 | 0.20 / 0.19 / 0.22 / 0.19 / 0.20 | 0.67 | 50 (50) | 0.24 | 31.6 / 6.34 / 0.00 / 12.1 | 1.24 ± 1.02 | 0.54 ± 1.02 | 0.001 | 0.002 | 0.17 / 0.03 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bag 40/20/15/5/5/5/10 | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| bag 40/20/15/5/5/5/10 | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| bag 40/20/15/5/5/5/10 | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| bag 40/20/15/5/5/5/10 | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| bag 20/15/10/15/15/15/10 | 2 | greedy | 0.042 ± 0.088 | 0.52 / 0.48 | 0.42 | 12 (12) | 0.20 | 8.5 / 1.02 / 0.00 / 2.4 | 1.21 ± 1.24 | 0.98 ± 1.08 | 0.007 | 0.007 | 0.30 / 0.25 / 0.08 | 0.00 | n/a / 0.500 | 0.00 |
| bag 20/15/10/15/15/15/10 | 3 | greedy | 0.039 ± 0.124 | 0.32 / 0.34 / 0.34 | 0.43 | 18 (18) | 0.16 | 13.7 / 1.42 / 0.00 / 2.9 | 1.58 ± 1.31 | 1.04 ± 1.18 | 0.005 | 0.005 | 0.33 / 0.12 / 0.03 | 0.00 | n/a / 0.333 | 0.00 |
| bag 20/15/10/15/15/15/10 | 4 | greedy | 0.177 ± 0.152 | 0.22 / 0.22 / 0.26 / 0.29 | 0.40 | 16 (16) | 0.00 | 15.8 / 0.14 / 0.00 / 0.1 | 2.32 ± 1.28 | 1.29 ± 1.38 | 0.007 | 0.007 | 0.30 / 0.06 / 0.02 | 0.00 | n/a / 0.250 | 0.00 |
| bag 20/15/10/15/15/15/10 | 5 | greedy | 0.179 ± 0.175 | 0.19 / 0.16 / 0.23 / 0.22 / 0.20 | 0.34 | 20 (20) | 0.00 | 19.8 / 0.18 / 0.00 / 0.0 | 2.95 ± 1.25 | 1.39 ± 1.65 | 0.008 | 0.008 | 0.26 / 0.10 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| bag 10/10/5/25/20/20/10 | 2 | greedy | 0.080 ± 0.088 | 0.54 / 0.46 | 0.38 | 12 (12) | 0.15 | 9.2 / 0.97 / 0.00 / 1.8 | 1.52 ± 1.47 | 1.24 ± 1.31 | 0.015 | 0.015 | 0.34 / 0.27 / 0.11 | 0.00 | n/a / 0.500 | 0.00 |
| bag 10/10/5/25/20/20/10 | 3 | greedy | 0.135 ± 0.124 | 0.30 / 0.32 / 0.38 | 0.38 | 18 (18) | 0.12 | 14.7 / 1.20 / 0.00 / 2.1 | 2.08 ± 1.50 | 1.39 ± 1.39 | 0.016 | 0.016 | 0.40 / 0.15 / 0.07 | 0.00 | n/a / 0.333 | 0.00 |
| bag 10/10/5/25/20/20/10 | 4 | greedy | 0.171 ± 0.152 | 0.21 / 0.26 / 0.26 / 0.27 | 0.30 | 16 (16) | 0.00 | 15.9 / 0.08 / 0.00 / 0.0 | 3.04 ± 1.36 | 1.70 ± 1.62 | 0.013 | 0.013 | 0.31 / 0.10 / 0.03 | 0.00 | n/a / 0.250 | 0.00 |
| bag 10/10/5/25/20/20/10 | 5 | greedy | 0.211 ± 0.175 | 0.20 / 0.18 / 0.21 / 0.24 / 0.16 | 0.30 | 20 (20) | 0.00 | 19.8 / 0.14 / 0.00 / 0.0 | 3.67 ± 1.45 | 1.70 ± 1.98 | 0.018 | 0.018 | 0.23 / 0.08 / 0.02 | 0.00 | n/a / 0.200 | 0.00 |
| bag 40/20/15/10/5/5/5 | 2 | greedy | 0.022 ± 0.088 | 0.49 / 0.51 | 0.45 | 12 (12) | 0.30 | 7.9 / 0.52 / 0.00 / 3.5 | 1.00 ± 1.12 | 0.79 ± 0.97 | 0.001 | 0.001 | 0.26 / 0.20 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| bag 40/20/15/10/5/5/5 | 3 | greedy | 0.167 ± 0.124 | 0.28 / 0.34 / 0.38 | 0.48 | 18 (18) | 0.27 | 12.7 / 0.52 / 0.00 / 4.8 | 1.37 ± 1.08 | 0.88 ± 1.00 | 0.004 | 0.004 | 0.31 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| bag 40/20/15/10/5/5/5 | 4 | greedy | 0.200 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.02 | 15.6 / 0.16 / 0.00 / 0.3 | 1.77 ± 0.99 | 0.97 ± 1.10 | 0.002 | 0.002 | 0.29 / 0.04 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| bag 40/20/15/10/5/5/5 | 5 | greedy | 0.270 ± 0.175 | 0.17 / 0.17 / 0.22 / 0.25 / 0.18 | 0.47 | 20 (20) | 0.01 | 19.8 / 0.11 / 0.00 / 0.1 | 2.24 ± 1.15 | 1.05 ± 1.36 | 0.004 | 0.004 | 0.21 / 0.07 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| bag 35/20/15/5/5/5/15 | 2 | greedy | 0.002 ± 0.088 | 0.50 / 0.50 | 0.65 | 12 (12) | 0.21 | 7.9 / 1.57 / 0.00 / 2.6 | 0.60 ± 0.95 | 0.47 ± 0.80 | 0.001 | 0.001 | 0.14 / 0.14 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| bag 35/20/15/5/5/5/15 | 3 | greedy | 0.136 ± 0.124 | 0.31 / 0.32 / 0.38 | 0.68 | 18 (18) | 0.17 | 12.3 / 2.54 / 0.00 / 3.1 | 0.70 ± 0.87 | 0.42 ± 0.75 | 0.001 | 0.001 | 0.17 / 0.08 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| bag 35/20/15/5/5/5/15 | 4 | greedy | 0.225 ± 0.152 | 0.23 / 0.21 / 0.25 / 0.31 | 0.58 | 16 (16) | 0.01 | 15.2 / 0.64 / 0.00 / 0.1 | 1.43 ± 1.02 | 0.79 ± 1.03 | 0.003 | 0.003 | 0.25 / 0.04 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| bag 35/20/15/5/5/5/15 | 5 | greedy | 0.220 ± 0.175 | 0.16 / 0.19 / 0.22 / 0.23 / 0.21 | 0.53 | 20 (20) | 0.00 | 19.0 / 0.95 / 0.00 / 0.0 | 1.75 ± 1.09 | 0.81 ± 1.17 | 0.002 | 0.002 | 0.24 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

### Sweep `market`: Market size

Command: `uv run python scripts/tune.py --sweep market`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| market_size = 3 | 2 | greedy | 0.018 ± 0.088 | 0.51 / 0.49 | 0.49 | 48 (48) | 0.73 | 11.3 / 1.65 / 0.00 / 35.0 | 0.85 ± 1.00 | 0.67 ± 0.88 | 0.001 | 0.002 | 0.22 / 0.20 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| market_size = 3 | 3 | greedy | 0.119 ± 0.124 | 0.31 / 0.32 / 0.37 | 0.50 | 45 (45) | 0.58 | 16.7 / 2.02 / 0.00 / 26.2 | 1.13 ± 1.00 | 0.72 ± 0.91 | 0.001 | 0.003 | 0.31 / 0.12 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| market_size = 3 | 4 | greedy | 0.155 ± 0.152 | 0.22 / 0.24 / 0.29 / 0.25 | 0.61 | 48 (48) | 0.42 | 24.5 / 3.22 / 0.00 / 20.3 | 1.33 ± 1.06 | 0.70 ± 1.02 | 0.001 | 0.001 | 0.24 / 0.04 / 0.01 | 0.00 | n/a / 0.250 | 0.00 |
| market_size = 3 | 5 | greedy | 0.203 ± 0.175 | 0.16 / 0.18 / 0.23 / 0.22 / 0.21 | 0.56 | 50 (50) | 0.28 | 32.1 / 3.76 / 0.00 / 14.2 | 1.68 ± 1.05 | 0.75 ± 1.18 | 0.001 | 0.002 | 0.22 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| market_size = 4 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 48 (48) | 0.72 | 11.4 / 1.79 / 0.00 / 34.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| market_size = 4 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| market_size = 4 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| market_size = 4 | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 50 (50) | 0.29 | 31.6 / 3.81 / 0.00 / 14.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| market_size = 5 | 2 | greedy | 0.022 ± 0.088 | 0.51 / 0.49 | 0.52 | 48 (48) | 0.72 | 11.3 / 1.90 / 0.00 / 34.8 | 0.87 ± 1.10 | 0.69 ± 0.94 | 0.003 | 0.006 | 0.23 / 0.18 / 0.04 | 0.00 | n/a / 0.500 | 0.00 |
| market_size = 5 | 3 | greedy | 0.132 ± 0.124 | 0.29 / 0.36 / 0.35 | 0.53 | 45 (45) | 0.59 | 16.4 / 2.24 / 0.00 / 26.3 | 1.11 ± 1.03 | 0.70 ± 0.90 | 0.001 | 0.001 | 0.26 / 0.13 / 0.01 | 0.00 | n/a / 0.333 | 0.00 |
| market_size = 5 | 4 | greedy | 0.099 ± 0.152 | 0.26 / 0.23 / 0.26 / 0.25 | 0.57 | 48 (48) | 0.44 | 23.6 / 3.38 / 0.00 / 21.0 | 1.40 ± 1.02 | 0.74 ± 1.03 | 0.002 | 0.003 | 0.24 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| market_size = 5 | 5 | greedy | 0.183 ± 0.175 | 0.17 / 0.18 / 0.24 / 0.22 / 0.20 | 0.50 | 50 (50) | 0.30 | 31.3 / 3.92 / 0.00 / 14.8 | 1.77 ± 1.11 | 0.80 ± 1.20 | 0.002 | 0.005 | 0.22 / 0.07 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| market_size = 3 | 2 | greedy | 0.004 ± 0.088 | 0.50 / 0.50 | 0.60 | 12 (12) | 0.27 | 7.8 / 1.01 / 0.00 / 3.2 | 0.66 ± 0.93 | 0.52 ± 0.80 | 0.001 | 0.001 | 0.17 / 0.16 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| market_size = 3 | 3 | greedy | 0.124 ± 0.124 | 0.29 / 0.34 / 0.37 | 0.56 | 18 (18) | 0.21 | 12.8 / 1.41 / 0.00 / 3.8 | 1.03 ± 0.98 | 0.67 ± 0.87 | 0.002 | 0.002 | 0.30 / 0.11 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| market_size = 3 | 4 | greedy | 0.191 ± 0.152 | 0.22 / 0.20 / 0.29 / 0.29 | 0.53 | 16 (16) | 0.02 | 15.3 / 0.43 / 0.00 / 0.3 | 1.45 ± 0.95 | 0.81 ± 1.01 | 0.003 | 0.003 | 0.30 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| market_size = 3 | 5 | greedy | 0.312 ± 0.175 | 0.14 / 0.18 / 0.22 / 0.25 / 0.21 | 0.47 | 20 (20) | 0.01 | 19.3 / 0.57 / 0.00 / 0.1 | 1.83 ± 1.05 | 0.86 ± 1.20 | 0.003 | 0.003 | 0.26 / 0.05 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| market_size = 4 | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| market_size = 4 | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| market_size = 4 | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| market_size = 4 | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| market_size = 5 | 2 | greedy | 0.028 ± 0.088 | 0.49 / 0.51 | 0.61 | 12 (12) | 0.26 | 7.7 / 1.21 / 0.00 / 3.1 | 0.67 ± 0.95 | 0.53 ± 0.82 | 0.002 | 0.002 | 0.17 / 0.16 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| market_size = 5 | 3 | greedy | 0.115 ± 0.124 | 0.31 / 0.32 / 0.37 | 0.55 | 18 (18) | 0.22 | 12.5 / 1.65 / 0.00 / 3.9 | 1.02 ± 1.03 | 0.63 ± 0.89 | 0.001 | 0.001 | 0.26 / 0.11 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| market_size = 5 | 4 | greedy | 0.190 ± 0.152 | 0.21 / 0.25 / 0.24 / 0.30 | 0.47 | 16 (16) | 0.01 | 15.5 / 0.33 / 0.00 / 0.2 | 1.63 ± 0.98 | 0.90 ± 1.04 | 0.002 | 0.002 | 0.30 / 0.04 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| market_size = 5 | 5 | greedy | 0.198 ± 0.175 | 0.17 / 0.16 / 0.24 / 0.23 / 0.20 | 0.41 | 20 (20) | 0.01 | 19.6 / 0.25 / 0.00 / 0.1 | 2.13 ± 1.08 | 1.01 ± 1.30 | 0.002 | 0.002 | 0.26 / 0.05 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |

### Sweep `rounds`: Rounds per player count (2/3/4/5 players): current, low and high end of the length target, and whole start-player rotations

Command: `uv run python scripts/tune.py --sweep rounds`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current: rounds 12/12/12/12 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 24 (24) | 0.45 | 11.4 / 1.79 / 0.00 / 10.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| current: rounds 12/12/12/12 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 36 (36) | 0.48 | 16.5 / 2.15 / 0.00 / 17.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| current: rounds 12/12/12/12 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| current: rounds 12/12/12/12 | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 60 (60) | 0.41 | 31.6 / 3.81 / 0.00 / 24.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| target low: rounds 23/15/12/9 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 46 (46) | 0.71 | 11.4 / 1.79 / 0.00 / 32.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| target low: rounds 23/15/12/9 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| target low: rounds 23/15/12/9 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| target low: rounds 23/15/12/9 | 5 | greedy | 0.194 ± 0.175 | 0.16 / 0.20 / 0.22 / 0.21 / 0.20 | 0.54 | 45 (45) | 0.21 | 31.6 / 3.75 / 0.00 / 9.6 | 1.74 ± 1.08 | 0.80 ± 1.19 | 0.002 | 0.003 | 0.21 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| target high: rounds 30/20/15/12 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 60 (60) | 0.78 | 11.4 / 1.79 / 0.00 / 46.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| target high: rounds 30/20/15/12 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 60 (60) | 0.69 | 16.5 / 2.15 / 0.00 / 41.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| target high: rounds 30/20/15/12 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 60 (60) | 0.55 | 23.7 / 3.25 / 0.00 / 33.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| target high: rounds 30/20/15/12 | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 60 (60) | 0.41 | 31.6 / 3.81 / 0.00 / 24.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| full rotations: rounds 24/15/12/10 | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 48 (48) | 0.72 | 11.4 / 1.79 / 0.00 / 34.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| full rotations: rounds 24/15/12/10 | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| full rotations: rounds 24/15/12/10 | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| full rotations: rounds 24/15/12/10 | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 50 (50) | 0.29 | 31.6 / 3.81 / 0.00 / 14.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| current: rounds 5/5/5/5 | 2 | greedy | 0.036 ± 0.088 | 0.48 / 0.52 | 0.52 | 10 (10) | 0.15 | 7.7 / 0.79 / 0.00 / 1.5 | 0.85 ± 1.04 | 0.68 ± 0.91 | 0.005 | 0.005 | 0.24 / 0.19 / 0.04 | 0.00 | n/a / 0.500 | 0.00 |
| current: rounds 5/5/5/5 | 3 | greedy | 0.142 ± 0.124 | 0.30 / 0.32 / 0.38 | 0.50 | 15 (15) | 0.10 | 12.4 / 1.05 / 0.00 / 1.5 | 1.18 ± 0.99 | 0.76 ± 0.94 | 0.001 | 0.001 | 0.29 / 0.16 / 0.03 | 0.00 | n/a / 0.333 | 0.00 |
| current: rounds 5/5/5/5 | 4 | greedy | 0.071 ± 0.152 | 0.23 / 0.24 / 0.25 / 0.27 | 0.53 | 20 (20) | 0.06 | 17.4 / 1.31 / 0.00 / 1.3 | 1.50 ± 1.05 | 0.83 ± 1.04 | 0.003 | 0.003 | 0.27 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| current: rounds 5/5/5/5 | 5 | greedy | 0.344 ± 0.175 | 0.16 / 0.19 / 0.27 / 0.20 / 0.18 | 0.48 | 25 (25) | 0.04 | 22.7 / 1.34 / 0.00 / 1.0 | 1.94 ± 1.20 | 0.89 ± 1.29 | 0.002 | 0.002 | 0.25 / 0.05 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| target low: rounds 5/4/3/2 | 2 | greedy | 0.036 ± 0.088 | 0.48 / 0.52 | 0.52 | 10 (10) | 0.15 | 7.7 / 0.79 / 0.00 / 1.5 | 0.85 ± 1.04 | 0.68 ± 0.91 | 0.005 | 0.005 | 0.24 / 0.19 / 0.04 | 0.00 | n/a / 0.500 | 0.00 |
| target low: rounds 5/4/3/2 | 3 | greedy | 0.102 ± 0.124 | 0.32 / 0.32 / 0.37 | 0.46 | 12 (12) | 0.03 | 11.3 / 0.33 / 0.00 / 0.4 | 1.28 ± 0.93 | 0.81 ± 0.92 | 0.001 | 0.001 | 0.32 / 0.15 / 0.03 | 0.00 | n/a / 0.333 | 0.00 |
| target low: rounds 5/4/3/2 | 4 | greedy | 0.384 ± 0.152 | 0.19 / 0.17 / 0.35 / 0.29 | 0.54 | 12 (12) | 0.00 | 12.0 / 0.01 / 0.00 / 0.0 | 1.40 ± 0.90 | 0.79 ± 0.98 | 0.001 | 0.001 | 0.32 / 0.02 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| target low: rounds 5/4/3/2 | 5 | greedy | 0.543 ± 0.175 | 0.12 / 0.22 / 0.31 / 0.21 / 0.15 | 0.63 | 10 (10) | 0.00 | 10.0 / 0.02 / 0.00 / 0.0 | 1.25 ± 0.89 | 0.61 ± 0.97 | 0.000 | 0.000 | 0.30 / 0.02 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| target high: rounds 10/6/5/4 | 2 | greedy | 0.044 ± 0.088 | 0.48 / 0.52 | 0.56 | 20 (20) | 0.55 | 7.9 / 1.18 / 0.00 / 10.9 | 0.72 ± 0.96 | 0.56 ± 0.83 | 0.003 | 0.003 | 0.19 / 0.17 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| target high: rounds 10/6/5/4 | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| target high: rounds 10/6/5/4 | 4 | greedy | 0.071 ± 0.152 | 0.23 / 0.24 / 0.25 / 0.27 | 0.53 | 20 (20) | 0.06 | 17.4 / 1.31 / 0.00 / 1.3 | 1.50 ± 1.05 | 0.83 ± 1.04 | 0.003 | 0.003 | 0.27 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| target high: rounds 10/6/5/4 | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| full rotations: rounds 6/6/4/4 | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| full rotations: rounds 6/6/4/4 | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| full rotations: rounds 6/6/4/4 | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| full rotations: rounds 6/6/4/4 | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |

### Sweep `die`: Bribe die faces, mixed seating (the saboteur bribes only when the swing beats (faces + 1) / 2)

Command: `uv run python scripts/tune.py --sweep die`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| die_faces = d4 | 2 | mixed | 0.000 ± 0.088 | 0.50 / 0.50 | 0.63 | 48 (48) | 0.72 | 11.4 / 1.77 / 0.08 / 34.8 | 0.56 ± 0.83 | 0.39 ± 0.79 | 0.000 | 0.000 | 0.14 / 0.11 / 0.01 | 0.07 | 0.257 / 0.509 | 0.09 |
| die_faces = d4 | 3 | mixed | 0.021 ± 0.124 | 0.34 / 0.33 / 0.33 | 0.59 | 45 (45) | 0.50 | 16.4 / 2.09 / 4.03 / 22.5 | 0.47 ± 0.77 | -3.01 ± 7.03 | 0.001 | 0.001 | 0.03 / 0.03 / 0.01 | 0.33 | 0.005 / 0.421 | 3.37 |
| die_faces = d4 | 4 | mixed | 0.084 ± 0.152 | 0.26 / 0.25 / 0.25 / 0.23 | 0.79 | 48 (48) | 0.36 | 23.7 / 3.23 / 3.97 / 17.1 | 0.55 ± 0.76 | -2.18 ± 5.56 | 0.001 | 0.001 | 0.01 / 0.00 / 0.00 | 0.42 | 0.000 / 0.310 | 2.47 |
| die_faces = d4 | 5 | mixed | 0.172 ± 0.175 | 0.19 / 0.23 / 0.23 / 0.18 / 0.17 | 0.79 | 50 (50) | 0.18 | 30.8 / 3.77 / 6.20 / 9.2 | 0.59 ± 0.78 | -2.82 ± 6.00 | 0.001 | 0.002 | 0.01 / 0.01 / 0.00 | 0.59 | 0.000 / 0.285 | 3.10 |
| die_faces = d6 | 2 | mixed | 0.006 ± 0.088 | 0.50 / 0.50 | 0.68 | 48 (48) | 0.73 | 11.4 / 1.77 / 0.00 / 34.8 | 0.50 ± 0.82 | 0.38 ± 0.70 | 0.000 | 0.000 | 0.12 / 0.12 / 0.01 | 0.00 | 0.000 / 0.501 | 0.00 |
| die_faces = d6 | 3 | mixed | 0.033 ± 0.124 | 0.33 / 0.33 / 0.34 | 0.77 | 45 (45) | 0.56 | 16.5 / 2.12 / 1.10 / 25.3 | 0.36 ± 0.75 | -1.04 ± 5.35 | 0.001 | 0.001 | 0.05 / 0.04 / 0.01 | 0.12 | 0.019 / 0.356 | 1.28 |
| die_faces = d6 | 4 | mixed | 0.049 ± 0.152 | 0.26 / 0.25 / 0.25 / 0.24 | 0.91 | 48 (48) | 0.42 | 23.8 / 3.26 / 0.73 / 20.2 | 0.37 ± 0.71 | -0.44 ± 3.26 | 0.001 | 0.001 | 0.02 / 0.01 / 0.00 | 0.13 | 0.000 / 0.264 | 0.63 |
| die_faces = d6 | 5 | mixed | 0.068 ± 0.175 | 0.20 / 0.21 / 0.20 / 0.19 / 0.20 | 0.91 | 50 (50) | 0.26 | 31.3 / 3.80 / 1.64 / 13.2 | 0.37 ± 0.71 | -0.99 ± 4.17 | 0.001 | 0.002 | 0.01 / 0.01 / 0.00 | 0.28 | 0.000 / 0.224 | 1.15 |
| die_faces = d8 | 2 | mixed | 0.004 ± 0.088 | 0.50 / 0.50 | 0.68 | 48 (48) | 0.73 | 11.4 / 1.77 / 0.00 / 34.8 | 0.49 ± 0.81 | 0.38 ± 0.69 | 0.000 | 0.000 | 0.12 / 0.12 / 0.01 | 0.00 | n/a / 0.500 | 0.00 |
| die_faces = d8 | 3 | mixed | 0.044 ± 0.124 | 0.32 / 0.33 / 0.35 | 0.81 | 45 (45) | 0.57 | 16.5 / 2.12 / 0.53 / 25.9 | 0.36 ± 0.74 | -0.60 ± 4.86 | 0.001 | 0.001 | 0.05 / 0.04 / 0.01 | 0.07 | 0.000 / 0.346 | 0.82 |
| die_faces = d8 | 4 | mixed | 0.081 ± 0.152 | 0.27 / 0.25 / 0.25 / 0.24 | 0.92 | 48 (48) | 0.43 | 23.8 / 3.26 / 0.31 / 20.6 | 0.34 ± 0.69 | -0.14 ± 2.59 | 0.000 | 0.000 | 0.02 / 0.01 / 0.00 | 0.07 | 0.000 / 0.256 | 0.31 |
| die_faces = d8 | 5 | mixed | 0.061 ± 0.175 | 0.20 / 0.21 / 0.20 / 0.19 / 0.20 | 0.91 | 50 (50) | 0.28 | 31.4 / 3.81 / 0.99 / 13.8 | 0.36 ± 0.67 | -0.77 ± 4.39 | 0.000 | 0.001 | 0.02 / 0.01 / 0.00 | 0.19 | 0.000 / 0.215 | 0.92 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| die_faces = d4 | 2 | mixed | 0.048 ± 0.088 | 0.48 / 0.52 | 0.65 | 12 (12) | 0.25 | 7.8 / 1.12 / 0.04 / 3.0 | 0.52 ± 0.83 | 0.39 ± 0.73 | 0.001 | 0.001 | 0.12 / 0.11 / 0.01 | 0.04 | 0.136 / 0.508 | 0.05 |
| die_faces = d4 | 3 | mixed | 0.012 ± 0.124 | 0.33 / 0.34 / 0.33 | 0.69 | 18 (18) | 0.19 | 12.3 / 1.60 / 0.76 / 3.3 | 0.42 ± 0.71 | -0.33 ± 1.74 | 0.001 | 0.001 | 0.05 / 0.05 / 0.01 | 0.26 | 0.014 / 0.388 | 0.64 |
| die_faces = d4 | 4 | mixed | 0.043 ± 0.152 | 0.26 / 0.25 / 0.24 / 0.24 | 0.85 | 16 (16) | 0.01 | 14.2 / 1.22 / 0.45 / 0.1 | 0.56 ± 0.81 | 0.04 ± 1.22 | 0.001 | 0.001 | 0.06 / 0.01 / 0.00 | 0.25 | 0.000 / 0.273 | 0.28 |
| die_faces = d4 | 5 | mixed | 0.143 ± 0.175 | 0.21 / 0.23 / 0.18 / 0.18 / 0.20 | 0.83 | 20 (20) | 0.00 | 17.3 / 1.60 / 1.08 / 0.1 | 0.71 ± 0.86 | -0.20 ± 1.68 | 0.001 | 0.001 | 0.05 / 0.03 / 0.00 | 0.44 | 0.000 / 0.233 | 0.52 |
| die_faces = d6 | 2 | mixed | 0.060 ± 0.088 | 0.47 / 0.53 | 0.69 | 12 (12) | 0.25 | 7.8 / 1.12 / 0.01 / 3.1 | 0.49 ± 0.83 | 0.38 ± 0.72 | 0.001 | 0.001 | 0.12 / 0.11 / 0.01 | 0.01 | 0.000 / 0.502 | 0.01 |
| die_faces = d6 | 3 | mixed | 0.028 ± 0.124 | 0.32 / 0.34 / 0.33 | 0.82 | 18 (18) | 0.21 | 12.5 / 1.62 / 0.17 / 3.7 | 0.36 ± 0.69 | 0.02 ± 1.27 | 0.000 | 0.000 | 0.07 / 0.04 / 0.00 | 0.08 | 0.034 / 0.345 | 0.21 |
| die_faces = d6 | 4 | mixed | 0.059 ± 0.152 | 0.26 / 0.25 / 0.24 / 0.25 | 0.87 | 16 (16) | 0.01 | 14.6 / 1.21 / 0.10 / 0.1 | 0.48 ± 0.79 | 0.17 ± 0.93 | 0.001 | 0.001 | 0.07 / 0.02 / 0.00 | 0.07 | 0.000 / 0.255 | 0.09 |
| die_faces = d6 | 5 | mixed | 0.138 ± 0.175 | 0.23 / 0.21 / 0.17 / 0.19 / 0.20 | 0.86 | 20 (20) | 0.00 | 18.1 / 1.54 / 0.26 / 0.1 | 0.62 ± 0.89 | 0.09 ± 1.24 | 0.000 | 0.000 | 0.05 / 0.02 / 0.00 | 0.15 | 0.000 / 0.209 | 0.18 |
| die_faces = d8 | 2 | mixed | 0.056 ± 0.088 | 0.47 / 0.53 | 0.69 | 12 (12) | 0.26 | 7.8 / 1.12 / 0.00 / 3.1 | 0.48 ± 0.83 | 0.37 ± 0.71 | 0.001 | 0.001 | 0.12 / 0.11 / 0.01 | 0.00 | 0.000 / 0.501 | 0.00 |
| die_faces = d8 | 3 | mixed | 0.034 ± 0.124 | 0.32 / 0.34 / 0.34 | 0.84 | 18 (18) | 0.21 | 12.6 / 1.62 / 0.08 / 3.7 | 0.34 ± 0.69 | 0.10 ± 1.06 | 0.000 | 0.000 | 0.06 / 0.04 / 0.00 | 0.04 | 0.000 / 0.340 | 0.12 |
| die_faces = d8 | 4 | mixed | 0.057 ± 0.152 | 0.26 / 0.25 / 0.24 / 0.25 | 0.87 | 16 (16) | 0.01 | 14.6 / 1.20 / 0.06 / 0.1 | 0.47 ± 0.79 | 0.19 ± 0.90 | 0.001 | 0.001 | 0.07 / 0.02 / 0.00 | 0.05 | 0.000 / 0.254 | 0.07 |
| die_faces = d8 | 5 | mixed | 0.164 ± 0.175 | 0.23 / 0.20 / 0.17 / 0.20 / 0.21 | 0.87 | 20 (20) | 0.00 | 18.2 / 1.55 / 0.16 / 0.1 | 0.59 ± 0.88 | 0.12 ± 1.20 | 0.000 | 0.000 | 0.05 / 0.02 / 0.00 | 0.10 | 0.000 / 0.205 | 0.14 |

### Sweep `bodega`: Flash bodega bonus: points for watered vineyards of N distinct varietals (Normal's bodega rate is in the final validation)

Command: `uv run python scripts/tune.py --sweep bodega`. 500 games per row, seed 20001.

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| +1 for 3 varietals (current) | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| +1 for 3 varietals (current) | 2 | mixed | 0.060 ± 0.088 | 0.47 / 0.53 | 0.69 | 12 (12) | 0.25 | 7.8 / 1.12 / 0.01 / 3.1 | 0.49 ± 0.83 | 0.38 ± 0.72 | 0.001 | 0.001 | 0.12 / 0.11 / 0.01 | 0.01 | 0.000 / 0.502 | 0.01 |
| +1 for 3 varietals (current) | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| +1 for 3 varietals (current) | 3 | mixed | 0.028 ± 0.124 | 0.32 / 0.34 / 0.33 | 0.82 | 18 (18) | 0.21 | 12.5 / 1.62 / 0.17 / 3.7 | 0.36 ± 0.69 | 0.02 ± 1.27 | 0.000 | 0.000 | 0.07 / 0.04 / 0.00 | 0.08 | 0.034 / 0.345 | 0.21 |
| +1 for 3 varietals (current) | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| +1 for 3 varietals (current) | 4 | mixed | 0.059 ± 0.152 | 0.26 / 0.25 / 0.24 / 0.25 | 0.87 | 16 (16) | 0.01 | 14.6 / 1.21 / 0.10 / 0.1 | 0.48 ± 0.79 | 0.17 ± 0.93 | 0.001 | 0.001 | 0.07 / 0.02 / 0.00 | 0.07 | 0.000 / 0.255 | 0.09 |
| +1 for 3 varietals (current) | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| +1 for 3 varietals (current) | 5 | mixed | 0.138 ± 0.175 | 0.23 / 0.21 / 0.17 / 0.19 / 0.20 | 0.86 | 20 (20) | 0.00 | 18.1 / 1.54 / 0.26 / 0.1 | 0.62 ± 0.89 | 0.09 ± 1.24 | 0.000 | 0.000 | 0.05 / 0.02 / 0.00 | 0.15 | 0.000 / 0.209 | 0.18 |
| +2 for 2 varietals | 2 | greedy | 0.026 ± 0.088 | 0.49 / 0.51 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.84 ± 1.21 | 0.64 ± 1.01 | 0.022 | 0.044 | 0.20 / 0.18 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| +2 for 2 varietals | 2 | mixed | 0.056 ± 0.088 | 0.47 / 0.53 | 0.69 | 12 (12) | 0.25 | 7.8 / 1.12 / 0.01 / 3.1 | 0.52 ± 0.95 | 0.40 ± 0.79 | 0.012 | 0.024 | 0.12 / 0.12 / 0.01 | 0.01 | 0.667 / 0.499 | 0.01 |
| +2 for 2 varietals | 3 | greedy | 0.221 ± 0.124 | 0.30 / 0.29 / 0.41 | 0.51 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.14 ± 1.12 | 0.72 ± 0.97 | 0.029 | 0.059 | 0.30 / 0.16 / 0.04 | 0.00 | n/a / 0.333 | 0.00 |
| +2 for 2 varietals | 3 | mixed | 0.031 ± 0.124 | 0.32 / 0.34 / 0.34 | 0.82 | 18 (18) | 0.21 | 12.5 / 1.62 / 0.17 / 3.7 | 0.38 ± 0.77 | 0.04 ± 1.25 | 0.008 | 0.016 | 0.07 / 0.05 / 0.00 | 0.08 | 0.052 / 0.345 | 0.21 |
| +2 for 2 varietals | 4 | greedy | 0.275 ± 0.152 | 0.21 / 0.22 / 0.25 / 0.32 | 0.45 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.71 ± 1.07 | 1.01 ± 1.10 | 0.051 | 0.102 | 0.37 / 0.11 / 0.03 | 0.00 | n/a / 0.250 | 0.00 |
| +2 for 2 varietals | 4 | mixed | 0.053 ± 0.152 | 0.26 / 0.25 / 0.24 / 0.25 | 0.87 | 16 (16) | 0.01 | 14.6 / 1.21 / 0.10 / 0.1 | 0.48 ± 0.82 | 0.19 ± 0.92 | 0.013 | 0.026 | 0.08 / 0.02 / 0.01 | 0.07 | 0.000 / 0.255 | 0.09 |
| +2 for 2 varietals | 5 | greedy | 0.328 ± 0.175 | 0.16 / 0.16 / 0.27 / 0.23 / 0.18 | 0.42 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.04 ± 1.12 | 1.06 ± 1.24 | 0.052 | 0.105 | 0.36 / 0.12 / 0.04 | 0.00 | n/a / 0.200 | 0.00 |
| +2 for 2 varietals | 5 | mixed | 0.115 ± 0.175 | 0.22 / 0.20 / 0.18 / 0.19 / 0.21 | 0.86 | 20 (20) | 0.00 | 18.1 / 1.54 / 0.26 / 0.1 | 0.62 ± 0.90 | 0.11 ± 1.22 | 0.012 | 0.023 | 0.06 / 0.02 / 0.01 | 0.15 | 0.010 / 0.208 | 0.18 |


### Sweep `combined`: The best single changes of the sweeps above, combined

Command: `uv run python scripts/tune.py --sweep combined`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 2 | greedy | 0.026 ± 0.088 | 0.51 / 0.49 | 0.50 | 48 (48) | 0.72 | 11.4 / 1.79 / 0.00 / 34.8 | 0.87 ± 1.04 | 0.69 ± 0.90 | 0.000 | 0.000 | 0.22 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| base | 3 | greedy | 0.192 ± 0.124 | 0.30 / 0.30 / 0.40 | 0.53 | 45 (45) | 0.59 | 16.5 / 2.15 / 0.00 / 26.3 | 1.05 ± 1.04 | 0.66 ± 0.90 | 0.000 | 0.000 | 0.29 / 0.13 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| base | 4 | greedy | 0.185 ± 0.152 | 0.22 / 0.23 / 0.30 / 0.26 | 0.58 | 48 (48) | 0.44 | 23.7 / 3.25 / 0.00 / 21.0 | 1.33 ± 1.01 | 0.72 ± 0.99 | 0.002 | 0.004 | 0.26 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| base | 5 | greedy | 0.189 ± 0.175 | 0.16 / 0.20 / 0.23 / 0.21 / 0.20 | 0.54 | 50 (50) | 0.29 | 31.6 / 3.81 / 0.00 / 14.5 | 1.73 ± 1.07 | 0.79 ± 1.18 | 0.002 | 0.003 | 0.22 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| 24 hexes/player | 2 | greedy | 0.032 ± 0.088 | 0.52 / 0.48 | 0.44 | 48 (48) | 0.64 | 15.4 / 2.08 / 0.00 / 30.6 | 1.01 ± 1.08 | 0.81 ± 0.95 | 0.004 | 0.008 | 0.27 / 0.22 / 0.05 | 0.00 | n/a / 0.500 | 0.00 |
| 24 hexes/player | 3 | greedy | 0.036 ± 0.124 | 0.33 / 0.32 / 0.34 | 0.46 | 45 (45) | 0.37 | 24.9 / 3.25 / 0.00 / 16.8 | 1.29 ± 1.07 | 0.83 ± 1.00 | 0.002 | 0.004 | 0.33 / 0.15 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| 24 hexes/player | 4 | greedy | 0.059 ± 0.152 | 0.24 / 0.24 / 0.26 / 0.26 | 0.54 | 48 (48) | 0.19 | 34.6 / 4.24 / 0.00 / 9.2 | 1.62 ± 1.10 | 0.87 ± 1.14 | 0.004 | 0.009 | 0.24 / 0.04 / 0.01 | 0.00 | n/a / 0.250 | 0.00 |
| 24 hexes/player | 5 | greedy | 0.143 ± 0.175 | 0.19 / 0.18 / 0.23 / 0.22 / 0.19 | 0.49 | 50 (50) | 0.06 | 43.2 / 4.01 / 0.00 / 2.8 | 2.08 ± 1.21 | 0.94 ± 1.35 | 0.004 | 0.009 | 0.21 / 0.05 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| 24 hexes/player, branchy bag | 2 | greedy | 0.022 ± 0.088 | 0.51 / 0.49 | 0.26 | 48 (48) | 0.53 | 20.0 / 2.66 / 0.00 / 25.4 | 1.94 ± 1.52 | 1.55 ± 1.37 | 0.017 | 0.034 | 0.45 / 0.31 / 0.15 | 0.00 | n/a / 0.500 | 0.00 |
| 24 hexes/player, branchy bag | 3 | greedy | 0.169 ± 0.124 | 0.28 / 0.34 / 0.39 | 0.24 | 45 (45) | 0.21 | 31.5 / 3.89 / 0.00 / 9.6 | 2.56 ± 1.41 | 1.70 ± 1.43 | 0.014 | 0.028 | 0.47 / 0.19 / 0.07 | 0.00 | n/a / 0.333 | 0.00 |
| 24 hexes/player, branchy bag | 4 | greedy | 0.115 ± 0.152 | 0.22 / 0.25 / 0.28 / 0.25 | 0.20 | 48 (48) | 0.04 | 42.7 / 3.43 / 0.00 / 1.8 | 3.45 ± 1.44 | 1.97 ± 1.74 | 0.027 | 0.054 | 0.34 / 0.18 / 0.06 | 0.00 | n/a / 0.250 | 0.00 |
| 24 hexes/player, branchy bag | 5 | greedy | 0.245 ± 0.175 | 0.18 / 0.19 / 0.25 / 0.19 / 0.19 | 0.19 | 50 (50) | 0.00 | 47.3 / 2.58 / 0.00 / 0.1 | 4.34 ± 1.57 | 2.15 ± 2.16 | 0.031 | 0.062 | 0.29 / 0.14 / 0.05 | 0.00 | n/a / 0.200 | 0.00 |
| 24 hexes/player, branchy bag, no stone | 2 | greedy | 0.122 ± 0.088 | 0.56 / 0.44 | 0.09 | 48 (48) | 0.39 | 26.1 / 2.95 / 0.00 / 18.9 | 3.09 ± 1.60 | 2.52 ± 1.51 | 0.060 | 0.120 | 0.67 / 0.44 / 0.30 | 0.00 | n/a / 0.500 | 0.00 |
| 24 hexes/player, branchy bag, no stone | 3 | greedy | 0.027 ± 0.124 | 0.34 / 0.32 / 0.34 | 0.14 | 45 (45) | 0.03 | 40.0 / 3.44 / 0.00 / 1.6 | 3.72 ± 1.42 | 2.57 ± 1.62 | 0.051 | 0.103 | 0.59 / 0.36 / 0.17 | 0.00 | n/a / 0.333 | 0.00 |
| 24 hexes/player, branchy bag, no stone | 4 | greedy | 0.229 ± 0.152 | 0.22 / 0.24 / 0.31 / 0.23 | 0.12 | 48 (48) | 0.00 | 45.6 / 2.36 / 0.00 / 0.0 | 4.57 ± 1.36 | 2.75 ± 1.94 | 0.058 | 0.116 | 0.46 / 0.30 / 0.11 | 0.00 | n/a / 0.250 | 0.00 |
| 24 hexes/player, branchy bag, no stone | 5 | greedy | 0.367 ± 0.175 | 0.18 / 0.20 / 0.27 / 0.16 / 0.18 | 0.10 | 50 (50) | 0.00 | 47.6 / 2.43 / 0.00 / 0.0 | 5.21 ± 1.59 | 2.68 ± 2.40 | 0.050 | 0.099 | 0.36 / 0.19 / 0.10 | 0.00 | n/a / 0.200 | 0.00 |
| 24 hexes/player, 3 vineyards/player | 2 | greedy | 0.018 ± 0.088 | 0.51 / 0.49 | 0.35 | 48 (48) | 0.64 | 15.0 / 2.23 / 0.00 / 30.8 | 1.28 ± 1.21 | 1.01 ± 1.07 | 0.004 | 0.008 | 0.33 / 0.22 / 0.06 | 0.00 | n/a / 0.500 | 0.00 |
| 24 hexes/player, 3 vineyards/player | 3 | greedy | 0.049 ± 0.124 | 0.32 / 0.34 / 0.34 | 0.37 | 45 (45) | 0.42 | 23.6 / 2.71 / 0.00 / 18.7 | 1.78 ± 1.19 | 1.18 ± 1.15 | 0.003 | 0.007 | 0.38 / 0.19 / 0.04 | 0.00 | n/a / 0.333 | 0.00 |
| 24 hexes/player, 3 vineyards/player | 4 | greedy | 0.191 ± 0.152 | 0.23 / 0.23 / 0.30 / 0.24 | 0.39 | 48 (48) | 0.24 | 32.6 / 3.74 / 0.00 / 11.6 | 2.03 ± 1.12 | 1.15 ± 1.20 | 0.004 | 0.007 | 0.34 / 0.07 / 0.01 | 0.00 | n/a / 0.250 | 0.00 |
| 24 hexes/player, 3 vineyards/player | 5 | greedy | 0.253 ± 0.175 | 0.17 / 0.17 / 0.22 / 0.19 / 0.25 | 0.39 | 50 (50) | 0.09 | 41.4 / 4.19 / 0.00 / 4.4 | 2.50 ± 1.24 | 1.21 ± 1.45 | 0.007 | 0.014 | 0.29 / 0.10 / 0.02 | 0.00 | n/a / 0.200 | 0.00 |

#### Flash

Base: rounds=6/6/4/4, hexes_per_player=14, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| base | 2 | greedy | 0.038 ± 0.088 | 0.48 / 0.52 | 0.56 | 12 (12) | 0.26 | 7.9 / 1.06 / 0.00 / 3.1 | 0.77 ± 1.02 | 0.60 ± 0.88 | 0.005 | 0.005 | 0.20 / 0.17 / 0.03 | 0.00 | n/a / 0.500 | 0.00 |
| base | 3 | greedy | 0.182 ± 0.124 | 0.30 / 0.31 / 0.39 | 0.53 | 18 (18) | 0.21 | 12.7 / 1.56 / 0.00 / 3.8 | 1.05 ± 0.93 | 0.66 ± 0.87 | 0.001 | 0.001 | 0.27 / 0.14 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| base | 4 | greedy | 0.187 ± 0.152 | 0.22 / 0.24 / 0.24 / 0.30 | 0.48 | 16 (16) | 0.01 | 15.6 / 0.29 / 0.00 / 0.1 | 1.66 ± 1.01 | 0.91 ± 1.08 | 0.003 | 0.003 | 0.28 / 0.03 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| base | 5 | greedy | 0.287 ± 0.175 | 0.17 / 0.17 / 0.26 / 0.23 / 0.18 | 0.46 | 20 (20) | 0.00 | 19.6 / 0.30 / 0.00 / 0.1 | 2.01 ± 1.09 | 0.96 ± 1.27 | 0.001 | 0.001 | 0.29 / 0.06 / 0.01 | 0.00 | n/a / 0.200 | 0.00 |
| branchy bag | 2 | greedy | 0.080 ± 0.088 | 0.54 / 0.46 | 0.38 | 12 (12) | 0.15 | 9.2 / 0.97 / 0.00 / 1.8 | 1.52 ± 1.47 | 1.24 ± 1.31 | 0.015 | 0.015 | 0.34 / 0.27 / 0.11 | 0.00 | n/a / 0.500 | 0.00 |
| branchy bag | 3 | greedy | 0.135 ± 0.124 | 0.30 / 0.32 / 0.38 | 0.38 | 18 (18) | 0.12 | 14.7 / 1.20 / 0.00 / 2.1 | 2.08 ± 1.50 | 1.39 ± 1.39 | 0.016 | 0.016 | 0.40 / 0.15 / 0.07 | 0.00 | n/a / 0.333 | 0.00 |
| branchy bag | 4 | greedy | 0.171 ± 0.152 | 0.21 / 0.26 / 0.26 / 0.27 | 0.30 | 16 (16) | 0.00 | 15.9 / 0.08 / 0.00 / 0.0 | 3.04 ± 1.36 | 1.70 ± 1.62 | 0.013 | 0.013 | 0.31 / 0.10 / 0.03 | 0.00 | n/a / 0.250 | 0.00 |
| branchy bag | 5 | greedy | 0.211 ± 0.175 | 0.20 / 0.18 / 0.21 / 0.24 / 0.16 | 0.30 | 20 (20) | 0.00 | 19.8 / 0.14 / 0.00 / 0.0 | 3.67 ± 1.45 | 1.70 ± 1.98 | 0.018 | 0.018 | 0.23 / 0.08 / 0.02 | 0.00 | n/a / 0.200 | 0.00 |
| branchy bag, no stone | 2 | greedy | 0.138 ± 0.088 | 0.57 / 0.43 | 0.15 | 12 (12) | 0.05 | 10.9 / 0.47 / 0.00 / 0.6 | 2.53 ± 1.51 | 2.07 ± 1.43 | 0.031 | 0.031 | 0.58 / 0.36 / 0.21 | 0.00 | n/a / 0.500 | 0.00 |
| branchy bag, no stone | 3 | greedy | 0.130 ± 0.124 | 0.30 / 0.32 / 0.38 | 0.15 | 18 (18) | 0.01 | 17.4 / 0.32 / 0.00 / 0.2 | 3.32 ± 1.34 | 2.28 ± 1.50 | 0.048 | 0.048 | 0.49 / 0.26 / 0.12 | 0.00 | n/a / 0.333 | 0.00 |
| branchy bag, no stone | 4 | greedy | 0.182 ± 0.152 | 0.30 / 0.25 / 0.23 / 0.23 | 0.21 | 16 (16) | 0.00 | 15.9 / 0.07 / 0.00 / 0.0 | 3.73 ± 1.26 | 2.13 ± 1.75 | 0.018 | 0.018 | 0.38 / 0.13 / 0.04 | 0.00 | n/a / 0.250 | 0.00 |
| branchy bag, no stone | 5 | greedy | 0.107 ± 0.175 | 0.19 / 0.19 / 0.22 / 0.22 / 0.18 | 0.20 | 20 (20) | 0.00 | 19.8 / 0.18 / 0.00 / 0.0 | 4.37 ± 1.41 | 2.08 ± 2.20 | 0.029 | 0.029 | 0.28 / 0.10 / 0.03 | 0.00 | n/a / 0.200 | 0.00 |
| branchy bag, +2 for 2 varietals | 2 | greedy | 0.084 ± 0.088 | 0.54 / 0.46 | 0.38 | 12 (12) | 0.15 | 9.2 / 0.97 / 0.00 / 1.8 | 1.89 ± 1.99 | 1.47 ± 1.70 | 0.124 | 0.248 | 0.35 / 0.32 / 0.17 | 0.00 | n/a / 0.500 | 0.00 |
| branchy bag, +2 for 2 varietals | 3 | greedy | 0.186 ± 0.124 | 0.28 / 0.32 / 0.40 | 0.33 | 18 (18) | 0.12 | 14.7 / 1.20 / 0.00 / 2.1 | 2.37 ± 1.83 | 1.65 ± 1.62 | 0.136 | 0.272 | 0.50 / 0.24 / 0.15 | 0.00 | n/a / 0.333 | 0.00 |
| branchy bag, +2 for 2 varietals | 4 | greedy | 0.231 ± 0.152 | 0.19 / 0.27 / 0.26 / 0.29 | 0.28 | 16 (16) | 0.00 | 15.9 / 0.08 / 0.00 / 0.0 | 3.15 ± 1.44 | 1.99 ± 1.60 | 0.153 | 0.307 | 0.46 / 0.22 / 0.08 | 0.00 | n/a / 0.250 | 0.00 |
| branchy bag, +2 for 2 varietals | 5 | greedy | 0.376 ± 0.175 | 0.19 / 0.16 / 0.22 / 0.28 / 0.15 | 0.27 | 20 (20) | 0.00 | 19.8 / 0.14 / 0.00 / 0.0 | 3.73 ± 1.48 | 2.01 ± 1.82 | 0.163 | 0.326 | 0.31 / 0.14 / 0.07 | 0.00 | n/a / 0.200 | 0.00 |

### Sweep `rounds2p`: Normal 2-player rounds on the owner's board (15 hexes/player); 3-5 players keep the full rotations

Command: `uv run python scripts/tune.py --sweep rounds2p`. 500 games per row, seed 20001.

#### Normal

Base: rounds=24/15/12/10, hexes_per_player=18, stone_share=10, vineyard_distance=4-4.

| Candidate | P | Seating | Advantage ± 95% | Win rate by position | Shared wins | Turns (min) | Pass share | Canal / gate / bribe / pass | Winning score | Score | Bodega rate | Bodega points | Winner has Malbec / Bonarda / Torrontés | Bribe games | Win rate bribers / non-bribers | Mean debt |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| rounds 8/15/12/10 | 2 | greedy | 0.044 ± 0.088 | 0.48 / 0.52 | 0.55 | 16 (16) | 0.33 | 9.5 / 1.19 / 0.00 / 5.4 | 0.75 ± 0.98 | 0.61 ± 0.86 | 0.000 | 0.000 | 0.19 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| rounds 8/15/12/10 | 3 | greedy | 0.088 ± 0.124 | 0.30 / 0.34 / 0.36 | 0.46 | 45 (45) | 0.64 | 14.5 / 1.72 / 0.00 / 28.8 | 1.17 ± 1.03 | 0.75 ± 0.91 | 0.001 | 0.001 | 0.32 / 0.16 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| rounds 8/15/12/10 | 4 | greedy | 0.115 ± 0.152 | 0.23 / 0.22 / 0.27 / 0.28 | 0.62 | 48 (48) | 0.52 | 20.0 / 2.83 / 0.00 / 25.1 | 1.21 ± 0.93 | 0.65 ± 0.93 | 0.000 | 0.000 | 0.25 / 0.01 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| rounds 8/15/12/10 | 5 | greedy | 0.172 ± 0.175 | 0.18 / 0.20 / 0.23 / 0.21 / 0.18 | 0.57 | 50 (50) | 0.42 | 25.4 / 3.34 / 0.00 / 21.2 | 1.62 ± 1.06 | 0.71 ± 1.15 | 0.002 | 0.004 | 0.23 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| rounds 10/15/12/10 | 2 | greedy | 0.044 ± 0.088 | 0.48 / 0.52 | 0.55 | 20 (20) | 0.47 | 9.5 / 1.19 / 0.00 / 9.3 | 0.75 ± 0.98 | 0.61 ± 0.86 | 0.000 | 0.000 | 0.19 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| rounds 10/15/12/10 | 3 | greedy | 0.088 ± 0.124 | 0.30 / 0.34 / 0.36 | 0.46 | 45 (45) | 0.64 | 14.5 / 1.72 / 0.00 / 28.8 | 1.17 ± 1.03 | 0.75 ± 0.91 | 0.001 | 0.001 | 0.32 / 0.16 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| rounds 10/15/12/10 | 4 | greedy | 0.115 ± 0.152 | 0.23 / 0.22 / 0.27 / 0.28 | 0.62 | 48 (48) | 0.52 | 20.0 / 2.83 / 0.00 / 25.1 | 1.21 ± 0.93 | 0.65 ± 0.93 | 0.000 | 0.000 | 0.25 / 0.01 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| rounds 10/15/12/10 | 5 | greedy | 0.172 ± 0.175 | 0.18 / 0.20 / 0.23 / 0.21 / 0.18 | 0.57 | 50 (50) | 0.42 | 25.4 / 3.34 / 0.00 / 21.2 | 1.62 ± 1.06 | 0.71 ± 1.15 | 0.002 | 0.004 | 0.23 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| rounds 12/15/12/10 | 2 | greedy | 0.044 ± 0.088 | 0.48 / 0.52 | 0.55 | 24 (24) | 0.56 | 9.5 / 1.19 / 0.00 / 13.3 | 0.75 ± 0.98 | 0.61 ± 0.86 | 0.000 | 0.000 | 0.19 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| rounds 12/15/12/10 | 3 | greedy | 0.088 ± 0.124 | 0.30 / 0.34 / 0.36 | 0.46 | 45 (45) | 0.64 | 14.5 / 1.72 / 0.00 / 28.8 | 1.17 ± 1.03 | 0.75 ± 0.91 | 0.001 | 0.001 | 0.32 / 0.16 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| rounds 12/15/12/10 | 4 | greedy | 0.115 ± 0.152 | 0.23 / 0.22 / 0.27 / 0.28 | 0.62 | 48 (48) | 0.52 | 20.0 / 2.83 / 0.00 / 25.1 | 1.21 ± 0.93 | 0.65 ± 0.93 | 0.000 | 0.000 | 0.25 / 0.01 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| rounds 12/15/12/10 | 5 | greedy | 0.172 ± 0.175 | 0.18 / 0.20 / 0.23 / 0.21 / 0.18 | 0.57 | 50 (50) | 0.42 | 25.4 / 3.34 / 0.00 / 21.2 | 1.62 ± 1.06 | 0.71 ± 1.15 | 0.002 | 0.004 | 0.23 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |
| rounds 24/15/12/10 | 2 | greedy | 0.044 ± 0.088 | 0.48 / 0.52 | 0.55 | 48 (48) | 0.78 | 9.5 / 1.19 / 0.00 / 37.3 | 0.75 ± 0.98 | 0.61 ± 0.86 | 0.000 | 0.000 | 0.19 / 0.19 / 0.02 | 0.00 | n/a / 0.500 | 0.00 |
| rounds 24/15/12/10 | 3 | greedy | 0.088 ± 0.124 | 0.30 / 0.34 / 0.36 | 0.46 | 45 (45) | 0.64 | 14.5 / 1.72 / 0.00 / 28.8 | 1.17 ± 1.03 | 0.75 ± 0.91 | 0.001 | 0.001 | 0.32 / 0.16 / 0.02 | 0.00 | n/a / 0.333 | 0.00 |
| rounds 24/15/12/10 | 4 | greedy | 0.115 ± 0.152 | 0.23 / 0.22 / 0.27 / 0.28 | 0.62 | 48 (48) | 0.52 | 20.0 / 2.83 / 0.00 / 25.1 | 1.21 ± 0.93 | 0.65 ± 0.93 | 0.000 | 0.000 | 0.25 / 0.01 / 0.00 | 0.00 | n/a / 0.250 | 0.00 |
| rounds 24/15/12/10 | 5 | greedy | 0.172 ± 0.175 | 0.18 / 0.20 / 0.23 / 0.21 / 0.18 | 0.57 | 50 (50) | 0.42 | 25.4 / 3.34 / 0.00 / 21.2 | 1.62 ± 1.06 | 0.71 ± 1.15 | 0.002 | 0.004 | 0.23 / 0.04 / 0.00 | 0.00 | n/a / 0.200 | 0.00 |

## Rules v2 (#103)

Phase B of #103: sweeps on the Rules v2 changes. All rows use the `score_aware` seating, 500 games per row, run seed **103001**. The full tables are generated by `scripts/tune.py`; below are only the key columns. Advantage is listed per player count; **bold** means it exceeds the 95% margin (±0.088 / ±0.124 / ±0.152 / ±0.175 for 2 / 3 / 4 / 5 players). Shared wins, winning score (mean) and the die columns are the range over 2-5 players. Die games is the share of games with a roll, Rolls/game the rolls per game, and Use rate the share of rolls used (not declined); "-" means no die.

### Sweep `b0`: Rules v1 baseline (the shipped presets)

Command: `uv run python scripts/tune.py --sweep b0`.

Normal:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| shipped (Rules v1) | 0.044 / 0.064 / 0.114 / 0.072 | 0.62-0.65 | 0.62-0.72 | - | - | - |

Flash:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| shipped (Rules v1) | 0.016 / 0.044 / 0.069 / 0.123 | 0.68-0.82 | 0.35-0.59 | - | - | - |

Findings:

- Rules v1 is balanced (no advantage over the margin), but scores are near 0 (winning score 0.35-0.72) and 62-82% of games end in a shared win.

### Sweep `b1`: Rules v2 provisional (old action die cost 2, faces 2/2/2, points 2 / rare 3, scale 1, 2 plots, no cap)

Command: `uv run python scripts/tune.py --sweep b1`.

Normal:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| Rules v2 provisional | 0.020 / 0.086 / **0.169** / **0.212** | 0.36-0.38 | 1.25-1.45 | 0.00-0.03 | 0.00-0.15 | 0.18-1.00 |

Flash:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| Rules v2 provisional | 0.006 / **0.140** / 0.124 / **0.184** | 0.36-0.49 | 0.87-1.15 | 0.00 | 0.00 | 0.00-0.50 |

Findings:

- Shared wins drop to 36-49% and scores rise, but the die is almost never rolled (at most 3% of games), and 4-5p Normal and 3p/5p Flash exceed the margin.

### Sweep `b2`: Score scale x rare bonus

Command: `uv run python scripts/tune.py --sweep b2`.

Normal:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| scale 1, points 2 / rare 3 | 0.020 / 0.086 / **0.169** / **0.212** | 0.36-0.38 | 1.25-1.45 | 0.00-0.03 | 0.00-0.15 | 0.18-1.00 |
| scale 2, points 4 / rare 5 | 0.016 / 0.070 / 0.145 / 0.158 | 0.34-0.37 | 2.24-2.41 | 0.02-0.06 | 0.04-0.79 | 0.16-0.55 |
| scale 2, points 4 / rare 6 | 0.016 / 0.098 / **0.153** / **0.254** | 0.37-0.39 | 2.30-2.54 | 0.03-0.09 | 0.13-0.76 | 0.15-0.54 |
| scale 3, points 6 / rare 7 | 0.026 / 0.078 / **0.164** / 0.153 | 0.36-0.39 | 2.10-3.08 | 0.12-0.23 | 0.47-1.86 | 0.20-0.43 |
| scale 3, points 6 / rare 9 | 0.026 / 0.060 / 0.092 / 0.149 | 0.38-0.44 | 1.79-3.01 | 0.12-0.33 | 0.48-2.04 | 0.31-0.43 |

Flash:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| scale 1, points 2 / rare 3 | 0.006 / **0.140** / 0.124 / **0.184** | 0.36-0.49 | 0.87-1.15 | 0.00 | 0.00 | 0.00-0.50 |
| scale 2, points 4 / rare 5 | 0.006 / **0.134** / 0.152 / **0.211** | 0.37-0.49 | 1.62-2.11 | 0.00-0.03 | 0.01-0.04 | 0.17-0.70 |
| scale 2, points 4 / rare 6 | 0.002 / **0.128** / 0.117 / **0.200** | 0.37-0.49 | 1.72-2.21 | 0.01-0.05 | 0.03-0.07 | 0.29-0.76 |
| scale 3, points 6 / rare 7 | 0.002 / **0.164** / 0.132 / **0.213** | 0.37-0.49 | 2.32-2.97 | 0.04-0.16 | 0.08-0.45 | 0.20-0.29 |
| scale 3, points 6 / rare 9 | 0.002 / **0.164** / 0.077 / **0.188** | 0.40-0.49 | 2.45-2.83 | 0.05-0.25 | 0.08-0.60 | 0.21-0.55 |

Findings:

- A larger scale raises scores and die use (scale 3: die in 12-33% of Normal games) without fixing the 4-5p advantage. Later sweeps use scale 3, rare +1.

### Sweep `b3`: Old action die cost x faces (floodgate/release/resow), and no die

Command: `uv run python scripts/tune.py --sweep b3 --scale 3 --rare-bonus 1`.

Normal:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| cost 0, faces 2/2/2 | 0.010 / 0.043 / 0.023 / 0.051 | 0.43-0.94 | 0.49-2.78 | 1.00 | 8.30-20.02 | 0.15-0.22 |
| cost 0, faces 3/2/1 | 0.034 / 0.036 / 0.015 / 0.073 | 0.43-0.95 | 0.27-2.58 | 1.00 | 8.28-19.08 | 0.13-0.17 |
| cost 1, faces 2/2/2 | 0.024 / 0.046 / 0.127 / 0.075 | 0.37-0.70 | -0.08-2.79 | 0.12-0.73 | 0.83-5.06 | 0.36-0.42 |
| cost 1, faces 3/2/1 | 0.006 / 0.004 / 0.067 / 0.071 | 0.37-0.80 | -0.42-2.64 | 0.12-0.83 | 0.87-5.19 | 0.40-0.46 |
| cost 2, faces 2/2/2 | 0.026 / 0.078 / **0.164** / 0.153 | 0.36-0.39 | 2.10-3.08 | 0.12-0.23 | 0.47-1.86 | 0.20-0.43 |
| cost 2, faces 3/2/1 | 0.006 / 0.041 / 0.092 / 0.120 | 0.37-0.45 | 1.60-2.50 | 0.12-0.34 | 0.64-1.90 | 0.31-0.48 |
| no die (no bribe either) | 0.020 / 0.064 / 0.152 / 0.138 | 0.33-0.37 | 3.46-4.23 | - | - | - |

Flash:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| cost 0, faces 2/2/2 | 0.036 / 0.050 / 0.065 / 0.112 | 0.52-0.75 | 1.04-1.92 | 0.89-1.00 | 2.31-5.05 | 0.14-0.27 |
| cost 0, faces 3/2/1 | 0.026 / 0.022 / 0.075 / 0.104 | 0.53-0.82 | 0.74-1.82 | 0.89-1.00 | 2.06-4.77 | 0.11-0.32 |
| cost 1, faces 2/2/2 | 0.014 / 0.105 / 0.044 / 0.135 | 0.46-0.52 | 1.75-2.32 | 0.05-0.62 | 0.16-1.37 | 0.22-0.48 |
| cost 1, faces 3/2/1 | 0.010 / 0.086 / 0.057 / 0.105 | 0.49-0.81 | 0.80-2.12 | 0.05-0.70 | 0.20-1.76 | 0.44-0.52 |
| cost 2, faces 2/2/2 | 0.002 / **0.164** / 0.132 / **0.213** | 0.37-0.49 | 2.32-2.97 | 0.04-0.16 | 0.08-0.45 | 0.20-0.29 |
| cost 2, faces 3/2/1 | 0.002 / **0.145** / 0.067 / **0.183** | 0.43-0.51 | 2.08-2.36 | 0.05-0.27 | 0.14-0.69 | 0.35-0.56 |
| no die (no bribe either) | 0.006 / 0.122 / 0.147 / **0.208** | 0.36-0.49 | 2.39-3.23 | - | - | - |

Findings:

- Cost 0 or 1: the die is used, but it is destructive. At 3-5 players shared wins reach 67-95% and winning scores fall to about 0 (negative at cost 1).
- Cost 2: the die is rarely used (12-34% of games, at most 1.9 rolls per game), so it adds little over no die.

### Sweep `b4`: Vineyard plots and board (distance 4)

Command: `uv run python scripts/tune.py --sweep b4`. Scale 1, rare +1.

Normal:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| 2 plots, 15 hexes/player, cap none | 0.020 / 0.086 / **0.169** / **0.212** | 0.36-0.38 | 1.25-1.45 | 0.00-0.03 | 0.00-0.15 | 0.18-1.00 |
| 2 plots, 15 hexes/player, cap 2 | 0.020 / 0.083 / **0.161** / **0.185** | 0.36-0.38 | 1.23-1.45 | 0.00-0.02 | 0.00-0.13 | 0.08-0.22 |
| 2 plots, 18 hexes/player, cap none | 0.032 / 0.083 / 0.101 / 0.141 | 0.29-0.35 | 1.42-1.63 | 0.00-0.02 | 0.00-0.12 | 0.24-1.00 |
| 2 plots, 18 hexes/player, cap 2 | 0.032 / 0.086 / 0.095 / 0.113 | 0.29-0.34 | 1.40-1.61 | 0.00-0.03 | 0.00-0.18 | 0.11-1.00 |
| 3 plots, 15 hexes/player, cap none | 0.006 / 0.083 / **0.165** / **0.213** | 0.27-0.41 | 1.15-1.72 | 0.00-0.05 | 0.00-0.18 | 0.22-0.75 |
| 3 plots, 15 hexes/player, cap 2 | 0.006 / 0.077 / **0.163** / **0.233** | 0.27-0.41 | 1.13-1.71 | 0.00-0.05 | 0.00-0.12 | 0.00-0.56 |
| 3 plots, 18 hexes/player, cap none | **0.094** / 0.016 / **0.242** / 0.175 | 0.26-0.32 | 1.55-1.96 | 0.00-0.06 | 0.00-0.28 | 0.32-1.00 |
| 3 plots, 18 hexes/player, cap 2 | **0.090** / 0.014 / **0.231** / 0.157 | 0.27-0.32 | 1.52-1.95 | 0.00-0.04 | 0.00-0.26 | 0.23-0.54 |

Flash:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| 2 plots | 0.006 / **0.140** / 0.124 / **0.184** | 0.36-0.49 | 0.87-1.15 | 0.00 | 0.00 | 0.00-0.50 |
| 3 plots | infeasible | | | | | |

Findings:

- 2 plots on 18 hexes per player is the best balance (every player count inside the margin).
- 3 plots is unbalanced at 4-5 players (and at 2 players on 18 hexes), and infeasible in Flash (not enough hexes at distance 4).
- The cap of 2 changes little. The bodega rate is under 1% in every row.

### Sweep `b3b`: Constructive die (floodgate/release/resow x2/good season/drought) x cost x season roll every X rounds, and no die

Command: `uv run python scripts/tune.py --sweep b3b --scale 3 --rare-bonus 1`.

Normal:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| constructive die, cost 1, season roll every 2 | 0.028 / 0.096 / **0.165** / 0.139 | 0.39-0.52 | 6.25-7.19 | 1.00 | 5.40-7.87 | 0.44-0.48 |
| constructive die, cost 1, season roll every 3 | 0.050 / **0.287** / **0.171** / **0.231** | 0.38-0.46 | 4.69-6.24 | 1.00 | 3.39-5.98 | 0.44-0.49 |
| constructive die, cost 1, season roll every 4 | 0.016 / **0.150** / **0.177** / 0.134 | 0.37-0.45 | 4.55-5.56 | 1.00 | 2.37-4.66 | 0.45-0.50 |
| constructive die, cost 2, season roll every 2 | 0.028 / 0.097 / **0.209** / 0.148 | 0.39-0.50 | 6.31-7.13 | 1.00 | 5.06-7.43 | 0.43-0.48 |
| constructive die, cost 2, season roll every 3 | 0.036 / **0.314** / **0.205** / **0.208** | 0.38-0.42 | 4.71-6.27 | 1.00 | 3.05-5.47 | 0.42-0.48 |
| constructive die, cost 2, season roll every 4 | 0.012 / **0.149** / **0.183** / 0.164 | 0.37-0.41 | 4.43-5.34 | 1.00 | 2.06-3.51 | 0.43-0.48 |
| no die (no bribe either) | 0.020 / 0.064 / 0.152 / 0.138 | 0.33-0.37 | 3.46-4.23 | - | - | - |

Flash:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| constructive die, cost 1, season roll every 2 | 0.000 / 0.123 / 0.126 / **0.265** | 0.36-0.51 | 3.69-4.83 | 1.00 | 2.07-3.33 | 0.37-0.42 |
| constructive die, cost 2, season roll every 2 | 0.000 / 0.113 / 0.134 / **0.260** | 0.36-0.50 | 3.73-4.77 | 1.00 | 2.02-3.20 | 0.36-0.41 |
| no die (no bribe either) | 0.006 / 0.122 / 0.147 / **0.208** | 0.36-0.49 | 2.39-3.23 | - | - | - |

Findings:

- The constructive die is rolled in 100% of games and roughly doubles the mean score over no die.
- The season roll gave a seat bias when gcd(X, P) > 1 (e.g. every 3 at 3p: advantage 0.29-0.31; every 2 at 4p). Fixed in #132: the season die passes to the next seat.

### Sweep `b5`: Best Normal board (2 plots, 18 hexes per player) x constructive die x cost x season roll every X rounds, and no die

Command: `uv run python scripts/tune.py --sweep b5 --scale 3 --rare-bonus 1`.

Normal:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| constructive die, cost 1, season roll every 3 | 0.042 / 0.089 / 0.112 / 0.141 | 0.35-0.42 | 5.59-6.28 | 1.00 | 3.39-5.97 | 0.45-0.51 |
| constructive die, cost 1, season roll every 4 | 0.008 / **0.139** / 0.111 / 0.091 | 0.33-0.39 | 5.15-5.62 | 1.00 | 2.39-4.31 | 0.47-0.53 |
| constructive die, cost 2, season roll every 3 | 0.046 / 0.094 / 0.119 / 0.107 | 0.36-0.41 | 5.46-6.25 | 1.00 | 3.03-5.34 | 0.42-0.49 |
| constructive die, cost 2, season roll every 4 | 0.010 / **0.145** / **0.164** / 0.129 | 0.32-0.37 | 5.04-5.56 | 1.00 | 2.02-3.57 | 0.42-0.51 |
| no die (no bribe either) | 0.032 / 0.088 / 0.086 / 0.136 | 0.28-0.34 | 4.02-4.75 | - | - | - |

Flash:

| Candidate | Advantage 2p / 3p / 4p / 5p | Shared wins | Winning score | Die games | Rolls/game | Use rate |
| --- | --- | --- | --- | --- | --- | --- |
| constructive die, cost 1, season roll every 2 | 0.026 / **0.152** / 0.113 / **0.232** | 0.37-0.51 | 3.66-4.96 | 1.00 | 2.07-3.34 | 0.38-0.42 |
| constructive die, cost 1, season roll every 3 | 0.002 / **0.252** / 0.117 / **0.183** | 0.34-0.49 | 3.28-3.99 | 1.00 | 1.08-2.36 | 0.37-0.43 |
| constructive die, cost 2, season roll every 2 | 0.026 / **0.145** / 0.116 / **0.227** | 0.37-0.50 | 3.68-4.84 | 1.00 | 2.03-3.20 | 0.37-0.41 |
| constructive die, cost 2, season roll every 3 | 0.002 / **0.208** / 0.116 / **0.181** | 0.34-0.49 | 3.33-4.01 | 1.00 | 1.03-2.21 | 0.35-0.42 |
| no die (no bribe either) | 0.006 / 0.122 / 0.147 / **0.208** | 0.36-0.49 | 2.39-3.23 | - | - | - |

Findings:

- Normal: cost 2, season every 3 is inside the margin at every player count (cost 1 every 3 too).
- Flash: every 2 is the better choice. Every 3 is biased at 3p because only about 2 rolls happen per game. The 3p/5p Flash advantage is already near or over the margin without the die.

### Phase C candidates

All use scale 3 and rare +1.

| Candidate | Die | Season roll | Board (Normal) |
| --- | --- | --- | --- |
| A | constructive, cost 2 | every 3 rounds (Normal), every 2 (Flash) | 2 plots, 18 hexes per player |
| B | constructive, cost 1 | every 3 rounds (Normal), every 2 (Flash) | 2 plots, 18 hexes per player |
| C | no die | - | 2 plots, 18 hexes per player |

Open: the bodega threshold (the bodega rate is under 1% in every sweep).

### Phase C: lookahead spot checks (A, B, C)

Script `output/tuning-103/phase-c.sh`, one run per candidate and mode:
`uv run python scripts/tune.py --candidate b5 "<candidate>" --mode <mode> --seating lookahead --games 100 --scale 3 --rare-bonus 1 --workers 3`.
100 games per row, seed 103002. The 95% margin is ±0.196 / 0.277 / 0.339 / 0.392 at 2p / 3p / 4p / 5p. The die is rolled in 100% of games with A and B.

| Mode | Candidate | Advantage 2p / 3p / 4p / 5p | At most 0.10 | Shared wins | Winning score | Die use rate | Bodega rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Normal | A (cost 2) | 0.010 / 0.090 / 0.220 / 0.175 | 2p, 3p | 0.32-0.46 | 5.51-7.12 | 0.56-0.60 | 0.000-0.015 |
| Normal | B (cost 1) | 0.030 / 0.030 / 0.163 / 0.154 | 2p, 3p | 0.33-0.50 | 5.05-7.03 | 0.57-0.61 | 0.000-0.015 |
| Normal | C (no die) | 0.130 / 0.045 / 0.150 / 0.335 | 3p | 0.20-0.49 | 3.92-6.28 | - | 0.002-0.035 |
| Flash | A (cost 2) | 0.040 / 0.225 / 0.140 / 0.297 | 2p | 0.40-0.52 | 3.82-5.37 | 0.47-0.53 | 0.000-0.005 |
| Flash | B (cost 1) | 0.050 / 0.190 / 0.147 / 0.297 | 2p | 0.41-0.54 | 3.63-5.10 | 0.48-0.54 | 0.000-0.007 |
| Flash | C (no die) | 0.100 / 0.285 / 0.230 / 0.170 | none | 0.34-0.56 | 2.57-4.68 | - | 0.000-0.015 |

Findings:

- The die is in play in every game, and lookahead uses 56-61% of its Normal rolls (47-54% in Flash) instead of declining them.
- Winning scores are higher with the die (Normal 5.1-7.1 vs 3.9-6.3 without; Flash 3.6-5.4 vs 2.6-4.7).
- 100 games per row cannot separate A and B: their margins are wider than the gap between them.
- The owner picked B (cost 1) for phase D.

### Phase D: candidate B with multiple bodegas

Script `output/tuning-103/phase-d.sh`, one run per mode and bot:
`uv run python scripts/tune.py --scale 3 --rare-bonus 1 --multiple-bodegas --workers 3 --candidate b5 "<B for the mode>" --mode <mode> --seating <bot>`,
plus `--games 500` for lookahead. score_aware and greedy use the final validation counts (margin ±0.044 / 0.049 / 0.049 / 0.049); lookahead uses 500 games per configuration (margin ±0.088 / 0.124 / 0.152 / 0.175). Seed 103002. The die is rolled in 100% of games.

| Mode | Bot | Advantage 2p / 3p / 4p / 5p | At most 0.10 | Shared wins | Winning score | Rolls/game | Die use rate | Bodega rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Normal | score_aware | 0.028 / 0.041 / 0.070 / **0.136** | 2p-4p | 0.37-0.41 | 5.49-6.48 | 3.32-6.13 | 0.46-0.51 | 0.001-0.002 |
| Normal | greedy | 0.052 / 0.065 / 0.050 / 0.068 | all | 0.43-0.60 | 4.84-8.07 | 3.00-5.00 | 0.48-0.62 | 0.003-0.009 |
| Normal | lookahead | 0.028 / 0.153 / 0.148 / 0.123 | 2p | 0.35-0.51 | 5.34-6.53 | 3.41-5.81 | 0.61-0.63 | 0.000-0.006 |
| Flash | score_aware | 0.008 / 0.049 / **0.173** / **0.142** | 2p, 3p | 0.38-0.49 | 3.99-4.93 | 2.08-3.27 | 0.39-0.43 | 0.000-0.001 |
| Flash | greedy | 0.027 / 0.058 / **0.226** / **0.210** | 2p, 3p | 0.51-0.61 | 4.06-6.56 | 2.00-3.00 | 0.41-0.50 | 0.001-0.004 |
| Flash | lookahead | 0.150 / 0.178 / **0.261** / **0.365** | none | 0.43-0.55 | 3.69-5.15 | 2.03-3.19 | 0.52-0.56 | 0.001-0.003 |

Findings:

- Normal: score_aware passes at 2p-4p and fails at 5p (0.136 ± 0.049); greedy passes at every player count. Lookahead's 3p-5p values are over 0.10 but inside their wider margins.
- Flash: 4p and 5p fail with every bot (0.14-0.37).
- Root cause hypothesis: fewer season rolls than players. Normal has 5 / 4 / 3 rolls at 3p / 4p / 5p (5p: 10 rounds / every 3 = 3 rolls); Flash 4p-5p has 4 rounds / every 2 = 2 rolls. With fewer rolls than seats, some seats never get the season roll's personal face.
- The bodega rate stays under 4% (under 1% in phase D) even with multiple bodegas.
- Verdict: B is not ready to ship, and #126 waits for a fix. Options for the owner: the season roll applies only good season or drought, or set X (season roll every X rounds) per player count.

### Phase D re-run: candidate B, season roll applies only good season or drought

The owner's fix for phase D (option 1, #138): a season roll applies only good season or drought; a personal face on a season roll does nothing. Script `output/tuning-103/phase-d2.sh`: the phase D commands plus `--season-global-only`. Same seeds, game counts, and margins as phase D.

| Mode | Bot | Advantage 2p / 3p / 4p / 5p | At most 0.10 | Shared wins | Winning score | Rolls/game | Die use rate | Bodega rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Normal | score_aware | 0.022 / 0.011 / 0.054 / **0.114** | 2p-4p | 0.32-0.35 | 5.61-6.95 | 3.32-6.13 | 0.87-0.97 | 0.000-0.002 |
| Normal | greedy | 0.024 / 0.061 / 0.107 / 0.106 | 2p, 3p | 0.36-0.47 | 5.30-9.25 | 3.00-5.00 | 1.00 | 0.005-0.013 |
| Normal | lookahead | 0.032 / 0.284 / 0.177 / 0.107 | 2p | 0.31-0.43 | 5.58-7.07 | 3.45-5.80 | 0.94-0.98 | 0.000-0.011 |
| Flash | score_aware | 0.026 / 0.081 / **0.169** / **0.143** | 2p, 3p | 0.35-0.48 | 4.10-5.16 | 2.08-3.27 | 0.97-0.99 | 0.000-0.001 |
| Flash | greedy | 0.016 / 0.063 / **0.188** / **0.231** | 2p, 3p | 0.43-0.55 | 4.26-7.13 | 2.00-3.00 | 1.00 | 0.002-0.006 |
| Flash | lookahead | 0.160 / 0.114 / **0.303** / **0.378** | none | 0.35-0.53 | 3.88-5.37 | 2.05-3.24 | 0.98-1.00 | 0.000-0.003 |

The die use rate is now near 1 because a season roll can no longer be declined.

Findings:

- Normal improves at 3p-4p with score_aware (0.011 / 0.054), but 5p is still just over the line (0.114 ± 0.049). Greedy 4p-5p (0.107 / 0.106) and lookahead 5p (0.107) are just over 0.10 and inside their margins.
- Flash 4p and 5p still fail with every bot. The last seat wins most (4p: 0.29-0.33; 5p seat 4 or 5: 0.22-0.28).
- The season-roll hypothesis does not explain the Flash failure. In sweep `b5`, Flash with no die was already biased at 4p-5p (0.147 / 0.208), and so was Normal 5p (0.136). The bias comes from the short game (Flash 4p-5p is 4 rounds, with almost no passes), not from the die.
- Verdict: B is still not ready to ship, and #126 still waits. Normal 2p-4p is ready; Flash 4p-5p and Normal 5p need a structural fix, a turn-order compensation, for example.

### Phase E: Flash turn-order fixes for candidate B (#142)

Script `output/tuning-103/phase-e.sh`: the phase D re-run command for Flash plus `--seat-bonus` or `--rounds`. Final validation counts, seed 103002. Baseline is the phase D re-run.

| Fix | Bot | Advantage 4p / 5p | Win rate by position 4p | Win rate by position 5p |
| --- | --- | --- | --- | --- |
| none (baseline) | score_aware | 0.169 / 0.143 | 0.27 / 0.24 / 0.21 / 0.29 | 0.21 / 0.19 / 0.17 / 0.22 / 0.22 |
| none (baseline) | greedy | 0.188 / 0.231 | 0.23 / 0.24 / 0.23 / 0.30 | 0.18 / 0.18 / 0.18 / 0.25 / 0.22 |
| +1 to seat 0 | score_aware | **1.423** / **1.619** | 0.61 / 0.11 / 0.11 / 0.18 | 0.52 / 0.10 / 0.10 / 0.14 / 0.14 |
| +1 to seat 0 | greedy | **0.877** / **0.827** | 0.47 / 0.16 / 0.16 / 0.21 | 0.37 / 0.12 / 0.13 / 0.21 / 0.17 |
| +1 to all but the final-round starter (4p: 1,1,1,0; 5p: 1,1,1,0,0) | score_aware | **0.700** / **0.624** | 0.34 / 0.30 / 0.29 / 0.07 | 0.30 / 0.27 / 0.25 / 0.08 / 0.10 |
| +1 to all but the final-round starter | greedy | **0.546** / **0.333** | 0.29 / 0.29 / 0.30 / 0.11 | 0.24 / 0.23 / 0.26 / 0.14 / 0.13 |
| 5 rounds at 4p-5p | score_aware | **0.165** / **0.235** | 0.29 / 0.25 / 0.21 / 0.25 | 0.21 / 0.19 / 0.16 / 0.19 / 0.25 |
| 5 rounds at 4p-5p | greedy | 0.055 / **0.137** | 0.24 / 0.25 / 0.25 / 0.26 | 0.18 / 0.19 / 0.20 / 0.21 / 0.23 |

Findings:

- A 1-point seat bonus overshoots by far. Flash scores are low and lumpy (winning score about 4-5, many ties), so 1 point mostly breaks ties and flips the bias to the bonus seats. The final-round starter's real edge is well under 1 point.
- 5 rounds fixes greedy 4p (0.055) but not score_aware 4p or 5p, and 5p (25 minutes) leaves the length target.
- Verdict: no fix passes. #126 still waits.

### Phase F: tiebreak against the final-round starter

Script `output/tuning-103/phase-f.sh`. Scale 6, rare +2, and die cost 2 double every score and cost of candidate B, so every score is even and a +1 seat bonus only breaks ties. The bonus goes to every seat except the one that starts the final round (Flash 4p: 1,1,1,0; 5p: 1,1,1,0,0; Normal 5p: 1,1,1,1,0). Final validation counts, seed 103002.

| Run | Bot | Advantage | Win rate by position | Shared wins |
| --- | --- | --- | --- | --- |
| Flash x2, no bonus | score_aware | 4p 0.169 / 5p 0.143 | same as the phase D re-run | 0.39 / 0.38 |
| Flash x2, no bonus | greedy | 4p 0.188 / 5p 0.231 | same as the phase D re-run | 0.55 / 0.48 |
| Flash x2, tiebreak | score_aware | 4p **0.694** / 5p **0.614** | 4p 0.34 / 0.30 / 0.29 / 0.08 | 0.38 / 0.35 |
| Flash x2, tiebreak | greedy | 4p **0.534** / 5p **0.331** | 4p 0.29 / 0.29 / 0.30 / 0.12 | 0.35 / 0.33 |
| Normal 5p x2, tiebreak | score_aware | **0.589** | 0.25 / 0.24 / 0.22 / 0.21 / 0.08 | 0.28 |
| Normal 5p x2, tiebreak | greedy | **0.454** | 0.20 / 0.21 / 0.22 / 0.25 / 0.11 | 0.28 |

Findings:

- Doubling every value gives the same results as candidate B (x2, no bonus), so the doubling is a fair stand-in.
- A tiebreak alone gives the same numbers as phase E's +1 bonus: at scale 3, +1 was already acting as a tiebreak. Ties are so frequent (shared wins 0.33-0.55) that any rule that picks a side among tied players overshoots.
- Verdict: compensation by points or tiebreak cannot be tuned finely enough. The remaining options are fewer ties (more scoring in short games) or limiting Flash to 2-3 players.

## Rules v3 (#149)

Overnight run, `score_aware` seating. Raw output: `output/tuning-149/night1.md` (sweeps `strip` and `v3`, 500 games per row, seeds 154001 and 153001) and `night2-4p.md` / `night2-5p.md` (sweep `v3` at 4p and 5p, 2000 games per row). Base: river strip with 5 river hexes per segment, bag 16 pieces per player, shipped Rules v2 values. The quality target is a turn-order advantage of at most 0.10.

### Sweep `strip`: river hexes per segment x bag size (500 games)

- 2p and Flash 2p are within the margin at every setting (0.01-0.14 ± 0.09).
- 3p sits at 0.06-0.29 ± 0.12; no setting is clearly better.
- 4p (0.16-0.33 ± 0.15) and 5p (0.19-0.45 ± 0.18) fail at every setting.
- River hexes and bag size barely change game flow: about 7 vineyards planted per player at 2p, 11 at 3p, 9 at 4p and 7.5 at 5p; bodega rate 0.79-0.86 at 2p, above 0.93 at 3-5p, about 0.65 in Flash.
- Passes almost never happen (at most 0.6 per game, with 4 river hexes).

### Sweep `v3`: one value at a time (Normal 4p and 5p, 2000 games)

| Candidate | 4p advantage ± 0.076 | 4p win rate by position | 5p advantage ± 0.088 | 5p win rate by position |
| --- | --- | --- | --- | --- |
| base | **0.207** | 0.24 / 0.25 / 0.30 / 0.20 | **0.365** | 0.17 / 0.20 / 0.24 / 0.26 / 0.13 |
| rounds -4 | **0.250** | 0.23 / 0.26 / 0.31 / 0.20 | **0.214** | 0.16 / 0.17 / 0.20 / 0.24 / 0.24 |
| rounds -2 | **0.277** | 0.32 / 0.19 / 0.22 / 0.27 | **0.310** | 0.25 / 0.26 / 0.14 / 0.16 / 0.19 |
| rounds +2 | **0.254** | 0.30 / 0.19 / 0.23 / 0.27 | **0.282** | 0.26 / 0.15 / 0.17 / 0.19 / 0.23 |
| die cost 0 | **0.275** | 0.25 / 0.26 / 0.31 / 0.18 | **0.324** | 0.16 / 0.22 / 0.25 / 0.24 / 0.14 |
| die cost 2 | **0.239** | 0.24 / 0.27 / 0.30 / 0.19 | **0.372** | 0.17 / 0.21 / 0.23 / 0.27 / 0.13 |
| points 2 / rare 3 | **0.202** | 0.22 / 0.28 / 0.30 / 0.20 | **0.304** | 0.17 / 0.20 / 0.24 / 0.25 / 0.14 |
| points 4 / rare 5 | **0.198** | 0.23 / 0.27 / 0.30 / 0.20 | **0.375** | 0.17 / 0.20 / 0.24 / 0.27 / 0.12 |
| points 6 / rare 9 | **0.265** | 0.22 / 0.27 / 0.32 / 0.19 | **0.320** | 0.16 / 0.19 / 0.24 / 0.26 / 0.14 |
| bodega 3 | **0.231** | 0.24 / 0.27 / 0.30 / 0.19 | **0.291** | 0.18 / 0.21 / 0.24 / 0.23 / 0.14 |
| bodega 9 | **0.241** | 0.24 / 0.25 / 0.31 / 0.19 | **0.385** | 0.18 / 0.20 / 0.24 / 0.26 / 0.12 |
| bodega 12 | **0.232** | 0.23 / 0.26 / 0.31 / 0.20 | **0.350** | 0.17 / 0.19 / 0.25 / 0.26 / 0.13 |
| resow can move | **0.218** | 0.23 / 0.26 / 0.30 / 0.20 | **0.340** | 0.16 / 0.20 / 0.25 / 0.26 / 0.13 |
| 4 river hexes/segment | **0.300** | 0.24 / 0.28 / 0.30 / 0.17 | **0.264** | 0.17 / 0.19 / 0.24 / 0.25 / 0.15 |
| 6 river hexes/segment | **0.208** | 0.25 / 0.27 / 0.28 / 0.20 | **0.363** | 0.18 / 0.21 / 0.23 / 0.25 / 0.13 |
| bag 12/player | **0.156** | 0.24 / 0.26 / 0.29 / 0.21 | **0.317** | 0.17 / 0.19 / 0.23 / 0.26 / 0.14 |
| bag 20/player | **0.185** | 0.24 / 0.27 / 0.29 / 0.20 | **0.291** | 0.18 / 0.20 / 0.24 / 0.25 / 0.14 |

At 2p, 3p and Flash (500 games), every candidate stays near the base: 2p 0.02-0.12, 3p 0.04-0.23, Flash 0.02-0.15. Rounds -4 makes Flash too short (bodega rate 0.01) and drops the 5p bodega rate to 0.67.

### Findings

- Rules v3 plays well at 2p and 3p and in Flash: low advantage, almost no passes, frequent bodegas, and games of 20 (2p), 45 (3p) and 12-18 (Flash) turns.
- At 4p and 5p the advantage is structural. Seat 2 leads at 4p and seat 3 at 5p, and the last seat trails (0.20 at 4p, 0.13 at 5p). No single value fixes it: die cost, varietal points, bodega points, resow moving a vineyard, river hexes and bag size leave the pattern in place.
- Only the round count moves the pattern, and it does so non-monotonically (rounds -2 and +2 both favour seat 0), so a round count alone is not a fix. The cause needs a diagnosis (seat-to-segment layout, bag exhaustion near the end, or the final turns) before more tuning.
- Verdict: no value change is proposed yet. The base (5 river hexes, bag 16, Rules v2 values) stays the reference for 2-3p and Flash; 4-5p wait for the diagnosis.

## Rules v3 split scoring (#160)

Sweep `v3split`, `score_aware`, 500 games per row, raw output `output/tuning-160/v3split.md` (4.5 h at 4 workers). Four setups: planting on any vertex or only between three canals (`vertex_needs_three_canals`), x the new die with Move or the old die (two Resow faces). Each has a base (5 river hexes, bag 16, bodega 6 / 3 Flash, shipped rounds) and one value changed at a time.

### Base rows

| Setup | Advantage 2p / 3p / 4p / 5p (± 0.09 / 0.12 / 0.15 / 0.18) | Planted per player 2p / 3p / 4p / 5p | Winning score 2p / 3p / 4p / 5p | Bodega rate 2p / 3p / 4p / 5p |
| --- | --- | --- | --- | --- |
| any vertex, Move die | 0.102 / 0.193 / **0.392** / **0.525** | 6.2 / 9.5 / 7.1 / 5.8 | 30 / 51 / 43 / 37 | 0.87 / 0.98 / 0.98 / 0.97 |
| any vertex, old die | 0.008 / 0.065 / **0.336** / **0.620** | 6.3 / 9.7 / 7.3 / 5.8 | 32 / 53 / 45 / 37 | 0.89 / 0.97 / 0.98 / 0.97 |
| 3 canals, Move die | 0.044 / 0.038 / **0.267** / **0.265** | 2.4 / 4.6 / 4.0 / 3.2 | 16 / 34 / 34 / 29 | 0.52 / 0.84 / 0.91 / 0.87 |
| 3 canals, old die | 0.058 / 0.145 / **0.202** / **0.320** | 2.4 / 4.6 / 4.0 / 3.2 | 16 / 33 / 33 / 29 | 0.52 / 0.82 / 0.91 / 0.84 |

Flash (2p / 3p): any vertex 0.10-0.14 / 0.14-0.25, about 3.3 vineyards per player, winning score about 14, bodega rate 0.65-0.72. Three canals leaves Flash with about 1.1 vineyards per player and a bodega rate under 0.25.

### Findings

- Split scoring keeps 2-3p near the target and leaves the 4-5p seat bias in place (0.34-0.62 on any vertex). No single value fixes it: bag 20/24, 6 river hexes, bodega 3/9 and rounds -2/+2 all stay above 0.2 at 4-5p. The diagnosis moves to #163.
- Three canals lowers the 4-5p advantage (0.20-0.32) but halves planting (about 4 vineyards per player in Normal, 1 in Flash) and halves winning scores. It makes Flash unplayable. Verdict: keep planting on any vertex.
- The Move die and the old die are within the margin of each other. Keep the Move die (owner's choice).
- Bag size (16/20/24) and river hexes (5/6) change nothing measurable: keep bag 16 and 5 river hexes per segment.
- Winning scores (any vertex) are about 30 / 51 / 43 / 37 in Normal 2-5p and 14 in Flash: the reference for a `score_target` end (#163), before blends and bodega buildings (#166) raise them.
- Floodgates: about 3 placed per game at 2p and 8 at 3-5p; the most on the table at once averages 2-4, with a maximum of 9-19 in a game. A physical supply of 12-15 floodgates is enough for nearly all games; to recheck once floodgates become optional (#168).

## Rules v3 cortes and bodega building (#166)

Sweep `v3blends`, `score_aware`, 500 games per row, raw output `output/tuning-166/v3blends.md` (4.2 h at 4 workers). Base: the `v3split` best setup (any-vertex planting, move die, 5 river hexes, bag 16). Candidates: the old bodega bonus, cortes `each_once` or `disjoint`, and cortes `each_once` plus the bodega building (12 or 15 points, 2 reds + 2 or 1 whites), each at points x0.5 / x1 / x1.5.

Normal, x1 (advantage at 2p / 3p / 4p / 5p; winning score at 4p):

| Candidate | Advantage | Win 4p | Requirement met 3p / 4p | Builders 4p |
| --- | --- | --- | --- | --- |
| old bodega 6 | 0.012 / 0.211 / 0.292 / 0.403 | 44.0 | - | - |
| cortes each_once | 0.026 / 0.160 / 0.444 / 0.525 | 36.9 | - | - |
| cortes disjoint | 0.028 / 0.223 / 0.348 / 0.575 | 29.2 | - | - |
| + building 12, 2R + 2W | 0.014 / 0.125 / 0.388 / 0.550 | 37.9 | 0.64 / 0.45 | 0.17 |
| + building 12, 2R + 1W | 0.020 / 0.142 / 0.468 / 0.558 | 38.4 | 0.97 / 0.93 | 0.43 |
| + building 15, 2R + 2W | 0.008 / 0.218 / 0.373 / 0.515 | 38.7 | 0.63 / 0.45 | 0.17 |
| + building 15, 2R + 1W | 0.036 / 0.166 / 0.544 / 0.450 | 40.7 | 0.97 / 0.92 | 0.43 |

Flash, x1, building 12: the requirement is met by 7% of players with 2 whites and 44% with 1 white (about a quarter build).

- Seat bias: no candidate fixes 4-5p; every row is above 0.2 there, with a 95% margin of ±0.15 to ±0.18. Differences between candidates at 4-5p are within noise. 2p passes everywhere and 3p is near the line
- Requirement: 2 reds + 2 whites is met too rarely (45% at 4p, 7% in Flash), so the requirement drops to 2 reds + 1 white, as the owner allowed. The bodega is then reachable for nearly every player in Normal
- Cortes: `each_once` scores about twice `disjoint` (8.7 vs 4.6 points per player at 4p) and keeps the most common cortes alive; `each_once` stays
- Building points: 12 and 15 are within noise; 12 keeps the building one of several goals rather than the main one
- Points x1.5 inflates winning scores (49 at 4p) without changing bias; x1 stays

Decision: `v3_best_base` moves to cortes `each_once` x1 plus the bodega building at 12 points with 2 reds + 1 white. The sweeps `v3bribe` (#168) and `v3end` (#163) run on it. The shipped presets are unchanged.

## Rules v3 optional floodgate faces (#168)

Sweep `v3bribe`, `score_aware`, 500 games per row, raw output `output/tuning-168/v3bribe.md` (3.1 h at 8 workers). Base: the #166 best setup. Candidates: the floodgate and release faces mandatory (the bribe paid on every roll of them) or optional (`bribe_optional`, paid only when used), x the bribe 1 / 2 / 3 / 4 / 6.

Normal, 3p / 4p:

| Candidate | Advantage | Winning score | Floodgate rolls used | Swing per use | Bribe paid per player |
| --- | --- | --- | --- | --- | --- |
| mandatory 1 | 0.185 / 0.416 | 44.0 / 39.4 | 0.81 / 0.81 | 2.2 / 0.3 | 5.0 / 4.0 |
| mandatory 3 | 0.229 / 0.488 | 35.9 / 30.5 | 0.81 / 0.81 | 2.3 / 0.2 | 15.1 / 12.0 |
| mandatory 6 | 0.191 / 0.460 | 21.7 / 19.5 | 0.81 / 0.81 | 2.1 / 0.3 | 30.0 / 24.2 |
| optional 1 | 0.239 / 0.448 | 43.6 / 38.0 | 0.61 / 0.54 | 4.5 / 2.3 | 3.1 / 2.2 |
| optional 2 | 0.260 / 0.480 | 41.4 / 36.4 | 0.55 / 0.46 | 4.8 / 2.5 | 5.5 / 3.7 |
| optional 3 | 0.238 / 0.624 | 40.0 / 35.5 | 0.50 / 0.40 | 5.0 / 2.6 | 7.5 / 4.9 |
| optional 4 | 0.226 / 0.496 | 39.9 / 36.2 | 0.43 / 0.33 | 5.8 / 3.0 | 8.6 / 5.3 |
| optional 6 | 0.263 / 0.520 | 38.7 / 36.2 | 0.33 / 0.23 | 6.6 / 3.4 | 10.0 / 5.6 |

Flash 3p, optional: floodgate rolls used 0.42 / 0.35 / 0.29 / 0.20 / 0.12 at bribe 1 / 2 / 3 / 4 / 6, swing per use 1.4 to 3.1.

- Seat bias: unchanged by either switch; 2p passes everywhere, 4-5p fails everywhere, all within noise
- Mandatory faces are a tax: bots pay on about 81% of floodgate rolls for a swing of 0.2-0.3 points at 4p, so a higher bribe only lowers every score (winning score 39 to 20 at 4p from bribe 1 to 6)
- Optional faces turn the floodgate into a decision: use falls as the bribe rises and the swing per use grows, so a floodgate is placed only when it pays
- Bribe 2 in Normal keeps floodgates in about half of the rolls (4 on the board at once, at most 10-11) and a swing above the bribe at 3p; bribe 3 or more makes them rare at 4-5p (40% or less). Flash has fewer points per vineyard, so bribe 1 keeps the swing (1.4) above the bribe; at bribe 2 the swing per use (1.5) is barely above it
- A supply of 12 floodgates is enough at every count

Decision: `v3_best_base` moves to optional floodgate faces with bribe 2 in Normal and 1 in Flash (`V3_BEST_BRIBE`). The sweep `v3end` (#163) runs on it. The shipped presets are unchanged.

## Rules v3 seat bias and end conditions (#163)

Sweep `v3end`, `score_aware`, 500 games per row, seed 163001, around `v3_best_base` (the best #160/#166/#168 setup in `scripts/tune.py`): `uv run python scripts/tune.py --sweep v3end`. Rows: the base; seats rotated and shuffled per game; an unlimited bag; `bag_empty`, `vineyards_out` (default markers 6 / 9 / 7 / 6, Flash 3) and `score_target` (#160's winning scores x1 / x1.5 / x2), each with `finish_round` on and off. Games whose trigger never fires end after twice the shipped rounds, and the table reports their share.

Status: the full run is for an overnight run on request; the numbers and the verdict (which option removes the seat bias, which end condition keeps the length near today's) go here then. A 10-game smoke run (Flash 2p) only checks the runner, but it already shows three things that do not depend on the sample:

- The river strip has no segment owned by a seat, and the bots are the same in every seat, so rotating or shuffling the seats plays the same games by position (identical rows by position, different by seat). The bias follows the turn position, not the seat; the seat rows are a control.
- The bag rarely runs out: a 4p Normal game of the base left 41 of 64 pieces in the bag after 12 rounds, so `bag_empty` mostly ends by the cap and the unlimited bag is expected to change little.
- Flash with 3 vineyard markers never builds a bodega (2 reds + 2 whites need 4 vineyards), so `vineyards_out` needs more Flash markers if the building stays.
