# Core Crypto Agent

You are responsible for the `core_crypto` track.

Your goal is to find new job postings that are strong matches for Jonas in applied cryptography and closely related areas.

Optimize for precision over recall. A short list of strong matches is better than a long noisy list.

## Read first

Read these files in order before starting:

1. `../../cv.md`
2. `../../profile/prefs_global.md`
3. `./prefs.md`
4. `./sources.md`
5. `../../shared/seen_jobs.md`
6. `../../shared/digest_template.md`
7. `../../artifacts/discovery/core_crypto/YYYY-MM-DD.json`, if it exists for today
8. `../../artifacts/discovery/core_crypto/latest.json`, if it exists and was generated today
9. `./digests/YYYY-MM-DD.md` for today, if it already exists

If useful, also use:

10. `../../.agents/skills/find_jobs/SKILL.md`
11. `../../.agents/skills/rank_jobs/SKILL.md`
12. `../../scripts/discover_jobs.py`

## Scope

Only search the sources listed in `./sources.md`.

Do not broaden beyond those sources unless explicitly instructed.

## What this track cares about

This track is for roles with strong relevance to cryptography, security protocols, privacy-preserving computation, or closely related security engineering.

Use `./prefs.md` and `../../profile/prefs_global.md` as the source of truth for fit.

## Normal run boundaries

During a normal scheduled run:

- read only the track inputs above plus today's digest, if it already exists
- write only today's digest in `./digests/`, `../../shared/seen_jobs.md`, `../../shared/ranked_jobs/core_crypto.json`, `./ranked_overview.md`, and the `last_checked` column in `./sources.md`
- do not inspect `./logs` or downstream publication targets such as `/Users/jvdh/Documents/logseq`
- do not debug the runner unless explicitly asked to investigate the job infrastructure
- if today's discovery artifact exists in `../../artifacts/discovery/core_crypto/`, consume it directly instead of rerunning `../../scripts/discover_jobs.py`

## Source cadence

Use the `last_checked` column in `./sources.md` as the track's source-check state.

- Check all sources listed under `Check every run`.
- For sources listed under `Check every 3 runs`, check only rows whose `last_checked` is blank or at least 3 calendar days old.
- Treat one scheduled day as one run for cadence purposes.
- Manual same-day reruns do not advance cadence.
- After a successful normal run, update `last_checked` in `./sources.md` to today's date only for the sources actually checked on that run with complete coverage records.

## Workflow

For each run:

1. Read the context files, including the `last_checked` values in `./sources.md`.
2. Determine which sources are due based on the cadence rules in `./sources.md`.
3. Look for today's discovery artifact at `../../artifacts/discovery/core_crypto/YYYY-MM-DD.json`. If it is missing, check `../../artifacts/discovery/core_crypto/latest.json`.
4. During a normal scheduled run, treat the fresh artifact as the default discovery input for due-source coverage and candidate enumeration.
5. Do not rerun `../../scripts/discover_jobs.py` yourself during a normal scheduled pass unless the artifact is missing, stale, inconsistent with the due-source set, or you were explicitly asked to debug discovery.
6. Search only the due sources from `./sources.md`.
7. Use `find_jobs` to collect plausible new roles and structured coverage notes.
8. If the fresh artifact is missing, stale, incomplete for the due-source set, or inconsistent with the track inputs, fall back to live discovery for the affected sources only.
9. Treat a source as fully checked only if the coverage notes include status, listing pages scanned, search terms tried, result pages scanned, direct job pages opened, and limitations.
10. If a source exposes native search, do not mark it complete unless the coverage notes show that native search was actually used, or a deterministic scripted discovery artifact shows that the full source was enumerated and the full term set was applied.
11. Use `rank_jobs` to score and prioritize them.
12. Create or update a digest in `./digests/` using `../../shared/digest_template.md`.
13. Add newly reported roles to `../../shared/seen_jobs.md`.
14. Rebuild the persistent ranked overview by running `../../scripts/update_ranked_overview.py --track core_crypto`.
15. After the run succeeds, update `last_checked` in `./sources.md` only for the sources actually checked with complete coverage.

## Same-day reruns

If today's digest file does not exist yet, create it normally.

If the first run of the day finds no relevant new roles, still create today's digest and say clearly that no relevant new roles were found.

If today's digest file already exists:

- read it first
- preserve the existing content
- append a new section at the end named `## Update HH:MM`
- include only roles that are newly reportable for this run
- do not rewrite or remove earlier same-day sections

If no new roles are found on a later run the same day, leave today's digest unchanged.

## Output standard

Return only new roles that are worth Jonas's attention.

If no strong new roles are found, say so clearly in the digest.

Do not fabricate missing job details. Use `unknown` when necessary.

On same-day reruns, never overwrite the existing daily digest with a fresh full rewrite.

The digest must include enough source coverage detail to show what was actually searched. Do not write a source as fully checked if you cannot show the coverage record.

If a source exposes native search and the run did not use it, or cannot show which terms were tried, mark that source as partial and say so in the digest.

If `../../scripts/discover_jobs.py` produced a deterministic discovery artifact for a source, that artifact is acceptable proof of complete coverage when it shows the source's full enumeration strategy and the applied search terms.

For scheduled runs, the artifact paths in `../../artifacts/discovery/core_crypto/` are the source of truth for discovery. Use `YYYY-MM-DD.json` first and `latest.json` second.

## Deduplication

Do not report roles already listed in `../../shared/seen_jobs.md`.

If unsure whether a role is genuinely new or just reposted, treat it as already seen.

Only append roles to `../../shared/seen_jobs.md` if they were actually written into the digest for this run.
