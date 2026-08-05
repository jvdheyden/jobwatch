from __future__ import annotations

from urllib.request import Request

import discover_jobs
from discover import http as discover_http


def test_ipv4_https_handler_uses_its_ssl_context(monkeypatch):
    handler = discover_http._IPv4HTTPSHandler()
    request = Request("https://example.com/")
    captured: dict[str, object] = {}

    def fake_do_open(connection_factory, opened_request, **kwargs):
        captured.update(
            connection_factory=connection_factory,
            request=opened_request,
            kwargs=kwargs,
        )
        return "response"

    monkeypatch.setattr(handler, "do_open", fake_do_open)

    assert handler.https_open(request) == "response"
    assert captured["request"] is request
    assert captured["kwargs"] == {"context": handler._context}


def test_discover_duality_uses_ipv4_for_cloudflare_blocked_careers_page(monkeypatch):
    html = """
    <html><body>
      <a href="/careers/applied-cryptography-engineer/">Applied Cryptography Engineer</a>
      <a href="/careers/head-of-defense-sales/">Head of Defense Sales</a>
      <a href="/careers/head-of-defense-sales/">Head of Defense Sales</a>
      <a href="https://www.oracle.com/news/announcement/privacy-first-security/">
        Duality delivers privacy-first security
      </a>
      <a href="/privacy-enhancing-technologies/">Privacy-enhancing technologies</a>
    </body></html>
    """
    source = discover_jobs.SourceConfig(
        source="Duality Technologies",
        url="https://dualitytech.com/careers/",
        discovery_mode="html",
        last_checked=None,
        cadence_group="every_run",
    )

    def fail_default_fetch(url: str, timeout_seconds: int) -> str:
        raise AssertionError("Duality should use the IPv4 fetch path")

    monkeypatch.setattr(discover_http, "fetch_text", fail_default_fetch)
    monkeypatch.setattr(discover_http, "fetch_text_ipv4", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_html(source, ["applied cryptography"], 5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    assert {candidate.url for candidate in coverage.candidates} == {
        "https://dualitytech.com/careers/applied-cryptography-engineer",
    }


def test_discover_lattica_news_requires_explicit_hiring_term(monkeypatch):
    html = """
    <html><body>
      <nav><a href="/technology/privacy-engineering">Security and Privacy</a></nav>
      <a href="/news/encrypted-ai-vector-search-fhe-benchmarks.html">
        Research: Measuring Encrypted AI and Vector Search with FHE Benchmarks
      </a>
      <a href="/news/we-are-hiring.html">We're hiring cryptography engineers</a>
    </body></html>
    """
    source = discover_jobs.SourceConfig(
        source="Lattica",
        url="https://www.lattica.ai/news",
        discovery_mode="html",
        last_checked=None,
        cadence_group="every_run",
    )
    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_html(source, ["hiring", "we're hiring", "we are hiring"], 5)

    assert coverage.enumerated_jobs == 3
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "We're hiring cryptography engineers"
    assert candidate.url == "https://www.lattica.ai/news/we-are-hiring.html"
    assert candidate.matched_terms == ["hiring", "we're hiring"]


def test_discover_html_admits_configured_sales_title_and_excludes_no_match(monkeypatch):
    html = """
    <html><body>
      <a href="/jobs/sales-engineer">Sales Engineer</a>
      <a href="/jobs/customer-success">Customer Success Associate</a>
    </body></html>
    """
    source = discover_jobs.SourceConfig(
        source="Example Careers",
        url="https://example.test/careers",
        discovery_mode="html",
        last_checked=None,
        cadence_group="every_run",
    )
    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_html(source, ["sales engineer"], 5)

    assert coverage.matched_jobs == 1
    assert coverage.candidates[0].title == "Sales Engineer"
    assert coverage.candidates[0].matched_terms == ["sales engineer"]
