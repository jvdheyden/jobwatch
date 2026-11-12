---
name: reviewing
description: Review pull requests and local code changes, including revisions; publish reviews and merge PRs when requested.
---

Produce actionable findings about correctness, reliability, security, and repository contracts. Before you start, check if there are existing reports for this PR under `docs/reviews/`.

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
- Complete the authorized actions without asking for confirmation again. If requirements prevent an action, complete other authorized work and report the blocker.

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

## Publishing reviews

- Read the [comment guidelines and templates](../../../.agents/skills/reviewing/references/pr-comments.md) when drafting a GitHub review. Batch findings into one review per pass and continue existing threads for the same issue.
- When authorized, approve (`APPROVE`) only after the reviewed scope is complete, relevant verification is sufficient, and no blockers or material validation gaps remain. Pending or failing required checks prevent approval. Request changes (`REQUEST_CHANGES`) for substantiated blockers within scope; comment (`COMMENT`) for nonblocking feedback, questions, or verification gaps.
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

## Handoff and report

- For substantial or repeated reviews, save a compact checkpoint under `docs/reviews/`: base/head SHAs, scope, findings, reproduction commands, checks and results, and remaining uncertainties.
- Report findings by severity, with file/line references, trigger, impact, and a concise correction direction.
- State which previous findings are resolved, what was verified, and any material limitations. Separate unrelated existing issues from blockers.

## Code quality and scope

- Prefer the smallest complete solution that preserves existing behavior. Check the path from input to consumer, including failure handling and competing conditions; a locally correct function may still produce the wrong overall result.

- Preserve architectural boundaries. In this repo, providers enumerate and extract, track rules filter, and agents evaluate fit. Keep source-family parsing in reusable provider modules rather than adding employer-specific
  branches to generic discovery.

- Reuse existing helpers and contracts when they fit. Flag duplicated parsing, validation, or routing policy that could diverge. Do not demand an abstraction merely because two pieces of code look similar.

- Require new abstractions, configuration options, dependencies, and fallback paths to serve a concrete current requirement. Prefer removing unnecessary complexity over documenting or wrapping it.

- Keep one authoritative definition of each policy. When prompts, deterministic checks, and downstream routing share responsibility, verify that they agree and that precedence is explicit.

- Keep changes focused. Distinguish cleanup needed for the requested behavior from unrelated refactoring; do not make unrelated cleanup a condition of approval.

- Favor tests of observable behavior and meaningful boundary cases. Check whether tests would catch the actual failure, rather than merely restating the implementation or locking down prose.

- Explain the concrete cost of maintainability findings: inconsistent behavior, hidden coupling, difficult extension, or unnecessary operational burden. Personal style preferences are not blockers.
