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
- For source integration, evaluate newly added or materially changed sources; do not reevaluate stable unchanged sources unless the user asks.

## Workflow

### 1. Gather the minimum `prefs.md` brief first

Start by collecting only the minimum information needed to draft `prefs.md`.

Ask for:
- user name, unless already known
- track display name
- proposed track slug; offer a slugified version using lowercase letters, digits, and underscores
- broad search area for the track
- goals / role types
- keep-only keywords, or an explicit `none yet`
- important constraints or red flags, or an explicit `none yet`
- geography / remote preferences, or an explicit `none yet`

Hard gate:
- Do not call `../discover-sources/SKILL.md` until this minimum brief is captured in the conversation or already exists in `tracks/{track_slug}/prefs.md`.
- Track name or slug alone is not enough.
- Do not infer a source list from `cv.md`, `profile/prefs_global.md`, or the track name alone.
- If the minimum brief is not available yet, stay in question-asking mode.

### 2. Ask for known companies and job boards

After the minimum `prefs.md` brief is captured, ask what sources the user already knows and wants on the track.

Ask for:
- known companies to track, if any
- known job boards or career pages, if any
- optional sectors, labs, or organizations to target
- existing sources already bucketed by cadence, if known:
  - `Check every run`
  - `Check every 3 runs`
  - `Check every month`
- track-wide search terms, if already known
- source-specific search terms, including whether any source should use `[override]`, if already known
- whether the user wants a launchd plist now, and if so, at what local time. By default schedule the agent for this to track to run along with other already scheduled agents for other tracks.

### 3. Optional source discovery

Use this branch only after the minimum `prefs.md` brief is available and the user has had a chance to provide known companies and job boards.

- First summarize the current setup brief and current source list:
  - goals / role types
  - keep-only keywords
  - constraints or red flags
  - geography / remote preferences
  - optional seed companies, sectors, labs, or organizations
  - any known companies, job boards, or career pages already supplied by the user
- Then ask whether the user wants help finding official sources via `../discover-sources/SKILL.md`.
- Treat discovery as opt-in assistance, not as a default setup step.
- If the user already has a strong official source list and does not want help expanding it, skip this branch.
- If the user wants help and the source list is missing, sparse, too broad, or clearly incomplete, hand off to `../discover-sources/SKILL.md`.
- Pass the handoff enough context to make the discovery preference-aware:
  - user name
  - track display name
  - broad search area
  - the stated track preferences above
  - any user-provided companies, sectors, labs, organizations, job boards, or career pages
  - any existing source list, if present
- Prefer official homepage-linked careers pages or ATS boards from user-supplied companies when `discover-sources` finds them.
- Treat the returned source pack as a recommendation, not as final config.
- Review the proposed sources with the user, let them trim or add to the list, and then continue with normalization.
- Reuse suggested cadence buckets and search terms from `discover-sources` as defaults when they fit.
- Do not turn this branch into source integration. Deep validation and coding escalation still happen later.

### 4. Normalize and confirm config

- Normalize the slug before writing files.
- Treat the final source list as coming from the user, from `discover-sources`, or from both.
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
- Common official board families worth recognizing during normalization include Greenhouse, Lever, Ashby, Workday, and Workable, even when some of them still fall back to `html`.
- If the correct mode is unclear, prefer `html` over inventing a new unsupported mode.
- If a source is clearly an official employer-linked board but has no dedicated supported mode, keep it with the best existing fallback, usually `html`, rather than excluding it for lacking a first-class integration.
- If track-wide or source-specific search terms were not already provided, derive an initial set from the user's stated preferences and any `discover-sources` suggestions.
- If `discover-sources` suggested cadence buckets, use those as defaults unless there is a clearer reason to place the source elsewhere.
- Only do lightweight validation during setup. Do not search every source exhaustively.
- If an existing mode is good enough, stop there. Do not escalate into coding work just because a source is imperfect.
- If a source clearly cannot be covered by an existing mode, tell the user and either:
  - leave it out for now, or
  - keep it in `sources.md` with the best existing mode and note that it needs follow-up integration

Before generating files, summarize the normalized config and confirm it.

### 4b. Optional source-integration escalation

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
- validation with `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --pretty`
- quality-gate validation with `./.venv/bin/python scripts/eval_source_quality.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`
- if that evaluation returns `repair_needed`, prefer `./.venv/bin/python scripts/repair_source.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]` over ad hoc manual retrying
- if shared code changed, `scripts/test.sh`

After the coding handoff succeeds:
- update `sources.md` with the correct `discovery_mode`
- treat the source as supported only if the quality-gate result is `final_status: "pass"`
- mention the new support explicitly in the final response

If the coding handoff is not requested or does not succeed:
- keep the source on the track only if an existing mode is still somewhat usable
- otherwise leave it out and note it as follow-up work

### 4c. Source-quality triage for setup-time integration

Use this branch when setup includes multiple newly added sources and the user wants a better-than-scaffolding integration pass.

Run `scripts/eval_source_quality.py` for each source that meets both conditions:
- it is newly added to the track or its scraper changed materially during this setup pass
- it was actually probed with a real `discover_jobs.py` run and has a canary

Do not run the quality gate for:
- stable unchanged sources already supported in the repo
- sources that were only scaffolded but not probed
- broad follow-up sources the user did not ask to integrate now

After running the quality gate, classify each evaluated source:
- `pass`: source is ready; keep it and report it as supported
- `repair_needed`: source is a candidate for coding repair
- `blocked`: stop treating the source as ready; report the blocker explicitly

Do not auto-escalate every `repair_needed` source into coding.

Instead, rank `repair_needed` sources by:
1. importance to the track
2. whether fallback parsing is unusable or too noisy
3. canary quality and reproducibility

Default repair budget during setup:
- escalate at most the top `2` `repair_needed` sources
- you may escalate `3` only if the user clearly asked for a broader integration pass
- leave the rest as follow-up work instead of turning setup into a long multi-source coding session

For each source selected for repair:
- hand off to repo-development coding work as described above
- prefer `scripts/repair_source.py` over ad hoc repeated retrying once an initial `eval_source_quality.py` run returns `repair_needed`
- treat the source as supported only if the final repair-loop result is `final_status: "pass"`

For each source not selected for repair:
- keep it only if the fallback mode is still somewhat usable and label it as partial/follow-up
- otherwise leave it out for now and report why

### 5. Generate files

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

## Location and work-mode preferences
{user input geography / remote preferences or "- none specified yet"}
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
- For `Check every month`, recheck once the calendar month changes.
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

## Check every month
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

Do not change the shared runner shape. The plist should still call `scripts/run_track.sh`. Reload the launch agent.

### 5. Validation

After scaffolding, run:

1. `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --list-sources`
2. `./.venv/bin/python scripts/discover_jobs.py --track {track_slug} --today YYYY-MM-DD --plan-only --due-only --pretty`
3. `./.venv/bin/python scripts/update_ranked_overview.py --track {track_slug}`

If you created a plist, also run:

4. `plutil -lint scripts/com.jvdh.{track_slug_with_hyphens}-job-agent.plist`

If setup required changes to shared code such as `scripts/discover_jobs.py`, also run:

5. `scripts/test.sh`

If setup included source integration with a canary, also run:

6. For each newly added or materially changed source that was actually probed and has a canary:
   `./.venv/bin/python scripts/eval_source_quality.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`

7. For at most the top 2 `repair_needed` sources by default:
   `./.venv/bin/python scripts/repair_source.py --track {track_slug} --source "{source_name}" --today YYYY-MM-DD --canary-title "..." [--canary-url "..."]`

Treat the source as ready only if the evaluation artifact reports `final_status: "pass"`.

### 6. Final response

Report:
- what files were created or changed
- whether `discover-sources` was used, and which returned sources were kept
- which sources were included and with which `discovery_mode`
- which validation commands passed
- which newly integrated sources passed the quality gate
- which sources were deferred instead of escalated, and why
- any sources that still need custom integration or follow-up
- a succinct suggested commit message
