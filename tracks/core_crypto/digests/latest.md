# Job Digest — 2026-03-28

Track: core_crypto
Run timestamp: 2026-03-28 09:04:36 CET
Sources checked: 29
New roles found: 9
High-signal matches: 6

## Executive summary

This is a manual full-source snapshot built from a fresh all-company discovery run and ranked as if `shared/seen_jobs.md` were empty. Under that no-dedup assumption, the strongest current roles are concentrated in explicit cryptography engineering, cryptographic systems, and privacy/security research. The best current fits are QEDIT, Fortanix, IBM Vault, secunet, Anthropic, and Google. Coinbase remains inaccessible to automation, and IBM remains usable but technically `partial` because its API paging is still slightly unstable.

## Recommended actions

- Review `QEDIT`, `Fortanix`, `IBM Vault`, and `secunet` first; these are the cleanest current overlaps with applied cryptography or privacy/security engineering.
- Treat `Anthropic` and `Google` as strong but less direct fits because they lean more toward AI safety / privacy research than core cryptographic systems work.
- Keep `Coinbase` and the broader `NXP` / `IBM` candidate pools on watch, but do not promote their weaker security-only roles without stronger direct evidence.

## Strong matches

### 1. Cryptography Engineer — QEDIT
Link: https://qed-it.com/careers
Location: unknown
Remote: unknown
Team / domain: zero-knowledge / privacy-preserving cryptography / blockchain infrastructure
Posted: unknown
Source: QEDIT careers

Why it matches:
- The role is explicitly for a hands-on cryptography engineer and the page names advanced cryptographic protocol design and implementation.
- The current careers page mentions Rust, internal and external review of cryptographic primitives, and close collaboration between researchers and engineers.
- Zero-knowledge and privacy-first systems are a strong thematic match for Jonas's MPC / privacy-preserving / protocol-engineering profile.

Possible concerns:
- The role sits in blockchain infrastructure, which may be narrower than a general applied-crypto search.
- The public page does not state location or remote policy clearly.

Fit score: 9/10
Recommendation: watch

### 2. Cryptography Engineer — Fortanix
Link: https://apply.workable.com/fortanix/j/A122E95976
Location: Netherlands
Remote: unknown
Team / domain: cryptography / confidential computing / data security
Posted: unknown
Source: IACR Jobs

Why it matches:
- The title is an exact track fit: `Cryptography Engineer`.
- The current IACR jobs listing still points directly to the Fortanix role and remains one of the few clear industry cryptography titles in the full-source run.
- Earlier direct verification for this same live role showed production cryptography work around secure APIs, key-management / PKI-adjacent responsibilities, and implementation depth.

Possible concerns:
- The direct Workable page exposes very little structured text in this environment, so some detail remains thinner than ideal in this snapshot.
- Earlier verified copies indicated meaningful backend systems expectations in Rust, C/C++, and/or Go.

Fit score: 8.7/10
Recommendation: watch

### 3. Backend Engineer (Cryptography Team) - Hashicorp Vault — IBM
Link: https://careers.ibm.com/careers/JobDetail?jobId=85519
Location: Multiple Cities
Remote: Hybrid
Team / domain: HashiCorp Vault / secrets management / backend security infrastructure
Posted: unknown
Source: IBM careers API

Why it matches:
- The title is unusually explicit: this is a backend role on a `Cryptography Team` tied to `HashiCorp Vault`.
- IBM's official careers API identifies it as a `Hybrid`, `Software Engineering`, `Professional` role, which makes the evidence usable even though the website detail page is WAF-blocked.
- Vault is directly relevant to applied cryptography, secrets management, encryption, and identity / access infrastructure.

Possible concerns:
- The accessible API snippet is thinner than a normal direct posting body, so some implementation specifics are still unknown.
- `Multiple Cities` plus hybrid delivery leaves practical location fit unclear.

Fit score: 8.5/10
Recommendation: watch

### 4. Software Developer (m/w/d) Schwerpunkt Kryptographie — secunet Security Networks AG
Link: https://jobs.secunet.com/Software-Developer-mwd-Schwerpunkt-Kryptographie-de-j3332.html
Location: Berlin or Eschborn
Remote: hybrid / mobile-office friendly
Team / domain: smartcard platform / ECC-PQC migration / PKI-grade product security
Posted: 2026-01-12
Source: secunet job board

Why it matches:
- The live posting explicitly mentions `Postquantenmigration`, smartcard platform work, and `ECC/PQC Kryptographie`.
- The role sits in a Germany-based security company and is geographically practical relative to Jonas's stated preferences.
- The posting also names protocol and risk-analysis experience, which makes it more than a narrow implementation-only role.

Possible concerns:
- The stack leans strongly toward C/C++, smartcard platforms, and product-security engineering.
- It is more embedded / systems-oriented than a pure research-engineering cryptography role.

Fit score: 8.4/10
Recommendation: watch

### 5. Security Labs Engineer — Anthropic
Link: https://job-boards.greenhouse.io/anthropic/jobs/5153564008
Location: San Francisco, CA
Remote: unknown
Team / domain: AI security research / cryptographic verification / confidential computing
Posted: unknown
Source: Anthropic Greenhouse board

Why it matches:
- The live posting explicitly mentions applied cryptography, zero-knowledge proofs, attestation protocols, secure enclaves, TPMs, and confidential computing primitives.
- The role is framed as an experiment-heavy security engineering position that asks whether cryptographic guarantees can replace trust in high-assurance workflows.
- It matches Jonas's research-plus-engineering profile better than most general product-security roles.

Possible concerns:
- The role is still centered on AI infrastructure and safety experiments rather than a traditional cryptography product team.
- The location is San Francisco and the practical relocation / visa path is unclear.

Fit score: 8.2/10
Recommendation: watch

### 6. Research Scientist, Security and Privacy, Google Research — Google
Link: https://www.google.com/about/careers/applications/jobs/results/74601972883169990-research-scientist-security-and-privacy-google-research
Location: New York, NY, USA; Seattle, WA, USA
Remote: unknown
Team / domain: security and privacy research / privacy-preserving technologies / agentic systems
Posted: unknown
Source: Google Careers

Why it matches:
- The live posting requires a PhD plus publications in security and privacy or related systems areas.
- Google explicitly lists privacy-preserving technologies such as differential privacy and contextual integrity in the preferred qualifications.
- The responsibilities center on research and prototype-building for privacy-preserving technologies and security protections, which fits Jonas's research-engineering orientation.

Possible concerns:
- The role sits partly at the intersection of security/privacy and LLM / agentic systems rather than squarely in cryptographic systems.
- The locations are US-based and do not obviously solve the practical work-location constraint.

Fit score: 8/10
Recommendation: watch

## Borderline / maybe

### 7. System Engineer - Cryptographic systems — Thales
Link: https://careers.thalesgroup.com/global/en/job/R0305314/System-Engineer-Cryptographic-systems
Location: Tubize, Belgium
Remote: unknown
Team / domain: cryptographic systems / secure communications / device and system engineering
Posted: 2026-01-26
Source: Thales careers

Why it matches:
- The title is directly on-track and the posting explicitly asks for background in cybersecurity / cryptography.
- The role covers system specification and design for security-related systems and names cryptography among the core domains.
- Belgium is at least regionally practical compared with many US-only roles.

Possible concerns:
- The role reads broader than a pure cryptography-engineering job and emphasizes systems / device engineering across multiple domains.
- The page looks closer to defense / secure-communications systems work than to privacy-preserving computation or protocol research.

Fit score: 7.7/10
Recommendation: watch

### 8. Staff+ Software Engineer, Privacy — Anthropic
Link: https://job-boards.greenhouse.io/anthropic/jobs/5159146008
Location: San Francisco, CA | New York City, NY | Seattle, WA
Remote: unknown
Team / domain: privacy infrastructure / data governance / privacy-enhancing technologies
Posted: unknown
Source: Anthropic Greenhouse board

Why it matches:
- The role explicitly names privacy-enhancing technologies including homomorphic encryption and secure enclaves.
- It is one of the clearest current large-scale privacy-engineering roles in the allowed source set.
- The posting is technically substantive and aligns with the feasible privacy-engineering pivot in the profile.

Possible concerns:
- This is a very senior `Staff+` role and asks for deep production-scale privacy infrastructure experience.
- The center of gravity is platform privacy engineering rather than cryptographic protocol design.

Fit score: 7.4/10
Recommendation: watch

### 9. Security Consultant – PKI & Crypto (German) — IBM
Link: https://careers.ibm.com/careers/JobDetail?jobId=93640
Location: Multiple Cities
Remote: unknown
Team / domain: PKI / crypto consulting / client-facing security delivery
Posted: unknown
Source: IBM careers API

Why it matches:
- The title explicitly includes `PKI & Crypto` and the German language requirement is practically compatible.
- It is one of the few IBM titles in the current API set that stays directly on-track.

Possible concerns:
- The role appears consulting-oriented rather than hands-on research / engineering oriented.
- The available API evidence is too thin to show the technical depth clearly.

Fit score: 7.1/10
Recommendation: watch

## Roles filtered out

- **NXP — Software Security Architect (m/f/d)** — real posting with a cryptography requirement, but it is heavily senior, embedded `C` / assembly, SoC-stack, and automotive / IoT security architecture work, so it sits too far from Jonas's strongest fit.
- **NXP — Crypto & Security Engineers** — talent-pool / future-openings page rather than a concrete current opening.
- **PQShield — Hardware Verification Engineer** — on-track employer and PQC adjacency, but the role is mainly hardware verification rather than applied cryptography or protocol engineering.
- **Google — Software Engineer III, Agent Observability, Security and Privacy** — credible security/privacy role, but the actual content is much more observability / developer-tools oriented than cryptography or privacy-preserving systems.

## Source notes

- IACR Jobs — mode: `html`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: very noisy board with many academic and non-job links; the strongest current industry hits were `Fortanix` and a mirrored `SandboxAQ` cryptography posting.
- PQShield — mode: `html`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: current visible hits were product pages, a speculative application, a hardware verification role, and a PQC intern posting.
- Zama — mode: `html`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: only a spontaneous-application page was visible.
- Roseman Labs — mode: `html`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: no current matching roles survived filtering.
- Duality Technologies — mode: `html`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: the current hits were FHE marketing pages plus sales and student roles rather than direct crypto-engineering jobs.
- QEDIT — mode: `qedit_inline`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `inline_roles=1`; direct pages opened: `0`; note: the single visible direct role, `Cryptography Engineer`, remains one of the strongest exact fits in the source set.
- Least Authority — mode: `leastauthority_careers`; status: `complete`; listing pages: `1`; search terms: `none`; result pages: `career_page=1`; direct pages opened: `0`; note: the careers page still exposes no direct current job links.
- Trail of Bits — mode: `trailofbits_browser`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `career_page=1`; direct pages opened: `0`; note: current openings are application security, blockchain, or AI-security roles, but none beat the bar above.
- Partisia Blockchain — mode: `partisia_site`; status: `complete`; listing pages: `2`; search terms: `none`; result pages: `homepage_scan=1`; direct pages opened: `0`; note: the official sites exposed no direct current job listings.
- Anthropic — mode: `greenhouse_api`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: large security/privacy pool; `Security Labs Engineer` and `Staff+ Software Engineer, Privacy` were the clearest fits.
- Automattic — mode: `automattic_browser`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `jobs_page=1`; direct pages opened: `0`; note: no matching roles survived filtering.
- Bosch — mode: `browser`; status: `complete`; listing pages: `60`; search terms: `33 track-wide plus source-specific terms`; result pages: `multi-term native search across 60 listing pages`; direct pages opened: `0`; note: current hits were generic product-security roles and internships rather than strong crypto-track matches.
- Coinbase — mode: `coinbase_browser`; status: `partial`; listing pages: `1`; search terms: `31 track-wide plus source-specific terms`; result pages: `challenge_page=1`; direct pages opened: `0`; note: Cloudflare still blocks automated access, so no reliable current Coinbase digest entry can be produced.
- Cybernetica — mode: `cybernetica_teamdash`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `filtered_links=1`; direct pages opened: `0`; note: visible roles leaned toward general security R&D and digital-identity engineering, but none were strong enough to surface here.
- Google — mode: `browser`; status: `complete`; listing pages: `7`; search terms: `cryptography`; result pages: `cryptography=7p/136`; direct pages opened: `0`; note: four privacy/security roles survived; the research-scientist posting was the strongest fit.
- Ethereum Foundation — mode: `lever_json`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: no current matching role survived filtering.
- IBM — mode: `ibm_api`; status: `partial`; listing pages: `2`; search terms: `28 track-wide terms`; result pages: `full_index=2p/192of197`; direct pages opened: `0`; note: the API surfaced strong Vault- and PKI-related titles, but pagination still lost a few unique records, so coverage remains technically partial.
- Infineon — mode: `infineon_api`; status: `complete`; listing pages: `197`; search terms: `28 track-wide terms`; result pages: `multi-term PCSx search across 197 listing pages`; direct pages opened: `0`; note: current hits are mostly OT, manufacturing, facility, or broad cybersecurity roles.
- Mistral AI — mode: `lever_json`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: the visible roles are cybersecurity operations and DevSecOps roles rather than core crypto or privacy engineering.
- NXP — mode: `workday_api`; status: `complete`; listing pages: `56`; search terms: `28 track-wide terms`; result pages: `cryptography=2p/27, cryptographer=2p/27, applied cryptography=2p/27, privacy=2p/34, privacy engineering=2p/30, privacy-preserving=1p/8, privacy-enhancing technologies=1p/8, PETs=0p/0, security=8p/160, security research=5p/86, protocol=3p/48, protocol security=2p/21, authentication=1p/7, digital identity=3p/41, key management=8p/156, post-quantum=0p/0, post-quantum cryptography=0p/0, PQC=0p/0, MPC=0p/0, multi-party computation=2p/29, zero-knowledge=1p/13, ZK=0p/0, FHE=0p/0, homomorphic encryption=0p/0, smart card=2p/27, embedded security=4p/78, secure hardware=4p/70, HSM=1p/1`; direct pages opened: `0`; note: coverage is now complete, but the strongest roles remain either embedded / SoC-heavy or talent-pool style.
- Palantir — mode: `lever_json`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: current hits are mostly application or product-security roles rather than core crypto roles.
- SandboxAQ — mode: `ashby_api`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: the direct source still did not surface a reportable role in this environment, though an IACR mirror points at a current `Staff Software Engineer, Cryptography R&D` posting.
- secunet — mode: `secunet_jobboard`; status: `complete`; listing pages: `1`; search terms: `32 track-wide plus source-specific terms`; result pages: `filtered_links=1`; direct pages opened: `0`; note: several Germany-based security roles remain live; the dedicated `Schwerpunkt Kryptographie` posting is the clearest fit.
- NEC Laboratories Europe — mode: `neclab_jobs`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `filtered_links=1`; direct pages opened: `0`; note: no current matching roles survived filtering.
- Quantinuum — mode: `lever_json`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: the only surviving role is a physical-security specialist position in Tokyo.
- Qrypt — mode: `lever_json`; status: `complete`; listing pages: `1`; search terms: `28 track-wide terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: no current matching role survived filtering.
- QuSecure — mode: `qusecure_careers`; status: `complete`; listing pages: `1`; search terms: `none`; result pages: `career_page=1`; direct pages opened: `0`; note: no direct job listings were visible on the current careers page.
- Rambus — mode: `icims_html`; status: `complete`; listing pages: `1`; search terms: `31 track-wide plus source-specific terms`; result pages: `local_filter=1`; direct pages opened: `0`; note: current hits were marketing / platform pages rather than direct current openings.
- Thales — mode: `thales_html`; status: `complete`; listing pages: `12`; search terms: `cryptography, multi-party computation, homomorphic encryption`; result pages: `cryptography=6p/60of57, multi-party computation=1p/1of1, homomorphic encryption=5p/50of47`; direct pages opened: `0`; note: the override terms surfaced one strong systems role plus several V&V and embedded positions.

## Seen jobs to append

If this snapshot were being treated as a true first run with no dedup history, these are the roles I would append:

- QEDIT | Cryptography Engineer | unknown | https://qed-it.com/careers
- Fortanix | Cryptography Engineer | Netherlands | https://apply.workable.com/fortanix/j/A122E95976
- IBM | Backend Engineer (Cryptography Team) - Hashicorp Vault | Multiple Cities | https://careers.ibm.com/careers/JobDetail?jobId=85519
- secunet Security Networks AG | Software Developer (m/w/d) Schwerpunkt Kryptographie | Berlin or Eschborn | https://jobs.secunet.com/Software-Developer-mwd-Schwerpunkt-Kryptographie-de-j3332.html
- Anthropic | Security Labs Engineer | San Francisco, CA | https://job-boards.greenhouse.io/anthropic/jobs/5153564008
- Google | Research Scientist, Security and Privacy, Google Research | New York, NY, USA; Seattle, WA, USA | https://www.google.com/about/careers/applications/jobs/results/74601972883169990-research-scientist-security-and-privacy-google-research
- Thales | System Engineer - Cryptographic systems | Tubize, Belgium | https://careers.thalesgroup.com/global/en/job/R0305314/System-Engineer-Cryptographic-systems
- Anthropic | Staff+ Software Engineer, Privacy | San Francisco, CA; New York City, NY; Seattle, WA | https://job-boards.greenhouse.io/anthropic/jobs/5159146008
- IBM | Security Consultant – PKI & Crypto (German) | Multiple Cities | https://careers.ibm.com/careers/JobDetail?jobId=93640

## Notes for next run

- This file is a manual no-dedup snapshot, not a scheduled daily digest. It should not be used to advance `last_checked` or mutate `shared/seen_jobs.md`.
- If this were converted into a live daily digest, I would still keep `Coinbase` partial until a real browser path exists and `IBM` partial until paging stops dropping records.
- If desired, the next refinement step would be to improve first-pass filtering for `IACR Jobs` and to preserve richer structured evidence for mirrored external roles like `Fortanix` and `SandboxAQ`.
