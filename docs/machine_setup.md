# Machine Setup

For first-time setup, choose the automation agent explicitly after cloning the repo:

```bash
bash scripts/bootstrap_machine.sh --agent claude
# or
bash scripts/bootstrap_machine.sh --agent codex
```

That will:

- create machine-local config via `scripts/setup_machine.sh`
- create local profile placeholders under `profile/`
- bootstrap the repo-local virtualenv via `scripts/bootstrap_venv.sh`
- print a final next-step block with the guided setup command

In an interactive terminal, bootstrap asks whether to launch the guided setup agent now; the default answer is yes. In non-interactive mode, it never launches the agent unless you pass `--start-setup-agent`. Use `--no-start-setup-agent` to suppress the prompt in interactive runs.

You can also launch guided setup directly after bootstrap:

```bash
bash scripts/start_setup_agent.sh --agent claude
# or
bash scripts/start_setup_agent.sh --agent codex
```

For Claude interactive setup, treat the workspace trust dialog as a real CLI constraint. `scripts/start_setup_agent.sh --agent claude` still scopes tools and appends the setup contract, but if Claude shows a trust prompt before the setup flow starts:

1. trust the folder
2. rerun `bash scripts/start_setup_agent.sh --agent claude`
3. if Claude still opens without the guided setup contract, paste this fallback prompt:

```text
Use the project skill $set-up for a guided first-track setup in this repo.

Default behavior:
- Propose recommended answers for missing profile and track preferences; let me override them.
- If the source list is sparse, use $discover-sources as the recommended next step.
- After discovery, apply the recommended keep/drop/cadence/filter defaults unless I object.
- Continue automatically through canaries, probing, scaffolding, validation, and the first local digest preview.
- Do not move on to email or scheduling before the first digest preview.
```

If you only need to refresh the generated machine-local config later, run `bash scripts/setup_machine.sh --agent claude` or `bash scripts/setup_machine.sh --agent codex` directly. Existing `.env.local` files can also supply the previous `JOB_AGENT_PROVIDER`. That creates:

- `.env.local` for machine-local paths and binaries
- `.codex/config.toml` when the provider is Codex
- `.schedule.local` for local scheduled jobs
- `.scheduler/` for generated cron and launchd artifacts
- `.scheduler/bwrap-userns-restrict` on Linux when the provider is Codex and `bwrap` is on `PATH`
- `profile/cv.md` and `profile/prefs_global.md` if they do not already exist

The `profile/` directory is local user data and is ignored by Git. `profile/cv.md` is the primary agent-readable CV context. `profile/prefs_global.md` stores durable cross-track preferences. You can also place a PDF CV in `profile/`; the setup agent can use it to draft `profile/cv.md` when the Markdown CV is still the default placeholder.

Do not edit `.agents/skills/set-up/templates/profile/*`. Those files are tracked defaults used only when local profile files are missing.

In a normal terminal, the setup script prompts for missing machine-local values after the agent is selected.

- `--agent codex|claude` selects the automation provider for first-time setup. If omitted and no existing `JOB_AGENT_PROVIDER` is available, setup exits with exact commands to rerun.
- `JOB_AGENT_PROVIDER` stores that selected provider in `.env.local`.
- `JOB_AGENT_BIN` is required. If the selected provider binary is already on `PATH`, the script offers that detected binary as the default.
- `LOGSEQ_GRAPH_DIR` is optional. If a common path such as `~/Documents/logseq` already exists, the script offers it as the default.
- SMTP settings are optional. The script writes non-secret SMTP placeholders to `.env.local` plus either an existing `JOB_AGENT_SECRETS_FILE` value or a commented platform-specific suggestion for real secrets stored outside the repo. Prefer `JOB_AGENT_SMTP_PASSWORD_CMD`; if you need a static password, keep it in the external secrets file instead of `.env.local`.

On Linux, the setup script canonicalizes an auto-detected `codex` path via `readlink -f` before writing `JOB_AGENT_BIN`. This helps scheduled runs use the real executable path when host policies such as AppArmor are tied to that path. On macOS, setup keeps the detected path as-is. Claude paths are written as detected.

For Codex, the setup script also writes `.codex/config.toml` with a managed `shell_environment_policy` that puts this checkout's `.venv/bin` first on `PATH`. This keeps Codex shell commands and patch helpers on the repo-local Python while preserving the rest of the setup-time PATH. If an existing unmanaged `shell_environment_policy` is present, setup leaves it unchanged and reports a conflict instead of overwriting local Codex preferences.

On Linux with `JOB_AGENT_PROVIDER=codex`, if `bwrap` is available on `PATH`, the setup script also writes `.scheduler/bwrap-userns-restrict`, a minimal AppArmor profile that grants `userns create` to the detected `bwrap` binary. This is meant for hosts that enforce AppArmor restrictions on unprivileged user namespaces. Claude setups do not generate Codex/bwrap AppArmor guidance.

To install and reload that generated profile on Linux, run:

```bash
sudo bash scripts/install_bwrap_apparmor.sh
```

The installer copies the generated profile into `/etc/apparmor.d/bwrap-userns-restrict` and reloads it with `apparmor_parser -r`.

In non-interactive mode, the script does not prompt. `JOB_AGENT_BIN` must already be supplied via `--agent-bin`, the environment, existing `.env.local`, or the selected provider binary must be on `PATH`.

Provider examples:

```bash
bash scripts/setup_machine.sh --agent codex --agent-bin /absolute/path/to/codex
bash scripts/setup_machine.sh --agent claude --agent-bin /absolute/path/to/claude
```

For Claude Code, authenticate locally before scheduled runs:

```bash
claude -p 'Respond with exactly: ok'
```

If that command reports `Not logged in`, run Claude Code login in an interactive terminal first. Scheduled Claude automation uses noninteractive `claude -p` with scoped allowed tools and normal project context loading; it does not use `--bare` by default.

The track setup agent normally asks about delivery and scheduling after it creates a track. When you choose scheduled runs, it writes `.schedule.local` with `scripts/configure_schedule.py` and installs the platform scheduler with `bash scripts/install_scheduler.sh`.

Track setup creates track-specific preferences in `tracks/<track>/prefs.md`. Those preferences are separate from `profile/prefs_global.md` and can override global preferences for that track.

During first-track setup, the guided agent:

- fills or defers `profile/cv.md` and `profile/prefs_global.md`
- collects the minimum track brief before source discovery, but proposes recommended answers instead of waiting for the user to invent each field
- proposes a starter source list, cadence defaults, and track-wide terms instead of making the user start from a blank sheet
- treats `discover-sources` as the recommended next step when the source list is sparse and keeps its summary concise
- applies recommended keep/drop/cadence/filter defaults after source discovery unless the user overrides them
- probes accepted sources with `scripts/probe_career_source.py` where useful
- stores canaries and mutable integration state in `tracks/<track>/source_state.json`
- runs source-quality checks and treats a source as ready only when `eval_source_quality.py` reports `final_status: "pass"`
- runs `scripts/source_integration.py` for at most the top 2 integration-needed sources, then queues the rest for `scripts/integrate_next_source.py`
- runs the first local digest before email dry-run testing

If a canary disappears later, refresh it instead of deleting quality checks:

```bash
./.venv/bin/python scripts/update_source_canary.py --track <track> --source "<Source Name>"
```

For manual maintenance, use the helper instead of editing `.schedule.local` by hand:

```bash
./.venv/bin/python scripts/configure_schedule.py --track core_crypto --cadence daily --time 08:00
./.venv/bin/python scripts/configure_schedule.py --track core_crypto --cadence weekly --weekday mon --time 08:00 --delivery logseq
./.venv/bin/python scripts/configure_schedule.py --track core_crypto --cadence monthly --month-day 1 --time 08:00 --delivery email
```

Supported schedule file forms are:

```text
daily HH:MM track <track-slug> [--delivery logseq|email]...
weekly mon HH:MM track <track-slug> [--delivery logseq|email]...
monthly 1 HH:MM track <track-slug> [--delivery logseq|email]...
```

After changing schedules manually with the helper, install or refresh the platform scheduler with `bash scripts/install_scheduler.sh`.

- On Linux, that updates your user crontab with one checkout-specific entry that runs `scripts/run_scheduled_jobs.sh` every minute.
- On macOS, that installs a checkout-specific LaunchAgent that runs the same shared scheduler script every minute.

Logseq sync is optional. Set `LOGSEQ_GRAPH_DIR` in `.env.local` only if you want digest publication into a Logseq graph.

Email delivery is optional. Fill the non-secret email settings in `.env.local` locally, and keep any real app password or SMTP token outside the repo. Do not put SMTP passwords in tracked files, `.env.local`, or chat transcripts.

For common providers, start with the provider/account shorthand and then add recipients plus password retrieval:

```bash
export JOB_AGENT_EMAIL_PROVIDER=gmail
export JOB_AGENT_EMAIL_ACCOUNT=jobs@example.com
export JOB_AGENT_SMTP_TO=you@example.com
export JOB_AGENT_SMTP_PASSWORD_CMD='pass show email/jobwatch-smtp'
```

`JOB_AGENT_EMAIL_PROVIDER` currently supplies host/port/tls defaults for `gmail`, `fastmail`, `hotmail` / `outlook`, and Proton business SMTP. `JOB_AGENT_EMAIL_ACCOUNT` defaults the sender address and, for provider-backed setups, the SMTP username. Explicit `JOB_AGENT_SMTP_*` values still win when you need to override those defaults.

Keep only the retrieval wiring in `.env.local`. The real secret belongs either in the password manager entry read by `JOB_AGENT_SMTP_PASSWORD_CMD` or, if you need a static secret, in the external shell snippet named by `JOB_AGENT_SECRETS_FILE` as `export JOB_AGENT_SMTP_PASSWORD=...`.

Provider-specific setup notes:

- Gmail: `JOB_AGENT_EMAIL_PROVIDER=gmail` fills `smtp.gmail.com`, port `587`, and `STARTTLS`. Turn on Google 2-Step Verification, create a Google app password, and store that app password outside the repo. Put the retrieval command in `.env.local` via `JOB_AGENT_SMTP_PASSWORD_CMD`, or keep `export JOB_AGENT_SMTP_PASSWORD=...` in `JOB_AGENT_SECRETS_FILE`.
- Fastmail: `JOB_AGENT_EMAIL_PROVIDER=fastmail` fills `smtp.fastmail.com`, port `587`, and `STARTTLS`. Fastmail requires an app password for third-party SMTP clients, and Fastmail Basic plans do not include SMTP or app-password support. Store the app password outside the repo and wire it in through `JOB_AGENT_SMTP_PASSWORD_CMD` or `JOB_AGENT_SECRETS_FILE`.
- Outlook.com / Hotmail: `JOB_AGENT_EMAIL_PROVIDER=outlook` or `hotmail` fills `smtp-mail.outlook.com`, port `587`, and `STARTTLS`. Microsoft documents Modern Auth / OAuth2 as the preferred authentication method, so use this preset only if your account has a working app password or SMTP credential for SMTP AUTH. Store that secret outside the repo and expose it through `JOB_AGENT_SMTP_PASSWORD_CMD` or `JOB_AGENT_SECRETS_FILE`.

`JOB_AGENT_EMAIL_PROVIDER=proton` now means Proton business SMTP, not Proton Mail Bridge. Use it only with a Proton-generated SMTP token and a custom-domain address in `JOB_AGENT_EMAIL_ACCOUNT`. Proton’s documented business SMTP settings are `smtp.protonmail.ch`, port `587`, `STARTTLS`, and SMTP-token auth.

Normal personal Proton Mail via Proton Mail Bridge is still out of scope for the preset path. If you ever wire Bridge manually, keep its local host/port/username/TLS details explicit in `JOB_AGENT_SMTP_*` instead of using the provider shorthand.

Optional external secrets pointer in `.env.local`:

```bash
# Linux default suggestion:
export JOB_AGENT_SECRETS_FILE=${XDG_CONFIG_HOME:-$HOME/.config}/jobwatch/secrets.sh

# macOS default suggestion:
export JOB_AGENT_SECRETS_FILE=$HOME/Library/Application\ Support/jobwatch/secrets.sh
```

When `JOB_AGENT_SECRETS_FILE` is not already set, setup writes the platform-specific path above as a commented suggestion instead of enabling it automatically. That keeps `JOB_AGENT_SMTP_PASSWORD_CMD` and unauthenticated local SMTP setups from pointing at a missing file by default.

Preferred password retrieval examples:

```bash
export JOB_AGENT_SMTP_PASSWORD_CMD='security find-generic-password -s jobwatch-smtp -a jobs@example.com -w'
export JOB_AGENT_SMTP_PASSWORD_CMD='secret-tool lookup service jobwatch-smtp account jobs@example.com'
export JOB_AGENT_SMTP_PASSWORD_CMD='pass show email/jobwatch-smtp'
```

If you prefer a static password over `JOB_AGENT_SMTP_PASSWORD_CMD`, put it in the external file named by `JOB_AGENT_SECRETS_FILE`:

```bash
export JOB_AGENT_SMTP_PASSWORD=app-password
```

Plaintext repo-local `JOB_AGENT_SMTP_PASSWORD` in `.env.local` is no longer supported. `JOB_AGENT_SMTP_PASSWORD_CMD` is executed only for real sends, not for `--dry-run`.

Email setup sequence:

```bash
bash scripts/run_track.sh --track <track>
test -f artifacts/digests/<track>/YYYY-MM-DD.json
./.venv/bin/python scripts/send_digest_email.py --track <track> --date YYYY-MM-DD --dry-run
```

Only test a real send or schedule email delivery after the digest exists and the dry run renders correctly.
