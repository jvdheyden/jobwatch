# Core crypto sources

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
| PQShield | https://pqshield.com/careers/ | html | 2026-04-01 |
| Zama | https://jobs.zama.org | html | 2026-04-01 |
| 0xPARC / PCD Team | https://pcd.team/jd | pcd_team | |
| Roseman Labs | https://rosemanlabs.com/en/working-at-roseman-labs | html | 2026-04-01 |
| Duality Technologies | https://dualitytech.com/careers/ | html | 2026-04-01 |
| QEDIT | https://qed-it.com/careers | qedit_inline | 2026-04-01 |
| Least Authority | https://leastauthority.com/careers/ | leastauthority_careers | 2026-04-01 |
| Trail of Bits | https://trailofbits.com/careers/ | trailofbits_browser | 2026-04-01 |
| Partisia Blockchain | https://partisiablockchain.com/ | partisia_site | 2026-04-01 |

## Check every 3 runs

| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Anthropic | https://job-boards.greenhouse.io/anthropic/ | greenhouse_api | 2026-04-01 |
| ASML | https://www.asml.com/en/careers/find-your-job | asml_browser | |
| Automattic | https://automattic.com/jobs/ | automattic_browser | 2026-04-01 |
| Bosch | https://jobs.bosch.de/ | browser | 2026-04-01 |
| Coinbase | https://www.coinbase.com/careers | coinbase_browser | 2026-03-25 |
| Cybernetica | https://cyber.ee/careers/open-positions | cybernetica_teamdash | 2026-04-01 |
| Google | https://www.google.com/about/careers/applications/jobs/results | browser | 2026-04-01 |
| Ethereum Foundation | https://jobs.lever.co/ethereumfoundation | lever_json | 2026-04-01 |
| IBM | https://www.ibm.com/careers/search | ibm_api | 2026-03-28 |
| Infineon | https://jobs.infineon.com/careers | infineon_api | 2026-04-01 |
| Mistral AI | https://jobs.lever.co/mistral | lever_json | 2026-04-01 |
| Meta | https://www.metacareers.com/jobs | browser | |
| NXP | https://nxp.wd3.myworkdayjobs.com/careers | workday_api | 2026-04-01 |
| Palantir | https://jobs.lever.co/palantir | lever_json | 2026-04-01 |
| SandboxAQ | https://jobs.ashbyhq.com/sandboxaq | ashby_api | 2026-04-01 |
| secunet | https://jobs.secunet.com/ | secunet_jobboard | 2026-04-01 |
| NEC Laboratories Europe | https://jobs.neclab.eu/ | neclab_jobs | 2026-04-01 |
| Quantinuum | https://jobs.eu.lever.co/quantinuum | lever_json | 2026-04-01 |
| Qrypt | https://jobs.lever.co/qrypt | lever_json | 2026-04-01 |
| QuSecure | https://www.qusecure.com/careers/ | qusecure_careers | 2026-04-01 |
| Rambus | https://www.rambus.com/careers/ | icims_html | 2026-04-01 |
| Thales | https://careers.thalesgroup.com/global/en/search-results | thales_html | 2026-04-01 |
| YC Startups | https://www.ycombinator.com/jobs/role/software-engineer | yc_jobs_board | 2026-04-01 |
| Hackernews Jobs | https://news.ycombinator.com/jobs | hackernews_jobs | 2026-04-01 |

## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms

- cryptography
- cryptographer
- applied cryptography
- privacy
- privacy engineering
- privacy-preserving
- privacy-enhancing technologies
- PETs
- security
- security research
- protocol
- protocol security
- authentication
- digital identity
- key management
- post-quantum
- post-quantum cryptography
- PQC
- MPC
- multi-party computation
- zero-knowledge
- ZK
- FHE
- homomorphic encryption
- smart card
- embedded security
- secure hardware
- HSM

### Source-specific search terms

Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.

Add `[override]` after the source name to replace the track-wide terms for that source.

- Anthropic — privacy, privacy engineering, privacy-preserving, security
- Bosch — Kryptographie, IT-Sicherheit, Embedded Security, Identität, Authentifizierung, Smartcard
- Google — cryptography
- Coinbase — blockchain, blockchain security, crypto-security, MPC, zero-knowledge, security
- secunet — Kryptographie, Smartcard, Security, Rust, Identität
- Rambus — cryptography, quantum safe, root of trust, security IP
- Thales [override] — cryptography, multi-party computation, homomorphic encryption

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ../../shared/seen_jobs.md
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
