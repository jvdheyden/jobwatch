from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from discover import http
from discover.core import SourceConfig
from discover.sources.successfactors import discover_successfactors_rss


TARGET_URL = (
    "https://careers.gi-de.com/GieseckeDevrient/job/"
    "M%C3%BCnchen-Kryptographie-und-Protokoll-Experte-%28mwd%29/1426626933"
)


def test_successfactors_rss_finds_localized_role_and_keeps_description(monkeypatch):
    target_feed = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel><item>
      <title><![CDATA[Kryptographie- und Protokoll Experte (m/w/d) (München, DE)]]></title>
      <description><![CDATA[
        <h2>Ihre Aufgaben</h2>
        <p>Konzeption und Entwicklung kryptographischer Protokolle mit Fokus auf Post-Quanten-Kryptographie.</p>
        <h2>Ihre Qualifikationen</h2>
        <p>Formale Verifikation und Privacy-Preserving Technologies.</p>
      ]]></description>
      <link>{TARGET_URL}/?feedId=null&amp;utm_source=J2WRSS&amp;utm_medium=rss</link>
    </item></channel></rss>"""
    empty_feed = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        fetched_urls.append(url)
        keyword = (parse_qs(urlparse(url).query).get("keywords") or [""])[0]
        return target_feed if keyword in {"Kryptographie", "Protokoll"} else empty_feed

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)
    source = SourceConfig(
        source="Giesecke+Devrient",
        url="https://careers.gi-de.com/search/?locale=de_DE",
        discovery_mode="successfactors_rss",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    terms = ["cryptography", "Kryptographie", "Protokoll"]

    coverage = discover_successfactors_rss(source, terms, 5)

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 3
    assert coverage.result_pages_scanned == "rss_search=3"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    assert len(fetched_urls) == 3
    assert all("/services/rss/job/" in url for url in fetched_urls)
    assert all(parse_qs(urlparse(url).query)["locale"] == ["de_DE"] for url in fetched_urls)
    candidate = coverage.candidates[0]
    assert candidate.title == "Kryptographie- und Protokoll Experte (m/w/d)"
    assert candidate.location == "München, DE"
    assert candidate.url == TARGET_URL
    assert candidate.matched_terms == ["Kryptographie", "Protokoll"]
    assert "Tasks: Konzeption und Entwicklung kryptographischer Protokolle" in candidate.notes
    assert "Qualifications: Formale Verifikation und Privacy-Preserving Technologies." in candidate.notes
    assert "Post-Quanten-Kryptographie" in candidate.description
    assert "Privacy-Preserving Technologies" in candidate.description


def test_successfactors_rss_reports_partial_coverage_when_one_term_fails(monkeypatch):
    empty_feed = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        del timeout_seconds
        if "keywords=broken" in url:
            raise TimeoutError("timed out")
        return empty_feed

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)
    source = SourceConfig(
        source="Example",
        url="https://careers.example.com/search/",
        discovery_mode="successfactors_rss",
        last_checked=None,
        cadence_group="every_run",
    )

    coverage = discover_successfactors_rss(source, ["security", "broken"], 5)

    assert coverage.status == "partial"
    assert coverage.listing_pages_scanned == 1
    assert coverage.limitations == ["RSS fetch failed for 'broken': TimeoutError: timed out"]
