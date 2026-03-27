# Core crypto sources

Only check the sources below for this track.

Goal: find roles that are genuinely strong matches for a PhD in applied cryptography, post-quantum cryptography, MPC, privacy-preserving computation, protocol engineering, or security research.

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
| IACR Jobs | https://www.iacr.org/jobs/ | html | 2026-03-27 |
| PQShield | https://pqshield.com/careers/ | html | 2026-03-27 |
| Zama | https://jobs.zama.org | html | 2026-03-27 |
| Roseman Labs | https://rosemanlabs.com/en/working-at-roseman-labs | html | 2026-03-27 |
| Duality Technologies | https://dualitytech.com/careers/ | html | 2026-03-27 |
| QEDIT | https://qed-it.com/careers | html | 2026-03-27 |
| Least Authority | https://leastauthority.com/careers/ | html | 2026-03-27 |
| Trail of Bits | https://trailofbits.com/careers/ | html | 2026-03-27 |
| Partisia Blockchain | https://partisiablockchain.com/career/ | html | 2026-03-26 |

## Check every 3 runs

| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |
| Anthropic | https://job-boards.greenhouse.io/anthropic/ | greenhouse_api | 2026-03-25 |
| Automattic | https://automattic.com/work-with-us/ | html | 2026-03-25 |
| Bosch | https://jobs.bosch.de/ | browser | 2026-03-25 |
| Coinbase | https://www.coinbase.com/careers | html | 2026-03-25 |
| Cybernetica | https://cyber.ee/careers/open-positions | html | 2026-03-25 |
| Google | https://www.google.com/about/careers/applications/jobs/results | browser | 2026-03-25 |
| Ethereum Foundation | https://jobs.lever.co/ethereumfoundation | lever_json | 2026-03-26 |
| IBM | https://www.ibm.com/careers/search | ibm_api | 2026-03-25 |
| Infineon | https://jobs.infineon.com/careers | infineon_api | 2026-03-25 |
| Mistral AI | https://jobs.lever.co/mistral | lever_json | 2026-03-25 |
| NXP | https://nxp.wd3.myworkdayjobs.com/careers | workday_api | 2026-03-25 |
| Palantir | https://jobs.lever.co/palantir | lever_json | 2026-03-25 |
| SandboxAQ | https://jobs.ashbyhq.com/sandboxaq | ashby_api | 2026-03-25 |
| secunet | https://jobs.secunet.com/ | html | 2026-03-25 |
| NEC Laboratories Europe | https://jobs.neclab.eu/ | html | 2026-03-25 |
| Quantinuum | https://jobs.eu.lever.co/quantinuum | lever_json | 2026-03-25 |
| Qrypt | https://jobs.lever.co/qrypt | lever_json | 2026-03-25 |
| QuSecure | https://www.qusecure.com/careers/ | html | 2026-03-25 |
| Rambus | https://www.rambus.com/careers/ | icims_html | 2026-03-25 |
| Thales | https://careers.thalesgroup.com/global/en/search-results | thales_browser | 2026-03-25 |

## Keep only roles matching at least one of these

- cryptography
- applied cryptography
- cryptography engineering
- protocol security
- security research
- post-quantum cryptography
- PQC
- multi-party computation
- MPC
- zero-knowledge
- ZK
- homomorphic encryption
- FHE
- privacy-enhancing technologies
- PETs
- privacy
- secure hardware
- HSM
- smart card
- embedded security
- digital identity
- authentication
- key management
- wallet security
- formal security

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

## Source-specific search terms

Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.

- Anthropic — privacy, privacy engineering, privacy-preserving, security
- Bosch — Kryptographie, IT-Sicherheit, Embedded Security, Identität, Authentifizierung, Smartcard
- Google — privacy, cryptography, security, protocol, authentication
- Coinbase — blockchain, blockchain security, crypto-security, MPC, zero-knowledge, security
- secunet — Kryptographie, Smartcard, Security, Rust, Identität
- Rambus — cryptography, quantum safe, root of trust, security IP
- Thales — cryptography, digital identity, smart card, key management

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ../../shared/seen_jobs.md
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
