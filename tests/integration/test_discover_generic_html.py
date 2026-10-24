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


def test_discover_amodo_preserves_qualifications_beyond_description_limit(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Amodo Design",
        url="https://amododesign.com/careers/",
        discovery_mode="html",
        last_checked=None,
        cadence_group="every_run",
    )
    job_url = "https://amododesign.com/career/ai-specialist"
    title = "Field Specialist – AI hardware security and verification"
    qualifications = (
        "Experience developing secure hardware architectures and leading engineering projects. "
        "Communicate technical requirements to AI researchers and policymakers."
    )
    listing = '<a href="/career/ai-specialist/">More info</a>' * 2
    detail = f"""
    <html><head><script>{'tracking_code ' * 500}</script>
      <style>.career-body {{ color: red; }}</style></head><body>
      <nav>Navigation content</nav><h1>{title}</h1>
      <div class="career-body prose" data-astro-cid-example>
        <p>Amodo builds hardware for AI verification.</p>
        <h2>What you’ll do</h2>
        <div><p>{'Develop hardware architectures for verifiable AI systems. ' * 100}</p></div>
        <h2>About you</h2><ul><li>{qualifications}</li></ul>
        <script>body_tracking_code</script>
      </div><footer>Footer content</footer>
    </body></html>
    """
    fetched = []

    def fetch_text(url: str, timeout_seconds: int) -> str:
        fetched.append(url)
        return {source.url: listing, job_url: detail}[url]

    monkeypatch.setattr(discover_http, "fetch_text", fetch_text)

    coverage = discover_jobs.discover_html(source, ["Specialist", "hardware", "security"], 5)

    assert fetched == [source.url, job_url]
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 1
    assert coverage.limitations == []
    candidate = coverage.candidates[0]
    assert candidate.url == job_url
    assert candidate.title == title
    assert candidate.matched_terms == ["Specialist", "hardware", "security"]
    assert candidate.description.startswith("Amodo builds hardware for AI verification.")
    assert candidate.description_truncated is True
    assert qualifications in candidate.notes
    for noise in ("tracking_code", "color: red", "Navigation content", "Footer content"):
        assert noise not in candidate.description + candidate.notes


def test_discover_amodo_keeps_candidate_when_detail_fetch_fails(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Amodo Design",
        url="https://amododesign.com/careers/",
        discovery_mode="html",
        last_checked=None,
        cadence_group="every_run",
    )

    def fetch_text(url: str, timeout_seconds: int) -> str:
        if url == source.url:
            return '<a href="/career/ai-specialist/">More info</a>'
        raise TimeoutError("detail unavailable")

    monkeypatch.setattr(discover_http, "fetch_text", fetch_text)

    coverage = discover_jobs.discover_html(source, ["Specialist"], 5)

    assert coverage.matched_jobs == 1
    assert coverage.candidates[0].url == "https://amododesign.com/career/ai-specialist"
    assert coverage.direct_job_pages_opened == 0
    assert any("detail unavailable" in limitation for limitation in coverage.limitations)
