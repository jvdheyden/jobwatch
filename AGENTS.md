# Repo rules

This repository supports three kinds of work:

1. Track runs
2. Track setup
3. Repo development

Mode selection:
- If the prompt explicitly says to run a track workflow, produce a digest, process discovery artifacts, or names `tracks/<track>/AGENTS.md`, treat the task as a track run.
- In track-run mode, follow the scheduled or user prompt first, then the relevant `tracks/<track>/AGENTS.md`.
- If the prompt asks to create, scaffold, initialize, or set up a new search track, or names `.agents/skills/set-up/SKILL.md`, treat the task as track setup.
- In track-setup mode, follow `.agents/skills/set-up/SKILL.md`.
- Otherwise, treat the task as repo development and read `.agents/skills/coding/SKILL.md`.
- Only ask the user which mode they want if the request is genuinely ambiguous.
