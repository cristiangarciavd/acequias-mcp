# Process

## Tasks

- Tasks are GitHub issues, one at a time
- Milestones follow the phases in `plan.md`; work through them in order
- Check an issue's "Depends on" list before starting it
- Read the acceptance criteria before starting and before closing

## Git workflow

- Never commit straight to `main`; every change goes through a pull request
- One branch per task, named `task-<issue>-<slug>` (e.g. `task-2-hex-model`)
- Commit regularly on the branch
- Before opening the PR, check every acceptance criterion and run `uv run pytest`
- The PR body includes `Closes #<issue>` and the PR gets the issue's milestone
- Merge on GitHub with a merge commit, then delete the branch
- Documentation changes not tied to the task go on their own branch
  (`docs-<slug>`) and their own PR
