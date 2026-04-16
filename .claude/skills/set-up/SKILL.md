<!-- GENERATED FILE: source of truth is .agents/skills/set-up/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: set-up
description: Set up a new search track for the job-agent.
---

# Skill: Set up a new track for the job-agent

Use this skill to scaffold a new track over the shared job-agent workflow.

Default assumption:
- This is a scaffolding task, not a full source-integration task.
- Reuse the shared scripts in `scripts/`.
- Do not add new discovery code to `scripts/discover_jobs.py` unless the user explicitly asks for source integration now.
- For source integration, evaluate newly added or materially changed sources; do not reevaluate stable unchanged sources unless the user asks.

## Workflow

### Before track setup. Check local profile readiness

Before creating or expanding a track, check the local profile files:

- `profile/cv.md`
- `profile/prefs_global.md`

These files are local user data and are ignored by Git. If either file is missing, run or recommend:

```bash
bash scripts/setup_machine.sh
```

Treat a profile file as still default if it contains `JOB_AGENT_PROFILE_TEMPLATE`.

For `profile/cv.md`:
- If it is filled, use it as the primary CV context.
- If it is still default, check whether a PDF CV already exists in `profile/`.
- If a PDF CV exists and `pdftotext` is available, use it to draft a concise Markdown CV in `profile/cv.md`, then ask the user to review and correct it before relying on it.
- If no PDF CV exists, ask the user to place a PDF CV in `profile/` or manually fill `profile/cv.md`.
- Do not ask the user to paste a full CV into chat unless they explicitly choose that route.

For `profile/prefs_global.md`:
- If it is filled, treat it as durable cross-track preference context.
- If it is still default, handhold the user to fill it with global preferences:
  - preferred locations and work mode
  - role seniority and durable role-shape preferences
  - hard constraints and dealbreakers
  - recurring red flags
  - compensation or practical constraints, if any
- Track-specific `tracks/{track_slug}/prefs.md` still gets created separately and can override global preferences.

If the user chooses to defer profile cleanup, continue from the track brief but explicitly note that ranking and source discovery may be weaker until `profile/cv.md` and `profile/prefs_global.md` are filled.

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
- Review the proposed sources with the user, let them trim or add to the list, and then continue with normalization.
- Reuse suggested cadence buckets and search terms from `discover-sources` as defaults when they fit.
- Do not turn this branch into source integration. Deep validation and coding escalation still happen later.

### 4. Normalize, confirm, and optionally integrate sources

Step 4 has one required path and two optional integration paths:
- `4a` is the normal setup path and must happen before files are generated.
- `4b` is only for a user-requested coding handoff for one specific source.
- `4c` is only for a user-requested quality pass across multiple newly added, probed sources.

#### 4a. Normalize and confirm config

- Normalize the slug before writing files.
- Treat the final source list as coming from the user, from `discover-sources`, or from both.
- Infer `discovery_mode` from the source URL when obvious.
- Prefer existing modes already supported by `scripts/discover_jobs.py`.
- Common modes worth trying first:
  - `workday_api`
  - `greenhouse_api`
  - `lever_json`
  - `ashby_api`
  - `ashby_html`
  - `html`
  - `iacr_jobs`
  - `yc_jobs_board`
  - `hackernews_jobs`
- Common official board families worth recognizing during normalization include Greenhouse, Lever, Ashby, Workday, and Workable, even when some of them still fall back to `html`.
- If the correct mode is unclear, prefer `html` over inventing a new unsupported mode.
- If a source is clearly an official employer-linked board but has no dedicated supported mode, keep it with the best existing fallback, usually `html`, rather than excluding it for lacking a first-class integration.
- If track-wide or source-specific search terms were not already provided, derive an initial set from the user's stated preferences and any `discover-sources` suggestions.
- If source-specific native filters were provided or are clearly needed to control result volume on a broad source, record them in `sources.json` using the source `filters` object rather than baking them into search terms.
- If `discover-sources` suggested cadence buckets, use those as defaults unless there is a clearer reason to place the source elsewhere.
- Only do lightweight validation during setup. Do not search every source exhaustively.
- If an existing mode is good enough, stop there. Do not escalate into coding work just because a source is imperfect.
- If a source clearly cannot be covered by an existing mode, tell the user and either:
  - leave it out for now, or
  - keep it in `sources.json` with the best existing mode and note that it needs follow-up integration

Before generating files, summarize the normalized config and confirm it.

#### 4b. Optional source-integration escalation

Use this branch only when the user wants source integration now for a specific source.

Escalate only if all of the following are true:
- the source is important enough that missing it would materially weaken the track
- an existing mode was tried or reasonably evaluated first
- `html` or another fallback does not produce usable results
- a canary is available, ideally with both title and URL

When those conditions hold, hand off to repo-development coding work governed by the project skill `coding`.

Treat the handoff as a narrow implementation task, not a continuation of setup exploration.

The handoff should include:
- track slug
- source name
- source URL
- current attempted `discovery_mode`
- canary title
- canary URL if available
- a short statement of what failed
- any known native filters that should be applied, especially when the failure is excessive result volume
- the expected success condition in `scripts/discover_jobs.py`

Expected coding output:
- minimal support for that source in `scripts/discover_jobs.py`
- native source-filter support when the board exposes stable filters and noisy volume is the problem
- one focused automated test
- validation with `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --pretty`
- quality-gate validation with `./.venv/bin/python scripts/eval_source_quality.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`
- if that evaluation returns `repair_needed`, prefer `./.venv/bin/python scripts/repair_source.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]` over ad hoc manual retrying
- if shared code changed, `scripts/test.sh`

After the coding handoff succeeds:
- update `sources.json` with the correct `discovery_mode`
- treat the source as supported only if the quality-gate result is `final_status: "pass"`
- mention the new support explicitly in the final response

If the coding handoff is not requested or does not succeed:
- keep the source on the track only if an existing mode is still somewhat usable
- otherwise leave it out and note it as follow-up work

#### 4c. Source-quality triage for setup-time integration

Use this branch when setup includes multiple newly added sources and the user wants a better-than-scaffolding integration pass.

Run `scripts/eval_source_quality.py` for each source that meets both conditions:
- it is newly added to the track or its scraper changed materially during this setup pass
- it was actually probed with a real `discover_jobs.py` run and has a canary

Do not run the quality gate for:
- stable unchanged sources already supported in the repo
- sources that were only scaffolded but not probed
- broad follow-up sources the user did not ask to integrate now

After running the quality gate, classify each evaluated source:
- `pass`: source is ready; keep it and report it as supported
- `repair_needed`: source is a candidate for coding repair
- `blocked`: stop treating the source as ready; report the blocker explicitly

Do not auto-escalate every `repair_needed` source into coding.

Instead, rank `repair_needed` sources by:
1. importance to the track
2. whether fallback parsing is unusable or too noisy
3. canary quality and reproducibility

If a source is too noisy because its native filters are not being applied, prefer adding declarative source-filter support over tightening post-extraction filtering.

Default repair budget during setup:
- escalate at most the top `2` `repair_needed` sources
- you may escalate `3` only if the user clearly asked for a broader integration pass
- leave the rest as follow-up work instead of turning setup into a long multi-source coding session

For each source selected for repair:
- hand off to repo-development coding work as described above
- prefer `scripts/repair_source.py` over ad hoc repeated retrying once an initial `eval_source_quality.py` run returns `repair_needed`
- treat the source as supported only if the final repair-loop result is `final_status: "pass"`

For each source not selected for repair:
- keep it only if the fallback mode is still somewhat usable and label it as partial/follow-up
- otherwise leave it out for now and report why

### 5. Generate files

Create:
- `tracks/{track_slug}/prefs.md`
- `tracks/{track_slug}/sources.json`
- `tracks/{track_slug}/source_state.json`
- `tracks/{track_slug}/sources.md`
- `tracks/{track_slug}/AGENTS.md`
- `tracks/{track_slug}/CLAUDE.md`
- `tracks/{track_slug}/digests/`

Do not hand-write `tracks/{track_slug}/ranked_overview.md` or `shared/ranked_jobs/{track_slug}.json`.
Let `scripts/update_ranked_overview.py --track {track_slug}` initialize those.

#### `prefs.md`

Write `tracks/{track_slug}/prefs.md` using this template:

```md
# {track display name} track preferences

Interpret this file as a specialization of `profile/prefs_global.md`.
If this file conflicts with the global preferences, this file takes precedence for the {track display name} track.

## Goals
Role types:
{user input goals / role types}

## Keep only roles matching at least one of these keywords
{user input keep-only keywords}

## Constraints and red flags
{user input constraints / red flags}

## Location and work-mode preferences
{user input geography / remote preferences or "- none specified yet"}
```

#### `sources.json`

Write `tracks/{track_slug}/sources.json` as the canonical machine-readable source config:

```json
{
  "schema_version": 1,
  "track": "{track_slug}",
  "track_terms": [
    "{track-wide term}"
  ],
  "sources": [
    {
      "id": "{stable_slugified_source_id}",
      "name": "{source display name}",
      "url": "{official source URL}",
      "discovery_mode": "{supported discovery mode}",
      "cadence_group": "every_run"
    },
    {
      "id": "{stable_slugified_source_id}",
      "name": "{source display name}",
      "url": "{official source URL}",
      "discovery_mode": "{supported discovery mode}",
      "cadence_group": "every_3_runs",
      "search_terms": {
        "mode": "append",
        "terms": ["{source-specific term}"]
      },
      "filters": {
        "location": ["{native filter value}"]
      }
    }
  ]
}
```

Rules:
- `id` is stable state identity; use lowercase ASCII slugs and do not change it during later display-name cleanup.
- `cadence_group` is one of `every_run`, `every_3_runs`, or `every_month`.
- `search_terms.mode` is `append` unless the source should replace track-wide terms with an `override`.
- Omit `search_terms` and `filters` when they are empty.

#### `source_state.json`

Write `tracks/{track_slug}/source_state.json` with null state for new sources:

```json
{
  "schema_version": 1,
  "track": "{track_slug}",
  "sources": {
    "{stable_slugified_source_id}": {
      "last_checked": null
    }
  }
}
```

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
> To change sources, invoke the set-up or source-curation agent.

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

Use `.agents/skills/set-up/templates/track_AGENTS.md` as the base template.

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

### 6. Delivery preferences and local config handholding

After files are generated, ask which delivery methods and schedule the user wants for this track.

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
- Tell the user to edit `.env.local` locally and uncomment/fill:
  - `JOB_AGENT_SMTP_HOST`
  - `JOB_AGENT_SMTP_PORT`
  - `JOB_AGENT_SMTP_FROM`
  - `JOB_AGENT_SMTP_TO`
  - `JOB_AGENT_SMTP_USERNAME`
  - `JOB_AGENT_SMTP_PASSWORD`
  - `JOB_AGENT_SMTP_TLS`
- After the user has filled those values locally and the first digest JSON exists, suggest a dry run first:

```bash
./.venv/bin/python scripts/send_digest_email.py --track {track_slug} --date YYYY-MM-DD --dry-run
```

Then test real delivery only when the user confirms the local SMTP config is ready.

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

### 7. Validation

After scaffolding, run:

1. Confirm `tracks/{track_slug}/CLAUDE.md` contains exactly `@AGENTS.md`.
2. `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --list-sources`
3. `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --today YYYY-MM-DD --plan-only --due-only --pretty`
4. `./.venv/bin/python scripts/update_ranked_overview.py --track {track_slug}`

If scheduled runs were configured, also run:

5. The selected `./.venv/bin/python scripts/configure_schedule.py ...` command
6. `bash scripts/install_scheduler.sh`

If setup required changes to shared code such as `scripts/discover_jobs.py`, also run:

7. `scripts/test.sh`

If setup included source integration with a canary, also run:

8. For each newly added or materially changed source that was actually probed and has a canary:
   `./.venv/bin/python scripts/eval_source_quality.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`

9. For at most the top 2 `repair_needed` sources by default:
   `./.venv/bin/python scripts/repair_source.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`

Treat the source as ready only if the evaluation artifact reports `final_status: "pass"`.

### 8. Final response

Report:
- what files were created or changed
- whether `discover-sources` was used, and which returned sources were kept
- which sources were included and with which `discovery_mode`
- whether `profile/cv.md` and `profile/prefs_global.md` were filled, default, or deferred
- which delivery methods the user selected, and which local config values still need to be filled
- whether scheduling was configured, with cadence, local time, and scheduler install status
- which validation commands passed
- which newly integrated sources passed the quality gate
- which sources were deferred instead of escalated, and why
- any sources that still need custom integration or follow-up
- a succinct suggested commit message
