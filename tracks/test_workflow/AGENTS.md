# Test Workflow Agent

You are responsible for the `test_workflow` track.

This track exists only to exercise the generic multi-track runner end-to-end with deterministic local fixture data.

## Read first

1. `./prefs.md`
2. `./sources.json`
3. `./source_state.json`
4. `./sources.md`
5. The review artifact supplied by the runner, or today's `../../artifacts/discovery/test_workflow/YYYY-MM-DD.json` if none was supplied
6. `../../shared/digest_schema.md`
7. `../../artifacts/digests/test_workflow/YYYY-MM-DD.json`, if it exists for today
8. `./digests/YYYY-MM-DD.md`, if it already exists for today

## Workflow

1. Use the supplied review artifact for coverage and queued candidates. Use today's discovery artifact if a review artifact was not supplied.
2. Write today's structured digest to the runner's output path, or `../../artifacts/digests/test_workflow/YYYY-MM-DD.json` in fallback runs.
3. Do not edit `./sources.md`, `./sources.json`, or `./source_state.json`; source state, markdown rendering, and ranked-overview rebuilds are handled by the runner.
4. Write the separate review receipt when requested, including when today's digest is unchanged.
5. Do not touch any other track.
