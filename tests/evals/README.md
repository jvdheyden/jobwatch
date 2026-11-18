# Opt-in agent quality evaluation

`cases.json` contains three self-contained synthetic scenarios; each supplies a
profile, track preferences and candidate postings. `expectations.json` holds the
separate admission/ranking rubrics, with a rationale for each judgment and a review
status for each scenario. All three rubrics were reviewed by Jonas von der Heyden on 2026-11-15.
New or changed scenarios require their own review. Do not use an unreviewed
rubric as a release gate or put real profile data here.

| Scenario | What it exercises |
| --- | --- |
| `crypto_engineering` (8 jobs) | Technical fit behind an understated title, adjacent privacy work, remote constraints, uncertain location, irrelevant keyword matches and embedded instructions. |
| `security_sales` (6 jobs) | Sales as a desired role family, cybersecurity as a required domain, quota ownership versus presales, and rejection of engineering/marketing work. |
| `public_service_entry` (7 jobs) | Entry-level public-service work, transferable education, explicit experience/language/credential requirements, location constraints and missing location evidence. |

The crypto and sales scenarios contain **identical** `protocols` and `sales`
postings. Both expected decisions reverse between those tracks. A model that always
prefers engineering, or always rejects sales, must fail one scenario. Shared job
IDs identify the same evidence; judgments are scoped by scenario. These examples
broaden coverage beyond crypto but do not establish quality for every possible track.

## Running an evaluation

Run separately from pytest and PR verification, when changing find-jobs, rank-jobs,
or their model configuration. No model invocation is built into the scorer.

1. Select one scenario from `cases.json`. Give the agent only that scenario and
   the production find-jobs/rank-jobs skill instructions, in a fresh isolated
   session. Keep `expectations.json`, the other scenarios and previous judgments
   out of its context and accessible workspace. Do not use a real local track.
2. State that this is a bounded semantic evaluation: `profile` supplies the CV
   evidence, `preferences` supplies the global/track requirements, and each job's
   `description` supplies the complete available posting evidence. All jobs are
   unseen; no additional profile facts, web requests, discovery or applications are
   permitted. This evaluates semantic decisions; the ordinary workflow E2E tests
   cover reading real artifacts and orchestrating stages.
3. Run find-jobs first. Preserve admission decisions, exclusions and explicit
   uncertainties by candidate id before ranking. Run rank-jobs only on admitted
   candidates and those retained for review. Do not let ranking retrospectively
   hide a find-jobs miss. Keep both raw stage outputs.
4. Normalize the two stages into one result per scenario. `admit` means retained,
   `filter` means explicitly excluded, and `review` means retained with unresolved
   evidence. Use score 1 as a bookkeeping value for filtered candidates, since
   rank-jobs does not evaluate them. Do not silently turn unaccounted-for candidates
   into exclusions: missing judgments are an incomplete evaluation and must fail.
5. Repeat with three fresh sessions for **each** scenario. Record provider, model,
   reasoning setting, skill revision, dataset id, date and raw outputs under local
   `artifacts/evals/<scenario>/`. Never carry one scenario's context into another.

A normalized result has this shape (the example shows one judgment; a real result
must include every candidate in the selected scenario exactly once):

```json
{
  "dataset_id": "jobwatch-tracks-v1",
  "scenario_id": "security_sales",
  "judgments": [{"id": "sales", "admission": "admit", "score": 9}]
}
```

Score each result against the explicitly selected scenario:

```bash
./.venv/bin/python tests/evals/score_jobs.py --scenario security_sales \
  artifacts/evals/security_sales/run-1.json
```

The scorer rejects mismatched dataset/scenario identities, foreign/duplicate/missing
candidate ids and malformed scores. Exit status is 0 for meeting the selected
rubric, 1 for semantic/ranking mismatches, and 2 for invalid input. A 0 from a draft
rubric is **not human validation**: the report carries its review status. The prior
crypto-only draft format is superseded; rerun it with the explicit scenario context.

## Reviewing expectations and results

Review each scenario's profile, preferences and complete posting text first. Then
check its rubric's admission decisions, score ranges, `critical_recall` flags and
`ordered_pairs`. A pair `[a, b]` requires `a` to score at least as highly as `b`;
ties are allowed. The rationale explains the evidence for each proposed decision.
Score ranges allow variation; generated prose is never compared.

A human reviewer should confirm or correct each scenario independently, then record
`review_status: reviewed` and a `review_note` naming the reviewer and review date
on that scenario. Changes to its evidence or judgments require renewed review;
substantive dataset revisions need a new dataset id so old results cannot be
mistaken for current evidence. Never adjust expectations simply to match a model's
latest output.

Inspect critical false negatives first, then false positives, uncertainty handling,
score-band violations and ranking reversals. An unexpected `review` decision is a
rubric issue, but only exclusion of a critical candidate counts as a critical false
negative: a retained candidate has not been lost. Compare all three runs per scenario
with the prior model/skill revision. Inspect the shared-posting contrasts explicitly;
a good crypto result cannot cancel a bad sales result. There is deliberately no
aggregate score that could conceal an underperforming track. A single pass is not
evidence of stable quality. Add a small reviewed scenario when a real failure
exposes an uncovered kind of preference or constraint.
