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
- Use `shared/discovery_modes.md` as the generated reference for supported `discovery_mode` values.
- Do not invoke source integration from normal scheduled track runs.

Interaction defaults:
- Prefer `recommend -> confirm or override` over blank questionnaires. For each missing profile or track field, propose a recommended answer grounded in the CV, current context, and prior answers.
- If the user replies with partial answers, terse confirmations, or delegation phrases such as `suggest`, `use your suggestions`, `pick whatever you think is best`, `default`, `sounds good`, or `go ahead`, treat the remaining low-risk choices as delegated and continue automatically.
- Ask only when the answer is genuinely high-risk, materially ambiguous, or not safely inferable from local context.
- At each transition, present one recommended next step rather than a neutral menu of equally weighted options.
- Do not reopen low-risk decisions the user has already delegated.

## Workflow

### Step zero. Make local profile files ready

Before creating or expanding a track, proactively make the local profile files usable:

- `profile/cv.md`
- `profile/prefs_global.md`

These files are local user data and are ignored by Git. Setup writes local `profile/` files only. Never edit `shared/templates/profile/*`.

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
- If no PDF CV exists, use this wording: **"If you want me to read a PDF, tell me the path or copy it into `profile/` now; then I will extract it. Otherwise complete `profile/cv.md` now and tell me when ready."**
- Ask only this profile-readiness question at that point; do not combine it with other setup questions.
- Do not ask the user to paste a full CV into chat unless they explicitly choose that route.

**Note on Ignored Files:** Gemini file tools (and other agents) may report that files in `profile/` or `tracks/` are ignored. Since these are local user files, always use shell commands (e.g., `cat` or `grep`) to read them when the standard file tools fail.

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

Refer to `docs/machine_setup.md` for detailed information on how `scripts/setup_machine.sh` configures automation providers (Claude `SessionStart`, Codex `shell_environment_policy`, etc.) and delivery secrets. Report setup-machine conflicts or relevant agent config changes only when they occur.

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

When one or more fields are missing:
- Offer a draft brief in the same message instead of waiting for the user to invent every field from scratch.
- Mark missing items as `recommended:` values when they are safe to infer, and invite corrections.
- If the user answers only some fields, carry forward the unanswered low-risk fields from the recommended draft unless the user objects.

Hard gate:
- Do not use the project skill `discover-sources` until this minimum brief is captured in the conversation or already exists in `tracks/{track_slug}/prefs.md`.
- Track name or slug alone is not enough.
- Do not infer a source list from `profile/cv.md`, `profile/prefs_global.md`, or the track name alone.
- If the minimum brief is not available yet, stay in question-asking mode.

### 2. Ask for known companies and job boards

After the minimum `prefs.md` brief is captured, ask what sources the user already knows and wants on the track.

Do not make the user generate the source list from a blank page:
- Offer a recommended starter seed list, cadence defaults, track-wide terms, and native-filter posture in the same message.
- If the user says `nothing specific`, delegates, or gives only a partial source answer, continue from the recommended starter set unless corrected.

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
- Then recommend whether to use the project skill `discover-sources`.
- Treat discovery as opt-in assistance only when the current official source list is already strong; otherwise treat it as the recommended next step.
- If the user already has a strong official source list and does not want help expanding it, skip this branch.
- If the user wants help and the source list is missing, sparse, too broad, or clearly incomplete, hand off to the project skill `discover-sources`.
- **Discovery will exclude the user's current or most recent employer by default.**
- If the source list is missing, sparse, too broad, or clearly incomplete and the user delegates, proceed with `discover-sources` by default.
- Pass the handoff enough context to make the discovery preference-aware:
  - user name
  - track display name
  - broad search area
  - the stated track preferences above
  - any user-provided companies, sectors, labs, organizations, job boards, or career pages
  - any existing source list, if present
- Prefer official homepage-linked careers pages or ATS boards from user-supplied companies when `discover-sources` finds them.
- Treat the returned source pack as a recommendation, not as final config.
- Present the user-facing discovery result as a concise shortlist: recommended sources, dropped sources, URL corrections, known caveats, recommended defaults to apply now, and only the truly necessary decisions. Do not dump full setup-ready records unless the user asks for debug detail.
- Review the proposed sources with the user by leading with one recommended keep/drop/cadence/filter package. If the user delegates or confirms the recommendation, apply it and continue automatically with normalization instead of reopening each item separately.
- Reuse suggested cadence buckets and search terms from `discover-sources` as defaults when they fit.
- Use `integration_follow_up` from `discover-sources` to distinguish normal config from partial/follow-up or unsupported sources.
- Treat `match_rule_suggestion` from `discover-sources` as a draft for broad/noisy sources only; confirm it with the user before writing it.
- Do not turn this branch into source integration. Deep validation and coding escalation still happen later.

### 4. Normalize, probe, and integrate sources

The goal of setup is a **first-digest milestone**: a rendered digest from a valid scaffold that proves the track works. **Do not let failed or complex secondary sources block this milestone.**

1. Normalize the source list.
   - Use `shared/templates/track_sources.json`, `track_source_state.json`, and `track_match_rules.json` as schema templates rather than inventing fields.
   - Normalize the slug before writing files.
   - Infer `discovery_mode` from the source URL when obvious.
   - If the correct mode is unclear, prefer `html` over inventing a new unsupported mode.
2. Read preference context before finalizing search terms and filters.
   - Read `profile/cv.md`, `profile/prefs_global.md`, and the draft `tracks/{track_slug}/prefs.md`.
3. Auto-pick canaries where possible.
   - Use `scripts/probe_career_source.py <url> --name "<source>" --term "<term>" --pretty` for setup probing.
   - Store selected or deferred canaries in each source's `source_state.json` `integration` object.
4. **Prioritize the first digest.**
   - Validate only enough sources (roughly 2-4) to prove the track works and produce a useful first digest.
   - After the first digest milestone is reached (see Step 6), report failed or deferred sources.
   - **Do not manually troubleshoot secondary sources** during interactive setup unless the user explicitly chooses that.
5. Defer complex integration.
   - **Do not run synchronous `scripts/source_integration.py`** during normal interactive setup.
   - If a source needs custom code, queue it for background integration instead of waiting for it.
   - Use `./.venv/bin/python scripts/start_source_integration.py --track {track_slug} --source "{source_name}"` to start a background job.
   - Report the log path for any background integration jobs: `logs/source-integration/<track>/<timestamp>-<source>.log`.
6. Queue remaining pending sources for follow-up.
   - Write each remaining source's mutable follow-up state under `source_state.json` at `sources.<source_id>.integration`.
   - The follow-up command is `./.venv/bin/python scripts/integrate_next_source.py --track {track_slug} --today YYYY-MM-DD`.

When an old canary disappears, refresh it with:

```bash
./.venv/bin/python scripts/update_source_canary.py --track {track_slug} --source "{source_name}"
```

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
- `tracks/{track_slug}/GEMINI.md`
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

#### `CLAUDE.md` and `GEMINI.md`

Create `tracks/{track_slug}/CLAUDE.md` and `tracks/{track_slug}/GEMINI.md` next to the generated `AGENTS.md`.

Write exactly:

```md
@AGENTS.md
```

Do not add any other content to either file.

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
- Telegram delivery: run with `--delivery telegram`; requires `JOB_AGENT_TELEGRAM_CHAT_ID` plus a bot token via `JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD` or `JOB_AGENT_SECRETS_FILE`
- combine any requested delivery methods by passing multiple delivery flags

Use these manual-run examples:

```bash
bash scripts/run_track.sh --track {track_slug}
bash scripts/run_track.sh --track {track_slug} --delivery logseq
bash scripts/run_track.sh --track {track_slug} --delivery email
bash scripts/run_track.sh --track {track_slug} --delivery telegram
bash scripts/run_track.sh --track {track_slug} --delivery logseq --delivery email
bash scripts/run_track.sh --track {track_slug} --delivery logseq --delivery telegram
```

For Logseq:
- Check whether `.env.local` already has `LOGSEQ_GRAPH_DIR`.
- If it is missing and the user wants Logseq, help them identify the graph root path.
- Prefer running `bash scripts/setup_machine.sh --logseq-graph-dir <absolute-path>` or adding `export LOGSEQ_GRAPH_DIR=<absolute-path>` to `.env.local`.
- Do not inspect the Logseq graph contents during setup.

For email:
- Never ask the user to paste SMTP passwords or app passwords into chat.
- Ask the user for their non-secret SMTP values: provider, account, to, from, username, host, port, TLS (as needed).
- Write these non-secret values to `.env.local` yourself.
- Read `JOB_AGENT_SECRETS_FILE` from `.env.local` to determine where secrets should go.
- Give the user a simple command to save their password locally, using the literal resolved path, for example:
  `printf '%s\\n' 'export JOB_AGENT_SMTP_PASSWORD=PASTE_PASSWORD_HERE' >> '/home/user/.config/jobwatch/secrets.sh'`
- Do not run `send_digest_email.py --dry-run` before a digest exists.
- Sequence email setup this way:
  1. Configure non-secret SMTP settings in `.env.local` and provide the `secrets.sh` append command.
  2. Reuse the digest produced by Step 6 at `artifacts/digests/{track_slug}/YYYY-MM-DD.json`. If Step 6 was skipped or deferred, run `bash scripts/run_track.sh --track {track_slug}` now and confirm the JSON exists before continuing.
  3. Dry-run the email render:

```bash
./.venv/bin/python scripts/send_digest_email.py --track {track_slug} --date YYYY-MM-DD --dry-run
```

Then test real delivery only when the user confirms the local SMTP config is ready. `--dry-run` renders from the digest JSON and should not require SMTP env or execute `JOB_AGENT_SMTP_PASSWORD_CMD`.

For Telegram:
- **Explain the model briefly:** BotFather (@BotFather) creates a bot, you start a DM with that bot, and jobwatch sends digests to that DM. Default Telegram setup is DM with the bot; do not tell the user to create a Telegram channel.
- **Provide steps for @BotFather:**
  1. Open @BotFather on Telegram.
  2. Use `/newbot` to create a new bot.
  3. Choose a display name (e.g., "My JobWatch Bot").
  4. Choose a username ending in `bot` (e.g., `jobwatch_<track_slug>_<initials>_bot`).
- **Retrieve the Chat ID:**
  1. Read `JOB_AGENT_SECRETS_FILE` from `.env.local` to determine where secrets should go.
  2. Give the user a simple command to save their bot token locally, using the literal resolved path, for example:
     `printf '%s\\n' 'export JOB_AGENT_TELEGRAM_BOT_TOKEN=PASTE_TOKEN_HERE' >> '/home/user/.config/jobwatch/secrets.sh'`
  3. Tell the user to open their new bot in Telegram and press **Start**.
  4. Run `./.venv/bin/python scripts/telegram_chat_id.py` to find the chat ID.
- Never ask the user to paste the bot token into chat.
- Once the chat ID is retrieved, write `JOB_AGENT_TELEGRAM_CHAT_ID=<id>` to `.env.local` yourself.
- Do not run `send_digest_telegram.py --dry-run` before a digest exists.
- Sequence Telegram setup this way:
  1. Provide the `secrets.sh` append command for the bot token.
  2. Run `telegram_chat_id.py` to get the chat ID and write it to `.env.local`.
  3. Reuse the digest produced by Step 6 at `artifacts/digests/{track_slug}/YYYY-MM-DD.json`. If Step 6 was skipped or deferred, run `bash scripts/run_track.sh --track {track_slug}` now and confirm the JSON exists before continuing.
  4. Dry-run the Telegram render:

```bash
./.venv/bin/python scripts/send_digest_telegram.py --track {track_slug} --date YYYY-MM-DD --dry-run
```

Then test real delivery only when the user confirms the local Telegram config is ready. `--dry-run` renders from the digest JSON and should not require Telegram secrets or execute `JOB_AGENT_TELEGRAM_BOT_TOKEN_CMD`.

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
--delivery telegram
--delivery logseq --delivery email
```

Scheduling caveats:
- One active schedule entry per track is the default; `scripts/configure_schedule.py` replaces an existing entry for the same track and preserves other tracks.
- If email delivery is scheduled, remind the user that SMTP values must be filled in `.env.local` before the scheduled run.
- If Telegram delivery is scheduled, remind the user that `JOB_AGENT_TELEGRAM_CHAT_ID` plus token retrieval must be filled in `.env.local` or `JOB_AGENT_SECRETS_FILE` before the scheduled run.
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

If Telegram delivery was requested, validate the sequence after the first digest exists:

15. `bash scripts/run_track.sh --track {track_slug}` with no delivery, unless already run.
16. Confirm `artifacts/digests/{track_slug}/YYYY-MM-DD.json` exists.
17. `./.venv/bin/python scripts/send_digest_telegram.py --track {track_slug} --date YYYY-MM-DD --dry-run`

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
- **A short "deferred sources / background jobs" section listing any sources that still need custom integration or follow-up.**
- **If repository files were changed, suggest a succinct commit message. Otherwise, note that generated profile/track artifacts are local and gitignored.**
