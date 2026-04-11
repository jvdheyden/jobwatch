# Test Workflow Agent

You are responsible for the `test_workflow` track.

This track exists only to exercise the generic multi-track runner end-to-end with deterministic local fixture data.

## Read first

1. `./prefs.md`
2. `./sources.md`
3. `../../artifacts/discovery/test_workflow/YYYY-MM-DD.json`, if it exists for today
4. `../../shared/digest_schema.md`
5. `../../artifacts/digests/test_workflow/YYYY-MM-DD.json`, if it exists for today
6. `./digests/YYYY-MM-DD.md`, if it already exists for today

Post-processing scripts are stable commands. During normal runs, do not read
`../../scripts/render_digest.py` or `../../scripts/update_ranked_overview.py`
unless one of the commands fails or the digest schema changed. Run them using
the workflow commands below.

## Workflow

1. Consume today's discovery artifact for `test_workflow`.
2. Write today's structured digest artifact in `../../artifacts/digests/test_workflow/YYYY-MM-DD.json`.
3. Render `./digests/YYYY-MM-DD.md` by running `../../scripts/render_digest.py --track test_workflow --date YYYY-MM-DD`.
4. Rebuild the ranked overview by running `../../scripts/update_ranked_overview.py --track test_workflow`.
5. Do not touch any other track.
