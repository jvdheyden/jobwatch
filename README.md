# Job Agent

This repository runs an agent-assisted job-search workflow with per-track discovery, ranking, digest generation, and optional delivery to Logseq or email. Scheduled automation supports Codex CLI and Claude Code CLI.

Each track run produces local JSON and Markdown artifacts first. Delivery is a separate opt-in step.

## New User Setup

1. Requirements:
   - Python 3
   - either the Codex CLI or Claude Code CLI
   - for Claude, run Claude Code login locally before scheduled runs
   - on Linux with Codex, `bwrap` if you want Codex sandboxing backed by Bubblewrap
2. From the repo root, choose the automation agent and bootstrap the checkout for local use:

```bash
bash scripts/bootstrap_machine.sh --agent claude
# or
bash scripts/bootstrap_machine.sh --agent codex
```

This writes machine-local config, creates local profile placeholders, bootstraps the repo-local virtualenv, and generates scheduler artifacts under `.scheduler/`.

Machine-local config lives in `.env.local`, which is gitignored. `setup_machine.sh` writes:

- `JOB_AGENT_ROOT`
- `JOB_AGENT_PROVIDER`
- `JOB_AGENT_BIN`
- optional `LOGSEQ_GRAPH_DIR`
- commented `JOB_AGENT_SMTP_*` placeholders for email delivery

Local profile data lives in `profile/`, which is also gitignored. Setup creates default placeholders:

- `profile/cv.md`: the primary agent-readable CV context
- `profile/prefs_global.md`: durable preferences that apply across tracks

Before or during your first track setup, replace those placeholders with your own information. You can also copy a PDF CV into `profile/`; if `profile/cv.md` is still the default, the setup agent can help turn the PDF into Markdown. The Markdown CV remains the canonical file the agent reads.

If you only need to regenerate machine-local config later, run:

```bash
bash scripts/setup_machine.sh --agent claude
# or
bash scripts/setup_machine.sh --agent codex
```

3. If you are on Ubuntu and using Codex with `bwrap`, install the generated AppArmor profile:

```bash
sudo bash scripts/install_bwrap_apparmor.sh
```

Skip this on macOS. On Linux, this is only needed on hosts where AppArmor restricts unprivileged user namespaces.

4. Run the setup agent to create your first search track. In Codex or Claude Code, ask for a new track setup from the repo root. The track-setup workflow is defined in [`AGENTS.md`](./AGENTS.md) and [`.agents/skills/set-up/SKILL.md`](./.agents/skills/set-up/SKILL.md).

Example prompt:

```text
Set up a new search track for privacy engineering roles in Germany.
```

The setup flow creates the track files, asks which delivery methods you want, configures scheduling if requested, and validates the track.

Track-specific preferences live in `tracks/<track-slug>/prefs.md`. They are still required even when `profile/cv.md` and `profile/prefs_global.md` are filled, because each track can have narrower goals, keywords, constraints, and red flags.

5. Let the setup agent configure delivery and scheduling.

The setup agent asks whether you want scheduled runs, how often they should run, and at what local time. It then writes `.schedule.local` with `scripts/configure_schedule.py` and installs the shared scheduler with `bash scripts/install_scheduler.sh`.

Supported schedule choices:

- daily at `HH:MM`
- weekly on `mon`, `tue`, `wed`, `thu`, `fri`, `sat`, or `sun` at `HH:MM`
- monthly on day `1` through `31` at `HH:MM`

On Linux, scheduler install updates your user crontab with the shared per-minute dispatcher. On macOS, it installs the corresponding LaunchAgent. If you skip scheduling during setup, you can still run tracks manually.

## Manual Run

To run a track immediately:

```bash
bash scripts/run_track.sh --track <track-slug>
```

By default, this leaves the local JSON and Markdown artifacts in the repository and does not deliver them anywhere else.

Optional delivery targets can be requested per run:

```bash
bash scripts/run_track.sh --track <track-slug> --delivery logseq
bash scripts/run_track.sh --track <track-slug> --delivery email
bash scripts/run_track.sh --track <track-slug> --delivery logseq --delivery email
```

## Agent Provider

Select the provider explicitly during setup. The setup scripts write the selected provider and executable path into `.env.local`.

For Codex:

```bash
export JOB_AGENT_PROVIDER=codex
export JOB_AGENT_BIN=/absolute/path/to/codex
```

For Claude Code:

```bash
export JOB_AGENT_PROVIDER=claude
export JOB_AGENT_BIN=/absolute/path/to/claude
```

`scripts/setup_machine.sh --agent claude` writes those values when `claude` is discoverable on `PATH`. Claude runs use `claude -p` noninteractively with scoped allowed tools and normal project context loading; `--bare` is not used by default.

## Scheduled Runs

The setup agent normally manages `.schedule.local`. For manual maintenance, use the helper rather than editing scheduler syntax by hand:

```bash
./.venv/bin/python scripts/configure_schedule.py --track <track-slug> --cadence daily --time 08:00
./.venv/bin/python scripts/configure_schedule.py --track <track-slug> --cadence weekly --weekday mon --time 08:00 --delivery logseq
./.venv/bin/python scripts/configure_schedule.py --track <track-slug> --cadence monthly --month-day 1 --time 08:00 --delivery email
bash scripts/install_scheduler.sh
```

`configure_schedule.py` keeps one active schedule entry per track, replaces that track's old entry, and preserves other scheduled tracks.

## Email Digest

Daily digest emails are rendered from the structured digest JSON and ranked overview JSON, not from the Logseq/Markdown output.

Preview an email without sending it:

```bash
./.venv/bin/python scripts/send_digest_email.py --track <track-slug> --date YYYY-MM-DD --dry-run
```

To send through SMTP, edit `.env.local` locally and uncomment/fill the SMTP placeholders:

```text
JOB_AGENT_SMTP_HOST
JOB_AGENT_SMTP_PORT
JOB_AGENT_SMTP_FROM
JOB_AGENT_SMTP_TO
JOB_AGENT_SMTP_USERNAME
JOB_AGENT_SMTP_PASSWORD
JOB_AGENT_SMTP_TLS
```

Do not put SMTP passwords in tracked files or chat transcripts. After `.env.local` is filled, run the same command without `--dry-run` or use `--delivery email` on `run_track.sh`.

## Logseq Delivery

Logseq delivery copies the rendered daily digest and ranked overview into a Logseq graph.

Set `LOGSEQ_GRAPH_DIR` in `.env.local`, either by rerunning setup:

```bash
bash scripts/setup_machine.sh --agent claude --logseq-graph-dir /absolute/path/to/logseq
# or
bash scripts/setup_machine.sh --agent codex --logseq-graph-dir /absolute/path/to/logseq
```

or by editing `.env.local` locally:

```bash
export LOGSEQ_GRAPH_DIR=/absolute/path/to/logseq
```

Then run `scripts/run_track.sh` with `--delivery logseq`.

## Development Checks

To run the repo test suite:

```bash
bash scripts/test.sh
```
