# PR comments

Read this when drafting or submitting a GitHub review. Adapt the examples to the evidence; omit empty sections.

## Decide whether to publish

Apply the publication rules in [the reviewing skill](../SKILL.md) before choosing a template. Detailed investigation, repeated verification, and the justification for every action belong in the mandatory local review record. GitHub feedback should add information or carry out an explicitly requested status change.

| Situation | GitHub action | Local record |
| --- | --- | --- |
| An unchanged blocker already appears in a comment; broad permission to choose review outcomes | None, even if no formal change request exists | Link the finding, record verification and why publication would duplicate it |
| Another reproduction confirms the same trigger and impact | None | Record the reproduction and result |
| New evidence materially changes an existing finding's impact or correction | Update the existing thread where possible; describe the delta only | Record the evidence and why the update matters |
| A revision fixes a previous blocker | Publish the verified change in conclusion when authorized; approve only after completing the review and checks | Record the fix, checks, and remaining findings |
| The user explicitly asks to set the review status to Request changes for an already documented blocker | Submit a brief formal review linking the existing finding | Record the explicit authorization and confirmed result |
| A first review finds no blockers, or identifies a new blocker | Approve or request changes when authorized and verification permits | Record the full assessment, verification, and publication result |
| The same verdict is already published and nothing material changed | None | Record the follow-up and why no external action was warranted |

For example, rechecking the unchanged credential-helper blocker on PR #21 or the routing blocker on PR #24 should produce a detailed local entry and no new GitHub comment or review. Broad permission to "comment/approve/request changes as you see fit" does not change that outcome.

## Findings

- Use one finding per thread, anchored to the smallest relevant changed range. Use the review summary for issues without a suitable inline location.
- Lead with the concrete problem. Explain its trigger and consequence, distinguish evidence from inference, and state the required behavioral outcome.
- Be direct and respectful; discuss behavior rather than the author. Clearly label blockers, nonblocking suggestions, and questions. Base severity on impact, not implementation difficulty.
- For an existing issue, post only a meaningful update allowed by the publication rules above, continuing its thread where possible. Verify fixes before describing earlier findings as resolved.
- Suggest an implementation only when it helps; allow other correct solutions. Omit generic praise, cosmetic objections, and investigation transcripts.

```markdown
[P2 · blocking] <Specific problem>

When <condition>, <actual behavior>. This causes <consequence>.

<Minimal reproduction or direct evidence, when useful.>

Please <required behavioral correction>.
```

Example:

> **[P2 · blocking] Navigation volume overrides the enumeration defect**
>
> With 121 navigation links and zero candidates, `result_volume` fails. With a supplied blocking `no_postings` defect, the ticket still selects `config_native_filters`, sending the integration loop toward filters instead of fixing enumeration.
>
> Please preserve the confirmed enumeration defect through both failure-mode and strategy selection. A regression test above the 120-link threshold would cover this interaction.

## Review summary

Keep the summary brief; do not repeat inline findings in full.

```markdown
Reviewed `<head SHA>` against `<base SHA>`.

<Verdict and concise reason, including remaining blockers if any.>

Verification: <commands or CI checks and results>.
Limitations: <material checks not performed or unresolved uncertainty>.
Previous findings: <verified fixes and any remaining issues, for follow-ups>.
```

For an explicitly requested formal status change with no new finding, use a minimal reference instead of repeating the explanation:

```markdown
Reviewed `<head SHA>`. Requesting changes for the unresolved [existing finding](<comment URL>), as requested.
```
