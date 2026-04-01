# Postdoc crypto sources

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
| IACR Jobs | https://www.iacr.org/jobs/ | iacr_jobs | 2026-04-01 |

## Check every 3 runs

| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Google | https://www.google.com/about/careers/applications/jobs/results | browser | 2026-04-01 |
| IBM Research | https://www.ibm.com/careers/search | ibm_api | 2026-04-01 |
| Meta | https://www.metacareers.com/jobs | browser | 2026-04-01 |

## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms

- multi-party computation
- MPC
- garbled circuits
- isogenies
- isogeny-based cryptography
- real-world cryptography
- real-world protocols
- privacy-enhancing applications
- privacy-preserving applications

### Source-specific search terms

Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.

Add `[override]` after the source name to replace the track-wide terms for that source.

- Google — research scientist, postdoctoral, postdoc
- IBM Research — research scientist, postdoctoral, postdoc, cryptography
- Meta — research scientist, cryptography, privacy-preserving, privacy-enhancing

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ../../shared/seen_jobs.md
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
