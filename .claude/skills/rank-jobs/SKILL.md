<!-- GENERATED FILE: source of truth is .agents/skills/rank-jobs/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: rank-jobs
description: Evaluate and rank previously found candidate roles against the current track preferences and the candidate profile. Use this skill after discovery to score, compare, and prioritize jobs, not to search for new ones.
---

# Skill: Rank Jobs

Use this skill to score and order candidate roles.

This skill is for evaluation and prioritization, not search.

## Input

Read these files before ranking:
- `profile/cv.md` — the user's CV
- `profile/prefs_global.md` — global preferences
- `tracks/<track>/prefs.md` — track-specific preferences

The candidate roles come from the discovery artifact or the find-jobs skill output for the current run.

Use these files as the source of truth for fit.

## Procedure

For each candidate role:

1. Compare the job against the user's CV and preferences.
2. Score the role holistically on a 1-10 scale.
3. Record concrete reasons for fit.
4. Record concrete concerns.
5. Assign one recommendation:
   - `apply_now`
   - `watch`
   - `skip`

Then return the roles ordered from strongest to weakest.

## What to optimize for

Prefer roles that:
- match the user's strongest skills and experience
- match the current track's priorities
- have clear evidence in the job posting
- are practically viable in terms of seniority, location, and work type

Down-rank roles that:
- are generic
- are weakly aligned
- are too vague
- are poor practical fits

## Evidence discipline

Base the ranking on visible evidence from the posting plus the user's documented profile and preferences.

Limited inference is allowed, but label it clearly with words like `likely` or `appears`.

Do not overrate a role just because the employer is prestigious.

Treat official first-party API evidence as valid posting evidence when that is the best accessible source.

For IBM in this repo:
- use the IBM careers API fields directly when ranking roles
- do not down-rank or discard an IBM role solely because the website job-detail page is blocked by WAF or bot protection
- score the role from the API-visible evidence: title, location, remote/hybrid status, description snippet, seniority/professional level when present, and any matched terms or notes captured in the discovery artifact
- note missing details as uncertainty, but do not turn missing website access itself into a separate concern unless it prevents meaningful evaluation

For Google in this repo:
- use the official Google careers payload evidence directly when ranking roles
- do not down-rank or discard a Google role solely because the synthesized public overview URL might be wrong or might not resolve cleanly
- if the artifact provides a best-effort public URL plus an alternate apply/sign-in URL, treat URL uncertainty as a minor note, not as a core fit concern
- score the role from the payload-visible evidence: title, employer, location, summary, responsibilities, requirements, and matched terms
- only treat the URL issue as material if the payload is too thin to evaluate the role itself

General rule:
- missing website HTML is only a ranking concern when it leaves the role too vague to assess
- if the official API evidence is sufficient to judge fit, rank the role normally

## Output format

Return two JSON arrays matching the digest schema (`shared/digest_schema.md`): `top_matches` for the strongest roles and `other_new_roles` for weaker but notable ones. Omit weak roles unless useful for auditability.

Both arrays must be ordered from strongest to weakest.

### `top_matches[]` entry

```json
{
  "company": "Example Co",
  "title": "Cryptography Engineer",
  "listing_url": "https://example.com/jobs/1",
  "location": "Remote",
  "remote": "remote",
  "source": "IACR Jobs",
  "fit_score": 8.5,
  "recommendation": "apply_now",
  "why_match": [
    "Exact applied-cryptography fit.",
    "Strong zero-knowledge systems emphasis."
  ],
  "concerns": [
    "Appears Vancouver-based rather than clearly remote."
  ]
}
```

Required fields: `company`, `title`, `listing_url`, `fit_score`, `recommendation`, `why_match`.
Optional fields: `job_key`, `alternate_url`, `location`, `remote`, `team_or_domain`, `posted_date`, `updated_date`, `source`, `source_url`, `concerns`.

### `other_new_roles[]` entry

```json
{
  "company": "Example Co",
  "title": "Security Engineer",
  "listing_url": "https://example.com/jobs/2",
  "location": "Berlin",
  "fit_score": 6.5,
  "recommendation": "watch",
  "short_note": "Broad security role, but embedded-systems focus aligns with track."
}
```

Required fields: `company`, `title`, `listing_url`, `fit_score`, `recommendation`, `short_note`.
Optional fields: `job_key`, `alternate_url`, `location`, `source`.
