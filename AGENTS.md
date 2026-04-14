# Repo rules

This repository supports four kinds of work:

1. Track runs
2. Track setup
3. Existing-track source curation
4. Repo development

Mode selection:
- If the prompt explicitly says to run a track workflow, produce a digest, process discovery artifacts, or names `tracks/<track>/AGENTS.md`, treat the task as a track run.
- In track-run mode, follow the scheduled or user prompt first, then the relevant `tracks/<track>/AGENTS.md`.
- If the prompt asks to create, scaffold, initialize, or set up a new search track, or names the project skill `set-up`, treat the task as track setup.
- In track-setup mode, use the project skill `set-up`.
- If the prompt clearly asks to add, evaluate, confirm, or look up a named employer or official source for an existing track, treat it as existing-track source curation. Examples include prompts like `add <company> as a source to <track>` or `evaluate <company> for <track>`.
- Existing-track source curation is narrow: use it for adding or evaluating a named source for an existing track, not for broad source discovery, removals, cadence changes, or search-term edits.
- In existing-track source-curation mode:
  - read `tracks/<track>/prefs.md`, `tracks/<track>/sources.json`, and `tracks/<track>/sources.md`
  - preserve existing sources unless the user explicitly asks to replace or remove them
  - determine the official source URL by checking the employer homepage and official careers path first
  - infer a conservative `discovery_mode` from the URL or board family, defaulting to `html` when unclear
  - prepare a normalized source entry suitable for `sources.json`
  - if the source looks straightforward, treat the prompt as permission to update the track config
  - after changing `sources.json`, run `scripts/render_sources_md.py --track <track>` to refresh the read-only Markdown summary
  - if support looks uncertain or weak, do not auto-escalate; instead suggest optional source-integration escalation using the project skill `set-up`, section `4b`
- Otherwise, treat the task as repo development and use the project skill `coding`.
- Only ask the user which mode they want if the request is genuinely ambiguous.
