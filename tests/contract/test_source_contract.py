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
        "iacr_jobs": "https://www.iacr.org/jobs/",
        "lever_json": "https://jobs.lever.co/example",
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
    if html_path.exists():
        html = html_path.read_text()
        monkeypatch.setattr(http, "fetch_text", lambda url, timeout_seconds: html)
        return
    if json_path.exists():
        payload = json.loads(json_path.read_text())
        monkeypatch.setattr(http, "fetch_json", lambda url, timeout_seconds: payload)
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
    assert coverage.search_terms_tried == TERMS
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

    coverage = core.discover_source(_source_for_mode(mode), TERMS, 5)

    assert coverage.status == "failed"
    assert coverage.matched_jobs == 0
    assert coverage.candidates == []
    assert coverage.limitations
