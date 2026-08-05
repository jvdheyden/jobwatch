<!-- GENERATED FILE: source of truth is .agents/skills/set-up/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: set-up
description: Set up a new search track for the job-agent.
---

# Skill: Set up a new track for the job-agent

Use this skill for one guided onboarding flow that ends with a rendered first digest preview. Keep the interactive coordinator focused on reviewed decisions; use bounded artifacts, fresh setup workers, and deterministic scripts for expensive data and predictable file generation.

Interaction defaults:

- Prefer `recommend -> confirm or override` over blank questionnaires.
- When the user gives partial answers or delegates with `suggest`, `use your suggestions`, `pick whatever you think is best`, `default`, `sounds good`, or `go ahead`, carry forward safe defaults and continue.
- Ask only about high-risk or materially ambiguous choices.
- Do not reopen low-risk decisions the user already confirmed or delegated.
- Do not perform routine direct web discovery in the coordinator session.
- The first-digest milestone comes before delivery, scheduling, probing secondary sources, or source integration.

## Workflow

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

Ask for known employers, official careers pages, job boards, sectors, labs, and organizations. Offer a starter seed list and default cadence/search posture in the same message. Preserve good user-supplied official sources.

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

Store only the reviewed bounded profile projection, track brief, source seeds, and selected-source section. Never store transcripts, prompts, full CV prose, delivery credentials, secrets, or environment dumps. Reload `setup.json` before every later command instead of trusting conversation state.

### 3. Discover and confirm sources through a bounded worker

If the known official list is already strong, do not replace it; use the source worker only to normalize or fill clear gaps. Otherwise discovery is the recommended default.

Run exactly one fresh source worker:

```bash
./.venv/bin/python scripts/run_setup_worker.py \
  --role source_discovery \
  --input artifacts/setup/<setup-id>/setup.json \
  --output artifacts/setup/<setup-id>/source-pack.json
```

The worker receives only `setup.json`, has web access but no workspace writes, and returns bounded validated JSON. Do not pass the conversation, profile files, or a second prose brief. The worker excludes current or recent employers, prefers official sources, recommends roughly 4–8 primary sources, validates no more than three URLs, and proposes match rules only for broad/noisy boards.

Present the deterministic summary printed by the runner. Lead with `recommended_source_ids`, URL corrections, dropped/follow-up sources, and genuinely unresolved decisions. Treat the pack as a recommendation until the user confirms or delegates it.

Apply recommended sources:

```bash
./.venv/bin/python scripts/setup_contracts.py select-sources \
  --setup artifacts/setup/<setup-id>/setup.json \
  --source-pack artifacts/setup/<setup-id>/source-pack.json \
  --all-recommended
```

For overrides, use repeated `--source-id <id>` instead. Add repeated `--match-rule-id <id>` only for broad-source rules the user accepted. This atomically stores only canonical source records, track terms, and accepted match rules in `setup.json`. At least one source is required before scaffolding.

### 4. Scaffold the track deterministically

Run:

```bash
./.venv/bin/python scripts/scaffold_track.py \
  --input artifacts/setup/<setup-id>/setup.json
```

This command validates the completed setup, renders all shared templates, creates source config/state/docs, optional match rules, instructions, empty seen state, the digest directory, and initial ranked state/overview. It invokes no model and refuses to overwrite an existing track or ranked-state file.

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

### 6. Handle weak sources after the milestone

Use source coverage notes to identify partial, failed, or landing-page-only sources. Offer to start background integration for the top two or three while continuing delivery setup. If accepted, run:

```bash
./.venv/bin/python scripts/start_source_integration.py --track {track_slug} --source "{source_name}"
```

Report each log under `logs/source-integration/<track>/`. Do not synchronously wait unless explicitly asked. Queue additional work through existing `source_state.json` integration state and validate it with:

```bash
./.venv/bin/python scripts/integrate_next_source.py --track {track_slug} --today YYYY-MM-DD --dry-run
```

Use `scripts/probe_career_source.py`, `scripts/eval_source_quality.py`, and `scripts/update_source_canary.py` only for sources coverage shows need follow-up. Source parser changes belong in provider modules under `scripts/discover/sources/`, never in track config or the scaffolder.

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
