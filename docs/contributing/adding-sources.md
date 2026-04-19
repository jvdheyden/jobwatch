# Adding Discovery Sources

Discovery source support lives behind `discovery_mode` providers. New source
support should usually be added by creating or extending a provider module under
`scripts/discover/sources/`, not by editing the `scripts/discover_jobs.py`
entrypoint.

## Choose A Provider Shape

Prefer a reusable board-family provider when the source is hosted by a known
ATS or job board, such as Greenhouse, Lever, Workday, Ashby, Workable, Personio,
Getro, or Eightfold. Add bespoke company-specific providers only when the site
does not expose a reusable board/API shape.

Each provider module should document:

- supported `discovery_mode` values
- expected source URL shape
- supported source `filters`
- known limitations

## Provider Contract

Provider modules export `SOURCE` or `SOURCES` using `SourceAdapter` from
`discover.registry`.

The discover callable must be compatible with:

```python
def discover(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    ...
```

Minimum behavior:

- return one `Coverage` object per source
- use status `complete`, `partial`, or `failed`
- populate listing counts, searched terms, result-page summary, limitations, and
  candidates
- deduplicate candidates by canonical job URL
- include candidate employer, title, URL, source URL, matched terms, and
  provenance notes
- use shared helpers from `discover.helpers` and transport from `discover.http`

## Fixtures And Tests

Add mocked provider fixtures under:

```text
tests/fixtures/sources/<discovery_mode>/
```

At minimum, add representative response and empty-result fixtures. Add duplicate
fixtures when the provider can surface the same job more than once.

Run:

```bash
./.venv/bin/python -m pytest tests/contract -k <discovery_mode>
```

Add or update provider-specific integration tests when parsing behavior, URL
construction, pagination, or source-specific filters need to be pinned.

When testing migrated providers, patch `discover.http.fetch_text`,
`discover.http.fetch_json`, or `discover.http.post_json`. Unmigrated legacy
handlers may still be patched through `discover_jobs.*` until they move.

## Live Quality Gate

Contract tests are a mechanical floor. For real source integration, also run a
live canary check through the existing quality workflow:

```bash
./.venv/bin/python scripts/discover_jobs.py --track <track> --source "<Source Name>" --today YYYY-MM-DD --pretty
./.venv/bin/python scripts/eval_source_quality.py --track <track> --source "<Source Name>" --today YYYY-MM-DD --canary-title "<Expected Title>"
```

If the evaluator reports `repair_needed`, use the generated repair ticket to
make the narrowest provider fix and add a focused regression test.

### When to run the full repair loop

For sources where the failure mode is unclear, where you want the loop to drive
the fix end-to-end, or where you're bringing up multiple sources at once, run
the orchestrator instead of editing manually:

```bash
./.venv/bin/python scripts/repair_source.py \
  --track <track> \
  --source "<Source Name>" \
  --today YYYY-MM-DD \
  --canary-title "<Expected Title>" \
  --max-attempts 3
```

This calls `eval_source_quality.py`, dispatches a coding agent against the
`repair_ticket`, rediscovers, and re-evaluates — looping until `pass`,
`blocked`, or `retry_limit`. See
[`docs/architecture.md`](../architecture.md) (Source repair loop) for the
sequence diagram and artifact paths.
