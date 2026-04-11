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

Assume the current track provides:
- the candidate roles
- the user's CV
- global preferences
- track-specific preferences

Use those files as the source of truth for fit.

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

Use this structure:

```md
### {{job_title}} — {{employer}}
- Link: {{url}}
- Fit score: {{score}}/10
- Recommendation: {{apply_now | watch | skip}}

Why it fits:
- {{reason_1}}
- {{reason_2}}
- {{reason_3}}

Concerns:
- {{concern_1}}
- {{concern_2}}

Overall judgment:
{{2-3 sentence summary}}
```

Then provide the roles in ranked order.

## Digest guidance

When this ranking is used for a digest:

- keep only the strongest roles in the main section
- place weaker but still notable roles separately
- omit weak roles unless useful for auditability
