# Public service sources

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
| Bund | https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html?view=processForm&nn=4641514&cl2Categories_Laufbahn=laufbahn-hoehererdienst | service_bund_search | 2026-04-02 |
| Verfassungsschutz | https://www.verfassungsschutz.de/SiteGlobals/Forms/Suche/Stellenangebotesuche_Formular.html?nn=719030&location=Grunds%C3%A4tzlich+Berlin+und+K%C3%B6ln&section.GROUP=1 | verfassungsschutz_rss | 2026-04-02 |
| BND | https://www.bnd.bund.de/SiteGlobals/Forms/Suche/erweiterte_Karrieresuche_Formular.html?nn=415896&cl2Categories_Abschluss=master#sprg415980 | bnd_career_search | 2026-04-02 |
| Bundeswehr | https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html#joblist/none/TwoColumnsMidExpanded | bundeswehr_jobsuche | |
| Rheinmetall | https://www.rheinmetall.com/de/karriere/aktuelle-stellenangebote?9dc11c304b4c06c2f71c48cc6574e7e5term=&9dc11c304b4c06c2f71c48cc6574e7e5filter=%257B%2522occupationalArea%2522%253A%255B%2522IT%2520und%2520Software%2522%255D%257D | rheinmetall_html | 2026-04-02 |
| Helsing | https://helsing.ai/jobs | helsing_browser | 2026-04-02 |
| Quantum Systems | https://career.quantum-systems.com/ | recruitee_inline | 2026-04-02 |
| Auswärtiges Amt | https://www.auswaertiges-amt.de/de/karriere/stellenanzeigen | auswaertiges_amt_json | 2026-04-02 |
| EnBW | https://careers.enbw.com/en_US/careers | enbw_phenom | 2026-04-02 |
| BSI | https://www.bsi.bund.de/DE/Karriere/Stellenangebote/stellenangebot_node.html | service_bund_links | 2026-04-02 |

## Check every 3 runs

| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |

## Check every month

| source | url | discovery_mode | last_checked |
| --- | --- | --- | --- |

## Search terms

Use these terms on searchable sources unless a source-specific search-term override says otherwise.

### Track-wide terms

- privacy
- Datenschutz
- cryptography
- Kryptographie
- cryptographer
- Kryptograph
- cryptography engineer
- Kryptographieingenieur
- advisor
- advisory
- Beratung
- referent
- engineering
- Ingenieur
- cybersecurity
- Cybersecurity
- IT-Sicherheit
- Cyberabwehr
- cyber defense
- Spionageabwehr
- counterintelligence

### Source-specific search terms

Use these in addition to the track-wide terms when the source has native search and these terms are a better fit for that source's vocabulary.

Add `[override]` after the source name to replace the track-wide terms for that source.

- Bund [override] — Kryptographie, IT-Sicherheit, Cyberabwehr, Spionageabwehr, Referent Kryptographie, Referent IT-Sicherheit, Referent Cyberabwehr
- Bund Karriere [override] — Kryptographie, IT-Sicherheit, Cyberabwehr, Spionageabwehr, Referent Kryptographie, Referent IT-Sicherheit, Referent Cyberabwehr
- Verfassungsschutz [override] — Kryptographie, IT-Sicherheit, Cyberabwehr, Spionageabwehr, Referent
- BND [override] — Kryptographie, IT-Sicherheit, Cyberabwehr, Spionageabwehr, Referent, IT und Informatik, Technik und Ingenieurwissenschaft, Requirements Engineering, IT-Systemadministrator
- Bundeswehr [override] — Kryptographie, IT-Sicherheit, Cyberabwehr, Referent, Cyber/IT, Informationstechnik
- Rheinmetall [override] — cryptography, security, cyber defense, IT-Sicherheit
- Helsing [override] — security engineer, cybersecurity, IT-Sicherheit, cyber defense, cryptography
- Quantum Systems [override] — cryptography, cybersecurity, IT-Sicherheit, cyber defense
- Auswärtiges Amt [override] — IT-Sicherheit, Cybersecurity, Cyberabwehr, Digitalisierung
- EnBW [override] — IT-Sicherheit, cybersecurity, information security, cryptography
- BSI [override] — Kryptographie, IT-Sicherheit, Cybersecurity, Referent Kryptographie, Referent IT-Sicherheit, privacy

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ../../shared/seen_jobs.md
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
