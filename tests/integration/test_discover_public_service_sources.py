from __future__ import annotations

import json
from html import escape

import discover_jobs


class FakeLink:
    def __init__(self, href: str, text: str) -> None:
        self._href = href
        self._text = text

    def get_attribute(self, name: str) -> str:
        assert name == "href"
        return self._href

    def inner_text(self) -> str:
        return self._text


class FakeLocator:
    def __init__(self, items: list[FakeLink]) -> None:
        self._items = items

    def count(self) -> int:
        return len(self._items)

    def nth(self, index: int) -> FakeLink:
        return self._items[index]


class FakePage:
    def __init__(self, links: list[FakeLink]) -> None:
        self._links = links

    def locator(self, selector: str) -> FakeLocator:
        assert selector == 'a[href^="/jobs/"]'
        return FakeLocator(self._links)


def test_discover_recruitee_inline_extracts_published_quantum_systems_roles(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Quantum Systems",
        url="https://career.quantum-systems.com/",
        discovery_mode="recruitee_inline",
        last_checked=None,
        cadence_group="every_run",
    )
    payload = {
        "appConfig": {
            "departments": [{"id": 7, "translations": {"en": "Security Engineering"}}],
            "offers": [
                {
                    "status": "published",
                    "slug": "cryptography-engineer",
                    "departmentId": 7,
                    "city": "Munich",
                    "primaryLangCode": "en",
                    "employmentType": "FULL_TIME",
                    "experience": "MID_LEVEL",
                    "education": "PHD",
                    "tags": ["privacy", "protocols"],
                    "translations": {
                        "en": {
                            "title": "Cryptography Engineer",
                            "country": "Germany",
                            "descriptionHtml": "<p>Build privacy-preserving systems.</p>",
                            "requirementsHtml": "<p>Applied cryptography experience.</p>",
                        }
                    },
                },
                {"status": "draft", "slug": "ignored-role"},
            ],
        }
    }
    html = f'<div data-component="PublicApp" data-props="{escape(json.dumps(payload), quote=True)}"></div>'
    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_recruitee_inline(
        source,
        ["cryptography", "privacy-preserving"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Cryptography Engineer"
    assert candidate.location == "Munich, Germany"
    assert candidate.url == "https://career.quantum-systems.com/o/cryptography-engineer"
    assert candidate.matched_terms == ["cryptography", "privacy-preserving"]


def test_discover_verfassungsschutz_rss_filters_to_relevant_roles(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Verfassungsschutz",
        url="https://www.verfassungsschutz.de/jobs",
        discovery_mode="verfassungsschutz_rss",
        last_checked=None,
        cadence_group="every_run",
    )
    xml_text = """
    <rss><channel>
      <item>
        <title>Referatsleitungen (m/w/d) im Bereich Cyberabwehr</title>
        <link>https://www.verfassungsschutz.de/SharedDocs/stellenangebote/refleitung-cyberabwehr.html</link>
        <description>Fachbereich IT-Sicherheit und Cyberabwehr</description>
        <pubDate>Tue, 01 Apr 2026 08:00:00 GMT</pubDate>
      </item>
      <item>
        <title>Mitarbeiter (m/w/d) Verwaltung</title>
        <link>https://www.verfassungsschutz.de/SharedDocs/stellenangebote/verwaltung.html</link>
        <description>Allgemeine Verwaltung</description>
        <pubDate>Tue, 01 Apr 2026 08:00:00 GMT</pubDate>
      </item>
    </channel></rss>
    """
    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: xml_text)

    coverage = discover_jobs.discover_verfassungsschutz_rss(
        source,
        ["Cyberabwehr", "IT-Sicherheit", "Referent"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Referatsleitungen (m/w/d) im Bereich Cyberabwehr"
    assert candidate.url.endswith("/refleitung-cyberabwehr.html")


def test_discover_auswaertiges_amt_json_extracts_structured_listings(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Auswärtiges Amt",
        url="https://www.auswaertiges-amt.de/de/karriere/stellenanzeigen",
        discovery_mode="auswaertiges_amt_json",
        last_checked=None,
        cadence_group="every_run",
    )
    html = """
    <form action="/ajax/json-filterlist/de/karriere/stellenanzeigen/2544254-2544254"></form>
    """
    seen_endpoints: list[str] = []

    def fake_fetch_json(url: str, timeout_seconds: int):
        seen_endpoints.append(url)
        return {
            "items": [
                {
                    "headline": "Referent*in IT-Sicherheit im Auswärtigen Dienst",
                    "link": "/de/karriere/stellenanzeigen/referent-it-sicherheit/999999",
                    "text": "Beratung zu Cybersecurity und Digitalisierung.",
                    "department": ["Berlin"],
                    "date": "01.04.2026",
                    "closingDate": "30.04.2026",
                },
                {
                    "headline": "Sachbearbeitung Haushalt",
                    "link": "/de/karriere/stellenanzeigen/haushalt/111111",
                    "text": "Haushaltsangelegenheiten",
                    "department": ["Berlin"],
                },
            ]
        }

    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: html)
    monkeypatch.setattr(discover_jobs, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_auswaertiges_amt_json(
        source,
        ["IT-Sicherheit", "Cybersecurity", "Referent"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    assert seen_endpoints == [
        "https://www.auswaertiges-amt.de/ajax/json-filterlist/de/karriere/stellenanzeigen/2544254-2544254"
    ]
    candidate = coverage.candidates[0]
    assert candidate.title == "Referent*in IT-Sicherheit im Auswärtigen Dienst"
    assert candidate.location == "Berlin"


def test_discover_enbw_phenom_paginates_embedded_search_payload(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="EnBW",
        url="https://careers.enbw.com/en_US/careers",
        discovery_mode="enbw_phenom",
        last_checked=None,
        cadence_group="every_run",
    )
    page_one_payload = {
        "eagerLoadRefineSearch": {
            "hits": 1,
            "totalHits": 2,
            "data": {
                "jobs": [
                    {
                        "jobId": "23176",
                        "title": "Information Security Engineer",
                        "company": "EnBW",
                        "cityStateCountry": "Karlsruhe, Germany",
                        "category": "Security",
                        "descriptionTeaser": "Drive IT-Sicherheit for critical infrastructure.",
                        "jobSeqNo": "EBQEBQGLOBAL23176EXTERNALDEDE",
                    }
                ]
            },
        }
    }
    page_two_payload = {
        "eagerLoadRefineSearch": {
            "hits": 1,
            "totalHits": 2,
            "data": {
                "jobs": [
                    {
                        "jobId": "23177",
                        "title": "Privacy Engineer",
                        "company": "EnBW",
                        "cityStateCountry": "Stuttgart, Germany",
                        "category": "Security",
                        "descriptionTeaser": "Build privacy engineering controls.",
                        "jobSeqNo": "EBQEBQGLOBAL23177EXTERNALDEDE",
                    }
                ]
            },
        }
    }
    seen_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        seen_urls.append(url)
        payload = page_two_payload if "from=1" in url else page_one_payload
        return f"<script>phApp.ddo = {json.dumps(payload)};</script>"

    monkeypatch.setattr(discover_jobs, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_enbw_phenom(
        source,
        ["security", "privacy"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 4
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 2
    assert any("from=1" in url for url in seen_urls)
    urls = {candidate.url for candidate in coverage.candidates}
    assert "https://careers.enbw.com/de/de/job/23176/information-security-engineer" in urls
    assert "https://careers.enbw.com/de/de/job/23177/privacy-engineer" in urls


def test_discover_bundeswehr_jobsuche_uses_profile_catalog_fallback(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Bundeswehr",
        url="https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html#joblist/none/TwoColumnsMidExpanded",
        discovery_mode="bundeswehr_jobsuche",
        last_checked=None,
        cadence_group="every_run",
    )
    html = """
    <html><body>
      <a class="jobtitle" href="/soldatin-soldat-in-der-informationstechnik-417">Soldatin / Soldat in der Informationstechnik</a>
      <a class="jobtitle" href="/koch-123">Köchin / Koch</a>
    </body></html>
    """
    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_bundeswehr_jobsuche(
        source,
        ["Informationstechnik", "Cyberabwehr"],
        timeout_seconds=5,
    )

    assert coverage.status == "partial"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Soldatin / Soldat in der Informationstechnik"
    assert candidate.url == "https://www.bundeswehrkarriere.de/soldatin-soldat-in-der-informationstechnik-417"


def test_extract_helsing_jobs_filters_visible_cards():
    page = FakePage(
        [
            FakeLink(
                "/jobs/4334849101",
                "Security Engineer\nApplied AI\nFull Time\nBerlin, Germany",
            ),
            FakeLink(
                "/jobs/9999999999",
                "Office Manager\nOperations\nFull Time\nBerlin, Germany",
            ),
        ]
    )
    source = discover_jobs.SourceConfig(
        source="Helsing",
        url="https://helsing.ai/jobs",
        discovery_mode="helsing_browser",
        last_checked=None,
        cadence_group="every_run",
    )

    result = discover_jobs.extract_helsing_jobs(
        page,
        source,
        term="catalog",
        terms=["security", "privacy", "cyber"],
        page_num=1,
    )

    assert result.visible_results == 2
    assert len(result.raw_ids) == 2
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.title == "Security Engineer"
    assert candidate.location == "Berlin, Germany"
    assert candidate.url == "https://helsing.ai/jobs/4334849101"
    assert candidate.matched_terms == ["security"]


def test_discover_bnd_career_search_extracts_native_result_cards(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="BND",
        url="https://www.bnd.bund.de/SiteGlobals/Forms/Suche/erweiterte_Karrieresuche_Formular.html?nn=415896#sprg415980",
        discovery_mode="bnd_career_search",
        last_checked=None,
        cadence_group="every_run",
    )
    html = """
    <html><body>
      <a href="SharedDocs/Stellenangebote/DE/Stellenangebote/AS-2026-038-ma-it-anforderungsmanagement-pullach.html?nn=415896" class="c-career-item__link">
        <strong class="c-career-item__title">Mitarbeiter / Mitarbeiterin (w/m/d) für IT-Anforderungsmanagement und Requirements Engineering</strong>
        <span class="c-career-item__bubbles">
          <span class="c-bubble">Pullach</span>
          <span class="c-bubble">IT und Informatik</span>
          <span class="c-bubble">Technik und Ingenieurwissenschaft</span>
          <span class="c-bubble">Bachelor/FH-Diplom</span>
        </span>
      </a>
      <a href="SharedDocs/Stellenangebote/DE/Stellenangebote/AS-2026-020-sicherungsangestellte-rheinhausen.html?nn=415896" class="c-career-item__link">
        <strong class="c-career-item__title">Sicherungsangestellte bzw. Fachkräfte (w/m/d) für Schutz und Sicherheit</strong>
        <span class="c-career-item__bubbles">
          <span class="c-bubble">Rheinhausen</span>
          <span class="c-bubble">Berufsausbildung</span>
        </span>
      </a>
    </body></html>
    """
    seen_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        seen_urls.append(url)
        return html

    monkeypatch.setattr(discover_jobs, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_bnd_career_search(
        source,
        ["IT-Sicherheit", "Referent", "engineering"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 3
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    assert all("templateQueryString=" in url for url in seen_urls)
    candidate = coverage.candidates[0]
    assert candidate.title == "Mitarbeiter / Mitarbeiterin (w/m/d) für IT-Anforderungsmanagement und Requirements Engineering"
    assert candidate.location == "Pullach"
    assert candidate.url == "https://www.bnd.bund.de/SharedDocs/Stellenangebote/DE/Stellenangebote/AS-2026-038-ma-it-anforderungsmanagement-pullach.html?nn=415896"
    assert candidate.matched_terms == ["engineering"]
