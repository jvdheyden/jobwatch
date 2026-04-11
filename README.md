# Job Agent

This repository runs a Codex-assisted job-search workflow with per-track discovery, ranking, digest generation, and optional scheduled runs.

## New User Setup

1. Install the base prerequisites:
   - Python 3
   - the Codex CLI on your `PATH`, or know the absolute path to the `codex` binary
   - on Linux, `bwrap` if you want Codex sandboxing backed by Bubblewrap
2. From the repo root, bootstrap the checkout for local use:

```bash
bash scripts/bootstrap_machine.sh
```

This writes machine-local config, bootstraps the repo-local virtualenv, and generates scheduler artifacts under `.scheduler/`.

If you only need to regenerate machine-local config later, run:

```bash
bash scripts/setup_machine.sh
```

3. If you are on Ubuntu, install the generated AppArmor profile for `bwrap`:

```bash
sudo bash scripts/install_bwrap_apparmor.sh
```

Skip this on macOS. On Linux, this is only needed on hosts where AppArmor restricts unprivileged user namespaces.

4. Run the setup agent to create your first search track. In Codex, ask for a new track setup from the repo root. The track-setup workflow is defined in [`AGENTS.md`](./AGENTS.md) and [`.agents/skills/set-up/SKILL.md`](./.agents/skills/set-up/SKILL.md).

Example prompt:

```text
Set up a new search track for privacy engineering roles in Germany.
```

5. Add one or more schedule entries to `.schedule.local`, for example:

```text
daily 08:00 track core_crypto
```

6. Install the scheduler:

```bash
bash scripts/install_scheduler.sh
```

On Linux this updates your user crontab with the shared per-minute dispatcher. On macOS it installs the corresponding LaunchAgent.

## Manual Run

To run a track immediately:

```bash
bash scripts/run_track.sh --track <track-slug>
```

## Email Digest

Daily digest emails are rendered from the structured digest JSON and ranked overview JSON, not from the Logseq/Markdown output.

Preview an email without sending it:

```bash
./.venv/bin/python scripts/send_digest_email.py --track <track-slug> --date YYYY-MM-DD --dry-run
```

To send through SMTP, set:

```bash
export JOB_AGENT_SMTP_HOST=smtp.example.com
export JOB_AGENT_SMTP_PORT=587
export JOB_AGENT_SMTP_FROM=jobs@example.com
export JOB_AGENT_SMTP_TO=you@example.com
export JOB_AGENT_SMTP_USERNAME=jobs@example.com
export JOB_AGENT_SMTP_PASSWORD=app-password
export JOB_AGENT_SMTP_TLS=starttls
```

Then run the same command without `--dry-run`.

## Development Checks

To run the repo test suite:

```bash
bash scripts/test.sh
```
