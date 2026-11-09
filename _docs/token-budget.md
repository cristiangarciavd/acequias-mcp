# Token budget

How the orchestrator and its subagents keep token use low. The owner works
under a usage limit; long sessions with many agents hit it, which stops
every running agent mid-task and wastes the work in flight.

## Rules

| Rule | Why |
|---|---|
| Status updates to the owner are 1-3 lines; never relay an agent's full report | The owner reads the issue/PR for details; repeating them doubles the tokens |
| Agent prompts point to the issue and `_docs/team/*.md` instead of restating them | Agents read those files anyway; restating costs tokens twice |
| Ask agents to reply in at most 10 lines: verdict, PR/links, only notable problems | Long reports are read once and discarded |
| Re-groom an issue only if its code context changed since it was groomed | Grooming is the most repeated step; a groomed issue usually stays valid |
| Batch docs reviews: one per milestone or per 3-4 merged tasks | Each review re-reads the whole README; fewer, larger reviews cost less |
| QA trusts green CI for the full suite and runs locally only the tests and scripts it needs | The full local suite with the `cad` extra takes minutes and a lot of output |
| Use a lighter model for PM grooming, docs reviews and simple QA; keep the strongest model for engineering and tricky QA | Most of the cost is model size; those roles rarely need the top model (the owner decides when to switch) |
| Don't poll background work; wait for the completion notice | Each poll is a full turn |
| Resume a stopped agent with a message instead of starting a new one | A new agent re-reads all the context from scratch |
| Run at most 2-3 agents at once, fewer near the limit | Parallel agents drain the limit faster and all die together when it is hit |
| Before stopping, push any unpushed agent commits | Stopping kills an agent's background jobs; pushed work survives |
| Keep long outputs (sweeps, logs, 3MF files) in files and report a path | Pasting them into chat costs tokens every time they are read |

## When the limit is hit

Agents stop with a rate-limit error. After the reset, send each one a short
"continue from where you stopped" message. Progress notes live in the
orchestrator's memory so a new session can resume without re-reading history.
