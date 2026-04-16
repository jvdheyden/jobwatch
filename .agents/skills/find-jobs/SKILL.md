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

A source is only fully checked if the artifact shows the coverage work that was actually done: the enumeration strategy, search terms applied, and result counts.

Do not broaden to external search engines unless the active track explicitly allows it.

## Search terms

Derive the expected term set from the active track inputs when evaluating artifact coverage.

Build the term set from:
- the track source file's role / keyword section, if present
- the track preferences
- the user's strong-fit profile and CV terms

Normalize and deduplicate terms:
- keep both common phrases and abbreviations when both matter
- prefer compact, high-signal terms over long natural-language queries
- avoid terms that are obviously too broad for the track

Use the term set to judge whether the artifact's coverage for a source is complete or partial.

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

If a fact is not visible, write `unknown`.

Do not invent details.

## Inclusion rule

Include a role only if it is a plausible match for the current track based on the current track's preferences.

Use titles and listing snippets only for discovery priority.

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
