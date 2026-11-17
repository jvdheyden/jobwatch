# Testing Jobwatch

The [testing skill](../.agents/skills/testing/SKILL.md) is the policy for humans,
coding agents, and reviewers. Tests protect job recall, truthful coverage, and
workflow state; test count is not a quality target.

## Local and CI verification

```bash
bash scripts/bootstrap_venv.sh --no-chromium  # one-time dependency installation
bash scripts/test.sh --fast                 # unit + registered provider contracts
bash scripts/test.sh                        # full offline regression suite
./.venv/bin/python -m pytest tests/integration/test_discover_avature_html.py -q
bash scripts/test.sh --durations=20         # profile before optimizing
```

The runner automatically discovers pytest modules. Both paths check shell syntax,
Python compilation, skill mirrors, and the generated discovery catalog. Full CI
runs on every PR. Dependency installation requires network; verification uses
fixtures and local HTTP servers. Python socket connections to external addresses
are blocked in pytest and inherited Python subprocesses. The guard is a regression
tripwire, not an OS sandbox for arbitrary external binaries. Agent and delivery
executables must be explicit doubles; never use a real model/account in pytest.

Each test has a temporary HOME; XDG and application settings are cleared. Use
`tmp_path`, `tmp_case_dir`, and `tmp_job_agent_root`, never a real local track.
Required tests cannot skip. Only a genuinely optional system capability can use
`@pytest.mark.optional` with a precise skip reason; provider fixtures are required.
Check optional capabilities inside the marked test, since module-level skips fail
collection and can conceal required tests.
Fast verification excludes subprocess workflow integration and E2E; full is the
pre-push/PR gate. No browser download is required for offline browser contracts.

## Provider contracts

`tests/contract/test_source_contract.py` gets its cases directly from
`discover.registry.load_registry()`. A new registration without a fixture pack
fails with its mode and missing path. Each `tests/fixtures/sources/<mode>/` contains:

- `contract.json`: source configuration, retrieval terms, independently specified
  expected job URLs/titles (and relevant metadata), authoritative empty status,
  and explicit pagination/detail/browser capability evidence.
- `response.html` and/or `response.json`: representative nonempty inputs.
- `empty.*`: an actual empty feed/catalog, or an explicitly documented uncertain
  empty observation. A missing payload must never stand in for an empty feed.
- `duplicates.*`: duplicate input with independently specified unique jobs. Use
  `duplicates_expected` if its jobs differ from the response fixture.

Expected results are authored by reading the source fixture and public identity
contract. **Never regenerate expected jobs from current scraper output.** Exact
set equality catches missing jobs and unexpected navigation links. Fixtures should
include several matching jobs, nonmatching jobs, and a matching role whose semantic
fit belongs to the agent (for example a security sales role). Keep native filtering
and protocol exclusions explicit. URL normalization and alternate URLs are part
of the interface.

The shared suite checks extraction, identity, provenance, term evidence, counts,
deduplication, network/response-decode failures, and empty semantics. Specialized
suites named by each manifest cover parsing, paging and enrichment. An empty
`tests` capability list requires an explanation of the unsupported behavior; it
is not a skip. Every installed-browser provider also exercises raw DOM observations,
navigation and missing-browser behavior. Browser doubles replace Playwright only;
they do not return Candidates or replace the production extractor. API/browser
paging suites cover later pages, repeated pages, early termination, errors and
limits. Non-emitting probes must explicitly report their limitations.

Provider-specific fixtures are intentionally retained even when a shared invariant
also applies. Add the regression at the narrowest useful boundary, then run the
mode contracts and its capability suites. For a dropped-job fix, temporarily
suppress the affected posting and confirm the regression fails.

## Live source assurance

Run live checks separately from PR verification. Use existing discovery,
`eval_source_quality.py`, `update_source_canary.py`, and `source_integration.py`;
there is no separate monitoring service. A practical cadence is weekly for a
representative installation of each family in active use, and after a provider
change for each affected high-value or unusual installation. Review other
installations monthly, or when run coverage changes. These are operator procedures,
not an automatically installed schedule.

1. Open the official board and independently record a current job, the visible
   total (if meaningful), and the configured search. Set conservative count floors
   and a canary expiry, normally within 14 days. Record provenance when registering with `update_source_canary.py --register`.
   A discovery-output suggestion remains a weaker regression check after review.
2. Run bounded discovery into an evaluation artifact, preserving normal run state:

   ```bash
   ./.venv/bin/python scripts/discover_jobs.py --track <track> --source '<Source>' \
     --today YYYY-MM-DD --timeout-seconds 15 --output /tmp/source-check.json --pretty
   ./.venv/bin/python scripts/eval_source_quality.py --track <track> --source '<Source>' \
     --today YYYY-MM-DD --artifact-path /tmp/source-check.json --output /tmp/source-eval.json \
     --reviewer off --timeout-seconds 15 --canary-title '<Reviewed title>' \
     --canary-url '<Official vacancy URL>' --canary-expires-on YYYY-MM-DD \
     --min-candidates 1 --min-enumerated 10 --min-detail-fraction 0.8
   ```

   Count and description-coverage floors are optional, manually reviewed,
   search-specific expectations. Description coverage prevents a single good
   posting from masking widespread missing or boilerplate-only descriptions.
   A separate scheduler should impose an overall deadline on live discovery;
   per-request timeouts alone do not bound an arbitrarily large board. Canary
   refresh itself has a 120-second discovery deadline. Evaluator raw-page samples
   are bounded; model review is disabled by `--reviewer off`.
3. Inspect the resulting checks: failed/partial execution, zero extraction from a
   nonempty board, count shortfall, repeated or missing pages, non-vacancy links,
   weak/boilerplate descriptions and missing current canaries. Compare with the
   previous reviewed artifact and check a job from the **last** result page.
   A stale review deadline is not confirmed vacancy closure. Stored canaries
   are loaded automatically; older missing or uncertain postings receive an
   independent availability check. Inconclusive checks preserve prior evidence
   and defer verification. Only confirmed expiration permits archival/rotation.
   Use the [shared review procedure](../shared/source_curation.md#review-and-rotation-coordinators-only)
   for dynamic pages or manual availability/scope confirmation. Legacy singular
   canaries remain readable but require review before independent verification.
4. Distinguish execution from search quality. A complete filtered feed can exclude
   a desired role because terms or native filters are restrictive. Compare the
   official vacancy text and configured retrieval; report a retrieval gap without
   changing the provider's execution status. The quality evaluator still fails an
   available, in-scope missing canary and reports the retrieval defect. Count floors describe the
   reviewed search; canary scope follows intended preferences so restrictive
   terms or filters remain detectable. Follow the existing maintenance workflow for preference or
   retrieval changes.
5. Capture a minimal sanitized response from a demonstrated failure, preserve its
   structure/page counts and a provenance note (URL/date/redactions), and write
   expected jobs independently. Reproduce offline before a narrow fix. Use the
   evaluator's integration ticket if needed; don't automatically accept live
   scraper output as a new golden file.

Family-specific checks complement the shared procedure (names are provider modules;
see the generated [mode catalog](../shared/discovery_modes.md) for their aliases):

| Families | Representative evidence and targeted checks |
| --- | --- |
| ashby, greenhouse, lever, hibob, pinpoint, bamboohr, dover, teamtailor, recruitee, personio | Official feed/schema; published-only and secondary locations; direct detail and real role text; test a second tenant when tenant behavior differs. |
| workday, workable, smartrecruiters, ultipro, eightfold, getro, ibm | Compare total/unique IDs across first and last pages; continuation tokens, native filters, bounded termination, detail errors. |
| avature, phenom, enbw, thales | Embedded payload/DOM selectors and totals, later offsets, duplicate pages, detail boilerplate; check localized installations separately. |
| successfactors, ecb, kula | RSS/XML structure, feed completeness and term-scoped feeds, duplicate offices, canonical links and descriptions. |
| browser | Per-strategy navigation/cookies, dynamic cards, next/load-more behavior, challenges and missing browser. Check Google, Meta, Bosch and each bespoke implementation separately. Coinbase is a non-emitting probe, not verified extraction. |
| generic_html, alphatheta, apple, jobvite, krisp, rheinmetall, softgarden | Actual vacancy links rather than navigation, explicit empty markers, static-vs-JavaScript changes, detail text. Include Factorial's anonymous apply links and KNDS fallback. |
| bundeswehr, public_service, service_bund | Native queries, SAP/portal pagination, localized IDs/URLs, query scope, deadlines and detail fields. |
| hackernews, yc, iacr, notion | Current thread/database/inline records, pagination/cursors, external vs canonical posting IDs, titles and structured role text. |
| static_pages | Independently verify each bespoke site's visible current roles; coverage-only modes must remain explicit and cannot certify recall. |

## Workflow and agent assurance

Integration tests exercise persistent state across complete, failed, partial and
repeated runs. E2E tests run the real track runner, discovery and post-processing
against a local source and synthetic agents. Agents write structured outputs only;
rendering, seen jobs, cadence updates, overview rebuilding and delivery belong to
the orchestrator. Delivery failures must remain visible without destroying local
artifacts.

Structured agent contracts are tested with production validators, including invalid
JSON, unknown/duplicate IDs, missing judgments, schema and size limits. Model
quality is a separate opt-in evaluation with independently reviewed track scenarios
and shared postings whose expected admission changes with preferences. See
[the evaluation guide](../tests/evals/README.md). Model runs are never part of
ordinary pytest or PR verification; pytest checks the scorer and dataset integrity.
