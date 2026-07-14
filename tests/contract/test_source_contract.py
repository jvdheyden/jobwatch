from __future__ import annotations

import inspect
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse

import pytest

from discover import core, http
from discover.registry import SourceAdapter, load_registry
from discover.sources import browser as browser_provider


TERMS = ["cryptography", "zero-knowledge", "security"]
BROWSER_MODES = {
    "asml_browser",
    "automattic_browser",
    "browser",
    "coinbase_browser",
    "helsing_browser",
    "thales_browser",
    "trailofbits_browser",
}


def _fixture_dir(repo_root: Path, mode: str) -> Path:
    return repo_root / "tests" / "fixtures" / "sources" / mode


def _source_for_mode(mode: str) -> core.SourceConfig:
    urls = {
        "ashby_api": "https://jobs.ashbyhq.com/example",
        "ashby_html": "https://jobs.ashbyhq.com/example",
        "alphatheta_html": "https://alphatheta.com/careers/",
        "apple_jobs": "https://jobs.apple.com/en-us/search?search=cryptography",
        "asml_browser": "https://www.asml.com/en/careers/find-your-job",
        "automattic_browser": "https://automattic.com/work-with-us/",
        "auswaertiges_amt_json": "https://www.auswaertiges-amt.de/de/karriere/stellenanzeigen",
        "bamboohr_api": "https://example.bamboohr.com/careers",
        "bnd_career_search": "https://www.bnd.bund.de/SiteGlobals/Forms/Suche/erweiterte_Karrieresuche_Formular.html?nn=415896#sprg415980",
        "bosch_autocomplete": "https://www.bosch.de/karriere/jobs",
        "browser": "https://www.google.com/about/careers/applications/jobs/results",
        "bundeswehr_jobsuche": "https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html#joblist/none/TwoColumnsMidExpanded",
        "coinbase_browser": "https://www.coinbase.com/careers",
        "cybernetica_teamdash": "https://cyber.ee/careers/",
        "demant_rss": "https://www.demant.com/careers",
        "dover_api": "https://app.dover.com/example/careers/123e4567-e89b-12d3-a456-426614174000",
        "ecb_avature_rss": "https://talent.ecb.europa.eu/careers/SearchJobs?jobRecordsPerPage=50",
        "eightfold_api": "https://apply.careers.microsoft.com/careers",
        "enbw_phenom": "https://careers.enbw.com/en_US/careers",
        "factorial": "https://example.factorialhr.com/",
        "getro_api": "https://jobs.example-getro.com/jobs",
        "greenhouse_api": "https://job-boards.greenhouse.io/example",
        "hackernews_jobs": "https://news.ycombinator.com/jobs",
        "hackernews_whoishiring_api": "https://news.ycombinator.com/user?id=whoishiring",
        "harman_html": "https://jobsearch.harman.com/en_US/careers/SearchJobs",
        "helsing_browser": "https://helsing.ai/jobs",
        "hibob_api": "https://example.careers.hibob.com",
        "html": "https://jobs.example.com/",
        "iacr_jobs": "https://www.iacr.org/jobs/",
        "ibm_api": "https://www.ibm.com/careers/search",
        "icims_html": "https://example.icims.com/jobs",
        "infineon_api": "https://jobs.infineon.com/careers",
        "jobvite_html": "https://jobs.jobvite.com/example/jobs",
        "knds_jobboard": "https://jobs.knds.de/content/search/?locale=de_DE",
        "krisp_html": "https://krisp.ai/careers/",
        "leastauthority_careers": "https://leastauthority.com/careers/",
        "lever_json": "https://jobs.lever.co/example",
        "lifeatspotify_api": "https://www.lifeatspotify.com/jobs",
        "neclab_jobs": "https://jobs.neclab.eu/",
        "partisia_site": "https://partisiablockchain.com/",
        "pcd_team": "https://pcd.team/jd",
        "personio_page": "https://example.jobs.personio.de/",
        "qedit_inline": "https://qed-it.com/careers",
        "qusecure_careers": "https://www.qusecure.com/careers/",
        "recruitee_inline": "https://career.quantum-systems.com/",
        "rheinmetall_html": "https://www.rheinmetall.com/de/karriere/aktuelle-stellenangebote",
        "sennheiser_rss": "https://jobs.sennheiser.com/",
        "service_bund_links": "https://www.bsi.bund.de/DE/Karriere/Stellenangebote/stellenangebot_node.html",
        "service_bund_search": (
            "https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html"
            "?view=processForm&nn=4641514"
        ),
        "secunet_jobboard": "https://www.secunet.com/karriere/stellenangebote",
        "softgarden_html": "https://example.softgarden.io/de/vacancies",
        "teamtailor_api": "https://www.rolandcareers.com/",
        "thales_browser": "https://careers.thalesgroup.com/global/en/search-results",
        "thales_html": "https://careers.thalesgroup.com/global/en/search-results",
        "trailofbits_browser": "https://trailofbits.com/careers/",
        "workable_api": "https://apply.workable.com/example/",
        "workday_api": "https://example.wd1.myworkdayjobs.com/Example",
        "ultipro_api": "https://recruiting2.ultipro.com/EXA1000EX/JobBoard/123e4567-e89b-12d3-a456-426614174000/",
        "verfassungsschutz_rss": "https://www.verfassungsschutz.de/jobs",
        "yc_jobs_board": "https://www.ycombinator.com/jobs/role/software-engineer",
    }
    names = {
        "asml_browser": "ASML",
        "automattic_browser": "Automattic",
        "browser": "Google",
        "coinbase_browser": "Coinbase",
        "helsing_browser": "Helsing",
        "thales_browser": "Thales",
        "trailofbits_browser": "Trail of Bits",
    }
    return core.SourceConfig(
        source=names.get(mode, mode.replace("_", " ").title()),
        url=urls.get(mode, "https://jobs.example.com/example"),
        discovery_mode=mode,
        last_checked=None,
        cadence_group="every_run",
    )


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
    pytest.skip(f"Missing provider fixture: expected {html_path} or {json_path}")


@pytest.mark.parametrize(("mode", "adapter"), _provider_modes())
def test_provider_signature_is_contract_compatible(mode: str, adapter: SourceAdapter):
    del mode
    signature = inspect.signature(adapter.discover)
    assert list(signature.parameters) == ["source", "terms", "timeout_seconds"]


@pytest.mark.parametrize(("mode", "adapter"), _provider_modes())
def test_provider_returns_valid_coverage(
    mode: str,
    adapter: SourceAdapter,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fixture(monkeypatch, _fixture_dir(repo_root, mode), "response")

    coverage = adapter.discover(_source_for_mode(mode), TERMS, 5)

    assert isinstance(coverage, core.Coverage)
    assert coverage.status in {"complete", "partial", "failed"}
    assert coverage.source
    assert coverage.source_url
    assert coverage.discovery_mode == mode
    assert coverage.cadence_group
    if adapter.emits_candidates:
        assert coverage.search_terms_tried == TERMS
    else:
        assert coverage.search_terms_tried in ([], TERMS)
    assert coverage.result_pages_scanned
    assert coverage.matched_jobs == len(coverage.candidates)
    assert isinstance(coverage.direct_job_pages_opened, int)
    assert isinstance(coverage.enumerated_jobs, int)


@pytest.mark.parametrize(("mode", "adapter"), _provider_modes())
def test_provider_candidates_have_required_fields(
    mode: str,
    adapter: SourceAdapter,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fixture(monkeypatch, _fixture_dir(repo_root, mode), "response")

    coverage = adapter.discover(_source_for_mode(mode), TERMS, 5)

    if not adapter.emits_candidates:
        assert coverage.candidates == []
        return
    assert coverage.candidates, f"{mode} response fixture should produce at least one candidate"
    for candidate in coverage.candidates:
        assert candidate.employer
        assert candidate.title
        assert candidate.url
        assert candidate.source_url
        assert candidate.notes
        parsed = urlparse(candidate.url)
        assert parsed.scheme in {"http", "https"}
        assert parsed.netloc


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


@pytest.mark.parametrize(("mode", "adapter"), _provider_modes())
def test_provider_empty_results_do_not_crash(
    mode: str,
    adapter: SourceAdapter,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fixture(monkeypatch, _fixture_dir(repo_root, mode), "empty")

    coverage = adapter.discover(_source_for_mode(mode), TERMS, 5)

    assert coverage.status in {"complete", "partial", "failed"}
    assert coverage.matched_jobs == 0
    assert coverage.candidates == []


@pytest.mark.parametrize(("mode", "adapter"), _provider_modes())
def test_provider_duplicate_candidate_urls_are_merged(
    mode: str,
    adapter: SourceAdapter,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _install_fixture(monkeypatch, _fixture_dir(repo_root, mode), "duplicates")

    coverage = adapter.discover(_source_for_mode(mode), TERMS, 5)
    if not adapter.emits_candidates:
        assert coverage.candidates == []
        assert coverage.matched_jobs == 0
        return
    urls = [candidate.url for candidate in coverage.candidates]

    assert urls
    assert len(urls) == len(set(urls))
    assert coverage.matched_jobs == len(urls)


@pytest.mark.parametrize(("mode", "_adapter"), _provider_modes())
def test_provider_network_error_returns_failed_coverage(mode: str, _adapter: SourceAdapter, monkeypatch: pytest.MonkeyPatch):
    if mode in BROWSER_MODES:
        _install_missing_browser(monkeypatch)

    def raise_url_error(url: str, timeout_seconds: int, headers: dict[str, str] | None = None):
        del url, timeout_seconds, headers
        raise URLError("fixture network failure")

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
    [(mode, adapter) for mode, adapter in _provider_modes() if mode in BROWSER_MODES],
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
