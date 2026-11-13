<!-- GENERATED FILE: source of truth is .agents/skills/reviewing/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: reviewing
description: Review pull requests and local code changes, including revisions; publish reviews and merge PRs when requested.
---

Produce actionable findings about correctness, reliability, security, and repository contracts. Before you start, read existing reports for this PR under `docs/reviews/` and begin the mandatory review record described below.

## Requested actions

Determine the authorized actions from the user's request and prior session instructions before starting. These are examples, not required keywords:

| Request | Authorized actions |
| --- | --- |
| "Review PR 24" | Review and report in chat. |
| "Post your findings on PR 24" | Publish comments, without approving or requesting changes. |
| "Approve if ready; otherwise comment" | Approve or comment. |
| "Submit a GitHub review: approve if ready, request changes for blockers, or comment if inconclusive" | Choose and submit the appropriate review outcome. |
| "Review and merge PR 24 if ready" | Review and merge when requirements are met; request changes for confirmed merge conflicts. Report other blockers in chat unless publication is also authorized. |
| "Approve and merge if ready; otherwise request changes" | Approve and merge when ready, or request changes for substantiated blockers. |

- Approval and merging are separate actions. Approval alone does not authorize merging. A merge request includes permission to request changes for confirmed merge conflicts; other review publication follows the requested scope. Explicit limits such as "do not post" take precedence, and prior session authorization still applies.
- Complete the authorized work without asking for confirmation again. Publication still follows the duplicate-feedback rules below: permission to publish does not require a submission on every PR. If requirements prevent an action, complete other authorized work and report the blocker.

## Review criteria

Assess every change against all three criteria below. Base conclusions on evidence; "no issues found" is a valid outcome. State any limits on what you could assess.

- **Correctness:** Verify that the change solves the stated problem without regressions. Follow the affected paths from input to consumer, including edge cases and failure handling. Check that tests cover observable behavior.

- **Code style:** Prefer clear code, established repo patterns, and the smallest complete solution. Flag unnecessary complexity, duplication, or unrelated changes when they have a concrete cost. Preserve the repo's boundaries: providers enumerate and extract, track rules filter, and agents evaluate fit. Personal style preferences are not blockers.

- **Product fit:** Assess whether the resulting behavior serves the intended user need and fits the repo's purpose and workflows. Check defaults and tradeoffs against the stated requirements, and surface unresolved product decisions.

## Scope and evidence

- Pin the base and head commits. Check whether the head changed before reporting.
- For follow-up reviews, read previous findings and inspect the changes since the reviewed commit, including affected callers. Expand the review when the base or scope changed.
- Distinguish introduced regressions, incomplete fixes within the PR's stated scope, and unrelated existing issues. Only the first two normally justify blocking the PR.
- Support findings with a concrete trigger, consequence, and reproduction or clear execution path. Label uncertainty; omit speculative objections and stylistic preferences. Finding no issues is a valid outcome.
- Use documented contracts and relevant tests to establish intended behavior. Surface unresolved product-policy questions explicitly.

## Verification

- Use the repo-local `.venv` for Python checks.
- Run focused tests and reproductions first. Run `scripts/test.sh` for broad changes, unresolved integration risk, or final merge validation. Equivalent passing CI checks must cover the reviewed commit.
- Distinguish actual discovery, mocked reviewer output, and live model evaluation. Do not describe one as another.
- Stop expanding checks once the affected behavior is covered and no material concern remains unresolved.

## Mandatory review record and handoff

- Every review takeover or follow-up must create or extend a detailed record under `docs/reviews/`, including review-only work and passes that publish nothing. Start the entry when taking ownership and update it as work proceeds, before handoff or the final response.
- Use an existing per-PR report where available; otherwise create `docs/reviews/pr-<number>.md`. For local changes without a PR, use a descriptive dated filename. Add a timestamped entry for each pass, identify the agent and resumable session ID when available, and preserve earlier entries. Link prior reports rather than replacing their history. Keep these records local; do not change their gitignore policy or force-add them.
- Document all review actions and their purpose, evidence, and outcome. Related read-only inspections may be grouped if their scope and conclusions remain explicit; do not omit failed attempts or recovery actions. Record evidence-based decision justifications, not private reasoning transcripts or secrets.

Each entry must include:

- **Request and starting state:** user request, authorized actions, PR URL (or local scope), pinned base/head commits, prior reports, and links to existing discussions with each finding's current disposition.
- **Executive Summary:** Give concise summary of what the PR wants to achieve and then your verdict/recommended action incl. short justification.
- **Inspection:** files and execution paths examined, what the inspections established, and why the reviewed scope is sufficient. Distinguish issues introduced by the change from pre-existing issues.
- **Verification:** commands and reproductions, relevant inputs, results, failures, tool limitations, and recovery actions. Distinguish actual discovery, supplied/mocked outputs, and live model evaluation. Include enough reproduction detail or durable supporting artifacts to reproduce the result after temporary files are deleted; a `/tmp` path alone is insufficient.
- **Assessment:** a brief conclusion and supporting evidence for each [review criterion](#review-criteria), findings accepted or rejected, severity, correction direction, and which previous findings are fixed, unchanged, or still uncertain.
- **Action decisions:** justification for publishing, approving, requesting changes, merging, or taking no external action, including comparison with existing feedback and verification sufficiency.
- **External mutations:** before each action, record the intended operation, authorization, target commit, and justification. Afterward, record the actual result, URL/identifier, and confirmation, including failures or ambiguous outcomes and how they were resolved. This applies to comments, reviews, thread changes, and merges.
- **Handoff:** remaining uncertainties, limitations, concrete next steps (or that none remain), and final review/publication state.

## Required final response

- Begin with a brief executive summary of the intended change, overall findings, and acceptance recommendation.
- Then give a brief verdict for each [review criterion](#review-criteria): **Correctness**, **Code style**, and **Product fit**. Keep each verdict to one sentence where possible.
- Follow with actionable findings by severity, including file/line references, trigger, impact, and correction direction. Identify resolved previous findings and separate unrelated existing issues from blockers.
- Finish with relevant verification, material limitations, and any publication or merge outcome.
- Before sending, check that the executive summary and all three verdicts appear in the final chat response itself.

## Publishing reviews

- Before deciding to publish, read existing GitHub comments, reviews, and threads alongside local reports. Compare proposed feedback by its underlying issue and conclusion, not wording or author; top-level and inline comments both count as existing findings.
- Do not republish an unchanged finding or verdict, including through a formal review. Publish only for a new finding, materially new evidence, a new or changed conclusion, or an explicit request to change review status. The absence of a formal review does not make an already documented finding or verdict new. Broad permission to comment, approve, or request changes is not an explicit status-change request. A new commit or another reproduction with the same result does not by itself justify repeating a finding.
- For a meaningful update to an existing finding, continue its thread where possible and explain only what changed. If an explicit status-change request requires a formal review, link existing findings without repeating their explanations. Do not create a second finding thread merely because the original was a top-level comment.
- Read the [comment guidelines and examples](../../../.agents/skills/reviewing/references/pr-comments.md) when drafting a GitHub review. Batch new findings into one review per pass. When no publication is warranted, record why locally and report that outcome in chat; the review is complete without a GitHub submission.
- When publication is warranted and authorized, approve (`APPROVE`) only after the reviewed scope is complete, relevant verification is sufficient, and no blockers or material validation gaps remain. Pending or failing required checks prevent approval. On approval, no further comment on GitHub is necessary. Request changes (`REQUEST_CHANGES`) for substantiated blockers within scope; comment (`COMMENT`) for nonblocking feedback, questions, or verification gaps.
- Refresh the PR's head and relevant base before submission; review any intervening changes. Anchor the review to the reviewed `commit_id`; this identifies the reviewed revision but does not lock the branch.
- Confirm the published outcome and URL. After an ambiguous timeout, inspect existing reviews before retrying. Report the outcome and link in chat; if publication fails, report the failure and preserve the prepared review.

## Merging

- When merging is authorized, finish the review and relevant verification first. Merge only with no unresolved blockers or material validation gaps; a passing test suite alone is not a completed review.
- Immediately before merging, refresh the head, base, PR state, required checks, and review status. The PR must be open, ready for review, conflict-free, and satisfy repository merge requirements. If the reviewed head or relevant base changed, review the delta and refresh affected checks first.
- If confirmed merge conflicts prevent merging, submit a Request changes review asking the author to rebase onto the current target branch, resolve the conflicts, and rerun relevant checks. Identify conflicting files when available, and avoid repeating an existing request for the same unresolved conflicts. Unknown mergeability or pending checks alone are not evidence of conflicts. Do not resolve conflicts or rewrite the author's branch unless asked.
- Use a merge operation guarded by the reviewed head SHA: `expected_head_sha` in the GitHub plugin or `--match-head-commit` with `gh pr merge`. If the guard rejects the merge, review the new revision before retrying; never simply substitute the latest SHA.
- Use **rebase** by default: `merge_method: "rebase"` in the GitHub plugin or `--rebase` with `gh pr merge`. Honor an explicit user override; if repository rules disallow rebase, report the constraint rather than silently selecting another method.
- Use a required merge queue rather than bypassing it. Do not use administrative overrides or change protection rules to force a merge; do not enable auto-merge for unmet requirements unless the user requested it.
- Confirm the actual result. After an ambiguous timeout, check PR state before retrying. Report merged, queued, or blocked accurately, with the PR URL and merge commit when available. Explicit branch deletion requires separate authorization.
