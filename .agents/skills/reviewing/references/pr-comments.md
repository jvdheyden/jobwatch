# PR comments

Read this when drafting or submitting a GitHub review. Adapt the examples to the evidence; omit empty sections.

## Findings

- Use one finding per thread, anchored to the smallest relevant changed range. Use the review summary for issues without a suitable inline location.
- Lead with the concrete problem. Explain its trigger and consequence, distinguish evidence from inference, and state the required behavioral outcome.
- Be direct and respectful; discuss behavior rather than the author. Clearly label blockers, nonblocking suggestions, and questions. Base severity on impact, not implementation difficulty.
- Read existing discussions before posting. Continue the existing thread when the issue is the same, and verify fixes before describing earlier findings as resolved.
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
