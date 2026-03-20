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
Then provide the roles in ranked order.

## Digest guidance

When this ranking is used for a digest:

- keep only the strongest roles in the main section
- place weaker but still notable roles separately
- omit weak roles unless useful for auditability
