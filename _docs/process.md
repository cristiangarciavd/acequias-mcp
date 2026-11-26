# Process

## Roles

- PM - grooms a task before anyone implements it, follows `_docs/team/pm.md`
- Engineer - implements one groomed task, follows `_docs/team/software-engineer.md`
- QA - checks the result against the acceptance criteria, follows `_docs/team/qa-engineer.md`
- Researcher - finds and checks facts and sources for docs and design, follows
  `_docs/team/researcher.md`
- Balance Analyst - reads finished simulation sweeps and drafts the tuning
  decision, follows `_docs/team/balance-analyst.md`

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
5. Wait for CI (the `Tests` workflow) to finish on the PR. Merge only when
   every job is green; if one fails, fix it on the branch first. Then merge on
   GitHub with a merge commit, delete the branch, and update `main`
6. Review the documentation (`README.md`, `AGENTS.md`, `_docs/`) against what
   the task changed or decided. If something needs updating, do it as a
   separate change: its own `docs-<slug>` branch, commit, PR, and merge

## Git rules

- Never commit straight to `main`; every change goes through a pull request
- A pull request is merged only when CI is green
- Documentation changes not tied to the task go on their own branch and PR
  (step 6), never mixed into the task's PR

## Orchestrator

The main session is the orchestrator. It launches the PM, the engineer
and QA as subagents. It does not groom, implement or test itself.

## When to spawn an agent

Spawn one only for:

- A role with its own file in `_docs/team/`, for a task that role owns
- Output that would flood the orchestrator's context (logs, sweeps, searches)
- An independent check, where a fresh context matters (QA)

Do it inline instead for an edit under about 20 lines, a docs typo, or
reading one file. Never run two engineers at once on overlapping code.

## Delegation prompt

Every agent prompt has these parts, in a few lines each:

- Role: "You're the <role>. Follow `_docs/team/<role>.md` and `AGENTS.md`"
  (an agent starts without the conversation, so rules do not carry over)
- Objective: one sentence, with the issue or PR link
- Inputs: the files or outputs to read, by path
- Boundaries: what not to touch, and where to write long output
- Output: the handoff block at the end of the role file

The orchestrator reads only the handoff block, and opens a file the block
names only when a decision needs it.

## Lifecycle

1. Pick the next open issue from the backlog
2. PM grooms it
3. Engineer implements it
4. QA verifies it
5. On FAIL, back to step 3 with the QA comment as input
6. On PASS, close the issue
7. Repeat until the backlog is empty

## Rules

- Do not skip step 2
- The engineer does not close the issue
- QA does not fix the code, only outputs PASS or FAIL
- The orchestrator closes the issue only after QA outputs PASS

## Keeping the PM fast

- The PM grooms in one pass: it rewrites the issue and files follow-ups,
  with no back-and-forth unless a decision is genuinely the owner's
- The PM runs on a lighter, faster model than the engineer, with a short
  prompt that points at the issue and the documents it needs
- The orchestrator grooms the next issue while the current one is being
  implemented or simulated, and may groom several issues in one PM run
- A research task follows the same lifecycle with the Researcher in place
  of the engineer
