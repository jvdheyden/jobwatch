# About jobwatch

jobwatch is an open-source, agent-assisted job search tool that helps users discover and prioritize relevant job opportunities while minimizing time spent searching.

Users organize their searches into **tracks**, each with its own goals, preferences, and sources.

The workflow consists of:
1. **Setup:** Understand the user's goals, find relevant sources, and configure a track.
2. **Discovery:** Collect job postings using deterministic scrapers and APIs where possible.
3. **Filtering:** Identify potentially relevant jobs based on track preferences and constraints.
4. **Ranking:** Evaluate jobs against the user's background and preferences.
5. **Reporting:** Deliver a concise digest of the best new opportunities.

Agents also help develop and maintain source integrations when needed.

## Guiding principles

- Optimize for relevant opportunities, not the number of jobs found.
- Minimize the user's time and attention spent searching.
- Base decisions on evidence; make uncertainty explicit.
- Prioritize recall during discovery and precision during ranking.
- Prefer deterministic, reusable solutions over agent-driven ones.
- Keep implementations simple, maintainable, and efficient.
- Protect user data and preserve user control.

## Repo rules

This repository supports six kinds of work:

1. Track runs
2. Track setup and maintenance
3. Existing-track source curation
4. Repo development
5. Code review
6. Other non-interactive / harness-launched sessions

Mode selection:
- If you were launched as a non-interactive session — a subprocess invocation, a scheduled run, a Codex `exec` session, a Claude `-p --no-session-persistence` session, or any other single-shot automation where no human is in the loop to take turns with — treat the task as a non-interactive / harness-launched session. 
- In non-interactive / harness-launched mode, your prompt is the contract. Follow it literally. 
- If the prompt explicitly says to run a track workflow, produce a digest, process discovery artifacts, or names `tracks/<track>/AGENTS.md`, treat the task as a track run.
- In track-run mode, follow the scheduled or user prompt first, then the relevant `tracks/<track>/AGENTS.md`.
- If the prompt asks to create, scaffold, initialize, or set up a new search track, or names the project skill `set-up`, treat the task as track setup.
- In track-setup mode, use the project skill `set-up`.
- If the prompt asks to update an existing track's preferences or reconcile its retrieval configuration (including after manual preference edits), use the existing-track maintenance branch of `set-up`. This is maintenance, not a normal track run; do not scaffold the track again.
- If the prompt clearly asks to add, evaluate, confirm, or look up a named employer or official source for an existing track, treat it as existing-track source curation. Examples include prompts like `add <company> as a source to <track>` or `evaluate <company> for <track>`.
- Existing-track source curation is narrow: use it for adding or evaluating a named source for an existing track, not for broad source discovery, removals, cadence changes, or search-term edits.
- In existing-track source-curation mode, use the project skill `existing-source-curation`.
- If the request expands into broad source discovery or broader source maintenance, route it back to `set-up`.
- If the prompt asks to review a pull request, commit, branch, or local code changes, or to merge a pull request, treat the task as code review. This includes follow-up requests such as "check the changes to PR 24", "did they address the findings?", or "review and merge PR 24 if ready".
- In code-review mode, use the project skill `reviewing`. Review-only work follows that skill's verification and reporting rules.
- If the user also requests fixes, use `reviewing` for the assessment and invoke `coding` before implementing the requested changes.
- Otherwise, treat the task as repo development. When the task is repo development, invoke the coding skill before making any changes.
- Only ask the user which mode they want if the request is genuinely ambiguous.
