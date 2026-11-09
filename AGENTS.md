# Commands

- `uv sync` - install dependencies
- `uv sync --extra cad` - also install build123d and trimesh (CAD tests
  skip without them)
- `uv run pytest` - the whole suite

# Rules

- Dependencies are added in `pyproject.toml`. Do not add one without
  asking
- "Do task N" means the full cycle in `_docs/process.md`: branch, implement,
  test, PR, merge, then a separate docs review
- MVP first: milestones 1 to 5 are the MVP (`README.md`, Roadmap > MVP).
  Do not pick up milestone 6 ("After the MVP") unless the user asks for it

# Documents

- `README.md` - the specification: game rules, design decisions,
  architecture, and roadmap
- `_docs/process.md` - how work is organized
- `_docs/task-template.md` - the shape every issue follows
- `_docs/team/` - role instructions (e.g. `pm.md` for grooming)
- `_docs/token-budget.md` - how to keep token use low (terse updates,
  lean prompts, batched reviews)
- Task backlog: GitHub issues, grouped by milestone (one per roadmap phase)

# Outdated documents

- Do not read anything in `_docs/outdated/` or use it as context. It holds
  superseded documents kept only for history; `README.md` and the GitHub
  issues replace them
- Open those files only when the user explicitly asks for them by name
- Never update them or cite them as the source of a rule; if something
  there seems missing from `README.md`, ask the user