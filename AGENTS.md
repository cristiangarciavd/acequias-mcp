# Commands

- `uv sync` - install dependencies
- `uv run pytest` - the whole suite

# Rules

- Dependencies are added in `pyproject.toml`. Do not add one without
  asking
- "Do task N" means the full cycle in `_docs/process.md`: branch, implement,
  test, PR, merge, then a separate docs review

# Documents

- `_docs/plan.md` - game and MCP specification (design and decisions)
- `_docs/process.md` - how work is organized
- Task backlog: GitHub issues, grouped by milestone (one per plan phase)