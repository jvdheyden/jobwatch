# Alignment Tech sources

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

## Check every 3 runs

| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Coefficient Giving | https://jobs.ashbyhq.com/coefficientgiving | ashby_api | 2026-04-09 |
| YC Startups | https://www.ycombinator.com/jobs/role/software-engineer | yc_jobs_board | 2026-04-09 |
| Deutsche Wildtier Stiftung | https://www.deutschewildtierstiftung.de/ueber-uns/stellenangebote | html | 2026-04-09 |
| Bergwaldprojekt | https://www.bergwaldprojekt.de/ueber-uns/stellen | html | 2026-04-09 |
| Waking Up | https://apply.workable.com/waking-up-1/ | workable_api | 2026-04-09 |
| Spirit Tech Collective Jobs | https://jobs.spirit-tech-collective.com/jobs | getro_api | 2026-04-09 |
| Albert Schweitzer Stiftung | https://albert-schweitzer-stiftung.jobs.personio.de/ | personio_page | 2026-04-09 |
| E.O. Wilson Biodiversity Foundation | https://eowilsonfoundation.org/about-us/careers/ | html | 2026-04-07 |

## Check every month

| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Hacker News Who Is Hiring | https://news.ycombinator.com/user?id=whoishiring | hackernews_whoishiring_api | 2026-04-03 |

## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms

- software engineer
- software developer
- programmer
- full stack
- security engineer
- IT security
- cybersecurity
- data analyst
- data analysis
- data visualization
- analyst
- cryptography
- volunteer
- internship

### Source-specific search terms

Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.

Add `[override]` after the source name to replace the track-wide terms for that source.

- Mindvalley [override] — cybersecurity, security engineer, full stack engineer, software engineer, data analyst
- Coefficient Giving [override] — analyst, data, operations, engineering, security
- One Acre Fund [override] — devops, software engineer, data analyst, analytics, MEL
- Innovate Animal Ag [override] — software engineer, data scientist, AI, technical, research
- YC Startups [override] — software engineer, security engineer, data analyst, full stack, data engineer
- Deutsche Wildtier Stiftung [override] — Daten, Analyst, Software, IT, Projekt, Praktikum
- Bergwaldprojekt [override] — IT, Daten, Software, Praktikum, FÖJ, Freiwillig
- Waking Up [override] — software engineer, data analyst, security, engineering
- Spirit Tech Collective Jobs [override] — software engineer, security engineer, data analyst, programmer
- Albert Schweitzer Stiftung [override] — Daten, Analyst, Software, IT, Praktikum

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ../../shared/seen_jobs.md
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
- For `YC Startups`, `Spirit Tech Collective Jobs`, and `Hacker News Who Is Hiring`, only surface roles with explicit evidence for the track sectors or a clearly known alignment-tech employer.
