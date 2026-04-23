---
name: discover-sources
description: Find employers and official job-board sources for a new job-search track based on the user's profile, stated track preferences, and target role shapes. Return a short tiered source pack plus setup-ready normalized records for set-up to use.
---

# Skill: Discover sources for a new track

Use this skill during track setup when the user needs help identifying companies and official job sources.

This skill is for source discovery, not track scaffolding, job discovery, ranking, or source integration.

## Precondition

Use this skill only after the minimum setup brief already exists either:
- in the current `set-up` conversation, or
- in an existing `tracks/{track_slug}/prefs.md`

Required minimum brief:
- track display name
- broad search area
- goals / role types
- keep-only keywords, or explicit `none yet`
- constraints / red flags, or explicit `none yet`
- geography / remote preferences, or explicit `none yet`

Track name or slug alone is not enough.

If this brief is not available yet, stop and return control to `set-up` so it can continue asking questions before any source search.

## Input

Assume `set-up` has already gathered the user's preferences. Use those preferences as the primary filter.

Read, when available:
- `tracks/{track_slug}/prefs.md`
- `profile/cv.md`
- `profile/prefs_global.md`
- `docs/source_curation.md` when choosing or explaining official-source selection or `discovery_mode` heuristics
- `docs/discovery_modes.md` when choosing or explaining supported `discovery_mode` values
- the user's stated setup preferences:
  - track display name or search area
  - goals / role types
  - keep-only keywords
  - constraints and red flags
  - geography / remote preferences
  - seed companies, sectors, labs, organizations, job boards, or career pages
  - any existing partial source list

If the user already has a strong official source list, do not replace it. Use this skill only to fill gaps, tighten the list, or propose better official sources after `set-up` has offered discovery and the user wants that help.

## Workflow

### 1. Build the fit profile

- Distill the target roles, strongest domains, exclusions, and location / remote boundaries from the stated preferences.
- Prefer explicit setup preferences over looser hints from the CV.
- Convert sparse inputs into a compact employer-and-source search brief before searching.

### 2. Discover candidate employers and official sources

- Prioritize employers, research labs, and organizations likely to post the target roles.
- When a target employer homepage is known, inspect the official homepage header, footer, and main navigation first for links such as `Careers`, `Jobs`, `Join us`, or `Work with us` before doing broader search.
- Prefer official career pages and first-party hosted boards.
- Treat homepage-linked official careers pages and homepage-linked ATS destinations as high-confidence official sources.
- Accept official Greenhouse, Lever, Ashby, Workday, Workable, and comparable first-party boards when they are clearly tied to the employer.
- Do not use third-party aggregators unless the user explicitly asks for them or the track scope requires them.
- If the user provided seed employers, preserve them unless they clearly conflict with the stated preferences.

### 3. Validate lightly

- Confirm the source appears official and relevant to the stated preferences.
- Detect board family or likely `discovery_mode` when obvious from the URL or page shape. Use `docs/source_curation.md` for the canonical official-source and fallback heuristics, and `docs/discovery_modes.md` as the supported-mode reference.
- If an official ATS board is linked from the employer homepage or official careers page, keep it even when it must fall back to `html`.
- If unclear, keep the source only when it still looks plausibly official and default `suggested_discovery_mode` to `html`.
- Do not do exhaustive browsing, canary discovery, source-quality evaluation, or scraper integration here.

### 4. Normalize for `set-up`

- Produce a short tiered list:
  - `primary`: high-confidence sources to use now
  - `follow_up`: plausible but lower-confidence or broader sources
- Keep the list concise. Prefer roughly `4-8` primary sources and a smaller follow-up list, not a catalog.
- For each source, provide setup-ready normalized fields and a short reason grounded in the user's stated preferences.
- Suggest search terms that reflect the target roles and source vocabulary.
- Suggest cadence conservatively:
  - `every_run` only for unusually high-value or fast-moving sources
  - `every_3_runs` by default
  - `every_month` for slower, lower-yield, or broad follow-up sources
- Keep user-specific logic in track config:
  - source lists, cadence, search terms, and native source filters belong in `tracks/{track_slug}/sources.json`
  - broad-source post-discovery filtering belongs in `tracks/{track_slug}/match_rules.json`
  - reusable source parsing belongs in provider modules under `scripts/discover/sources/`, not in track config
- Suggest match rules only for broad or noisy sources such as ecosystem boards, public-service searches, Hacker News, YC role boards, or community job lists. Do not suggest match rules for ordinary official employer boards unless they are predictably noisy.

## Shared heuristics

Use `docs/source_curation.md` as the canonical reference for official-source selection, common `discovery_mode` mappings, fallback behavior, and when to surface source-integration follow-up. Use `docs/discovery_modes.md` as the supported-mode catalog.

## Output contract

Return a concise human-readable shortlist by default. Keep internally structured notes for `set-up`, but do not dump full setup-ready records unless the user asks for debug detail.

Default user-facing shape:

- Recommended sources: source name, URL, board family, suggested `discovery_mode`, cadence, and one short reason.
- Dropped sources: source name, URL if known, and the reason it should not be used now.
- URL corrections: user-supplied URL -> better official URL, with a short explanation.
- Known caveats: unsupported/partial board families, broad/noisy source warnings, or filters that should be confirmed.
- Decisions needed: keep/drop/add, cadence changes, native filters, or broad-source match-rule confirmation.

Keep the shortlist concise. Prefer roughly `4-8` recommended primary sources and a smaller follow-up list, not a catalog.

When `set-up` needs structured detail, provide setup-ready records in a collapsible/debug-style section or only on request. Use this structure:

```md
## Primary sources

### {source_name} — {employer}
- URL: ...
- Why it fits: ...
- Board family: ...
- Suggested discovery_mode: ...
- Suggested cadence: ...
- Suggested search terms: ...
- Confidence: ...
- Notes: ...

## Follow-up sources

### ...

## Setup-ready source records (debug detail)

### {source_name}
- employer: ...
- source_name: ...
- source_url: ...
- official_source_type: careers_page | greenhouse | lever | ashby | workday | workable | getro | personio | recruitee | broad_board | other_official
- suggested_discovery_mode: ...
- suggested_cadence: every_run | every_3_runs | every_month
- search_terms: ...
- fit_reason: ...
- confidence: high | medium | low
- integration_follow_up: none | consider_provider | unsupported
- match_rule_suggestion: ...
- notes: ...

## Suggested match rules

Only include this section when one or more broad sources likely need track-specific filtering. Use this shape:

```json
{
  "id": "short_rule_id",
  "source_ids": ["source_id_if_known"],
  "source_names": ["Source Name If ID Unknown"],
  "keep_if_any_text_term": ["term one", "term two"],
  "limitation": "Track filter removed {removed} candidate(s) from this broad source without explicit fit evidence."
}
```

Use concise `source_name` labels that are ready to use as source display names in `sources.json`.

If no strong official sources are found, say so clearly and return only the best follow-up options rather than padding the list.

## Handoff back to `set-up`

- `set-up` should call this skill only after the minimum setup brief is available, the user has been asked for known companies and job boards, and the user wants help finding additional sources.
- `set-up` owns the final source list, confirmation step, normalization, and file writes.
- Treat the output as recommended input to normalize, confirm, and write into `sources.json` and, when needed, `match_rules.json`.
- After this skill returns, `set-up` must continue automatically: ask keep/drop/add, ask cadence changes, infer or confirm filters, and auto-pick canaries unless the user volunteers specific canaries.
- If the user rejects or trims sources, adapt the shortlist instead of rerunning unnecessary discovery.

## Boundaries

- Do not search for individual jobs to report.
- Do not deduplicate against `seen_jobs.json`.
- Do not write track files.
- Do not add new scraping support or test `scripts/discover_jobs.py` unless the user explicitly pivots to repo development.
- If a source looks important but not clearly supported, include it with conservative defaults and note `integration_follow_up: consider_provider` or `unsupported`.
- If future deterministic source support is needed, point implementation to `scripts/discover/sources/`, fixture coverage, and provider contract tests; do not point contributors at editing `scripts/discover_jobs.py`.
