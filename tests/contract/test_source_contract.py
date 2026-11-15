from __future__ import annotations

import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse

import pytest

from discover import core, http
from discover.registry import SourceAdapter, load_registry
from discover.sources import browser as browser_provider


TERMS = ["cryptography", "zero-knowledge", "security"]
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "sources"


def _contract(mode):
    path = FIXTURES / mode / "contract.json"
    assert path.is_file(), f"{mode}: add {path} with independently reviewed expected jobs and capability checks"
    return json.loads(path.read_text())


def _fixture_dir(repo_root, mode):
    return FIXTURES / mode


def _source_for_mode(mode):
    return core.SourceConfig(**_contract(mode)["source"], discovery_mode=mode,
                             last_checked=None, cadence_group="every_run")


def _provider_modes() -> list[tuple[str, SourceAdapter]]:
    return sorted(load_registry().items())


class _RaisingChromium:
    def launch(self, headless: bool = True):
        del headless
        raise RuntimeError(
            "BrowserType.launch: Executable doesn't exist at /tmp/chromium/chrome\n"
            "Please run the following command to download new browsers:\n"
            "playwright install"
        )


class _MissingBrowserContext:
    def __enter__(self):
        return type("FakePlaywright", (), {"chromium": _RaisingChromium()})()

    def __exit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


def _install_missing_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(browser_provider, "load_sync_playwright", lambda: _MissingBrowserContext)


def _install_fixture(monkeypatch: pytest.MonkeyPatch, fixture_dir: Path, stem: str) -> None:
    contract = _contract(fixture_dir.name)
    if contract.get("transport") == "browser":
        from browser_fixtures import install_browser
        path = fixture_dir / f"{stem}.json"
        assert path.is_file(), f"Missing required browser fixture: {path}"
        return install_browser(monkeypatch, json.loads(path.read_text()))
    html_path = fixture_dir / f"{stem}.html"
    json_path = fixture_dir / f"{stem}.json"
    installed = False
    if html_path.exists():
        html = html_path.read_text()
        monkeypatch.setattr(http, "fetch_text", lambda url, timeout_seconds, headers=None: html)
        installed = True
    if json_path.exists():
        payload = json.loads(json_path.read_text())
        monkeypatch.setattr(
            http,
            "fetch_json",
            lambda url, timeout_seconds, headers=None: payload[url] if isinstance(payload, dict) and url in payload else payload,
        )
        monkeypatch.setattr(http, "post_json", lambda url, data, timeout_seconds, headers=None: payload)
        installed = True
    if installed:
        return
    pytest.fail(f"Missing required provider fixture: expected {html_path} or {json_path}")


@pytest.mark.parametrize(("mode", "adapter"), _provider_modes())
@pytest.mark.parametrize("case", ["response", "empty", "duplicates"])
def test_provider_extraction_contract(mode, adapter, case, repo_root, monkeypatch):
    contract = _contract(mode)
    expected = [] if case == "empty" else contract.get(f"{case}_expected", contract["expected"])
    assert contract["expected"] or not adapter.emits_candidates, f"{mode}: emitting providers need nonempty ground truth"
    browser = _install_fixture(monkeypatch, _fixture_dir(repo_root, mode), case)
    source = _source_for_mode(mode)
    coverage = adapter.discover(source, contract["terms"], 5)
    assert isinstance(coverage, core.Coverage)
    assert coverage.source == source.source
    assert coverage.source_url == source.url
    assert coverage.discovery_mode == mode
    assert coverage.cadence_group == source.cadence_group
    assert coverage.status in {"complete", "partial", "failed"}
    assert coverage.result_pages_scanned
    assert coverage.matched_jobs == len(coverage.candidates)
    assert coverage.enumerated_jobs >= coverage.matched_jobs
    if case == "empty":
        assert coverage.status == contract["empty_status"]
    else:
        assert coverage.status != "failed"
    if coverage.status != "complete":
        assert coverage.limitations
    if adapter.emits_candidates:
        assert coverage.search_terms_tried == contract.get("search_terms_tried", contract["terms"])
    else:
        assert not coverage.candidates
        assert coverage.limitations, "Non-emitting probes must explain their limitations"
    actual = {c.url: c for c in coverage.candidates}
    assert len(actual) == len(coverage.candidates), "Duplicate candidate URLs"
    assert set(actual) == {c["url"] for c in expected}, f"{mode}/{case}: expected vacancies were missed or unexpected links admitted"
    for wanted in expected:
        candidate = actual[wanted["url"]]
        for field, value in wanted.items():
            assert getattr(candidate, field) == value, f"{mode}/{case}: {field} for {wanted['url']}"
        assert candidate.employer
        assert candidate.source_url == source.url
        assert candidate.matched_terms
        assert set(candidate.matched_terms) <= set(contract["terms"])
        assert candidate.notes
        assert urlparse(candidate.url).scheme in {"http", "https"}
    if browser:
        assert browser.page.visited, "Provider must navigate the browser"
        assert browser.closed, "Provider must release the browser"


def test_secunet_jobboard_enriches_kept_candidates_from_jobposting_json_ld(
    monkeypatch: pytest.MonkeyPatch,
):
    listing_html = """
    <html><body>
      <a href="https://jobs.secunet.com/Security-Engineer-de-j123.html">Security Engineer</a>
    </body></html>
    """
    detail_html = """
    <html><body>
      <header>Navigation and employer marketing must not become role detail.</header>
      <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "title": "Security Engineer (m/w/d)",
          "description": "&lt;p&gt;Develop high-assurance products for public-sector customers.&lt;/p&gt;",
          "responsibilities": "&lt;ul&gt;&lt;li&gt;Design cryptographic protocols and review security architectures.&lt;/li&gt;&lt;li&gt;Implement secure services in Rust.&lt;/li&gt;&lt;/ul&gt;",
          "qualifications": "&lt;ul&gt;&lt;li&gt;Experience with applied cryptography and embedded security.&lt;/li&gt;&lt;li&gt;Strong software engineering skills.&lt;/li&gt;&lt;/ul&gt;",
          "jobBenefits": "Flexible work and individual professional development."
        }
      </script>
      <footer>Cookie settings and generic careers content.</footer>
    </body></html>
    """
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        fetched_urls.append(url)
        if url.endswith("-j123.html"):
            return detail_html
        return listing_html

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = core.discover_source(_source_for_mode("secunet_jobboard"), TERMS, 5)

    assert coverage.status == "complete"
    assert coverage.direct_job_pages_opened == 1
    assert len(fetched_urls) == 2
    candidate = coverage.candidates[0]
    assert candidate.title == "Security Engineer (m/w/d)"
    assert "Tasks: Design cryptographic protocols and review security architectures." in candidate.notes
    assert "Qualifications: Experience with applied cryptography and embedded security." in candidate.notes
    assert "Develop high-assurance products" in candidate.description
    assert "Implement secure services in Rust." in candidate.description
    assert "employer marketing" not in candidate.description
    assert "Cookie settings" not in candidate.description
    assert "<li>" not in candidate.description


def test_thales_html_enriches_kept_candidates_from_detail_pages(monkeypatch: pytest.MonkeyPatch):
    listing_html = """
    <html><body>
      <a href="/global/en/job/123/security-engineer">Security Engineer</a>
      <script>window.__DATA__ = {"eagerLoadRefineSearch":{"hits":1,"totalHits":1,"data":{"jobs":[{"reqId":"123","jobSeqNo":"THALES123","title":"Security Engineer","cityStateCountry":"Munich, Germany","descriptionTeaser":"Build cryptography systems.","category":"Security"}]}}};</script>
    </body></html>
    """
    detail_html = """
    <html><body>
      <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "JobPosting",
          "description": "&lt;h2&gt;Responsibilities&lt;/h2&gt;&lt;p&gt;Design cryptography services for secure identity products.&lt;/p&gt;&lt;h2&gt;Qualifications&lt;/h2&gt;&lt;p&gt;Experience with applied security engineering and production cryptography.&lt;/p&gt;&lt;h2&gt;Benefits&lt;/h2&gt;&lt;p&gt;Competitive salary and flexible benefits.&lt;/p&gt;&lt;h2&gt;About Thales&lt;/h2&gt;&lt;p&gt;This company overview should not be copied into notes.&lt;/p&gt;"
        }
      </script>
    </body></html>
    """
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        assert timeout_seconds == 5
        fetched_urls.append(url)
        if "/global/en/job/123/" in url:
            return detail_html
        return listing_html

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    coverage = core.discover_source(_source_for_mode("thales_html"), ["cryptography"], 5)

    assert coverage.status == "complete"
    assert coverage.direct_job_pages_opened == 1
    assert len(fetched_urls) == 2
    candidate = coverage.candidates[0]
    assert candidate.title == "Security Engineer"
    assert "Tasks: Design cryptography services for secure identity products." in candidate.notes
    assert "Qualifications: Experience with applied security engineering and production cryptography." in candidate.notes
    assert "Compensation: Competitive salary and flexible benefits." in candidate.notes
    assert "<p>" not in candidate.notes
    assert "company overview" not in candidate.notes


@pytest.mark.parametrize(("mode", "_adapter"), _provider_modes())
@pytest.mark.parametrize("error", [URLError("fixture network failure"), ValueError("malformed response: invalid JSON/XML")], ids=["network", "decode"])
def test_provider_transport_failure_is_truthful(mode, _adapter, monkeypatch, error):
    if _contract(mode).get("transport") == "browser":
        from browser_fixtures import install_browser
        install_browser(monkeypatch, [{}], error=error)

    def raise_url_error(url: str, timeout_seconds: int, headers: dict[str, str] | None = None):
        del url, timeout_seconds, headers
        raise error

    monkeypatch.setattr(http, "fetch_text", raise_url_error)
    monkeypatch.setattr(http, "fetch_json", raise_url_error)
    monkeypatch.setattr(http, "post_json", lambda url, data, timeout_seconds, headers=None: raise_url_error(url, timeout_seconds))

    coverage = core.discover_source(_source_for_mode(mode), TERMS, 5)

    assert coverage.status in {"failed", "partial"}
    assert coverage.matched_jobs == 0
    assert coverage.candidates == []
    assert coverage.limitations


@pytest.mark.parametrize(
    ("mode", "adapter"),
    [(mode, adapter) for mode, adapter in _provider_modes() if "playwright.sync_api" in adapter.requires],
)
def test_browser_provider_missing_browser_binaries_returns_partial(
    mode: str,
    adapter: SourceAdapter,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_missing_browser(monkeypatch)

    coverage = adapter.discover(_source_for_mode(mode), TERMS, 5)

    assert coverage.status == "partial"
    assert coverage.matched_jobs == 0
    assert coverage.candidates == []
    assert coverage.limitations == [
        "Playwright browser binaries are not installed; run ./.venv/bin/python -m playwright install chromium"
    ]


@pytest.mark.parametrize(("mode", "adapter"), _provider_modes())
def test_registered_provider_has_explicit_capability_evidence(mode, adapter):
    contract = _contract(mode)
    assert set(contract['capabilities']) == {'pagination', 'details', 'browser'}
    for capability, evidence in contract['capabilities'].items():
        assert evidence['note'], f'{mode}: explain scope of {capability}'
        for path in evidence['tests']:
            assert (FIXTURES.parents[1] / path).is_file(), f'{mode}: missing {capability} regression suite {path}'
    if 'playwright.sync_api' in adapter.requires:
        assert contract.get('transport') == 'browser'
        assert contract['capabilities']['browser']['tests']
    if contract['empty_status'] != 'complete':
        assert contract['empty_reason'], f'{mode}: explain why an empty fixture is not authoritative'
