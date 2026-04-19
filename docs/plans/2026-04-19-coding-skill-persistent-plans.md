# Coding Skill Persistent Plans

Status: complete
Owner: Codex CLI agent; agent_id: 019da0de-f5fc-7132-99ce-197dd0ca9c8e
Last updated: 2026-04-19 10:19 CEST

## Goal

Update the `$coding` skill so non-trivial repo-development plans are saved as Markdown files with progress tracking and handoff notes. The owner field must include the agent/provider identity and the concrete agent id when available, so the user can resume that agent if needed.

## Current State

- Canonical skill file: `.agents/skills/coding/SKILL.md`.
- Generated mirror: `.claude/skills/coding/SKILL.md`.
- Existing repo docs include plan files directly under `docs/`; there was no `docs/plans/` directory yet.
- Skill mirror workflow requires `bash scripts/sync_claude_skills.sh` after canonical skill changes.

## Implementation Plan

- [x] Create this persistent plan file under `docs/plans/`.
- [x] Add planning, progress, and handoff rules to `$coding`.
- [x] Sync `.claude/skills/coding/SKILL.md`.
- [x] Run skill mirror check and `scripts/test.sh`.
- [x] Update this plan with final status, verification, and handoff notes.

## Progress Log

- 2026-04-19 10:05 CEST - Created initial persistent plan and captured the implementation scope.
- 2026-04-19 10:06 CEST - Updated `.agents/skills/coding/SKILL.md` with persistent plan, progress, handoff, and owner/agent_id rules.
- 2026-04-19 10:06 CEST - Ran `bash scripts/sync_claude_skills.sh`; generated `.claude/skills/coding/SKILL.md` is synced.
- 2026-04-19 10:07 CEST - Ran `bash scripts/sync_claude_skills.sh --check`; passed.
- 2026-04-19 10:09 CEST - Ran `bash scripts/test.sh`; passed with 388 passed, 28 skipped.
- 2026-04-19 10:10 CEST - Ran `git diff --check`; passed.
- 2026-04-19 10:10 CEST - Checked runtime environment and found `CODEX_THREAD_ID=019da0de-f5fc-7132-99ce-197dd0ca9c8e`; updated owner metadata and `$coding` guidance.
- 2026-04-19 10:10 CEST - Re-ran `bash scripts/test.sh` after the `$coding` guidance update; passed with 388 passed, 28 skipped.
- 2026-04-19 10:11 CEST - Added the exact safe shell check for Codex thread ids: `printf '%s\n' "${CODEX_THREAD_ID:-unknown}"`.
- 2026-04-19 10:15 CEST - Re-ran `bash scripts/test.sh` after the exact shell-check wording change; passed with 388 passed, 28 skipped.
- 2026-04-19 10:16 CEST - Added Claude Code cloud-session guidance: check `CLAUDE_CODE_REMOTE_SESSION_ID`; do not treat `CLAUDECODE=1` as a resumable id.
- 2026-04-19 10:19 CEST - Re-ran `bash scripts/test.sh` after the Claude Code guidance update; passed with 388 passed, 28 skipped.

## Handoff Notes

Implementation is complete. Changed files are `.agents/skills/coding/SKILL.md`, `.claude/skills/coding/SKILL.md`, and this plan file. The current Codex thread id is recorded in `Owner`. Final remaining step for any future agent is review/commit.

## Verification

- [x] `bash scripts/sync_claude_skills.sh --check`
- [x] `bash scripts/test.sh`
- [x] `git diff --check`

## Caveats

- The prompt did not expose a resumable id directly, but the shell environment exposed `CODEX_THREAD_ID`.
