# Machine Setup

For first-time setup, run `bash scripts/bootstrap_machine.sh` after cloning the repo.

That will:

- create machine-local config via `scripts/setup_machine.sh`
- create local profile placeholders under `profile/`
- bootstrap the repo-local virtualenv via `scripts/bootstrap_venv.sh`

If you only need to refresh the generated machine-local config later, run `bash scripts/setup_machine.sh` directly. That creates:

- `.env.local` for machine-local paths and binaries
- `.schedule.local` for local scheduled jobs
- `.scheduler/` for generated cron and launchd artifacts
- `.scheduler/bwrap-userns-restrict` on Linux when `bwrap` is on `PATH`
- `profile/cv.md` and `profile/prefs_global.md` if they do not already exist

The `profile/` directory is local user data and is ignored by Git. `profile/cv.md` is the primary agent-readable CV context. `profile/prefs_global.md` stores durable cross-track preferences. You can also place a PDF CV in `profile/`; the setup agent can use it to draft `profile/cv.md` when the Markdown CV is still the default placeholder.

In a normal terminal, the setup script prompts for any missing machine-local values.

- `CODEX_BIN` is required. If `codex` is already on `PATH`, the script offers that detected binary as the default.
- `LOGSEQ_GRAPH_DIR` is optional. If a common path such as `~/Documents/logseq` already exists, the script offers it as the default.
- SMTP settings are optional. The script writes commented placeholders to `.env.local`; uncomment and fill them locally if you want email delivery.

On Linux, the setup script canonicalizes an auto-detected `codex` path via `readlink -f` before writing `CODEX_BIN`. This helps scheduled runs use the real executable path when host policies such as AppArmor are tied to that path. On macOS, setup keeps the detected path as-is.

On Linux, if `bwrap` is available on `PATH`, the setup script also writes `.scheduler/bwrap-userns-restrict`, a minimal AppArmor profile that grants `userns create` to the detected `bwrap` binary. This is meant for hosts that enforce AppArmor restrictions on unprivileged user namespaces.

To install and reload that generated profile on Linux, run:

```bash
sudo bash scripts/install_bwrap_apparmor.sh
```

The installer copies the generated profile into `/etc/apparmor.d/bwrap-userns-restrict` and reloads it with `apparmor_parser -r`.

In non-interactive mode, the script does not prompt. `CODEX_BIN` must already be supplied via `--codex-bin`, the environment, existing `.env.local`, or `PATH`.

The track setup agent normally asks about delivery and scheduling after it creates a track. When you choose scheduled runs, it writes `.schedule.local` with `scripts/configure_schedule.py` and installs the platform scheduler with `bash scripts/install_scheduler.sh`.

Track setup creates track-specific preferences in `tracks/<track>/prefs.md`. Those preferences are separate from `profile/prefs_global.md` and can override global preferences for that track.

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

- On Linux, that updates your user crontab with one generic entry that runs `scripts/run_scheduled_jobs.sh` every minute.
- On macOS, that installs a LaunchAgent that runs the same shared scheduler script every minute.

Logseq sync is optional. Set `LOGSEQ_GRAPH_DIR` in `.env.local` only if you want digest publication into a Logseq graph.

Email delivery is optional. Fill the `JOB_AGENT_SMTP_*` values in `.env.local` locally; do not put SMTP passwords in tracked files or chat transcripts.
