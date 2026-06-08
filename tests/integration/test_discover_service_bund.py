from __future__ import annotations

import discover_jobs
from discover import http as discover_http


def test_discover_service_bund_search_uses_native_term_queries_and_pagination(monkeypatch):
    page_one = """
    <html><body>
      <a href="IMPORTE/Stellenangebote/editor/Test/2026/04/1.html;jsessionid=E04094E94F0757C468870D022B1171FB.internet592?nn=4642046&amp;type=0&amp;searchResult=true&amp;templateQueryString=Kryptographie">
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
    urls_by_title = {candidate.title: candidate.url for candidate in coverage.candidates}
    assert (
        urls_by_title["Referentin / Referent Kryptographie (w/m/d)"]
        == "https://www.service.bund.de/IMPORTE/Stellenangebote/editor/Test/2026/04/1.html"
    )
    listing_urls = [url for url in seen_urls if "Formular.html" in url]
    assert all("cl2Categories_Laufbahn=laufbahn-hoehererdienst" in url for url in listing_urls)


def test_discover_service_bund_search_enriches_candidate_detail_fields(monkeypatch):
    listing_html = """
    <html><body>
      <a href="/IMPORTE/Stellenangebote/interamt/2026/05/1452343.html;jsessionid=abc?nn=4642046&amp;searchResult=true&amp;templateQueryString=ZITiS">
        <div><h3><em>Stellenbezeichnung</em>Se&shy;ni&shy;or Soft&shy;wa&shy;re&shy;ent&shy;wick&shy;le&shy;rin (w/m/d) für Backend</h3>
        <p><em>Arbeitgeber</em> Zen&shy;tra&shy;le Stel&shy;le für In&shy;for&shy;ma&shy;ti&shy;ons&shy;tech&shy;nik im Si&shy;cher&shy;heits&shy;be&shy;reich</p></div>
        <div><p><em>Veröffentlicht</em> 28.05.26</p></div>
        <div><p><em>Bewerbungsfrist</em> 21.06.26</p></div>
      </a>
    </body></html>
    """
    detail_html = """
    <html><body>
      <dl>
        <dt>Ort</dt><dd>München</dd>
      </dl>
      <p><strong>DEINE AUFGABEN SIND U. A.:</strong></p>
      <p>Sie entwickeln Backend-Services für IT-Sicherheit und Kryptographie.</p>
      <p><strong>DIESE QUALIFIKATIONEN SIND EIN MUSS:</strong></p>
      <p>Erforderlich sind Erfahrung in Softwareentwicklung und sichere Kommunikation.</p>
      <p><strong>DAS IST FINANZIELL FÜR DICH DRIN:</strong></p>
      <p>Entgeltgruppe E 13 TVöD Bund.</p>
      <p><strong>SO GEHT ES WEITER:</strong></p>
      <p>Bitte nutzen Sie das Bewerbungsportal.</p>
    </body></html>
    """
    detail_url = "https://www.service.bund.de/IMPORTE/Stellenangebote/interamt/2026/05/1452343.html"
    source = discover_jobs.SourceConfig(
        source="ZITiS",
        url="https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html?templateQueryString=ZITiS",
        discovery_mode="service_bund_search",
        last_checked=None,
        cadence_group="every_run",
    )

    seen_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        seen_urls.append(url)
        if url == detail_url:
            return detail_html
        return listing_html

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_service_bund_search(source, ["ZITiS", "IT-Sicherheit"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.direct_job_pages_opened == 1
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    assert seen_urls[-1] == detail_url
    candidate = coverage.candidates[0]
    assert candidate.title == "Senior Softwareentwicklerin (w/m/d) für Backend"
    assert candidate.employer == "Zentrale Stelle für Informationstechnik im Sicherheitsbereich"
    assert candidate.location == "München"
    assert set(candidate.matched_terms) == {"IT-Sicherheit", "ZITiS"}
    assert "Tasks: Sie entwickeln Backend-Services für IT-Sicherheit und Kryptographie." in candidate.notes
    assert "Qualifications: Erforderlich sind Erfahrung in Softwareentwicklung und sichere Kommunikation." in candidate.notes
    assert "Compensation: Entgeltgruppe E 13 TVöD Bund." in candidate.notes


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
