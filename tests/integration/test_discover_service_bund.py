from __future__ import annotations

import discover_jobs
from discover import http as discover_http


def test_discover_service_bund_search_uses_native_term_queries_and_pagination(monkeypatch):
    page_one = """
    <html><body>
      <a href="IMPORTE/Stellenangebote/editor/Test/2026/04/1.html?nn=4642046&amp;type=0&amp;searchResult=true&amp;templateQueryString=Kryptographie">
        <div><h3><em>Stellenbezeichnung</em>Referentin / Referent Kryptographie (w/m/d)</h3>
        <p><em>Arbeitgeber</em> Bundesamt Test</p></div>
        <div><p><em>Veröffentlicht</em> 01.04.26</p></div>
        <div><p><em>Bewerbungsfrist</em> 30.04.26</p></div>
      </a>
      <li class="next" aria-hidden="true">
        <button title="eine Seite weiter" form="form-4642034" class="c-pagination-button" type="submit" name="gtp" value="4642266_list=2">eine Seite weiter</button>
      </li>
    </body></html>
    """
    page_two = """
    <html><body>
      <a href="IMPORTE/Stellenangebote/editor/Test/2026/04/2.html?nn=4642046&amp;type=0&amp;searchResult=true&amp;templateQueryString=Kryptographie">
        <div><h3><em>Stellenbezeichnung</em>IT-Sicherheitsexperte (w/m/d)</h3>
        <p><em>Arbeitgeber</em> Bundesamt Test</p></div>
        <div><p><em>Veröffentlicht</em> 02.04.26</p></div>
        <div><p><em>Bewerbungsfrist</em> 01.05.26</p></div>
      </a>
    </body></html>
    """
    source = discover_jobs.SourceConfig(
        source="Bund",
        url=(
            "https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html"
            "?view=processForm&nn=4641514&cl2Categories_Laufbahn=laufbahn-hoehererdienst"
        ),
        discovery_mode="service_bund_search",
        last_checked=None,
        cadence_group="every_run",
    )

    seen_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        seen_urls.append(url)
        if "gtp=4642266_list%3D2" in url:
            return page_two
        return page_one

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_service_bund_search(
        source,
        ["Kryptographie", "IT-Sicherheit"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 4
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 2
    titles = {candidate.title for candidate in coverage.candidates}
    assert titles == {"Referentin / Referent Kryptographie (w/m/d)", "IT-Sicherheitsexperte (w/m/d)"}
    assert all("cl2Categories_Laufbahn=laufbahn-hoehererdienst" in url for url in seen_urls)


def test_discover_service_bund_links_filters_to_real_job_links(monkeypatch):
    html = """
    <html><body>
      <a href="https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html?jobsrss=true">RSS - Newsfeed</a>
      <a href="https://www.service.bund.de/IMPORTE/Stellenangebote/editor/BVA-BSI/2026/03/6450395.html">
        Referentin/Referent (w/m/d) im Bereich Attack Surface Management BSI-2026-027
      </a>
      <a href="https://www.example.org/not-a-job">Weitere Informationen</a>
    </body></html>
    """
    source = discover_jobs.SourceConfig(
        source="BSI",
        url="https://www.bsi.bund.de/DE/Karriere/Stellenangebote/stellenangebot_node.html",
        discovery_mode="service_bund_links",
        last_checked=None,
        cadence_group="every_run",
    )

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_service_bund_links(
        source,
        ["Referent", "IT-Sicherheit", "Kryptographie"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.employer == "BSI"
    assert candidate.title == "Referentin/Referent (w/m/d) im Bereich Attack Surface Management BSI-2026-027"
    assert candidate.url == "https://www.service.bund.de/IMPORTE/Stellenangebote/editor/BVA-BSI/2026/03/6450395.html"
