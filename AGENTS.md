# Repo rules

This repository supports five kinds of work:

1. Track runs
2. Track setup
3. Existing-track source curation
4. Repo development
5. Other non-interactive / harness-launched sessions

Mode selection:
- If you were launched as a non-interactive session — a subprocess invocation, a scheduled run, a Codex `exec` session, a Claude `-p --no-session-persistence` session, or any other single-shot automation where no human is in the loop to take turns with — treat the task as a non-interactive / harness-launched session. 
- In non-interactive / harness-launched mode, your prompt is the contract. Follow it literally. 
- If the prompt explicitly says to run a track workflow, produce a digest, process discovery artifacts, or names `tracks/<track>/AGENTS.md`, treat the task as a track run.
- In track-run mode, follow the scheduled or user prompt first, then the relevant `tracks/<track>/AGENTS.md`.
- If the prompt asks to create, scaffold, initialize, or set up a new search track, or names the project skill `set-up`, treat the task as track setup.
- In track-setup mode, use the project skill `set-up`.
- If the prompt clearly asks to add, evaluate, confirm, or look up a named employer or official source for an existing track, treat it as existing-track source curation. Examples include prompts like `add <company> as a source to <track>` or `evaluate <company> for <track>`.
- Existing-track source curation is narrow: use it for adding or evaluating a named source for an existing track, not for broad source discovery, removals, cadence changes, or search-term edits.
- In existing-track source-curation mode, use the project skill `existing-source-curation`.
- If the request expands into broad source discovery or broader source maintenance, route it back to `set-up`.
- Otherwise, treat the task as repo development. When the task is repo development, invoke the coding skill before making any changes.
- Only ask the user which mode they want if the request is genuinely ambiguous.
