# Process

## Roles

- PM - grooms a task before anyone implements it, follows `_docs/team/pm.md`

## Tasks

- Tasks are GitHub issues, one at a time
- Milestones follow the phases in the README roadmap; work through them in order
- Milestones 1 to 5 are the MVP (README, Roadmap > MVP). Milestone 6, "After
  the MVP", is lower priority: start its issues only once milestones 1 to 5
  are closed, unless the user asks for one by number
- A new idea outside the MVP goes into an issue in milestone 6
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
