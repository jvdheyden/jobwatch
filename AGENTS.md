# Repo rules

  This repository supports two kinds of work:

  1. Track runs
  2. Repo development

  Mode selection:
  - If the prompt explicitly says to run a track workflow, produce a digest, process discovery artifacts, or names
  `tracks/<track>/AGENTS.md`, treat the task as a track run.
  - In track-run mode, follow the scheduled/user prompt first, then the relevant `tracks/<track>/AGENTS.md`.
  - Otherwise, treat the task as repo development and read `.agents/skills/coding/SKILL.md`.
  - Only ask the user which mode they want if the request is genuinely ambiguous.