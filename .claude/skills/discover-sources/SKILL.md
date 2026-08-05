<!-- GENERATED FILE: source of truth is .agents/skills/discover-sources/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: discover-sources
description: Find employers and official job-board sources for a new job-search track from a bounded setup artifact and return a validated source pack.
---

# Skill: Discover sources for a new track

Use this skill only for source discovery during new-track setup. It does not scaffold tracks, search for individual jobs, rank roles, probe canaries, or integrate source code.

## Preconditions and input boundary

The minimum brief must already exist in a validated v1 `jobwatch_setup` artifact and include:

- track display name, slug, and broad search area
- goals or role types
- keep-only keywords or explicit none
- constraints or red flags or explicit none
- geography or remote preferences or explicit none
- the reviewed bounded profile projection
- any source seeds supplied by the user

The fresh `source_discovery` worker receives `setup.json` as its only user-specific input. Do not request or read the setup transcript, full CV, global preferences, track files, environment, delivery config, or credentials. If the brief is incomplete, return control to `set-up` rather than guessing from a track name.

## Discovery rules

- Prefer official employer careers pages and clearly first-party hosted boards.
- Exclude current and recent employers listed in the setup artifact.
- Preserve good user-supplied official seeds unless they conflict with explicit preferences.
- When a homepage is known, inspect its careers navigation before broader search.
- Accept official Greenhouse, Lever, Ashby, Workday, Workable, Getro, Personio, Recruitee, and comparable boards when clearly tied to the employer.
- Do not use third-party aggregators unless the track explicitly requires one.
- Recommend at most eight primary and four follow-up sources. Do not pad a weak list.
- Validate at most three URLs in this phase. Stop after one failed or oversized fetch.
- Use only discovery modes listed in the runner's fixed prompt. Prefer `html` when a source is official but its board family is uncertain.
- Default to `every_3_runs`; use `every_run` only for unusually valuable or fast-moving sources and `every_month` for slower/broad follow-up sources.
- Put source-specific search terms and native filters in the source record.
- Suggest match rules only for broad/noisy ecosystem, public-service, community, or multi-employer boards—not normal employer boards.
- Do not run `discover_jobs.py`, source-quality evaluation, canary probing, or source integration.

## Structured output contract

Return exactly one JSON object with no prose or Markdown fences. It must contain:

- `schema_version: 1`
- `kind: "jobwatch_source_pack"`
- the exact `setup_id` and required setup `input_hash`
- bounded `track_terms`
- `recommended_sources` and `follow_up_sources`
- `dropped_sources` and at most three `url_corrections`
- `match_rule_suggestions`
- `recommended_source_ids`
- only genuinely unresolved `decisions_needed`

Each source is already shaped like a canonical `sources.json` record:

```json
{
  "id": "stable_source_id",
  "name": "Source display name",
  "url": "https://official.example/jobs",
  "discovery_mode": "html",
  "cadence_group": "every_3_runs",
  "search_terms": {
    "mode": "append",
    "terms": ["privacy engineer"]
  },
  "filters": {
    "location": ["Europe"]
  },
  "fit_reason": "One short preference-grounded reason.",
  "confidence": "high"
}
```

Omit `search_terms` and `filters` when empty. Confidence is `high`, `medium`, or `low`. Source ids are stable lowercase underscore identifiers; cadence is `every_run`, `every_3_runs`, or `every_month`.

Dropped records use `name`, nullable `url`, and `reason`. URL corrections use `original_url`, `corrected_url`, and `reason`. Match-rule suggestions use the canonical fields `id`, `source_ids`, `source_names`, `keep_if_any_text_term`, and optional `limitation`.

The runner rejects unknown fields, unsafe URLs, unsupported modes, invalid ids/enums, excluded employers, duplicate ids, excess source counts, wrong hashes, secret-like keys, and oversized output before writing `source-pack.json`.

## Coordinator handoff

The runner renders the human-facing summary deterministically after validation. The coordinator should not reproduce the worker transcript or dump raw records. It presents the recommended package, records confirmed ids and accepted broad-source rules in `setup.json` with `scripts/setup_contracts.py select-sources`, and continues to deterministic scaffolding.

If no strong official sources exist, return an empty primary list and only credible follow-up options; say why through the bounded dropped/follow-up fields rather than padding the recommendation.
