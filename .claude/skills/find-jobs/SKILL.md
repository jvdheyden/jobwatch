<!-- GENERATED FILE: source of truth is .agents/skills/find-jobs/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: find-jobs
description: Extract and filter plausible candidate roles from discovery artifacts, deduplicate against seen_jobs.json, and return a short high-signal candidate list with coverage notes. Use this skill for extraction and filtering, not for final ranking.
---

# Skill: Find Jobs

Use this skill to search sources and extract plausible candidate roles.

This skill is for discovery and extraction, not final ranking.

## Input

Assume the current track provides:
- a set of allowed sources
- preferences for what counts as a match
- a `seen_jobs.json` file for deduplication

Read those files before searching.

If the current track provides `source_state.json`, honor the track's cadence rules and treat `last_checked` as track-owned source state. Do not update source state yourself during a normal scheduled run; the runner updates it from the discovery artifact.

If the track instructions name a discovery artifact path, look for that artifact first.

For this repo:
- treat the scheduled JSON artifact as the default discovery input
- do not invoke `scripts/discover_jobs.py` yourself unless the track explicitly tells you to, or you are debugging discovery infrastructure

Use this discovery order:
1. Read the track-named artifact path for today, if it exists.
2. If that is missing, read the track-named `latest` artifact, if it exists and is fresh for the current run.
3. If a fresh artifact covers the requested source set, use it as the discovery input for enumeration, search-term application, and direct job URL collection.
4. If no usable artifact exists for a source, mark that source as not checked in the coverage notes and note why.

Treat the artifact path from the track instructions as the scheduler-to-agent handoff contract.
During a normal scheduled run, do not rerun `scripts/discover_jobs.py`.

## Discovery workflow

For each allowed source:

1. Check whether a fresh artifact contains coverage and candidates for that source.
2. If yes, use the artifact data and run the extraction steps on the candidate set before deciding final inclusion.
3. If no artifact coverage exists for a source, mark it as not checked in the coverage notes and note why.

When an artifact is used, verify that it is fresh for the current run and covers the sources you are about to treat as checked.

Review the unseen candidates in manageable batches by source or stable slices.
After deduplication and explicit hard exclusions, read each candidate's description
before deciding fit. Track which batches remain; if review is incomplete, name
the unreviewed sources or candidates in coverage notes.

A source is only fully checked if the artifact shows the coverage work that was actually done: the enumeration strategy, search terms applied, and result counts.

Do not broaden to external search engines unless the active track explicitly allows it.

## Execution coverage

Use `tracks/<track>/sources.json` as the source of truth for configured retrieval, not generated `sources.md` prose or terms inferred from preferences, track instructions, or the CV. Resolve each source's effective terms as discovery does:

- Without source `search_terms`, use `track_terms`.
- With `search_terms.mode: append`, combine `track_terms` and the source's terms.
- With `search_terms.mode: override`, use only the source's terms.
- Trim whitespace and deduplicate case-insensitively, preserving the first spelling and order.

Compare the fresh artifact's reported work with that source's configuration and provider strategy, including native filters and limitations. A provider may enumerate a feed and filter locally; `search_terms_tried` does not necessarily mean separate remote queries. An intentionally empty term list for a provider that does not apply terms is not a missing field. If the strategy is unclear, report uncertainty rather than inventing evidence of execution.

Preserve genuine partial or failed execution and identify any missing configured work. Zero matches for one or all applied terms can still be complete. A source override does not have to apply the global terms it replaces. A source not due this run is not an execution gap.

Keep candidate-review limitations explicit too: name unreviewed candidates or missing descriptions that prevent admission, even when deterministic retrieval completed. Do not describe the whole review as finished just because the scraper finished.

## Search-quality observations

Separately compare the effective retrieval configuration with requested role families and domains in the current preferences and track instructions. Report only concrete, plausible gaps: name the requirement, the restrictive terms or filters, and the kind of role that may be excluded. Keyword absence alone is insufficient; consider broader terms, source-specific vocabulary, and whether the preference is a ranking signal or an exclusion rather than a retrieval target. If instructions conflict with preferences, report that conflict instead of assuming a new retrieval requirement.

Put an observation in the affected source's existing coverage limitations, prefixed `Search-quality observation:`. In the structured digest, use `runs[].source_notes[].limitations`; preserve the artifact's execution limitations as well. Do not downgrade otherwise complete execution solely for a search-quality concern. Say a role *may* be missed unless an actual omission is evidenced; zero results alone do not prove a gap.

Example: `Search-quality observation: Preferences include privacy engineering, but this source retrieves only "cryptography". Privacy roles without that term may be missed. Request retrieval reconciliation for this track.`

Do not edit preferences or retrieval configuration, invoke maintenance or a maintenance subagent, or rerun discovery to investigate these observations during a normal run. Maintenance is user-triggered through `set-up`; observations are advisory and cannot guarantee recall.

## Extraction

For each plausible role in the artifact, extract:

- employer
- title
- direct job URL
- source URL
- location
- remote / hybrid / onsite status
- posted date, if visible
- short summary of responsibilities
- short summary of requirements
- notes on uncertainty or missing data

Each candidate in the discovery artifact carries a `description` field with the
fetched JD body, bounded to a shared character budget; `description_truncated`
marks bodies that were cut. Base the responsibilities and requirements
summaries on that field. The `notes` field is enumeration/diagnostic metadata;
do not treat it as the JD body.

If `description` is empty, missing, or unusable (for example, only scripts or
page navigation), record the evidence gap in `Missing / uncertain`. Treat fit
as unknown, not poor, and do not guess responsibilities from the title. If the
gap prevents admission, identify the candidate and missing evidence in coverage
notes rather than silently dropping it.

If a fact is not visible, write `unknown`.

Do not invent details.

## Inclusion rule

Evaluate these questions separately for every candidate, using the active track's preferences as the source of truth:

1. Does the title or the described work plausibly belong to a role family requested by the track?
2. Does the posting satisfy the track's stated domain or keyword requirements?
3. Does a hard constraint or red flag require exclusion?

Include a role only when the combined answers make it a plausible match for the current track. A domain mention alone does not establish role-family fit, and a role-title match alone does not satisfy a required domain constraint. Hard constraints and red flags override otherwise positive evidence.

Use titles and listing snippets only for discovery priority. Do not use a title
keyword allowlist or regex to discard candidates before reading their
descriptions. A missing title keyword is not a rejection reason; assess the
described work against the track's preferences, including equivalent wording.

When in doubt, exclude rather than include.

## Exclude early

Exclude roles that are clearly:
- outside the current track
- generic or weakly related
- duplicates of already seen roles
- too vague to evaluate

## Deduplication

Use the track's `seen_jobs.json` to avoid repeats.

Deduplicate twice:
- when collecting candidate URLs from listings and search results
- again before final output against `seen_jobs.json`

Treat roles as duplicates if the employer and substantially the same title already appear, even if the link or posting date changed.

## Output format

Return a candidate list in this structure:

```md
## Candidate roles

### {{job_title}} — {{employer}}
- Direct link: {{url}}
- Source: {{source_url}}
- Location: {{location}}
- Remote: {{remote_status}}
- Posted: {{posted_date_or_unknown}}
- Responsibilities: {{1-3 sentence summary}}
- Requirements: {{1-3 sentence summary}}
- Missing / uncertain: {{notes}}
- Initial signal: {{high | medium | weak}}

## Coverage notes

### {{source_name}}
- Status: {{complete | partial | failed}}
- Listing pages scanned: {{count_or_unknown}}
- Search terms tried: {{terms_or_none}}
- Result pages scanned: {{per_term_counts_or_none}}
- Direct job pages opened: {{count_or_examples}}
- Limitations: {{brief_note}}

### {{source_name}}
- Status: {{complete | partial | failed}}
- Listing pages scanned: {{count_or_unknown}}
- Search terms tried: {{terms_or_none}}
- Result pages scanned: {{per_term_counts_or_none}}
- Direct job pages opened: {{count_or_examples}}
- Limitations: {{brief_note}}
```

Only return plausible candidates. Keep the list short and high-signal.

## Failure handling

If a source's artifact coverage shows it could not be accessed or parsed:

- note this briefly in the coverage notes
- mark the source as `failed`

If the required coverage fields are missing for a source, treat that source as partial rather than complete.
