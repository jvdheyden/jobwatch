# Machine Setup

Run `bash scripts/setup_machine.sh` after cloning the repo. That creates:

- `.env.local` for machine-local paths and binaries
- `.schedule.local` for local scheduled jobs
- `.scheduler/` for generated cron and launchd artifacts

In a normal terminal, the setup script prompts for any missing machine-local values.

- `CODEX_BIN` is required. If `codex` is already on `PATH`, the script offers that detected binary as the default.
- `LOGSEQ_GRAPH_DIR` is optional. If a common path such as `~/Documents/logseq` already exists, the script offers it as the default.

On Linux, the setup script canonicalizes an auto-detected `codex` path via `readlink -f` before writing `CODEX_BIN`. This helps scheduled runs use the real executable path when host policies such as AppArmor are tied to that path. On macOS, setup keeps the detected path as-is.

In non-interactive mode, the script does not prompt. `CODEX_BIN` must already be supplied via `--codex-bin`, the environment, existing `.env.local`, or `PATH`.

The setup script does not install scheduling. After you have created one or more tracks, add entries to `.schedule.local` using this format:

```text
daily 08:00 track core_crypto
```

Then install the platform scheduler with `bash scripts/install_scheduler.sh`.

- On Linux, that updates your user crontab with one generic entry that runs `scripts/run_scheduled_jobs.sh` every minute.
- On macOS, that installs a LaunchAgent that runs the same shared scheduler script every minute.

Logseq sync is optional. Set `LOGSEQ_GRAPH_DIR` in `.env.local` only if you want digest publication into a Logseq graph.
