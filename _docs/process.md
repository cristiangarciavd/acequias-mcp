# Process

## Tasks

- Tasks are GitHub issues, one at a time
- Milestones follow the phases in `plan.md`; work through them in order
- Check an issue's "Depends on" list before starting it
- Read the acceptance criteria before starting and before closing

## Doing a task, end to end

"Do task N" means the whole cycle below, without further prompting:

1. Update `main` and create the branch `task-<issue>-<slug>` (e.g. `task-2-hex-model`)
2. Implement the task with its tests; commit regularly on the branch
3. Review the work: check every acceptance criterion and run `uv run pytest`
   (the whole suite, so earlier tasks are not broken)
4. Push the branch and open a PR whose body includes `Closes #<issue>`;
   give the PR the issue's milestone
5. Merge on GitHub with a merge commit, delete the branch, and update `main`
6. Review the documentation (`README.md`, `AGENTS.md`, `_docs/`) against what
   the task changed or decided. If something needs updating, do it as a
   separate change: its own `docs-<slug>` branch, commit, PR, and merge

## Git rules

- Never commit straight to `main`; every change goes through a pull request
- Documentation changes not tied to the task go on their own branch and PR
  (step 6), never mixed into the task's PR
