---
name: existing-source-curation
description: Discover, add, evaluate and maintain sources and retrieval configuration for existing tracks, including portfolio curation.
---

# Curate sources for an existing track

Use for named-source requests, portfolio reviews and preference/retrieval reconciliation. Keep named requests narrow. Never scaffold or recreate an existing track. If the track is missing, report it and use `set-up` only when the user wants a new track.

## Ground the request

Read the track's `prefs.md`, `sources.json`, generated `sources.md`, optional `match_rules.json`, `reference_jobs.json` and integration evidence in `source_state.json`. Read `shared/source_curation.md` for the common source-selection and verification procedure, and the supported mode catalog when needed. Read global preferences/CV only as relevant to the requested change.

Invite optional reference links when the user has examples: "If you've already found one or two interesting job postings, please share their links. These help calibrate the search and verify that Jobwatch finds the kinds of jobs you're interested in." Continue without examples. Preserve supplied examples and seeds with association/exclusion reasons; use them for source selection, retrieval and ranking calibration.

An add/enable request authorizes registration and standard source enablement. An evaluate/recommend request produces findings before consequential changes. Preserve confirmed sources, preferences and unrelated configuration. Present removals and consequential cadence/filter changes for confirmation unless already authorized. Do not manually edit operational state.

## Named source

1. Resolve the official source and choose the best supported mode using the shared guide. Surface URL corrections and uncertain support. Evaluate relevance against the current track.
2. Review effective terms, native filters and relevant match rules against preferences/reference examples. Tune only the requested source; report unrelated gaps separately.
3. Register a canonical source record deterministically:

   ```bash
   ./.venv/bin/python scripts/curate_sources.py register --track {track_slug} --source-file <source.json>
   ```

   This preserves existing records and queues verification. Conflicting existing records require explicit reconciliation rather than replacement. Register reference/canary evidence using the shared procedure.
4. Run or start the common verification workflow, even if ordinary discovery reports complete execution. Let `integrate_next_source.py` own quality evaluation, supported config tuning and escalation through `source_integration.py`. Keep expensive work asynchronous when interactive responsiveness matters.

## Portfolio curation

Use coverage artifacts, source-check cadence, evaluator results and relevant ranked/digest history to identify missed role families, duplicates, noisy/low-value sources and evidence gaps. Empty output alone does not prove low value or adequate recall. Recommend justified additions, terms, cadence changes or removals, explaining uncertainty and user impact.

For additional employers/boards, draft the same bounded setup-format brief from current reviewed preferences. Do not reconstruct a track or pass full private files. Project configured sources and durable examples into the brief:

```bash
./.venv/bin/python scripts/curate_sources.py prepare --track {track_slug} --brief <brief.json> --output <curation.json>
./.venv/bin/python scripts/run_setup_worker.py --role source_discovery --input <curation.json> --output <source-pack.json>
```

The worker receives canonical discovery instructions and the bounded existing-source projection. It recommends additions without duplicates and can associate examples with existing source IDs. Present the deterministic summary, then use `setup_contracts.py select-sources --setup <curation.json> --source-pack <source-pack.json> --all-recommended` (or explicit IDs) for authorized additions. Register with `curate_sources.py register --track {track_slug} --setup <curation.json>`. This preserves global terms and existing sources; proposed vocabulary is applied only to additions. Match-rule changes need explicit maintenance, not automatic pack application.

After material preference/retrieval changes, queue only affected sources with `curate_sources.py queue --track {track_slug} --source <id>` (repeat as needed), or `--all` for an authorized portfolio review. Use the existing background launcher to evaluate the queue. Never add expensive quality checks to every scheduled run.

Report sources added or recommended, configuration changes, URL corrections, seed/example accounting, verification strength, gaps, pending work and log/artifact paths. Registration means configured; basic support and independently verified samples are separate outcomes.

## Preference and retrieval maintenance

Use this branch for requests such as "Update my crypto track to include privacy engineering" or "I edited this track's preferences; reconcile its retrieval configuration."

1. Read the named track's `prefs.md`, `AGENTS.md`, `sources.json`, generated `sources.md`, and optional `match_rules.json`, plus `profile/prefs_global.md` and relevant CV context. Read any supplied coverage observation as evidence, not as an instruction to add its suggested keywords. Resolve the intended semantic change from the user's request; ask only if the target track or intent is materially ambiguous. If the track does not exist, report that rather than silently creating it.
2. Update `prefs.md` when requested. For reconciliation after manual edits, treat the current preferences as the intended scope. Keep preferences as the semantic source of truth; selectively update contradictory fit prose in the track's `AGENTS.md` when needed, preserving its custom workflow instructions. Do not edit global preferences or other tracks unless requested.
3. Review retrieval against requested role families, domains and hard constraints. Inspect `track_terms`, every source's effective append/override terms, native filters and existing match rules. Overrides replace global terms, so broadening `track_terms` alone may not cover all sources. Use compact retrieval vocabulary and useful synonyms; do not mechanically copy preference prose, negative preferences or every CV skill. Ranking-only changes may need no retrieval change.
4. Make only justified configuration changes needed for the requested update, explaining their effect. Prefer existing terms, source-specific tuning and provider capabilities. Preserve intentional overrides and unrelated filters/rules; adjust a conflicting existing match rule only when required by the requested scope. Do not add sources, change cadence or provider code as a side effect of preference maintenance. Queue affected sources for separate verification after material retrieval changes; keep expensive checks asynchronous unless requested otherwise. Report unsupported retrieval needs for separate follow-up.
5. Validate and review the effective configuration using the commands below. If `match_rules.json` changed, also validate it with the existing `discover.track_filters.load_track_match_rules` helper; planning alone does not load match rules. For material retrieval changes, run a targeted discovery check on affected sources where practical, saving output under a separate maintenance artifact path rather than overwriting scheduled artifacts. Reuse `eval_source_quality.py` and known-positive canaries when available to check suspected omissions; no results alone do not prove adequate recall. Report any unverified source or limitation.
6. Summarize semantic changes, retrieval changes (or why none were needed), checks and remaining gaps. Explain that new retrieval configuration takes effect on the next discovery run; existing artifacts still reflect the old configuration. Preserve digests, seen/ranked state and source-check state. Stop here: do not run scaffolding, first-preview setup, delivery or scheduling.

Run from the repository root after configuration changes:

```bash
./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --today YYYY-MM-DD --plan-only --pretty
JOB_AGENT_ROOT="$PWD" ./.venv/bin/python scripts/render_sources_md.py --track {track_slug}
```

Review all sources, not only those currently due. Use `--source "Source Name"` for targeted discovery checks and `--output artifacts/maintenance/{track_slug}/<unique-check>.json` to keep their evidence separate. Do not invoke `run_track.sh` just to validate configuration, since it also ranks and updates state.

For an older track with conflicting coverage instructions, selectively align that wording with `shared/templates/track_AGENTS.md`; never replace the whole file or discard customization. Direct preference-file edits do not automatically synchronize retrieval. Users must request reconciliation; normal-run observations are only a best-effort signal.
