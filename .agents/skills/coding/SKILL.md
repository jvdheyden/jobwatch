---
name: coding
description: Coding agent for this repo.
---

# Coding Instructions

## Style
- Prefer the smallest change that solves the task.
- Clarity over cleverness; simplest working solution unless I ask for optimization.
- Separate concerns.
- Do not make unrelated changes.

## Code understanding
When explaining code, prefer call diagrams and (if relevant) state diagrams.

## Skill mirroring
- Canonical skill files live in `.agents/skills/`.
- After changing any skill, run `bash scripts/sync_claude_skills.sh` to refresh the generated mirrors in `.claude/skills/`.
- Never edit `.claude/skills/` directly unless explicitly asked.
- Before finishing any skill change, run `bash scripts/sync_claude_skills.sh --check`.

## Testing and verification
- Use the repo-local Python virtualenv at `./.venv` for Python tests and helper scripts.
- If `./.venv` is missing, bootstrap it with `bash scripts/bootstrap_venv.sh` before running Python test commands.
- Prefer `./.venv/bin/python -m pytest ...` over bare `pytest` or `python3 -m pytest`.
- When changing behavior or fixing a bug, add or update tests where reasonable.
- Do not force TDD for trivial refactors, config changes, or docs-only edits.
- Run relevant checks during development when helpful.
- Always run `scripts/test.sh` before finishing, unless the task is explicitly docs-only or the script is not applicable.
- If tests or checks fail, say so clearly and do not present the task as complete.

## Scope control
- Preserve existing behavior unless the task requires changing it.
- Prefer minimal diffs.
- Do not rename files, move files, or add dependencies unless necessary.
- Flag any uncertainty instead of guessing.

## Required response contract after code changes
After making changes, always:
1. Explain what changed and why.
2. Report how you verified it.
3. State whether `scripts/test.sh` passed or failed.
4. Mention any remaining caveats or assumptions.
5. Suggest a succinct commit message.
