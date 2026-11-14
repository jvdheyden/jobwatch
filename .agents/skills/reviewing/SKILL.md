---
name: reviewing
description: Review PRs and local changes, including revisions; publish reviews and merge when requested.
---

Review for **correctness**, **code style**, and **product fit**. Report substantiated issues, not speculative concerns. No findings is a valid outcome.

## Authorization

Follow the user's requested scope. Reviewing permits a chat report; posting, approving, requesting changes, and merging require authorization. Approval does not authorize merging. Respect explicit restrictions, and do not ask for confirmation already given.

## Review

1. Read the request, relevant repository contracts, prior `docs/reviews/` reports, and existing PR discussions. Pin the base and head commits. On follow-ups, verify earlier findings and review changes since the last reviewed head; expand scope if affected code or the base changed.
2. Assess:
   - **Correctness:** Does the change solve the problem without regressions, including relevant failure cases? For changed behavior or tests, apply `.agents/skills/testing/SKILL.md` to assess test adequacy and required provider contracts.
   - **Code style:** Is this the simplest clear solution consistent with repository conventions? Keep providers responsible for extraction, track rules for filtering, and agents for fit evaluation.
   - **Product fit:** Does the behavior meet the user need and intended workflow? Flag unresolved product decisions.
   - **Architectural fit:** Check changes against `docs/architecture.md`. Flag violations of component responsibilities or boundaries as blockers unless explicitly authorized. Updating the documentation is not authorization.
3. Trace affected execution paths and callers. Distinguish introduced or in-scope issues from unrelated existing ones. For each finding, give its trigger, impact, supporting evidence, and desired correction. Avoid cosmetic and speculative findings.
4. Run focused checks first using `.venv` for Python. Run `scripts/test.sh` for broad changes, material integration uncertainty, or merge validation; equivalent passing CI must cover the reviewed commit. State material verification gaps.

## Record and response

Start or extend a **local** record at `docs/reviews/pr-<number>.md` (or a dated file for local changes) for every review pass. Preserve previous entries. Each timestamped entry should contain the request and authorized actions, agent/session ID when available, base/head SHAs, summary and verdict for all three criteria, findings and prior-finding dispositions, tests and evidence, external actions and outcomes, limitations, and next steps. Include links to existing discussions. Update before handoff.

In chat, briefly summarize the change and recommendation, give a verdict for each criterion, list actionable findings by severity with locations, and finish with verification, limitations, and any GitHub outcome.

## Publishing

Publish only when authorized. Check existing comments and reviews first; do not repeat unchanged findings or verdicts. Update the existing thread for materially new evidence where possible. Follow [PR comment guidelines](references/pr-comments.md) and batch new findings into one review.

- `APPROVE`: complete review, sufficient passing verification, no blockers or material gaps.
- `REQUEST_CHANGES`: substantiated blocking issues, when authorized.
- `COMMENT`: nonblocking findings, questions, or validation gaps, when authorized.

Before publishing, refresh the head and relevant base, inspect changes, and anchor the review to the reviewed commit. Confirm the outcome; after an ambiguous failure, check GitHub before retrying.

## Merging

Merge only when authorized and the review is complete, with no unresolved blockers or material gaps. Immediately beforehand, recheck head/base, PR state, conflicts, required checks, and review requirements. If the revision changed, review the delta first; report merge blockers without inventing conflicts or publishing unauthorized feedback.

Use a head-SHA guard (`expected_head_sha` or `--match-head-commit`) and **rebase** by default unless the user directs otherwise. Respect repository protections and merge queues; never bypass them. Confirm the result before reporting it. Do not delete branches without separate authorization.
