# Test Workflow Agent

You are responsible for the `test_workflow` track.

This track exists only to exercise the generic multi-track runner end-to-end with deterministic local fixture data.

## Read first

1. `./prefs.md`
2. `./sources.json`
3. `./source_state.json`
4. `./sources.md`
5. `../../artifacts/discovery/test_workflow/YYYY-MM-DD.json`, if it exists for today
6. `../../shared/digest_schema.md`
7. `../../artifacts/digests/test_workflow/YYYY-MM-DD.json`, if it exists for today
8. `./digests/YYYY-MM-DD.md`, if it already exists for today

## Workflow

1. Consume today's discovery artifact for `test_workflow`.
2. Write today's structured digest artifact in `../../artifacts/digests/test_workflow/YYYY-MM-DD.json`.
3. Do not edit `./sources.md`, `./sources.json`, or `./source_state.json`; source state, markdown rendering, and ranked-overview rebuilds are handled by the runner.
6. Do not touch any other track.
