from __future__ import annotations

import discover_jobs
from discover import http as discover_http


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
