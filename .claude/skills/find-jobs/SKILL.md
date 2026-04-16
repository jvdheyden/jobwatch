<!-- GENERATED FILE: source of truth is .agents/skills/find-jobs/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: find-jobs
description: Search official job and career pages for plausible roles matching the current track, extract verified facts only, deduplicate against the seen-jobs file, and return a short high-signal candidate list. Use this skill for discovery and extraction, not for final ranking.
---

# Skill: Find Jobs

Use this skill to search sources and extract plausible candidate roles.

This skill is for discovery and extraction, not final ranking.

## Input

Assume the current track provides:
- a set of allowed sources
- preferences for what counts as a match
- a seen-jobs file for deduplication

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

If the track inputs are sparse, use this fallback set:
- `cryptography`
- `cryptographer`
- `privacy`
- `security`
- `protocol`
- `post-quantum`
- `PQC`
- `MPC`
- `zero-knowledge`
- `ZK`
- `FHE`
- `PETs`
- `digital identity`
- `authentication`
- `smart card`
- `embedded security`

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

## Official API evidence

When an official first-party careers API or official board API is the source of the candidate data, treat that API response as posting evidence.

This matters most when:
- the source's job-detail website is blocked by bot protection or WAF
- the helper artifact already captured source-native API fields
- the API is first-party and clearly tied to the official careers source

For IBM in this repo:
- the IBM careers search API is an acceptable evidence source even when the website job-detail page returns an AWS WAF challenge or empty body
- do not exclude an IBM role solely because the direct website page cannot be fetched
- use the IBM API fields that are available, such as title, location, remote/hybrid status, seniority/professional level when present, description snippet, source URL, and matched terms
- mark missing fields as `unknown`
- note clearly that the website detail page was inaccessible, but do not treat that alone as a reason to drop the role

For Google in this repo:
- the official Google careers search payload (`ds:1`) is acceptable evidence for discovery and extraction
- the helper may synthesize a public overview URL from the Google job id and the title slug because the payload's primary URL field points to the apply/sign-in flow
- do not exclude a Google role solely because the synthesized overview URL might be imperfect or might fail to resolve
- if a fallback apply/sign-in URL is present in the artifact, treat it as supporting evidence, not as a reason to drop the listing
- note URL uncertainty clearly when it exists, but keep the role if the payload still provides enough title, location, summary, responsibilities, and requirements evidence to evaluate it

More generally:
- if an official API provides enough information to judge track relevance, practical viability, and uniqueness, you may keep the role in the candidate set even without direct-page HTML
- if the official API evidence is too thin to evaluate the role at all, exclude it and say why

## Inclusion rule

Include a role only if it is a plausible match for the current track based on the current track's preferences.

Use titles and listing snippets only for discovery priority.

Preferred rule:
- final inclusion should normally be based on the full direct posting

Exception:
- if the source's official API is the best available first-party evidence and the direct posting is inaccessible due to bot protection, you may base inclusion on the official API evidence instead
- for IBM, do this by default rather than filtering the role out for missing website access

When in doubt, exclude rather than include.

## Exclude early

Exclude roles that are clearly:
- outside the current track
- generic or weakly related
- duplicates of already seen roles
- too vague to evaluate

## Deduplication

Use the seen-jobs file to avoid repeats.

Deduplicate twice:
- when collecting candidate URLs from listings and search results
- again before final output against the seen-jobs file

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

If the artifact shows the listing or API was accessible but the direct job page was blocked:

- keep candidates that are still evaluable from official API evidence
- record the website-access limitation in the coverage notes
- do not collapse those candidates into `failed` discovery just because the detail page could not be opened

If the required coverage fields are missing for a source, treat that source as partial rather than complete.
