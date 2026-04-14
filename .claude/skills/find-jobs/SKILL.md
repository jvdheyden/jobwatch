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
- if no usable artifact exists, fall back to live source exploration by default
- do not invoke `scripts/discover_jobs.py` yourself unless the track explicitly tells you to, or you are debugging discovery infrastructure
- do not rerun the helper or browse source listings live for a source already covered by a fresh artifact

Use this discovery order:
1. Read the track-named artifact path for today, if it exists.
2. If that is missing, read the track-named `latest` artifact, if it exists and is fresh for the current run.
3. If a fresh artifact covers the requested source set, use it as the discovery input for enumeration, search-term application, and direct job URL collection.
4. Only if no usable artifact exists for a source, fall back to live discovery for that source.

Treat the artifact path from the track instructions as the scheduler-to-agent handoff contract.
During a normal scheduled run, do not rerun `scripts/discover_jobs.py`. Use the artifact if present; otherwise use live source exploration for the uncovered sources.

## Discovery workflow

For each allowed source:

1. Check whether a fresh artifact already contains coverage and candidates for that source.
2. If yes, use the artifact for discovery and skip live source exploration for that source.
3. If no, use the fallback live source exploration steps below.
4. In either case, run the extraction steps on the resulting candidate set before deciding final inclusion.

## Fallback live source exploration

Use this only for sources not covered by a usable artifact.

Before opening role pages, fully explore each allowed source. Do not assume the first listing page is representative.

For each uncovered source:
1. Open the official jobs or careers page.
2. Detect whether the source exposes:
   - a general listing
   - pagination
   - site-native search
   - filters that narrow job families or locations
3. Exhaust the plain listing first:
   - click through all pages if paginated
   - stop only when there is no next page, the page URL repeats, or the visible result set repeats
   - use a safety cap of 20 pages per source view to avoid loops
4. If site-native search exists, run a derived term set and exhaust all result pages for each term.
5. Build a deduplicated set of plausible direct job URLs from the listing and search passes.
6. Open the direct job page for each plausible role.
7. Extract verified facts only.
8. Exclude roles that are already in the seen-jobs file.
9. Return a concise candidate list plus structured coverage notes.

If a site-native search exists but cannot be used reliably, note that and continue with the listing-only pass, but mark the source as `partial` rather than `complete`.

A deterministic scripted helper can satisfy the same completeness bar as manual site-native search when it:
- enumerates the full official source through static HTML, official query URLs, or official/public board APIs
- applies the full relevant term set to the enumerated roles
- records the exact coverage work in a machine-readable artifact

When an artifact is used, verify that it is fresh for the current run and covers the sources you are about to treat as checked.

When that standard is met, you may mark a source `complete` even if you did not manually type into the visible UI search box.

Do not broaden to external search engines unless the active track explicitly allows it.

A source is only fully checked if you can show the coverage work that was actually done.
If a source exposes native search, a listing-only pass is not enough for `complete` status.

## Search terms

Derive search terms from the active track inputs before searching a source.

Build the term set from:
- the track source file's role / keyword section, if present
- the track preferences
- the user's strong-fit profile and CV terms

Normalize and deduplicate terms before searching:
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

Search the source with all relevant terms, not just one.

## Source-family guidance

Use the source's native interaction model when it is visible.

- Greenhouse boards:
  - inspect the default listing page and its pagination state
  - run the full relevant term set in the board's search UI
  - scan all result pages for each term
  - if the board search cannot be executed reliably, mark the source partial
- Lever boards:
  - inspect the full listing
  - use native search or filters if visible
  - do not treat the first visible screen as complete coverage when pagination or lazy loading exists
- Ashby boards:
  - inspect all visible listing groups
  - use native search or filters if visible
  - note clearly when the board exposes only partial results or hidden tabs

If a source family is unfamiliar, prefer conservative completeness checks over optimistic assumptions.

When a scripted helper advertises a source-specific `discovery_mode`, prefer that over ad hoc browsing if it gives more deterministic coverage than the visible UI.

## Extraction

These extraction steps apply to candidates discovered from either:
- a scheduled or live JSON artifact
- fallback live source exploration

For each plausible role, extract:

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

If a source cannot be accessed or parsed:

- skip it
- note this briefly in the coverage notes

If the listing or API is accessible but the direct job page is blocked:

- keep candidates that are still evaluable from official API evidence
- record the website-access limitation in the coverage notes
- do not collapse those candidates into `failed` discovery just because the detail page could not be opened

If pagination exists, do not mark the source as fully checked until pagination has been exhausted or a clear stopping condition has been reached.

If the required coverage fields are missing for a source, treat that source as partial rather than complete.

If native search exists and was not used, or if the search terms tried cannot be shown in coverage notes, treat that source as partial rather than complete.

Exception: if a scripted helper deterministically enumerated the whole source and applied the full term set, use the helper artifact as proof instead of manual search-box interaction.
