# Official Source And `discovery_mode` Heuristics

Use this guide when a skill needs to identify the best official source URL for a track or choose a conservative `discovery_mode`.

## Official source priority

- Start from the employer homepage when possible. Check the header, footer, and primary navigation for links such as `Careers`, `Jobs`, `Join us`, or `Work with us` before doing broader search.
- Prefer official careers pages and homepage-linked ATS destinations over third-party aggregators.
- Treat homepage-linked ATS boards as official when they are clearly tied to the employer, including hosted boards on Greenhouse, Lever, Ashby, Workday, Workable, Getro, Personio, Recruitee, and similar providers.
- If the user supplied a direct ATS or careers URL, verify it against the employer homepage before accepting or replacing it.
- Only keep third-party boards when the workflow explicitly calls for broad-board discovery or the user asked for them.

## `discovery_mode` selection

- Use a mode listed in `shared/discovery_modes.md`. Do not invent a new `discovery_mode`.
- Common mappings:
  - Workday career pages or APIs: `workday_api`
  - Greenhouse boards: `greenhouse_api`
  - Lever boards: `lever_json`
  - Ashby boards with usable API responses: `ashby_api`
  - Ashby boards without reliable API clues: `ashby_html`
  - Workable boards: `workable_api`
  - SmartRecruiters boards: `smartrecruiters_api`
  - Pinpoint boards (`<company>.pinpointhq.com`): `pinpoint_api`
  - Kula boards (`careers.kula.ai/<company>`): `kula_rss`
  - Public Notion careers pages backed by a database (`<workspace>.notion.site`): `notion_site`
  - Getro collection boards: `getro_api`
  - Personio pages: `personio_page`
  - Recruitee inline pages: `recruitee_inline`
  - Softgarden vacancy pages: `softgarden_html`
  - YC jobs role boards: `yc_jobs_board`
  - Hacker News jobs pages: `hackernews_jobs`
  - service.bund search URLs: `service_bund_search`
  - IACR jobs: `iacr_jobs`
  - Other official ATS pages without dedicated support: `html`
  - Unknown or custom official pages: `html`
- If more than one mode seems plausible, choose the most conservative supported option and note the uncertainty.
- If a source is clearly official but the dedicated support is weak or unknown, keep it with the best supported fallback, usually `html`, rather than inventing a mode or dropping the source outright.

## Fallback and escalation

- If an employer homepage links directly to an official ATS board, keep that board as the source of truth even when it must fall back to `html`.
- When support looks uncertain or weak, surface the caveat and suggest source-integration follow-up instead of auto-escalating into provider-development work.
- Keep source selection and source integration separate: picking the official URL and the best current `discovery_mode` comes first; adding provider support belongs under `scripts/discover/sources/` with fixtures and contract tests.

## Retrieval and cadence

Default to `every_3_runs`; use `every_run` for particularly valuable or fast-moving
sources and `every_month` for slow or broad follow-ups. Keep search terms compact
and grounded in role families, domain vocabulary and supplied reference jobs.
`append` extends track terms; `override` replaces them. Check native filters and
track match rules for accidental exclusions. Negative preferences and ranking
signals are not literal retrieval queries. Prefer recall in retrieval; semantic
fit belongs to finding and ranking. Suggest match rules only for broad/noisy
multi-employer boards, not ordinary employer boards.

## Reference jobs and canaries

A **reference job** records an example the user likes and why. It remains useful
for source selection, terms/filters, match rules and ranking after expiration.
A **live canary** is an independently confirmed, available posting within the
intended search scope that discovery should find. A posting can serve both roles.
Use a posting ID or normalized URL; a title is only a fallback without either.
Never silently discard supplied examples or official seeds: associate them with
canonical sources or record why excluded/unresolved.

Prefer user-supplied live postings, then independently found official vacancies,
then separate probing, then discovery-output suggestions. Acquisition provenance
stays attached even after a suggestion is reviewed. A discovery-derived posting
can test regression but cannot certify independent coverage.

## Common onboarding and verification (coordinators only)

1. Select the official source and best supported mode; selection does not require
   provider implementation. Register through `scaffold_track.py` for a new track
   or `curate_sources.py register` for an existing track. Both queue verification.
2. Register examples and canaries through setup selection or
   `update_source_canary.py --track <track> --source <id> --register <evidence.json>`.
   The bounded object contains `reference_jobs` and/or `canaries`; see the
   [evidence contract](../docs/architecture.md#source-evidence-contracts).
3. Evaluate with `integrate_next_source.py --track <track> --source <id>`.
   It runs discovery and the shared evaluator, including all stored canaries,
   regardless of reported execution completeness. Use `--reviewer off` for
   deterministic-only checks. Config tuning precedes provider implementation;
   unresolved evidence or track-rule changes require review, not speculative code.
4. During interactive setup, finish the first preview before expensive checks.
   Use `start_source_integration.py --track <track> --limit 3` for authorized
   background work; source-scoped runs accept `--source <id>`. Remaining work
   stays queued. Scheduled track runs never drain this queue automatically.
5. Report **configured**, **basic support**, or **independently verified sample**.
   No canary is not an onboarding failure. A live, in-scope missing canary is a
   defect; finding a canary is necessary evidence, never proof of exhaustive recall.

## Review and rotation (coordinators only)

`eval_source_quality.py` loads stored evidence automatically. Older missing or
stale evidence is checked against the official vacancy independently. Same-day
explicit observations are accepted as current evidence. Review deadlines mean
"check again", not confirmed closure. Dynamic/blocked pages and ambiguous
responses produce inconclusive verification and preserve prior evidence.

`update_source_canary.py` without `--register` discovers and independently checks
current canaries before considering rotation. It keeps live missing and unknown
postings; confirmed expiration archives them. With no retained canary it prefers
separate official-page probing before suggesting discovery output. Suggestions
require scope review. Failed discovery/probes must not erase known evidence.

For an independent manual review, use:

```bash
./.venv/bin/python scripts/update_source_canary.py --track <track> --source <id> \
  --review-canary <canary-id> --availability live --scope in_scope \
  --evidence-url '<official vacancy URL>' --evidence-note '<what establishes availability and scope>'
```

Use `expired` only for confirmed closure; this archives the live record and
permits a replacement while preserving its reference job. Use `unknown` for an
inconclusive check. Registration adds evidence; it cannot silently overwrite an
existing canary or turn discovery-output provenance into independent evidence.
