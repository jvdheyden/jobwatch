<!-- GENERATED FILE: source of truth is .agents/skills/coding/SKILL.md -->
<!-- Do not edit here directly. After changing the source, resync mirrored skills. -->

---
name: coding
description: Coding agent for repo-development work in this open-source job-search agent repository.
---

# Coding Instructions

This skill has two halves. The sections above the **Non-interactive pivot** apply to every agent touching this repo's code, whether a human is driving or not. The sections below the pivot apply only to interactive repo-development work.

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
- If a simpler approach exists, say so.

## Behavioral defaults
- State assumptions explicitly when they affect implementation.
- If multiple plausible interpretations would lead to materially different implementations, surface or note them briefly instead of silently choosing.
- If the task is interactive and ambiguity blocks correct implementation, ask.
- If the task is unattended or scheduled, choose the most conservative minimal interpretation, state that assumption, and avoid speculative changes.

## Scope control
- Preserve existing behavior unless the task requires changing it.
- Match existing style, even if you would structure it differently.
- If you notice unrelated issues, note them; do not fix them unless asked.
- Prefer minimal diffs.
- Touch only code required for the task.
- Do not rename files, move files, or add dependencies unless necessary.
- Flag or note any uncertainty instead of guessing.
- Do not introduce abstractions, flags, or configuration unless the task clearly requires them.

## Non-interactive pivot

**If you are a non-interactive agent — a subprocess-invoked run, a scheduled job, a Codex `exec` session, a Claude `-p --no-session-persistence` session, or any other single-shot automation — your prompt is the contract. Stop reading here. Only the sections above (public vs private files, style, behavioral defaults, scope control) apply to you. Everything below this pivot applies only to interactive repo-development work where a human is in the loop.**

---

## Repo context

This is an open-source repository for an agent-assisted job-search workflow. The system combines deterministic Python code under `scripts/`, agent skills under `.agents/skills/`, tests under `tests/`, and gitignored per-user local state such as `profile/`, `tracks/<your-track>/`, `artifacts/`, and `logs/`.

Use this skill for **repo development**: changing shared code, tests, skills, scripts, or docs. Do not treat every task like a generic Python edit; first identify which subsystem you are touching and preserve the existing architecture and mode boundaries described in the repo docs.

## Read before editing

Before making non-trivial changes, read the smallest relevant set of docs for the subsystem you are touching:

- `AGENTS.md` for mode routing and repo-level rules
- `README.md` for the user-facing workflow, setup, scheduling, and delivery
- `docs/architecture.md` for the high-level system design and component boundaries
- `CONTRIBUTING.md` for contributor workflow and placement rules

When relevant, also read:

- `docs/discovery_modes.md` if the task touches discovery behavior or provider capabilities
- `docs/contributing/adding-sources.md` if the task adds or changes a discovery source
- the relevant skill under `.agents/skills/<skill>/SKILL.md` if the task touches agent behavior
- existing tests and fixtures in `tests/` for the subsystem you are changing

Do not read the entire repo by default for tiny localized edits. Read enough to understand the affected subsystem and avoid breaking architectural boundaries.

## Code understanding
When explaining code, prefer call diagrams and (if relevant) state diagrams.

## Planning and handoff

When you create a plan for non-trivial repo-development work, save it as Markdown under `docs/plans/` before or alongside implementation. For multi-step plans, pair each implementation step with a concrete verification check.

Use this default path shape:

```text
docs/plans/YYYY-MM-DD-<short-task-slug>.md
```

Save a plan for multi-step coding tasks, refactors, source integrations, or any task where another agent would need more than the final response to resume safely. You may skip a saved plan for tiny single-step edits, direct command answers, docs-only answers without implementation, or when the user explicitly asks not to write a plan.

Use the plan template in `docs/plans/template.md`.

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
- If resuming from an existing task, read the relevant `docs/plans/*.md` first and continue from its checklist instead of reconstructing context from chat. If you have a different agent id from the one in the plan, add your agent id to the owner field.
- If a plan becomes obsolete, mark `Status: complete` or explain why it was superseded.
- When you mark `Status: complete` also move the corresponding entry in `docs/roadmap.md` to Completed, if it exists.

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
- Prefer behavioral tests or consumer-level checks over prose-locking tests.
- Do not add tests that merely assert literal strings in docs, `AGENTS.md`, or skill files unless some script, parser, generator, or harness depends on that exact text.
- For docs-only or instruction-only changes, verification may be limited to manual review, mirror sync, and targeted checks of consuming code or generated artifacts.
- Avoid brittle tests that lock down non-semantic wording.
- Do not force TDD for trivial refactors, config changes, or docs-only edits.
- Run relevant checks during development when helpful.
- Always run `scripts/test.sh` before finishing, unless the task is explicitly docs-only or the script is not applicable.
- If tests or checks fail, say so clearly and do not present the task as complete.

## Required response contract after code changes
After making changes, always:
1. Explain what changed and why.
2. Report how you verified it.
3. State whether `scripts/test.sh` passed or failed.
4. Mention any remaining caveats or assumptions.
5. Suggest a succinct commit message.
