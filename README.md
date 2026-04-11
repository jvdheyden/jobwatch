# Job Agent

This repository runs a Codex-assisted job-search workflow with per-track discovery, ranking, digest generation, and optional delivery to Logseq or email.

Each track run produces local JSON and Markdown artifacts first. Delivery is a separate opt-in step:

## New User Setup

1. Requirements:
   - Python 3
   - the Codex CLI 
   - on Linux, `bwrap` if you want Codex sandboxing backed by Bubblewrap
2. From the repo root, bootstrap the checkout for local use:

```bash
bash scripts/bootstrap_machine.sh
```

This writes machine-local config, bootstraps the repo-local virtualenv, and generates scheduler artifacts under `.scheduler/`.

Machine-local config lives in `.env.local`, which is gitignored. `setup_machine.sh` writes:

- `JOB_AGENT_ROOT`
- `CODEX_BIN`
- optional `LOGSEQ_GRAPH_DIR`
- commented `JOB_AGENT_SMTP_*` placeholders for email delivery

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

The setup flow creates the track files, validates the track, then asks which delivery methods you want: local artifacts only, Logseq, email, or both.

5. Add one or more schedule entries to `.schedule.local`, for example:

```text
daily 08:00 track core_crypto
daily 08:00 track core_crypto --delivery logseq
daily 08:00 track core_crypto --delivery email
daily 08:00 track core_crypto --delivery logseq --delivery email
```

The first form produces local artifacts only. Add delivery flags only after the matching local config is ready.

- local artifacts only: no delivery flag
- Logseq sync: `--delivery logseq`
- email delivery: `--delivery email`
- both: pass both delivery flags


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

By default, this leaves the local JSON and Markdown artifacts in the repository and does not deliver them anywhere else.

Optional delivery targets can be requested per run:

```bash
bash scripts/run_track.sh --track <track-slug> --delivery logseq
bash scripts/run_track.sh --track <track-slug> --delivery email
bash scripts/run_track.sh --track <track-slug> --delivery logseq --delivery email
```

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
bash scripts/setup_machine.sh --logseq-graph-dir /absolute/path/to/logseq
```

or by editing `.env.local` locally:

```bash
export LOGSEQ_GRAPH_DIR=/absolute/path/to/logseq
```

Then run with `--delivery logseq`.

## Development Checks

To run the repo test suite:

```bash
bash scripts/test.sh
```
