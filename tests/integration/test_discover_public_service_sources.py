from __future__ import annotations

import json
import re
from html import escape
from urllib.parse import parse_qs, urlparse

import discover_jobs
from discover import http as discover_http
from discover.sources import bundeswehr as bundeswehr_provider


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
    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

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
    detail_pages = {
        "https://www.verfassungsschutz.de/SharedDocs/stellenangebote/refleitung-cyberabwehr.html": """
        <html><head>
          <meta name="description" content="Wir suchen Referatsleitungen (m/w/d) mit Schwerpunkt Cyberabwehr in Berlin und Köln"/>
        </head><body>
          <main>
            <strong class="label">Bewerbungsfrist</strong><span class="value">17. April 2026</span>
            <strong class="label">Laufbahn</strong><span class="value">Höherer Dienst</span>
            <strong class="label">Arbeitszeit</strong><span class="value">Vollzeit, Teilzeit</span>
            <span class="label">Arbeitsort</span><span class="value">Berlin, Köln</span>
            <a href="https://bewerbung.example/refleitung" class="application-link">Zum Bewerbungsportal</a>
            <h2>Ihre Aufgaben</h2>
            <p>Sie leiten ein Team in der Cyberabwehr und beraten zu IT-Sicherheit.</p>
            <h2>Ihr Profil</h2>
            <p>Master in Informatik, Mathematik oder Cybersecurity.</p>
            <h2>Wir bieten</h2>
            <p>Unbefristete Einstellung und E 13 TV EntgO Bund.</p>
          </main>
        </body></html>
        """,
        "https://www.verfassungsschutz.de/SharedDocs/stellenangebote/verwaltung.html": """
        <html><body><main>
          <span class="label">Arbeitsort</span><span class="value">Köln</span>
          <h2>Ihre Aufgaben</h2><p>Allgemeine Verwaltung.</p>
        </main></body></html>
        """,
    }

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if url == discover_jobs.VERFASSUNGSSCHUTZ_RSS_URL:
            return xml_text
        return detail_pages[url]

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_verfassungsschutz_rss(
        source,
        ["Cyberabwehr", "IT-Sicherheit", "Referent"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.direct_job_pages_opened == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Referatsleitungen (m/w/d) im Bereich Cyberabwehr"
    assert candidate.url.endswith("/refleitung-cyberabwehr.html")
    assert candidate.location == "Berlin, Köln"
    assert candidate.alternate_url == "https://bewerbung.example/refleitung"
    assert "Deadline: 17. April 2026" in candidate.notes
    assert "Tasks: Sie leiten ein Team in der Cyberabwehr und beraten zu IT-Sicherheit." in candidate.notes
    assert "Profile: Master in Informatik, Mathematik oder Cybersecurity." in candidate.notes


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

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)
    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

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


def bundeswehr_source() -> discover_jobs.SourceConfig:
    return discover_jobs.SourceConfig(
        source="Bundeswehr",
        url="https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html#joblist/none/TwoColumnsMidExpanded",
        discovery_mode="bundeswehr_jobsuche",
        last_checked=None,
        cadence_group="every_run",
    )


def bundeswehr_odata_category_from_url(url: str) -> str:
    filter_expression = bundeswehr_odata_filter_from_url(url)
    assert "Langu eq 'D'" in filter_expression
    for category in discover_jobs.BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES:
        if f"SearchCategory eq '{category}'" in filter_expression:
            return category
    raise AssertionError(f"missing Bundeswehr SearchCategory filter: {url}")


def bundeswehr_odata_filter_from_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return query["$filter"][0]


def bundeswehr_odata_keyword_from_url(url: str) -> str | None:
    match = re.search(r"Keywords eq '((?:''|[^'])*)'", bundeswehr_odata_filter_from_url(url))
    if not match:
        return None
    return match.group(1).replace("''", "'")


def test_sap_odata_url_encodes_filters_and_literals():
    literal = discover_jobs.sap_odata_string_literal("O'Neil")
    assert literal == "'O''Neil'"

    url = discover_jobs.build_sap_odata_list_url(
        "https://example.com/odata/",
        "Jobs",
        f"(Name eq {literal})",
        ("Title", "PinstGuid"),
        10,
        20,
    )

    assert "%24filter=" in url
    query = parse_qs(urlparse(url).query)
    assert query["$filter"] == ["(Name eq 'O''Neil')"]
    assert query["$select"] == ["Title,PinstGuid"]
    assert query["$top"] == ["10"]
    assert query["$skip"] == ["20"]
    assert query["$format"] == ["json"]


def test_discover_bundeswehr_jobsuche_uses_sap_odata_with_full_pagination(monkeypatch):
    source = bundeswehr_source()
    monkeypatch.setattr(bundeswehr_provider, "BUNDESWEHR_ODATA_PAGE_SIZE", 1)
    rows_by_category = {
        "0021": [
            {
                "PinstGuid": "GUID-IT",
                "Title": "Einstellung Offizierin / Offizier im Bereich IT-Architektur",
                "BesOrt": "Euskirchen",
                "PostingTxt": "Informationstechnik und IT-Sicherheit im Geschaeftsbereich.",
                "RefCode": "SE-IT-1",
                "SearchCategory": "0021",
                "ApplicationEnd": "30.04.2026",
                "Arbeitszeit": "Vollzeit",
            },
            {
                "PinstGuid": "GUID-KOCH",
                "Title": "Koechin / Koch",
                "BesOrt": "Berlin",
                "PostingTxt": "Verpflegung und Kuechenorganisation.",
                "RefCode": "SE-KOCH-1",
                "SearchCategory": "0021",
            },
        ],
        "0026": [
            {
                "PinstGuid": "GUID-CYBER",
                "Title": "Buerosachbearbeiterin / Buerosachbearbeiter IT-Systempflege",
                "BesOrt": "Koenigswinter",
                "PostingTxt": "Cyber/IT und digitale Netze.",
                "RefCode": "ZIV-IT-1",
                "SearchCategory": "0026",
            }
        ],
        "0022": [],
        "0027": [],
        "0023": [],
        "0028": [],
    }
    details_by_guid = {
        "GUID-IT": {
            "PinstGuid": "GUID-IT",
            "JobDesc": "Sie gestalten IT-Grundschutz und sichere Informationstechnik.",
            "RequireDesc": "Erfahrung in IT-Sicherheit ist wuenschenswert.",
            "ContactDesc": "Kontakt ueber das Karrierecenter.",
        },
        "GUID-CYBER": {
            "PinstGuid": "GUID-CYBER",
            "JobDesc": "Sie betreuen Cyber/IT Verfahren.",
            "RequireDesc": "Kenntnisse in Netzen und Systempflege.",
        },
    }
    rows_by_keyword = {"Informationstechnik": [], "IT-Sicherheit": [], "Cyber/IT": []}
    list_requests: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        assert urlparse(url).path.endswith("/Stellensuche_Set/$count")
        keyword = bundeswehr_odata_keyword_from_url(url)
        if keyword is not None:
            return str(len(rows_by_keyword[keyword]))
        return str(len(rows_by_category[bundeswehr_odata_category_from_url(url)]))

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert timeout_seconds == 5
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/Stellensuche_Set"):
            assert query["$top"] == ["1"]
            skip = int(query["$skip"][0])
            keyword = bundeswehr_odata_keyword_from_url(url)
            if keyword is not None:
                rows = rows_by_keyword[keyword][skip : skip + 1]
            else:
                list_requests.append(url)
                category = bundeswehr_odata_category_from_url(url)
                rows = rows_by_category[category][skip : skip + 1]
            return {"d": {"results": rows}}

        match = re.search(r"PinstGuid='([^']+)'", parsed.path)
        assert match, f"unexpected detail URL: {url}"
        query = parse_qs(parsed.query)
        assert query["$format"] == ["json"]
        assert "JobDesc" in query["$select"][0]
        return {"d": details_by_guid[match.group(1)]}

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_bundeswehr_jobsuche(
        source,
        ["Informationstechnik", "IT-Sicherheit", "Cyber/IT"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 3
    assert coverage.direct_job_pages_opened == 2
    assert coverage.enumerated_jobs == 3
    assert coverage.matched_jobs == 2
    assert "0021:2p/2of2" in coverage.result_pages_scanned
    assert "0026:1p/1of1" in coverage.result_pages_scanned
    assert len(list_requests) == 3
    urls = {candidate.url for candidate in coverage.candidates}
    assert urls == {
        "https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html?job=GUID-IT",
        "https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html?job=GUID-CYBER",
    }
    candidate = next(candidate for candidate in coverage.candidates if candidate.url.endswith("GUID-IT"))
    assert candidate.location == "Euskirchen"
    assert candidate.matched_terms == ["IT-Sicherheit", "Informationstechnik"]
    assert "RefCode: SE-IT-1" in candidate.notes
    assert "Job: Sie gestalten IT-Grundschutz" in candidate.notes
    assert "Requirements: Erfahrung in IT-Sicherheit" in candidate.notes


def test_discover_bundeswehr_jobsuche_marks_partial_when_odata_detail_fails(monkeypatch):
    source = bundeswehr_source()
    rows_by_category = {category: [] for category in discover_jobs.BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES}
    rows_by_category["0021"] = [
        {
            "PinstGuid": "GUID-IT",
            "Title": "Referentin / Referent Informationstechnik",
            "BesOrt": "Bonn",
            "PostingTxt": "IT-Sicherheit und digitale Netze.",
            "RefCode": "SE-IT-2",
            "SearchCategory": "0021",
        }
    ]
    rows_by_keyword = {"Informationstechnik": []}

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert urlparse(url).path.endswith("/Stellensuche_Set/$count")
        keyword = bundeswehr_odata_keyword_from_url(url)
        if keyword is not None:
            return str(len(rows_by_keyword[keyword]))
        return str(len(rows_by_category[bundeswehr_odata_category_from_url(url)]))

    def fake_fetch_json(url: str, timeout_seconds: int):
        parsed = urlparse(url)
        if parsed.path.endswith("/Stellensuche_Set"):
            keyword = bundeswehr_odata_keyword_from_url(url)
            if keyword is not None:
                return {"d": {"results": rows_by_keyword[keyword]}}
            return {"d": {"results": rows_by_category[bundeswehr_odata_category_from_url(url)]}}
        raise TimeoutError("detail unavailable")

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_bundeswehr_jobsuche(source, ["Informationstechnik"], timeout_seconds=5)

    assert coverage.status == "partial"
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 0
    assert "detail enrichment failed for 1 matched candidate" in coverage.limitations[-1]
    assert coverage.candidates[0].url.endswith("?job=GUID-IT")


def test_discover_bundeswehr_jobsuche_keyword_pass_extracts_detail_only_matches(monkeypatch):
    source = bundeswehr_source()
    rows_by_category = {category: [] for category in discover_jobs.BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES}
    rows_by_category["0021"] = [
        {
            "PinstGuid": "GUID-LIST",
            "Title": "Expertin / Experte Informationstechnik",
            "BesOrt": "Koeln",
            "PostingTxt": "Informationstechnik im militaerischen Kontext.",
            "RefCode": "SE-LIST",
            "SearchCategory": "0021",
        },
        {
            "PinstGuid": "GUID-HIDDEN",
            "Title": "Sachbearbeitung Infrastruktur",
            "BesOrt": "Bonn",
            "PostingTxt": "Koordination und Dokumentation.",
            "RefCode": "SE-HIDDEN",
            "SearchCategory": "0021",
        },
    ]
    rows_by_keyword = {
        "Informationstechnik": [],
        "IT-Sicherheit": [rows_by_category["0021"][0], rows_by_category["0021"][1]],
    }
    details_by_guid = {
        "GUID-LIST": {
            "PinstGuid": "GUID-LIST",
            "JobDesc": "Sie bearbeiten technische Anforderungen.",
        },
        "GUID-HIDDEN": {
            "PinstGuid": "GUID-HIDDEN",
            "JobDesc": "Sie koordinieren IT-Sicherheit fuer digitale Infrastruktur.",
            "RequireDesc": "Kenntnisse sicherer Netze sind wuenschenswert.",
        },
    }
    detail_requests: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert urlparse(url).path.endswith("/Stellensuche_Set/$count")
        keyword = bundeswehr_odata_keyword_from_url(url)
        if keyword is not None:
            return str(len(rows_by_keyword[keyword]))
        return str(len(rows_by_category[bundeswehr_odata_category_from_url(url)]))

    def fake_fetch_json(url: str, timeout_seconds: int):
        parsed = urlparse(url)
        if parsed.path.endswith("/Stellensuche_Set"):
            keyword = bundeswehr_odata_keyword_from_url(url)
            query = parse_qs(parsed.query)
            skip = int(query["$skip"][0])
            top = int(query["$top"][0])
            if keyword is not None:
                return {"d": {"results": rows_by_keyword[keyword][skip : skip + top]}}
            category = bundeswehr_odata_category_from_url(url)
            return {"d": {"results": rows_by_category[category][skip : skip + top]}}

        match = re.search(r"PinstGuid='([^']+)'", parsed.path)
        assert match, f"unexpected detail URL: {url}"
        detail_requests.append(match.group(1))
        return {"d": details_by_guid[match.group(1)]}

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_bundeswehr_jobsuche(
        source,
        ["Informationstechnik", "IT-Sicherheit"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 2
    assert coverage.direct_job_pages_opened == 2
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 2
    assert detail_requests == ["GUID-LIST", "GUID-HIDDEN"]
    assert "keywords[Informationstechnik:0p/0of0, IT-Sicherheit:1p/2of2]" in coverage.result_pages_scanned
    candidates_by_url = {candidate.url: candidate for candidate in coverage.candidates}
    list_candidate = candidates_by_url["https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html?job=GUID-LIST"]
    hidden_candidate = candidates_by_url[
        "https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html?job=GUID-HIDDEN"
    ]
    assert list_candidate.matched_terms == ["IT-Sicherheit", "Informationstechnik"]
    assert hidden_candidate.matched_terms == ["IT-Sicherheit"]
    assert "Job: Sie koordinieren IT-Sicherheit" in hidden_candidate.notes


def test_discover_bundeswehr_jobsuche_keeps_category_results_when_keyword_search_fails(monkeypatch):
    source = bundeswehr_source()
    rows_by_category = {category: [] for category in discover_jobs.BUNDESWEHR_ODATA_OPPORTUNITY_CATEGORIES}
    rows_by_category["0021"] = [
        {
            "PinstGuid": "GUID-IT",
            "Title": "Expertin / Experte Informationstechnik",
            "BesOrt": "Bonn",
            "PostingTxt": "Informationstechnik und digitale Netze.",
            "RefCode": "SE-IT",
            "SearchCategory": "0021",
        }
    ]

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert urlparse(url).path.endswith("/Stellensuche_Set/$count")
        if bundeswehr_odata_keyword_from_url(url) is not None:
            raise TimeoutError("keyword count unavailable")
        return str(len(rows_by_category[bundeswehr_odata_category_from_url(url)]))

    def fake_fetch_json(url: str, timeout_seconds: int):
        parsed = urlparse(url)
        if parsed.path.endswith("/Stellensuche_Set"):
            return {"d": {"results": rows_by_category[bundeswehr_odata_category_from_url(url)]}}
        return {"d": {"PinstGuid": "GUID-IT", "JobDesc": "Informationstechnik fuer digitale Netze."}}

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)
    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_bundeswehr_jobsuche(source, ["Informationstechnik"], timeout_seconds=5)

    assert coverage.status == "partial"
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 1
    assert "Informationstechnik:failed" in coverage.result_pages_scanned
    assert "keyword search for 'Informationstechnik' failed" in coverage.limitations[-1]


def test_discover_bundeswehr_jobsuche_falls_back_to_profile_catalog_when_odata_fails(monkeypatch):
    source = bundeswehr_source()
    html = """
    <html><body>
      <a class="jobtitle" href="/soldatin-soldat-in-der-informationstechnik-417">Soldatin / Soldat in der Informationstechnik</a>
      <a class="jobtitle" href="/koch-123">Köchin / Koch</a>
    </body></html>
    """
    detail_html = """
    <html><body>
      <h2>Ihre Aufgaben</h2>
      <ul>
        <li>Betreiben sicherer IT-Systeme.</li>
        <li>Unterstuetzung bei der Abwehr von Cyberangriffen.</li>
      </ul>
      <h2>Was fuer uns zaehlt</h2>
      <p>Interesse an Informationstechnik und belastbare technische Grundlagen.</p>
      <h2>Was fuer Sie zaehlt</h2>
      <p>Besoldung nach dem Soldatengesetz sowie unentgeltliche truppenaerztliche Versorgung.</p>
    </body></html>
    """

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        if url.startswith(discover_jobs.BUNDESWEHR_ODATA_SERVICE_ROOT):
            raise TimeoutError("gateway unavailable")
        if url == discover_jobs.BUNDESWEHR_JOBSUCHE_URL:
            return html
        if url == "https://www.bundeswehrkarriere.de/soldatin-soldat-in-der-informationstechnik-417":
            return detail_html
        raise AssertionError(f"unexpected fetch: {url}")

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_bundeswehr_jobsuche(
        source,
        ["Informationstechnik", "Cyberabwehr"],
        timeout_seconds=5,
    )

    assert coverage.status == "partial"
    assert "SAP OData discovery failed" in coverage.limitations[0]
    assert coverage.direct_job_pages_opened == 1
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Soldatin / Soldat in der Informationstechnik"
    assert candidate.url == "https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html?job=soldatin-soldat-in-der-informationstechnik-417"
    assert candidate.alternate_url == "https://www.bundeswehrkarriere.de/soldatin-soldat-in-der-informationstechnik-417"
    assert "Tasks: Betreiben sicherer IT-Systeme." in candidate.notes
    assert "Qualifications: Interesse an Informationstechnik" in candidate.notes
    assert "Compensation: Besoldung nach dem Soldatengesetz" in candidate.notes


def test_discover_bundeswehr_profile_fallback_keeps_allowlisted_portal_url_when_detail_fetch_fails(monkeypatch):
    source = bundeswehr_source()
    html = """
    <html><body>
      <a class="jobtitle" href="/soldatin-soldat-in-der-informationstechnik-417">Soldatin / Soldat in der Informationstechnik</a>
    </body></html>
    """

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        if url.startswith(discover_jobs.BUNDESWEHR_ODATA_SERVICE_ROOT):
            raise TimeoutError("gateway unavailable")
        if url == discover_jobs.BUNDESWEHR_JOBSUCHE_URL:
            return html
        if url == "https://www.bundeswehrkarriere.de/soldatin-soldat-in-der-informationstechnik-417":
            raise TimeoutError("detail fetch blocked")
        raise AssertionError(f"unexpected fetch: {url}")

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_bundeswehr_jobsuche(
        source,
        ["Informationstechnik"],
        timeout_seconds=5,
    )

    assert coverage.direct_job_pages_opened == 0
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html?job=soldatin-soldat-in-der-informationstechnik-417"
    assert candidate.alternate_url == "https://www.bundeswehrkarriere.de/soldatin-soldat-in-der-informationstechnik-417"
    assert candidate.notes == "Bundeswehr jobsuche profile catalog fallback; Bewerbungsportal returned a generic error page in automation"


def test_discover_rheinmetall_html_extracts_structured_ssr_cards(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Rheinmetall",
        url="https://www.rheinmetall.com/de/karriere/aktuelle-stellenangebote",
        discovery_mode="rheinmetall_html",
        last_checked=None,
        cadence_group="every_run",
    )
    html = """
    <div class="gap-4 md:gap-6 flex flex-col">
      <div class="flex gap-0.5 group">
        <a href="/de/job/privacy_engineer__m_w_d_/123456" target="_blank" rel="noreferrer" class="print-avoid-page-break hidden"></a>
        <div class="flex flex-col flex-grow overflow-hidden relative p-4 bg-neutral text-secondary transition duration-300 hover:bg-neutral-dark border-l-8">
          <a href="/de/job/privacy_engineer__m_w_d_/123456" target="_blank" rel="noreferrer" class="print-avoid-page-break flex-grow pr-8">
            <div class="text-sm font-bold mb-4"><div class="flex">Job</div></div>
            <div class="text-sm font-bold md:text-xl mb-2">Privacy Engineer (m/w/d)</div>
          </a>
          <div class="flex justify-between items-end text-sm font-bold">
            <div class="flex flex-col md:flex-row md:flex-wrap md:items-end">
              <div class="flex flex-wrap mr-6">Rheinmetall Electronics GmbH | Bremen</div>
            </div>
          </div>
        </div>
      </div>
      <div class="flex gap-0.5 group">
        <a href="/de/job/office_manager__m_w_d_/999999" target="_blank" rel="noreferrer" class="print-avoid-page-break hidden"></a>
        <div class="flex flex-col flex-grow overflow-hidden relative p-4 bg-neutral text-secondary transition duration-300 hover:bg-neutral-dark border-l-8">
          <a href="/de/job/office_manager__m_w_d_/999999" target="_blank" rel="noreferrer" class="print-avoid-page-break flex-grow pr-8">
            <div class="text-sm font-bold mb-4"><div class="flex">Job</div></div>
            <div class="text-sm font-bold md:text-xl mb-2">Office Manager (m/w/d)</div>
          </a>
          <div class="flex justify-between items-end text-sm font-bold">
            <div class="flex flex-col md:flex-row md:flex-wrap md:items-end">
              <div class="flex flex-wrap mr-6">Rheinmetall AG | Düsseldorf</div>
            </div>
          </div>
        </div>
      </div>
    </div>
    """
    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_rheinmetall_html(
        source,
        ["privacy", "cryptography", "IT-Sicherheit"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Privacy Engineer (m/w/d)"
    assert candidate.employer == "Rheinmetall Electronics GmbH"
    assert candidate.location == "Bremen"
    assert candidate.url == "https://www.rheinmetall.com/de/job/privacy_engineer__m_w_d_/123456"
    assert candidate.matched_terms == ["privacy"]


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

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

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
