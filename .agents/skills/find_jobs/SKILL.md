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

## Procedure

For each allowed source:

1. Open the official jobs or careers page.
2. Identify roles that might match the current track.
3. Open the direct job page for each plausible role.
4. Extract verified facts only.
5. Exclude roles that are already in the seen-jobs file.
6. Return a concise candidate list.

## Extract only these facts

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

## Inclusion rule

Include a role only if it is a plausible match for the current track based on the current track's preferences.

When in doubt, exclude rather than include.

## Exclude early

Exclude roles that are clearly:
- outside the current track
- generic or weakly related
- duplicates of already seen roles
- too vague to evaluate

## Deduplication

Use the seen-jobs file to avoid repeats.

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

Only return plausible candidates. Keep the list short and high-signal.

## Failure handling

If a source cannot be accessed or parsed:

- skip it
- note this briefly in the output
