# Contributing

Thanks for your interest in contributing. This repo is the upstream for [jvdheyden/jobwatch](https://github.com/jvdheyden/jobwatch/). Patches land via fork and pull request.

If you haven't yet, skim [`docs/architecture.md`](./docs/architecture.md) — one diagram of how the agent skills, deterministic scripts, and on-disk artifacts fit together.

## Fork and bring up a working checkout

1. Fork [`jvdheyden/jobwatch`](https://github.com/jvdheyden/jobwatch/) on GitHub, then clone your fork:

   ```bash
   git clone https://github.com/<your-user>/jobwatch.git
   cd jobwatch
   git remote add upstream https://github.com/jvdheyden/jobwatch.git
   ```

2. Bootstrap a local dev environment. Pick the agent CLI you'll run with:

   ```bash
   bash scripts/bootstrap_machine.sh --agent claude
   # or
   bash scripts/bootstrap_machine.sh --agent codex
   ```

   This creates the repo-local virtualenv at `./.venv`, writes machine-local config to `.env.local`, and seeds local profile placeholders under `profile/`. All of that is gitignored.

3. Confirm the baseline is green:

   ```bash
   bash scripts/test.sh
   ```

## Branch and develop

- Branch off `master`: `git checkout -b <short-topic-slug>`.
- Use the repo-local Python venv: `./.venv/bin/python -m pytest ...`. If `./.venv` is missing, `bash scripts/bootstrap_venv.sh` rebuilds it.
- Match the existing commit-message style — short imperative subject, optional body. `git log` is the canonical reference.
- Keep diffs minimal and avoid drive-by changes; the `coding` skill at [`.agents/skills/coding/SKILL.md`](./.agents/skills/coding/SKILL.md) spells out the conventions Claude Code and Codex follow when working in this repo, and they apply equally to human contributors.

## Where new code goes

| Change | Start here |
| --- | --- |
| Add or modify a discovery source | [`docs/contributing/adding-sources.md`](./docs/contributing/adding-sources.md) — provider lives under `scripts/discover/sources/`, never directly in `scripts/discover_jobs.py` |
| Edit an agent skill (`coding`, `existing-source-curation`, `find-jobs`, `rank-jobs`, `discover-sources`, `set-up`) | Edit the canonical file under `.agents/skills/<skill>/SKILL.md`, then run `bash scripts/sync_claude_skills.sh`. Never edit `.claude/skills/` directly. |
| Touch the track-run pipeline | `scripts/run_track.sh`, `scripts/run_scheduled_jobs.sh`, and the post-processing helpers around them. See [`docs/architecture.md`](./docs/architecture.md) for the call graph. |
| Add a new provider contract test | `tests/contract/` with fixtures under `tests/fixtures/sources/<discovery_mode>/`. |

## Docs placement

- Keep human-facing documentation in `docs/`.
- Keep tracked reference material that agents or scripts read directly in `shared/`, including generated catalogs and schemas.

## Before you push

```bash
bash scripts/sync_claude_skills.sh --check   # if you touched any .agents/skills/ file
bash scripts/test.sh
```

Both must pass.

## Open a pull request

1. Push your branch to your fork: `git push -u origin <short-topic-slug>`.
2. Open a PR against `https://github.com/jvdheyden/jobwatch` `master`. The GitHub CLI works well: `gh pr create --base master --head <your-user>:<short-topic-slug>`.
3. Describe what changed and why, and confirm `bash scripts/test.sh` passed locally.

## What never belongs in a PR

The following paths are gitignored and contain machine-local or personal data. They should never appear in a diff:

- `.env.local`, `.schedule.local`, `.scheduler/`
- `profile/`, `cv.md`, any `*.pdf`
- `tracks/*` except `tracks/test_workflow/` (the only tracked example track)
- `tracks/*/digests/`, `artifacts/`, `logs/`
- `shared/seen_jobs.md`, `shared/ranked_jobs/*`, `ranked_overview.md`
- `docs/plans/` (per-task agent handoff notes)

If `git status` shows any of these, run `git check-ignore -v <path>` to confirm and unstage.
