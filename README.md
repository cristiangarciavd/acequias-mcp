# Acequias MCP

Acequias is a competitive board game for 2 to 5 players with 3D-printed hex pieces. Players build canals to carry water from the mountains to the vineyards of Mendoza. This repo holds an MCP server that generates balanced boards, scores games, simulates them with bots to tune the rules, and outputs printable STL pieces for a Bambu Lab A1.

> **Status:** early development. The rules and the plan are written, and the project scaffolding is in place; game logic comes next. Progress is tracked in the [GitHub issues](../../issues) and [milestones](../../milestones).

## MCP tools (planned)

| Tool | Purpose |
| --- | --- |
| `generate_board` | Balanced, reproducible map for a number of players, a seed, and a mode (Normal/Flash) |
| `calculate_score` | Points per player: vineyards, bodega bonus, water rights, bribe debt |
| `simulate_game` | Bot games that measure balance (turn-order advantage, varietals) |
| `generate_piece_stl` | Parametric STL pieces: terrain hexes, canals, tokens |
| `build_plate` | Lays pieces out on the 256 x 256 mm build plate |

## Stack

Python, [FastMCP](https://github.com/modelcontextprotocol/python-sdk), [uv](https://docs.astral.sh/uv/), [build123d](https://github.com/gumyr/build123d), trimesh + numpy, pytest + hypothesis.

## Development

```sh
uv sync          # install dependencies
uv run pytest    # run the test suite
```

## Documents

- [Game and MCP specification](_docs/plan.md): rules, design decisions, architecture, and the phased plan
- [Process](_docs/process.md): how work is organized
- [AGENTS.md](AGENTS.md): instructions for coding agents
