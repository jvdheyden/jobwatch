from __future__ import annotations

import inspect
import json
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse

import pytest

from discover import core, http
from discover.registry import SourceAdapter, load_registry


TERMS = ["cryptography", "zero-knowledge", "security"]


def _fixture_dir(repo_root: Path, mode: str) -> Path:
    return repo_root / "tests" / "fixtures" / "sources" / mode


def _source_for_mode(mode: str) -> core.SourceConfig:
    urls = {
        "ashby_api": "https://jobs.ashbyhq.com/example",
        "ashby_html": "https://jobs.ashbyhq.com/example",
        "auswaertiges_amt_json": "https://www.auswaertiges-amt.de/de/karriere/stellenanzeigen",
        "bnd_career_search": "https://www.bnd.bund.de/SiteGlobals/Forms/Suche/erweiterte_Karrieresuche_Formular.html?nn=415896#sprg415980",
        "bosch_autocomplete": "https://www.bosch.de/karriere/jobs",
        "bundeswehr_jobsuche": "https://bewerbung.bundeswehr-karriere.de/erece/portal/index.html#joblist/none/TwoColumnsMidExpanded",
        "cybernetica_teamdash": "https://cyber.ee/careers/",
        "eightfold_api": "https://apply.careers.microsoft.com/careers",
        "enbw_phenom": "https://careers.enbw.com/en_US/careers",
        "getro_api": "https://jobs.example-getro.com/jobs",
        "greenhouse_api": "https://job-boards.greenhouse.io/example",
        "hackernews_jobs": "https://news.ycombinator.com/jobs",
        "hackernews_whoishiring_api": "https://news.ycombinator.com/user?id=whoishiring",
        "html": "https://jobs.example.com/",
        "iacr_jobs": "https://www.iacr.org/jobs/",
        "ibm_api": "https://www.ibm.com/careers/search",
        "icims_html": "https://example.icims.com/jobs",
        "infineon_api": "https://jobs.infineon.com/careers",
        "leastauthority_careers": "https://leastauthority.com/careers/",
        "lever_json": "https://jobs.lever.co/example",
        "neclab_jobs": "https://jobs.neclab.eu/",
        "partisia_site": "https://partisiablockchain.com/",
        "pcd_team": "https://pcd.team/jd",
        "personio_page": "https://example.jobs.personio.de/",
        "qedit_inline": "https://qed-it.com/careers",
        "qusecure_careers": "https://www.qusecure.com/careers/",
        "recruitee_inline": "https://career.quantum-systems.com/",
        "rheinmetall_html": "https://www.rheinmetall.com/de/karriere/aktuelle-stellenangebote",
        "service_bund_links": "https://www.bsi.bund.de/DE/Karriere/Stellenangebote/stellenangebot_node.html",
        "service_bund_search": (
            "https://www.service.bund.de/Content/DE/Stellen/Suche/Formular.html"
            "?view=processForm&nn=4641514"
        ),
        "secunet_jobboard": "https://www.secunet.com/karriere/stellenangebote",
        "thales_html": "https://careers.thalesgroup.com/global/en/search-results",
        "workable_api": "https://apply.workable.com/example/",
        "workday_api": "https://example.wd1.myworkdayjobs.com/Example",
        "verfassungsschutz_rss": "https://www.verfassungsschutz.de/jobs",
        "yc_jobs_board": "https://www.ycombinator.com/jobs/role/software-engineer",
    }
    return core.SourceConfig(
        source=mode.replace("_", " ").title(),
        url=urls.get(mode, "https://jobs.example.com/example"),
        discovery_mode=mode,
        last_checked=None,
        cadence_group="every_run",
    )


def _provider_modes() -> list[tuple[str, SourceAdapter]]:
    return sorted(load_registry().items())


def _install_fixture(monkeypatch: pytest.MonkeyPatch, fixture_dir: Path, stem: str) -> None:
    html_path = fixture_dir / f"{stem}.html"
    json_path = fixture_dir / f"{stem}.json"
    installed = False
    if html_path.exists():
        html = html_path.read_text()
        monkeypatch.setattr(http, "fetch_text", lambda url, timeout_seconds: html)
        installed = True
    if json_path.exists():
        payload = json.loads(json_path.read_text())
        monkeypatch.setattr(
            http,
            "fetch_json",
            lambda url, timeout_seconds: payload[url] if isinstance(payload, dict) and url in payload else payload,
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
    def raise_url_error(url: str, timeout_seconds: int):
        del url, timeout_seconds
        raise URLError("fixture network failure")

    monkeypatch.setattr(http, "fetch_text", raise_url_error)
    monkeypatch.setattr(http, "fetch_json", raise_url_error)
    monkeypatch.setattr(http, "post_json", lambda url, data, timeout_seconds, headers=None: raise_url_error(url, timeout_seconds))

    coverage = core.discover_source(_source_for_mode(mode), TERMS, 5)

    assert coverage.status in {"failed", "partial"}
    assert coverage.matched_jobs == 0
    assert coverage.candidates == []
    assert coverage.limitations
