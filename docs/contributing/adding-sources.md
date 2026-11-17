# Adding Discovery Sources

Discovery source support lives behind `discovery_mode` providers. New source
support should usually be added by creating or extending a provider module under
`scripts/discover/sources/` incl. fixtures and 
contract tests, not by editing the `scripts/discover_jobs.py`
entrypoint.

## Choose A Provider Shape

Prefer a reusable board-family provider when the source is hosted by a known
ATS or job board, such as Greenhouse, Lever, Workday, Ashby, Workable, Personio,
Getro, Eightfold, or Phenom. Add bespoke company-specific providers only when the site
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

The track's `track_terms` and source-specific `search_terms` are retrieval
vocabulary, not a taxonomy of technical or non-technical roles. Once a
provider has enumerated a posting and found at least one configured term in its
searchable payload, it should emit the candidate for downstream track
evaluation. Do not add shared title allowlists or denylists for user-fit policy.
Provider-native filters and source-specific predicates required to enumerate a
board correctly are still appropriate; document and test those as protocol
behavior. Semantic role-family, domain, and exclusion decisions belong to the
active track's preferences and the `find-jobs`/`rank-jobs` stages.

## Fixtures And Tests

Add mocked provider fixtures under:

```text
tests/fixtures/sources/<discovery_mode>/
```

Follow the [testing skill](../../.agents/skills/testing/SKILL.md) and
[provider fixture guide](../testing.md#provider-contracts). Every registration
automatically inherits the shared contracts. Add `contract.json` with independently
specified expected jobs and capability evidence, plus nonempty, empty and duplicate
responses. Browser providers supply raw DOM observations at the Playwright boundary.
Missing fixtures fail; declaring a mode non-emitting must describe its actual probe
or coverage-only purpose. Never generate expectations from the extractor output.

Run:

```bash
./.venv/bin/python -m pytest tests/contract -k <discovery_mode>
```

Add or update provider-specific checks for parsing, URL construction, pagination,
detail failures or native filters. Record their paths and scope in the manifest.
Use the [live assurance procedure](../testing.md#live-source-assurance) for reviewed
count floors, expiring canaries and capturing upstream failures as offline fixtures.

When testing migrated providers, patch `discover.http.fetch_text`,
`discover.http.fetch_json`, or `discover.http.post_json`. Unmigrated legacy
handlers may still be patched through `discover_jobs.*` until they move.

## Source onboarding

Select the official URL and best supported mode using
[`shared/source_curation.md`](../../shared/source_curation.md). Register through
`scaffold_track.py` or `curate_sources.py`, and register user/independent canaries
with `update_source_canary.py --register`. Both paths queue the same evaluation
workflow. Complete execution alone does not establish recall. A missing live,
in-scope posting must be investigated before accepting provider support.

## Live Quality Gate

Contract tests are a mechanical floor. For real source integration, also run a
live canary check through the existing quality workflow:

```bash
./.venv/bin/python scripts/discover_jobs.py --track <track> --source "<Source Name>" --today YYYY-MM-DD --pretty
./.venv/bin/python scripts/eval_source_quality.py --track <track> --source "<Source Name>" --today YYYY-MM-DD --canary-title "<Expected Title>" --canary-url "<Official vacancy URL>"
```

If the evaluator reports `integration_needed`, use the generated source integration ticket to
make the narrowest provider fix and add a focused regression test.

### When to run the full source integration loop

For sources where the failure mode is unclear, where you want the loop to drive
the fix end-to-end, or where you're bringing up multiple sources at once, run
the orchestrator instead of editing manually:

```bash
./.venv/bin/python scripts/source_integration.py \
  --track <track> \
  --source "<Source Name>" \
  --today YYYY-MM-DD \
  --canary-title "<Expected Title>" --canary-url "<Official vacancy URL>" \
  --max-attempts 3
```

This calls `eval_source_quality.py`, dispatches a coding agent against the
`integration_ticket`, rediscovers, and re-evaluates — looping until `pass`,
`blocked`, or `retry_limit`. See
[`docs/architecture.md`](../architecture.md) (Source integration loop) for the
sequence diagram and artifact paths.
