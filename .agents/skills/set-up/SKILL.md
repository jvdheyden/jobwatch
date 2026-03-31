---
name: set-up
description: Set up a new search track for the job-agent.
---

# Skill: Set up a new track for the job-agent

Use this skill to scaffold a new track over the shared job-agent workflow.

Default assumption:
- This is a scaffolding task, not a full source-integration task.
- Reuse the shared scripts in `scripts/`.
- Do not add new discovery code to `scripts/discover_jobs.py` unless the user explicitly asks for source integration now.

## Workflow

### 1. Gather input

Ask for:
- user name, unless already known
- track display name
- proposed track slug; offer a slugified version using lowercase letters, digits, and underscores
- broad search area for the track
- track preferences:
  - goals / role types
  - keep-only keywords
  - important constraints or red flags
- sources:
  - `Check every run`
  - `Check every 3 runs`
- track-wide search terms
- source-specific search terms, including whether any source should use `[override]`
- whether the user wants a launchd plist now, and if so, at what local time. By default schedule the agent for this to track to run along with other already scheduled agents for other tracks.

### 2. Normalize and confirm config

- Normalize the slug before writing files.
- Infer `discovery_mode` from the source URL when obvious.
- Prefer existing modes already supported by `scripts/discover_jobs.py`.
- Common modes worth trying first:
  - `workday_api`
  - `greenhouse_api`
  - `lever_json`
  - `ashby_api`
  - `ashby_html`
  - `html`
  - `iacr_jobs`
  - `yc_jobs_board`
  - `hackernews_jobs`
- If the correct mode is unclear, prefer `html` over inventing a new unsupported mode.
- Only do lightweight validation during setup. Do not search every source exhaustively.
- If an existing mode is good enough, stop there. Do not escalate into coding work just because a source is imperfect.
- If a source clearly cannot be covered by an existing mode, tell the user and either:
  - leave it out for now, or
  - keep it in `sources.md` with the best existing mode and note that it needs follow-up integration

Before generating files, summarize the normalized config and confirm it.

### 2b. Optional source-integration escalation

Use this branch only when the user wants source integration now for a specific source.

Escalate only if all of the following are true:
- the source is important enough that missing it would materially weaken the track
- an existing mode was tried or reasonably evaluated first
- `html` or another fallback does not produce usable results
- a canary is available, ideally with both title and URL

When those conditions hold, hand off to repo-development coding work governed by `.agents/skills/coding/SKILL.md`.

Treat the handoff as a narrow implementation task, not a continuation of setup exploration.

The handoff should include:
- track slug
- source name
- source URL
- current attempted `discovery_mode`
- canary title
- canary URL if available
- a short statement of what failed
- the expected success condition in `scripts/discover_jobs.py`

Expected coding output:
- minimal support for that source in `scripts/discover_jobs.py`
- one focused automated test
- validation with `python3 scripts/discover_jobs.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --pretty`
- if shared code changed, `scripts/test.sh`

After the coding handoff succeeds:
- update `sources.md` with the correct `discovery_mode`
- mention the new support explicitly in the final response

If the coding handoff is not requested or does not succeed:
- keep the source on the track only if an existing mode is still somewhat usable
- otherwise leave it out and note it as follow-up work

### 3. Generate files

Create:
- `tracks/{track_slug}/prefs.md`
- `tracks/{track_slug}/sources.md`
- `tracks/{track_slug}/AGENTS.md`
- `tracks/{track_slug}/digests/`
- optionally `scripts/com.jvdh.{track_slug_with_hyphens}-job-agent.plist`

Do not hand-write `tracks/{track_slug}/ranked_overview.md` or `shared/ranked_jobs/{track_slug}.json`.
Let `scripts/update_ranked_overview.py --track {track_slug}` initialize those.

#### `prefs.md`

Write `tracks/{track_slug}/prefs.md` using this template:

```md
# {track display name} track preferences

Interpret this file as a specialization of `profile/prefs_global.md`.
If this file conflicts with the global preferences, this file takes precedence for the {track display name} track.

## Goals
Role types:
{user input goals / role types}

## Keep only roles matching at least one of these keywords
{user input keep-only keywords}

## Constraints and red flags
{user input constraints / red flags}
```

#### `sources.md`

Write `tracks/{track_slug}/sources.md` using this template:

```md
Only check the sources below for this track.

Do not waste time on broad employer pages outside this list.

Cadence note:
- `last_checked` is updated only on successful normal daily runs.
- For `Check every 3 runs`, treat one scheduled day as one run.
- Skip sources checked in the previous 2 scheduled days; recheck on day 3 or later.
- Manual same-day reruns do not advance cadence.
- `discovery_mode` is used by `../../scripts/discover_jobs.py` for deterministic source coverage.

## Check every run
| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Check every 3 runs
| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms
{track-wide terms}

### Source-specific search terms
Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.

Add `[override]` after the source name to replace the track-wide terms for that source.

{source-specific terms}

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ../../shared/seen_jobs.md
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
```

#### `AGENTS.md`

Use `tracks/core_crypto/AGENTS.md` as the base template.

Copy its structure, then replace all track-specific values:
- change the title and track slug
- replace every `core_crypto` artifact path, ranked-state path, and script argument with `{track_slug}`
- replace the candidate name with the current user name
- rewrite the fit language so it matches the new track's search area instead of applied cryptography
- keep the same workflow structure unless the user explicitly wants a different one

Important:
- Do not leave any `core_crypto` path behind in the generated file
- Do not leave crypto-specific fit text in a non-crypto track
- Keep the run boundaries, same-day rerun behavior, JSON digest flow, and ranked-overview rebuild steps aligned with the current shared workflow

#### Optional launchd plist

If the user wants scheduled runs, create `scripts/com.jvdh.{track_slug_with_hyphens}-job-agent.plist` by adapting `scripts/com.jvdh.core-crypto-job-agent.plist`.

Change:
- plist label
- plist filename
- `--track {track_slug}`
- schedule time
- launchd stdout/stderr log paths

Do not change the shared runner shape. The plist should still call `scripts/run_track.sh`.

### 4. Validation

After scaffolding, run:

1. `python3 scripts/discover_jobs.py --track {track_slug} --list-sources`
2. `python3 scripts/discover_jobs.py --track {track_slug} --today YYYY-MM-DD --plan-only --due-only --pretty`
3. `python3 scripts/update_ranked_overview.py --track {track_slug}`

If you created a plist, also run:

4. `plutil -lint scripts/com.jvdh.{track_slug_with_hyphens}-job-agent.plist`

If setup required changes to shared code such as `scripts/discover_jobs.py`, also run:

5. `scripts/test.sh`

### 5. Final response

Report:
- what files were created or changed
- which sources were included and with which `discovery_mode`
- which validation commands passed
- any sources that still need custom integration or follow-up
- a succinct suggested commit message
