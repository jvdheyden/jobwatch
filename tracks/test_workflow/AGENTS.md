# Test Workflow Agent

You are responsible for the `test_workflow` track.

This track exists only to exercise the generic multi-track runner end-to-end with deterministic local fixture data.

## Read first

1. `./prefs.md`
2. `./sources.md`
3. `../../artifacts/discovery/test_workflow/YYYY-MM-DD.json`, if it exists for today
4. `./digests/YYYY-MM-DD.md`, if it already exists for today

## Workflow

1. Consume today's discovery artifact for `test_workflow`.
2. Write a short digest in `./digests/YYYY-MM-DD.md`.
3. Rebuild the ranked overview by running `../../scripts/update_ranked_overview.py --track test_workflow`.
4. Do not touch any other track.
