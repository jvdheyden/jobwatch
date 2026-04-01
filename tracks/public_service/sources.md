# Public service sources

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
| Bund | https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html?view=processForm&nn=4641514&cl2Categories_Laufbahn=laufbahn-hoehererdienst | service_bund_search | |
| Bund Karriere | https://karriere.bund.de/ | html | |
| Verfassungsschutz | https://www.verfassungsschutz.de/SiteGlobals/Forms/Suche/Stellenangebotesuche_Formular.html?nn=719030&location=Grunds%C3%A4tzlich+Berlin+und+K%C3%B6ln&section.GROUP=1 | html | |
| BND | https://www.bnd.bund.de/SiteGlobals/Forms/Suche/erweiterte_Karrieresuche_Formular.html?nn=415896#sprg415980 | html | |
| Bundeswehr | https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html#joblist/none/TwoColumnsMidExpanded | html | |
| Rheinmetall | https://www.rheinmetall.com/de/karriere/aktuelle-stellenangebote | html | |
| Helsing | https://helsing.ai/jobs | html | |
| Quantum Systems | https://career.quantum-systems.com/ | html | |
| Auswärtiges Amt | https://www.auswaertiges-amt.de/de/karriere/stellenanzeigen | html | |
| EnBW | https://careers.enbw.com/en_US/careers | html | |
| BSI | https://www.bsi.bund.de/DE/Karriere/Stellenangebote/stellenangebot_node.html | service_bund_links | |

## Check every 3 runs

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
- BND [override] — Kryptographie, IT-Sicherheit, Cyberabwehr, Spionageabwehr, Referent
- Bundeswehr [override] — Kryptographie, IT-Sicherheit, Cyberabwehr, Referent
- Rheinmetall — cryptography, security, cyber defense, IT-Sicherheit
- Helsing — cryptography, security, privacy, cyber defense
- Quantum Systems — cryptography, security, cyber defense, IT-Sicherheit
- Auswärtiges Amt [override] — IT-Sicherheit, Cybersecurity, Referent, Digitalisierung
- EnBW — security, privacy, cryptography, IT-Sicherheit
- BSI [override] — Kryptographie, IT-Sicherheit, Cybersecurity, Referent Kryptographie, Referent IT-Sicherheit, privacy

## Output discipline

- If a source has no relevant role, omit it from the digest.
- Never report a role already listed in ../../shared/seen_jobs.md
- Prefer 3-8 strong matches over a long noisy list.
- Include direct job links in the digest, not just the company careers page.
