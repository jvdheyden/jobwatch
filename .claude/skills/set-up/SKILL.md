<!-- GENERATED FILE: source of truth is .agents/skills/set-up/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: set-up
description: Set up a new search track for the job-agent.
---

# Skill: Set up a new track for the job-agent

Use this skill to scaffold a new track over the shared job-agent workflow.

Default assumption:
- Set-up includes source normalization, preference-derived terms/filters, canary collection, targeted probing, and quality triage for newly added or materially changed sources.
- Reuse the shared scripts in `scripts/`.
- Tune source-specific config before adding discovery code.
- New source-integration code should live in a provider module under `scripts/discover/sources/`; keep `scripts/discover_jobs.py` as the CLI compatibility entrypoint.
- Use `docs/discovery_modes.md` as the generated reference for supported `discovery_mode` values.
- Do not invoke source integration from normal scheduled track runs.

## Workflow

### Step zero. Make local profile files ready

Before creating or expanding a track, proactively make the local profile files usable:

- `profile/cv.md`
- `profile/prefs_global.md`

These files are local user data and are ignored by Git. Setup writes local `profile/` files only. Never edit `.agents/skills/set-up/templates/profile/*`.

If either profile file is missing, run or recommend:

```bash
bash scripts/setup_machine.sh
```

Treat a profile file as still default if it contains `JOB_AGENT_PROFILE_TEMPLATE`.

For `profile/cv.md`:
- If it is filled, use it as the primary CV context.
- If it is still default, check whether a PDF CV already exists in `profile/`.
- If exactly one PDF CV exists and `pdftotext` is available, use it to draft a concise Markdown CV in `profile/cv.md`, then ask the user to review and correct it before relying on it.
- If multiple PDF CVs exist, ask which one to use before extracting text.
- If no PDF CV exists, ask the user to place a PDF CV in `profile/` or manually fill `profile/cv.md`.
- Do not ask the user to paste a full CV into chat unless they explicitly choose that route.

For `profile/prefs_global.md`:
- If it is filled, treat it as durable cross-track preference context.
- If it is still default, infer only safe facts from the CV and handhold the user to fill it with global preferences:
  - preferred locations and work mode
  - role seniority and durable role-shape preferences
  - contract type
  - hard constraints and dealbreakers
  - authorization constraints
  - strong positive signals
  - borderline or weak-fit signals
  - recurring red flags
  - compensation or practical constraints, if any
- Track-specific `tracks/{track_slug}/prefs.md` still gets created separately and can override global preferences.

If the user chooses to defer profile cleanup, continue from the track brief but explicitly note that ranking and source discovery may be weaker until `profile/cv.md` and `profile/prefs_global.md` are filled.

When `scripts/setup_machine.sh` is run with `--agent claude`, it also merges a repo-local `SessionStart` hook into `.claude/settings.local.json` that exports `CLAUDE_SESSION_ID`. The `coding` skill reads that variable to record a resumable `agent_id` in plan files. The merge is idempotent and preserves any existing `permissions` or other settings.

When `scripts/setup_machine.sh` is run with `--agent codex`, it also writes a repo-local `.codex/config.toml` with a managed `shell_environment_policy` that puts `./.venv/bin` first on `PATH`. The merge is idempotent and preserves unrelated Codex settings. If a user already has an unmanaged `shell_environment_policy`, setup reports a conflict and leaves it unchanged.

### 1. Gather the minimum `prefs.md` brief first

Start by collecting only the minimum information needed to draft `prefs.md`.

Ask for:
- user name, unless already known
- track display name
- proposed track slug; offer a slugified version using lowercase letters, digits, and underscores
- broad search area for the track
- goals / role types
- keep-only keywords, or an explicit `none yet`
- important constraints or red flags, or an explicit `none yet`
- geography / remote preferences, or an explicit `none yet`

Hard gate:
- Do not use the project skill `discover-sources` until this minimum brief is captured in the conversation or already exists in `tracks/{track_slug}/prefs.md`.
- Track name or slug alone is not enough.
- Do not infer a source list from `profile/cv.md`, `profile/prefs_global.md`, or the track name alone.
- If the minimum brief is not available yet, stay in question-asking mode.

### 2. Ask for known companies and job boards

After the minimum `prefs.md` brief is captured, ask what sources the user already knows and wants on the track.

Ask for:
- known companies to track, if any
- known job boards or career pages, if any
- optional sectors, labs, or organizations to target
- existing sources already bucketed by cadence, if known:
  - `Check every run`
  - `Check every 3 runs`
  - `Check every month`
- track-wide search terms, if already known
- source-specific search terms, including whether any source should use `[override]`, if already known
- source-specific native filters, such as location, degree, organization, or job type filters, if already known

### 3. Optional source discovery

Use this branch only after the minimum `prefs.md` brief is available and the user has had a chance to provide known companies and job boards.

- First summarize the current setup brief and current source list:
  - goals / role types
  - keep-only keywords
  - constraints or red flags
  - geography / remote preferences
  - optional seed companies, sectors, labs, or organizations
  - any known companies, job boards, or career pages already supplied by the user
- Then ask whether the user wants help finding official sources via the project skill `discover-sources`.
- Treat discovery as opt-in assistance, not as a default setup step.
- If the user already has a strong official source list and does not want help expanding it, skip this branch.
- If the user wants help and the source list is missing, sparse, too broad, or clearly incomplete, hand off to the project skill `discover-sources`.
- Pass the handoff enough context to make the discovery preference-aware:
  - user name
  - track display name
  - broad search area
  - the stated track preferences above
  - any user-provided companies, sectors, labs, organizations, job boards, or career pages
  - any existing source list, if present
- Prefer official homepage-linked careers pages or ATS boards from user-supplied companies when `discover-sources` finds them.
- Treat the returned source pack as a recommendation, not as final config.
- Present the user-facing discovery result as a concise shortlist: recommended sources, dropped sources, URL corrections, known caveats, and decisions needed. Do not dump full setup-ready records unless the user asks for debug detail.
- Review the proposed sources with the user, ask keep/drop/add, ask whether cadence defaults should change, and then continue automatically with normalization.
- Reuse suggested cadence buckets and search terms from `discover-sources` as defaults when they fit.
- Use `integration_follow_up` from `discover-sources` to distinguish normal config from partial/follow-up or unsupported sources.
- Treat `match_rule_suggestion` from `discover-sources` as a draft for broad/noisy sources only; confirm it with the user before writing it.
- Do not turn this branch into source integration. Deep validation and coding escalation still happen later.

### 4. Normalize, probe, and integrate sources

Source integration is part of setup prioritization. Do not ask the user whether integration should happen as a separate choice; use the source importance, canary availability, and quality results to decide how far to go within the default budget.

Use this canonical path:

1. Normalize the source list.
   - Normalize the slug before writing files.
   - Treat the final source list as coming from the user, from `discover-sources`, or from both.
   - Infer `discovery_mode` from the source URL when obvious.
   - Prefer modes listed in `docs/discovery_modes.md`, which is generated from the provider registry. Use `scripts/discover_jobs.py` as the stable CLI entrypoint, not as the place to add source logic.
   - Common modes worth trying first: `workday_api`, `greenhouse_api`, `lever_json`, `ashby_api`, `ashby_html`, `workable_api`, `getro_api`, `personio_page`, `recruitee_inline`, `service_bund_search`, `html`, `iacr_jobs`, `yc_jobs_board`, `hackernews_jobs`.
   - If the correct mode is unclear, prefer `html` over inventing a new unsupported mode.
   - If a source is clearly an official employer-linked board but has no dedicated supported mode, keep it with the best existing fallback, usually `html`, rather than excluding it for lacking a first-class integration.
2. Read preference context before finalizing search terms and filters.
   - Read `profile/cv.md`, `profile/prefs_global.md`, and the draft `tracks/{track_slug}/prefs.md`.
   - Derive track-wide terms from durable role goals and keep-only criteria.
   - Derive source-specific `search_terms` from the user's CV vocabulary, target role shapes, sector constraints, and source vocabulary.
   - Derive source-specific `filters` from location/work-mode preferences, degree requirements, job family, organization, employment type, and other stable native filters.
3. Keep logic in the right file.
   - `prefs.md`: human intent, fit criteria, constraints, and geography.
   - `sources.json`: official source identity, URL, discovery mode, cadence, track terms, source-specific search terms, and native source filters.
   - `source_state.json`: mutable cadence and integration state, including canaries, priority, attempts, last attempted date, accepted fallback decisions, and next actions.
   - `match_rules.json`: track-specific post-discovery filtering for broad or noisy sources after source IDs are stable.
   - `scripts/discover/sources/`: reusable provider parsing, enumeration, pagination, and native-filter support.
4. Auto-pick canaries where possible.
   - Explain canaries as known current postings that prove the source is covered.
   - For each accepted source, try to identify one current posting.
   - Prefer both exact title and direct job detail URL.
   - If only an ATS application URL exists, accept it but note the source family.
   - A title-only canary is acceptable only when the source hides URLs.
   - Use `scripts/probe_career_source.py <url> --name "<source>" --term "<term>" --pretty` for setup probing when possible instead of ad hoc `WebFetch` guesses.
   - Ask the user only when the selected canary appears stale, the source is high-value and no canary is found, or the source is broad/noisy and the canary defines intended fit.
   - If no canary is found, write `source_state.json` integration state with `status: "pending"`, `canary.status: "missing"`, a priority, and a concrete `next_action`.
   - Store selected or deferred canaries in each source's `source_state.json` `integration` object.
5. Probe sources with the best existing mode plus inferred config.
   - Run source-scoped discovery for important newly added sources that have canaries or high track value.
   - Do not invoke source integration from normal scheduled track runs.
6. Run source-quality evaluation.
   - Use `scripts/eval_source_quality.py` for probed sources with canaries.
   - Do not treat `scripts/discover_jobs.py` source status `complete` as enough; source quality must reject nav/share/link-only candidate sets.
   - `pass`: source is ready.
   - `integration_needed`: inspect the `integration_ticket.suggested_strategy`.
   - `blocked`: stop treating the source as ready and report the blocker.
   - Store pass/fail/deferred state in `source_state.json`.
7. Tune config before code.
   - For `config_terms_override`, update only that source's `search_terms` in `sources.json` with mode `override`, rerender `sources.md`, rediscover, and re-evaluate.
   - For `config_terms_append`, update only that source's `search_terms` in `sources.json` with mode `append`, rerender, rediscover, and re-evaluate.
   - For `config_native_filters`, update only that source's `filters` in `sources.json`, rerender, rediscover, and re-evaluate.
   - For `provider_filter_support`, keep the declarative filters in `sources.json` and invoke source integration to add reusable provider support for those filters.
   - For `dedicated_provider_logic`, invoke source integration only after the existing mode and config cannot satisfy the canary and quality checks.
8. Invoke source integration for at most the top 2 sources that still need code.
   - Rank by importance to the track, canary quality, current source failure severity, whether one provider fix helps multiple sources, and likely implementation effort.
   - Use `./.venv/bin/python scripts/source_integration.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`.
   - Prefer reusable providers under `scripts/discover/sources/` when multiple accepted sources share a board family such as Applied, Jobvite, Workable, Recruitee, Personio, Ashby, Lever, Greenhouse, or Workday.
   - Avoid one-off branches in `generic_html.py` unless the site is truly unique and no reusable family exists.
   - Treat the source as supported only if the final loop result is `final_status: "pass"`.
9. Queue remaining pending sources for one-per-day follow-up.
   - Write each remaining source's mutable follow-up state under `source_state.json` at `sources.<source_id>.integration`.
   - Include `status: "pending"` or `status: "integration_needed"`, `priority`, `canary`, `attempts`, `last_attempted` when present, `next_action`, and any `suggested_search_terms` or `suggested_filters`.
   - The follow-up command is `./.venv/bin/python scripts/integrate_next_source.py --track {track_slug} --today YYYY-MM-DD`.
   - After queue creation, run `./.venv/bin/python scripts/integrate_next_source.py --track {track_slug} --today YYYY-MM-DD --dry-run` and confirm it selects one eligible source.

When an old canary disappears, refresh it with:

```bash
./.venv/bin/python scripts/update_source_canary.py --track {track_slug} --source "{source_name}"
```

Do not delete source-quality checks just because a canary aged out.

Before generating files, summarize the normalized config, inferred source-specific terms/filters, canary status, and any queued integration follow-up.

### 5. Generate files

Create:
- `tracks/{track_slug}/prefs.md`
- `tracks/{track_slug}/sources.json`
- `tracks/{track_slug}/match_rules.json`, only when accepted broad-source filtering rules exist
- `tracks/{track_slug}/source_state.json`
- `tracks/{track_slug}/sources.md`
- `tracks/{track_slug}/AGENTS.md`
- `tracks/{track_slug}/CLAUDE.md`
- `tracks/{track_slug}/digests/`

Do not hand-write `tracks/{track_slug}/ranked_overview.md` or `shared/ranked_jobs/{track_slug}.json`.
Let `scripts/update_ranked_overview.py --track {track_slug}` initialize those.

Step 5 scaffold templates live in `shared/templates/`:
- `shared/templates/track_prefs.md`
- `shared/templates/track_sources.json`
- `shared/templates/track_match_rules.json`
- `shared/templates/track_source_state.json`
- `shared/templates/track_AGENTS.md`

Copy these templates as starting points, replace all placeholders, then remove any example-only entries that do not apply. Do not edit the shared templates during normal track setup.

#### `prefs.md`

Use `shared/templates/track_prefs.md` as the base template for `tracks/{track_slug}/prefs.md`.

Replace:
- `{track_display_name}` with the final track display name
- `{goals_or_role_types}` with the user's goals and role types
- `{keep_only_keywords}` with the user's keep-only keywords or `- none specified yet`
- `{constraints_or_red_flags}` with the user's constraints and red flags or `- none specified yet`
- `{geography_or_remote_preferences}` with the user's geography and remote preferences or `- none specified yet`

#### `sources.json`

Use `shared/templates/track_sources.json` as the base shape for `tracks/{track_slug}/sources.json`, then write the canonical machine-readable source config.

Rules:
- `id` is stable state identity; use lowercase ASCII slugs and do not change it during later display-name cleanup.
- `cadence_group` is one of `every_run`, `every_3_runs`, or `every_month`.
- `search_terms.mode` is `append` unless the source should replace track-wide terms with an `override`.
- Omit `search_terms` and `filters` when they are empty.

#### `match_rules.json`

Use `shared/templates/track_match_rules.json` as the base shape for `tracks/{track_slug}/match_rules.json` only when the user accepted track-specific filtering for a broad or noisy source.

Rules:
- Omit the file entirely when no broad-source filtering rule is needed.
- Prefer `source_ids` after source IDs are known; use `source_names` only as a compatibility fallback or readability aid.
- `keep_if_any_text_term` should contain concrete evidence terms from `prefs.md` or the accepted `discover-sources` suggestion.
- Do not use match rules for normal official employer boards, source parsing, or native filters.

#### `source_state.json`

Use `shared/templates/track_source_state.json` as the base shape for `tracks/{track_slug}/source_state.json` with null `last_checked` state for new sources.

The runner owns this file during normal track runs.

#### `sources.md`

Generate `tracks/{track_slug}/sources.md` from `sources.json` by running:

```bash
JOB_AGENT_ROOT="$PWD" ./.venv/bin/python scripts/render_sources_md.py --track {track_slug}
```

The generated Markdown must be read-only human documentation and must not include `last_checked` or other mutable state. It should follow this shape:

```md
> Generated read-only summary. Do not edit this file directly.
> Source definitions live in `sources.json`; cadence state lives in `source_state.json`.
> To change sources, invoke the set-up or existing-source-curation agent.

Only check the sources below for this track.

Do not waste time on broad employer pages outside this list.

Cadence note:
- For `Check every 3 runs`, treat one scheduled day as one run.
- For `Check every month`, recheck once the calendar month changes.
- Manual same-day reruns do not advance cadence.
- `discovery_mode` is used by `../../scripts/discover_jobs.py` for deterministic source coverage.

## Check every run
| source | url | discovery_mode |
| --- | --- | --- |
| ... | ... | ... |

## Check every 3 runs
| source | url | discovery_mode |
| --- | --- | --- |
| ... | ... | ... |

## Check every month
| source | url | discovery_mode |
| --- | --- | --- |
| ... | ... | ... |

## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms
{track-wide terms}

### Source-specific search terms
Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.

Add `[override]` after the source name to replace the track-wide terms for that source.

{source-specific terms}

### Source-specific filters
Use these native filters on searchable sources when the source supports stable URL or API filters.

Write filters as `- Source Name — key: value; value | key: value`.

{source-specific filters or "- none"}

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ./seen_jobs.json
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
```

#### `AGENTS.md`

Use `shared/templates/track_AGENTS.md` as the base template.

Copy its structure, then replace all template placeholders:
- replace `{track_display_name}` with the final track display name
- replace `{track_slug}` with the normalized track slug everywhere it appears
- replace `{user_name}` with the current user name
- replace `{fit_language}` with a short track-specific description of the role types, fit bar, constraints, and red flags from `prefs.md`
- keep the same workflow structure unless the user explicitly wants a different one

Important:
- Do not use a real user track as the template.
- Do not leave any unreplaced `{...}` placeholder in the generated file.
- Do not leave domain-specific fit text from another track in the generated file.
- Keep the run boundaries, same-day rerun behavior, JSON digest flow, and ranked-overview rebuild steps aligned with the current shared workflow

#### `CLAUDE.md`

Create `tracks/{track_slug}/CLAUDE.md` next to the generated `AGENTS.md`.

Write exactly:

```md
@AGENTS.md
```

Do not add any other content.

### 6. First local digest preview

After Step 5 files are generated, run a first local track digest with no delivery and paste a preview of the rendered digest into the conversation. This is how guided setup ends: do not move on to delivery or scheduling until the user has seen what today's digest produces for this track.

1. Run:

```bash
bash scripts/run_track.sh --track {track_slug}
```

2. Confirm the structured digest exists at `artifacts/digests/{track_slug}/YYYY-MM-DD.json`.
3. Read the rendered digest at `tracks/{track_slug}/digests/YYYY-MM-DD.md`.
4. Paste a preview of the rendered digest into the conversation:
   - the rendered digest body verbatim if it is short, otherwise the first ~40 lines with a note about where the full file lives
   - a one-line summary of strong vs. borderline matches
5. If the digest finds zero relevant new roles, say so explicitly. The scaffold is still ready.
6. If `bash scripts/run_track.sh` fails, surface the error and treat it as a blocker. Do not move on to delivery or scheduling until the first digest has been produced and previewed, or the user explicitly decides to defer the preview.

### 7. Delivery preferences and local config handholding

After the first digest has been previewed, ask which delivery methods and schedule the user wants for this track.

Explain the options clearly:
- local artifacts only: always available; `run_track.sh` leaves JSON and Markdown files in the repo
- Logseq sync: run with `--delivery logseq`; requires `LOGSEQ_GRAPH_DIR`
- email delivery: run with `--delivery email`; requires SMTP variables
- both Logseq and email: pass both delivery flags

Use these manual-run examples:

```bash
bash scripts/run_track.sh --track {track_slug}
bash scripts/run_track.sh --track {track_slug} --delivery logseq
bash scripts/run_track.sh --track {track_slug} --delivery email
bash scripts/run_track.sh --track {track_slug} --delivery logseq --delivery email
```

For Logseq:
- Check whether `.env.local` already has `LOGSEQ_GRAPH_DIR`.
- If it is missing and the user wants Logseq, help them identify the graph root path.
- Prefer running `bash scripts/setup_machine.sh --logseq-graph-dir <absolute-path>` or adding `export LOGSEQ_GRAPH_DIR=<absolute-path>` to `.env.local`.
- Do not inspect the Logseq graph contents during setup.

For email:
- Never ask the user to paste SMTP passwords or app passwords into chat.
- Ensure `.env.local` has commented SMTP placeholders by running or recommending `bash scripts/setup_machine.sh`.
- Tell the user to edit `.env.local` locally and uncomment/fill non-secret SMTP values:
  - `JOB_AGENT_SMTP_HOST`
  - `JOB_AGENT_SMTP_PORT`
  - `JOB_AGENT_SMTP_FROM`
  - `JOB_AGENT_SMTP_TO`
  - `JOB_AGENT_SMTP_USERNAME`
  - `JOB_AGENT_SMTP_TLS`
- Prefer `JOB_AGENT_SMTP_PASSWORD_CMD` for the password. Use one of these local command examples, adapted by the user:
  - macOS Keychain: `security find-generic-password -s jobwatch-smtp -a jobs@example.com -w`
  - Linux Secret Service: `secret-tool lookup service jobwatch-smtp account jobs@example.com`
  - pass: `pass show email/jobwatch-smtp`
- `JOB_AGENT_SMTP_PASSWORD` remains a legacy/local-only plaintext fallback; do not recommend it unless the user explicitly accepts that tradeoff.
- Do not run `send_digest_email.py --dry-run` before a digest exists.
- Sequence email setup this way:
  1. Configure non-secret SMTP settings and password-command retrieval.
  2. Reuse the digest produced by Step 6 at `artifacts/digests/{track_slug}/YYYY-MM-DD.json`. If Step 6 was skipped or deferred, run `bash scripts/run_track.sh --track {track_slug}` now and confirm the JSON exists before continuing.
  3. Dry-run the email render:

```bash
./.venv/bin/python scripts/send_digest_email.py --track {track_slug} --date YYYY-MM-DD --dry-run
```

Then test real delivery only when the user confirms the local SMTP config is ready. `--dry-run` renders from the digest JSON and should not require SMTP env or execute `JOB_AGENT_SMTP_PASSWORD_CMD`.

For scheduling:
- Ask whether the user wants scheduled runs for this track now.
- If not, do not edit `.schedule.local`; tell the user manual runs are available with the examples above.
- If yes, ask for cadence and time:
  - daily: local `HH:MM`
  - weekly: weekday as `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, or `sun`, plus local `HH:MM`
  - monthly: day `1` through `31`, plus local `HH:MM`
- Do not ask the user to hand-edit `.schedule.local`.
- Generate or update `.schedule.local` with `scripts/configure_schedule.py`, passing delivery flags that match the selected delivery methods.
- Then install the shared platform scheduler with `bash scripts/install_scheduler.sh`.

Use these schedule commands:

```bash
./.venv/bin/python scripts/configure_schedule.py --track {track_slug} --cadence daily --time HH:MM
./.venv/bin/python scripts/configure_schedule.py --track {track_slug} --cadence weekly --weekday mon --time HH:MM
./.venv/bin/python scripts/configure_schedule.py --track {track_slug} --cadence monthly --month-day 1 --time HH:MM
```

Append delivery flags when requested:

```bash
--delivery logseq
--delivery email
--delivery logseq --delivery email
```

Scheduling caveats:
- One active schedule entry per track is the default; `scripts/configure_schedule.py` replaces an existing entry for the same track and preserves other tracks.
- If email delivery is scheduled, remind the user that SMTP values must be filled in `.env.local` before the scheduled run.
- If `bash scripts/install_scheduler.sh` needs approval to update crontab or launchd, request that approval and then continue.

### 8. Validation

After scaffolding, run:

1. Confirm `tracks/{track_slug}/CLAUDE.md` contains exactly `@AGENTS.md`.
2. `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --list-sources`
3. `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --today YYYY-MM-DD --plan-only --due-only --pretty`
4. `./.venv/bin/python scripts/update_ranked_overview.py --track {track_slug}`

If `match_rules.json` was created and an affected broad source was probed during setup, also run:

5. `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --pretty`

If the source was not probed during setup, report that the match rule will first be exercised on the next real discovery run.

If scheduled runs were configured, also run:

6. The selected `./.venv/bin/python scripts/configure_schedule.py ...` command
7. `bash scripts/install_scheduler.sh`

If setup required changes to shared code such as `scripts/discover/`, provider docs metadata, or `scripts/discover_jobs.py`, also run:

8. `scripts/test.sh`

If setup included source integration with a canary, also run:

9. For each newly added or materially changed source that was actually probed and has a canary:
   `./.venv/bin/python scripts/eval_source_quality.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`

10. For at most the top 2 `integration_needed` sources that still need code after config tuning:
   `./.venv/bin/python scripts/source_integration.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`

11. If sources remain queued for follow-up, validate the queue can select exactly one eligible source:
   `./.venv/bin/python scripts/integrate_next_source.py --track {track_slug} --today YYYY-MM-DD --dry-run`

Treat the source as ready only if the evaluation artifact reports `final_status: "pass"`.

If email delivery was requested, validate the sequence after the first digest exists:

12. `bash scripts/run_track.sh --track {track_slug}` with no delivery, unless already run.
13. Confirm `artifacts/digests/{track_slug}/YYYY-MM-DD.json` exists.
14. `./.venv/bin/python scripts/send_digest_email.py --track {track_slug} --date YYYY-MM-DD --dry-run`

### 9. Final response

Report:
- what files were created or changed
- whether `discover-sources` was used, and which returned sources were kept
- which sources were included and with which `discovery_mode`
- whether `match_rules.json` was created, and which broad sources it affects
- whether `profile/cv.md` and `profile/prefs_global.md` were filled, default, or deferred
- whether the first local digest was produced and previewed, with the digest path and a short summary of what was found
- whether the Codex project config was installed, already present, updated, conflicted, or not applicable (only relevant when `--agent codex` was used)
- whether the Claude `SessionStart` hook was installed, already present, or not applicable (only relevant when `--agent claude` was used)
- which delivery methods the user selected, and which local config values still need to be filled
- whether scheduling was configured, with cadence, local time, and scheduler install status
- which validation commands passed
- which newly integrated sources passed the quality gate
- which sources were deferred instead of escalated, and why
- any sources that still need custom integration or follow-up
- a succinct suggested commit message
