---
name: set-up
description: Interactively onboard a new search track, gather preferences and reference jobs, and produce its first digest.
---

# Skill: Set up a new search track

For existing-track preferences, source discovery or maintenance, use `existing-source-curation`.

## New-track setup

Use this skill for one guided onboarding flow that ends with a rendered first digest preview. Keep the interactive coordinator focused on reviewed decisions; use bounded artifacts, fresh setup workers, and deterministic scripts for expensive data and predictable file generation.

Interaction defaults:

- Prefer `recommend -> confirm or override` over blank questionnaires.
- When the user gives partial answers or delegates with `suggest`, `use your suggestions`, `pick whatever you think is best`, `default`, `sounds good`, or `go ahead`, carry forward safe defaults and continue.
- Ask only about high-risk or materially ambiguous choices.
- Do not reopen low-risk decisions the user already confirmed or delegated.
- Do not perform routine direct web discovery in the coordinator session.
- The first-digest milestone comes before delivery, scheduling, probing secondary sources, or source integration.

### Step zero. Make local profile files ready

Before creating a track, make these ignored local files usable:

- `profile/cv.md`
- `profile/prefs_global.md`

Never edit `shared/templates/profile/*`. If either local file is missing, run or recommend `bash scripts/setup_machine.sh`. Treat a file containing `JOB_AGENT_PROFILE_TEMPLATE` as default.

For `profile/cv.md`:

- Use a filled Markdown CV as the primary source.
- If it is default, check for PDFs in `profile/`.
- If exactly one PDF exists and `pdftotext` is available, draft concise Markdown and ask the user to review it.
- If several PDFs exist, ask which to use.
- If none exists, ask only: **"If you want me to read a PDF, tell me the path or copy it into `profile/` now; then I will extract it. Otherwise complete `profile/cv.md` now and tell me when ready."**
- Do not ask the user to paste a full CV into chat unless they explicitly choose that.

For `profile/prefs_global.md`, infer only safe facts from the CV and review durable preferences: work mode, geography, seniority, contract type, authorization, hard constraints, positive signals, borderline signals, red flags, and practical or compensation constraints. Track preferences may override these later.

If the user defers profile cleanup, continue but warn that source selection and ranking will be weaker. Ignored local files may be unreadable through some provider file tools; use shell reads when necessary.

### 1. Gather the minimum track brief

Collect:

- user name
- display name and a lowercase underscore slug
- broad search area
- goals or role types
- keep-only keywords, or explicit `none yet`
- constraints or red flags, or explicit `none yet`
- geography or remote preferences, or explicit `none yet`

Offer a recommended draft based on the reviewed profile. Do not start source discovery from only a name, slug, CV, or global preferences.

### 2. Gather source seeds

Ask for known employers, official careers pages, job boards, sectors, labs, and organizations. Offer a starter seed list and default cadence/search posture in the same message. Also invite optional reference postings: **"If you've already found one or two interesting job postings, please share their links. These help calibrate the search and verify that Jobwatch finds the kinds of jobs you're interested in."** Do not wait for examples or block onboarding if the user has none.

Use `shared/source_curation.md` for selection and evidence policy. Store examples in `reference_jobs`, including why the user likes them. An example remains useful after expiration; only independently confirmed available, in-scope postings become live canaries. Keep all examples and official seeds, including unresolved associations or explicit exclusion reasons. Refer to the evidence contracts in `docs/architecture.md`.

The durable setup state uses this layout:

```text
artifacts/setup/<setup-id>/
  setup.json
  source-pack.json
  preview-context.json
  preview-result.json
```

Generate a setup id shaped like `YYYYMMDDTHHMMSSZ-xxxxxxxx`. Draft the v1 `jobwatch_setup` object described in `docs/architecture.md` at `setup.draft.json`, then normalize and atomically persist it:

```bash
./.venv/bin/python scripts/setup_contracts.py validate \
  --kind setup \
  --input artifacts/setup/<setup-id>/setup.draft.json \
  --output artifacts/setup/<setup-id>/setup.json
```

Store only the reviewed bounded profile projection, track brief, source seeds, reference jobs, canary evidence and selected-source section. Never store transcripts, prompts, full CV prose, delivery credentials, secrets, or environment dumps. Reload `setup.json` before every later command instead of trusting conversation state.

### 3. Discover and confirm sources through a bounded worker

If the known official list is already strong, do not replace it; use the source worker only to normalize or fill clear gaps. Otherwise discovery is the recommended default.

Run exactly one fresh source worker:

```bash
./.venv/bin/python scripts/run_setup_worker.py \
  --role source_discovery \
  --input artifacts/setup/<setup-id>/setup.json \
  --output artifacts/setup/<setup-id>/source-pack.json
```

The worker receives only `setup.json` as user context, plus the canonical discovery skill and shared selection instructions inline. It has web access but no workspace writes and returns bounded validated JSON. Do not pass the conversation, profile files or a second prose brief.

Present the deterministic summary printed by the runner. Lead with `recommended_source_ids`, URL corrections, seed outcomes, reference associations, dropped/follow-up sources and genuinely unresolved decisions. Resolve omitted or unexplained user seeds/examples before selection. Treat the pack as a recommendation until the user confirms or delegates it.

Before confirming the pack, review its retrieval vocabulary against the brief's requested role families and domains. Check effective source overrides, native filters and proposed match rules for accidental exclusions. Keep semantic preferences distinct from literal retrieval terms; missing preference words alone do not require adding terms. Resolve concrete gaps in the pack before selection and revalidate it with the existing source-pack validator. A zero-result preview later proves execution, not adequate recall.

Apply recommended sources:

```bash
./.venv/bin/python scripts/setup_contracts.py select-sources \
  --setup artifacts/setup/<setup-id>/setup.json \
  --source-pack artifacts/setup/<setup-id>/source-pack.json \
  --all-recommended
```

For overrides, use repeated `--source-id <id>` instead. Add repeated `--match-rule-id <id>` only for broad-source rules the user accepted. This atomically stores canonical source records, track terms, accepted match rules, reference associations, seed outcomes and canary evidence in `setup.json`. Evidence for unselected sources remains in that decision artifact. At least one source is required before scaffolding.

### 4. Scaffold the track deterministically

Run:

```bash
./.venv/bin/python scripts/scaffold_track.py \
  --input artifacts/setup/<setup-id>/setup.json
```

This command validates the completed setup, renders all shared templates, creates source config/state/docs, durable reference jobs, pending source verification (including live canaries), optional match rules, instructions, empty seen state, the digest directory, and initial ranked state/overview. It invokes no model and refuses to overwrite an existing track or ranked-state file.

Do not hand-render these files during normal setup. If the command returns `status: incomplete`, do not delete the committed track; report its exact incomplete output and run the returned `recovery_command`.

Keep source probing and integration outside the scaffolder. Failed or complex secondary sources must not block the first digest. Never run synchronous `scripts/source_integration.py` during interactive setup.

### 5. Run the compact first digest preview

Run:

```bash
./.venv/bin/python scripts/run_setup_preview.py \
  --setup artifacts/setup/<setup-id>/setup.json \
  --today YYYY-MM-DD
```

This runner:

1. Executes deterministic discovery.
2. Builds bounded `preview-context.json`, excluding seen jobs and full discovery diagnostics.
3. Launches one fresh no-web `preview_ranker` with only that artifact.
4. Validates `preview-result.json` and requires one judgment per candidate id.
5. Deterministically assembles the standard digest and runs existing Markdown/state post-processing.

Do not use `run_track.sh` for the first preview. Do not give the preview worker the full discovery artifact, profile files, track instructions, or setup conversation.

Confirm these outputs:

- `artifacts/setup/<setup-id>/preview-context.json`
- `artifacts/setup/<setup-id>/preview-result.json`
- `artifacts/digests/{track_slug}/YYYY-MM-DD.json`
- `tracks/{track_slug}/digests/YYYY-MM-DD.md`

Paste the rendered digest body if short, otherwise its first roughly 40 lines, and summarize strong versus borderline matches in one line. Say explicitly when no relevant roles were found; a valid zero-result digest still proves the scaffold works. Treat runner failure as a blocker unless the user explicitly defers the preview.

### 6. Verify sources asynchronously after the milestone

Use the common onboarding/verification procedure in `shared/source_curation.md`. All newly registered sources are queued, including sources reporting complete execution. Prioritize user canaries, other independent evidence and weak/high-value sources. A complete scrape with a missing live canary still needs evaluation; no canary means basic support at best.

Start authorized verification/integration in the background for the top two or three sources while continuing delivery setup:

```bash
./.venv/bin/python scripts/start_source_integration.py --track {track_slug} --limit 3
```

Report logs under `logs/source-integration/<track>/` and leave remaining sources queued. Do not synchronously wait unless asked. No expensive evaluation belongs in scaffolding, the first-preview runner or scheduled track runs. Report configured, basic-support and independently-verified sources accurately; canary presence never proves exhaustive coverage.

### 7. Configure delivery and scheduling

Only after the first preview, ask which delivery methods and schedule the user wants:

- local artifacts only
- Logseq via `--delivery logseq`
- email via `--delivery email`
- Telegram via `--delivery telegram`
- multiple delivery flags when requested

Manual runs continue to use the unchanged scheduled/ordinary path:

```bash
bash scripts/run_track.sh --track {track_slug}
bash scripts/run_track.sh --track {track_slug} --delivery logseq
bash scripts/run_track.sh --track {track_slug} --delivery email
bash scripts/run_track.sh --track {track_slug} --delivery telegram
```

For Logseq, read `LOGSEQ_GRAPH_DIR`; if missing, ask for the graph root and write it through `scripts/setup_machine.sh`. Do not inspect graph contents.

For email:

- Never ask for SMTP passwords in chat.
- Write only non-secret provider/account/to/from/username/host/port/TLS values to `.env.local`.
- Read the literal `JOB_AGENT_SECRETS_FILE` path and give the user a local command to store `JOB_AGENT_SMTP_PASSWORD` there.
- Reuse the first-preview digest and run `scripts/send_digest_email.py --dry-run` before any real send.
- Send for real only after explicit confirmation.

For Telegram:

- Explain that BotFather creates a bot and the default target is a DM with that bot, not a channel.
- Have the user create the bot with `/newbot`, open it, press Start, and send a message such as `hi`; Start alone is insufficient.
- Never ask for the bot token in chat. Give a local command that stores `JOB_AGENT_TELEGRAM_BOT_TOKEN` in `JOB_AGENT_SECRETS_FILE`.
- Run `./.venv/bin/python scripts/telegram_chat_id.py` directly; do not source env/secrets manually around it.
- Write the resulting non-secret `JOB_AGENT_TELEGRAM_CHAT_ID` to `.env.local`.
- Reuse the first-preview digest and run `scripts/send_digest_telegram.py --dry-run` before any real send.
- Send for real only after explicit confirmation.

For scheduling, ask for daily time, weekly weekday/time, or monthly day/time. Use `scripts/configure_schedule.py` and append the selected delivery flags. Preserve one active entry per track and other tracks' entries. Install with `bash scripts/install_scheduler.sh` only after explicit confirmation.

### 8. Validate

The scaffolder and preview runner perform their own validation. Also verify:

```bash
./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --list-sources
./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --today YYYY-MM-DD --plan-only --due-only --pretty
```

Confirm `CLAUDE.md` and `GEMINI.md` contain exactly `@AGENTS.md`, the structured digest validates, and the rendered Markdown and ranked outputs exist. Run delivery dry-runs and schedule commands only when selected. Ordinary `run_track.sh`, scheduled ranking defaults, and source-integration routing remain unchanged.

### 9. Final response

Report:

- the setup id and artifact directory
- profile readiness status
- which source recommendations were kept and their discovery modes
- whether accepted broad-source match rules were created
- deterministic scaffold status
- first-preview JSON/Markdown paths and a short result summary
- partial/deferred sources and background job log paths
- selected delivery methods and missing local configuration
- scheduling cadence/time/install status
- validation commands that passed or failed
- provider-specific machine setup status when relevant
- that generated profile, setup, and track artifacts are local and ignored unless shared repository files were also changed
