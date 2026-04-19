---
name: coding
description: Coding agent for this repo.
---

# Coding Instructions

## Public vs private files

This repo mixes shared, git-tracked code with per-user, gitignored local state. The two halves follow different rules:

- **Tracked files** (anything not matched by `.gitignore`) are public/shared. On these files, the rules in this skill, `AGENTS.md`, and any per-skill `SKILL.md` take precedence over conflicting personal preferences from your global `~/.claude/CLAUDE.md` or `~/.codex/AGENTS.md`. Project conventions win.
- **Gitignored files** (your `profile/`, `tracks/<your-track>/`, `.env.local`, `.schedule.local`, `artifacts/`, `logs/`, `docs/plans/`, `shared/seen_jobs.md`, `shared/ranked_jobs/*`, etc.) are local-only. Your personal preferences win on these files.

If you are unsure which side a file is on, run `git check-ignore -v <path>`. If `git check-ignore` prints a match, the file is private; if it prints nothing, the file is public/tracked and project conventions apply.

## Style
- Prefer the smallest change that solves the task.
- Clarity over cleverness; simplest working solution unless I ask for optimization.
- Separate concerns.
- Do not make unrelated changes.

## Code understanding
When explaining code, prefer call diagrams and (if relevant) state diagrams.

## Planning and handoff

When you create a plan for non-trivial repo-development work, save it as Markdown under `docs/plans/` before or alongside implementation.

Use this default path shape:

```text
docs/plans/YYYY-MM-DD-<short-task-slug>.md
```

Save a plan for multi-step coding tasks, refactors, source integrations, repair work, or any task where another agent would need more than the final response to resume safely. You may skip a saved plan for tiny single-step edits, direct command answers, docs-only answers without implementation, or when the user explicitly asks not to write a plan.

Each plan file should include:

```md
# <Task Title>

Status: planned | in_progress | blocked | complete
Owner: <agent/provider>; agent_id: <resumable id if available, otherwise unknown>
Last updated: YYYY-MM-DD HH:MM <timezone>

## Goal
<What the user wants and why>

## Current State
<Relevant repo facts, files inspected, existing behavior, constraints>

## Implementation Plan
- [ ] Step 1
- [ ] Step 2

## Progress Log
- YYYY-MM-DD HH:MM - <decision, edit, command, result, or blocker>

## Handoff Notes
<Exactly what the next agent needs to know>

## Verification
- [ ] <focused check>
- [ ] `bash scripts/test.sh`, when required

## Caveats
<Open questions, blockers, flaky tests, known risks>
```

Owner requirements:
- Include the current agent/provider name.
- Include a concrete resumable agent id when the runtime exposes one.
- Check common runtime variables first, especially `$CODEX_THREAD_ID` for Codex sessions. A safe shell check is: `printf '%s\n' "${CODEX_THREAD_ID:-unknown}"`.
- For local Claude Code sessions, read `$CLAUDE_SESSION_ID` by running `echo $CLAUDE_SESSION_ID` (or the safer `printf '%s\n' "${CLAUDE_SESSION_ID:-unknown}"`).
- For Claude Code cloud sessions, check `$CLAUDE_CODE_REMOTE_SESSION_ID`. A safe shell check is: `printf '%s\n' "${CLAUDE_CODE_REMOTE_SESSION_ID:-unknown}"`. `$CLAUDECODE=1` only means the shell was spawned by Claude Code; it is not a resumable session id.
- If no resumable id is available, write `agent_id: unknown` rather than omitting the field.

Progress tracking rules:
- Keep checklist items current as work progresses.
- Update `Progress Log` after meaningful milestones, test runs, blockers, or scope changes.
- Before ending a turn, quota-limited pause, blocked state, or final response, update `Handoff Notes` with files changed, commands run and results, next concrete step, unresolved risks, and whether `scripts/test.sh` passed, failed, or was not run.
- If resuming from an existing task, read the relevant `docs/plans/*.md` first and continue from its checklist instead of reconstructing context from chat.
- If a plan becomes obsolete, mark `Status: complete` or explain why it was superseded.

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
