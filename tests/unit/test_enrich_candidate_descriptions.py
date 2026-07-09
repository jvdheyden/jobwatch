from __future__ import annotations

from discover import http
from discover.core import Candidate, Coverage, enrich_candidate_descriptions


def _coverage(candidates: list[Candidate]) -> Coverage:
    return Coverage(
        source="Example",
        source_url="https://example.com/jobs",
        discovery_mode="html",
        cadence_group="every_run",
        last_checked=None,
        due_today=True,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=["security"],
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(candidates),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def test_enrich_fills_description_from_fetched_html(monkeypatch):
    pages: dict[str, str] = {
        "https://example.com/jobs/security-engineer": (
            "<html><body><h1>Security Engineer</h1>"
            "<p>Build cryptography systems.</p></body></html>"
        ),
    }

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        return pages[url]

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    candidate = Candidate(
        employer="Example",
        title="Security Engineer",
        url="https://example.com/jobs/security-engineer",
        source_url="https://example.com/jobs",
    )
    coverage = _coverage([candidate])

    enrich_candidate_descriptions(coverage, timeout_seconds=5)

    assert "Security Engineer" in candidate.description
    assert "Build cryptography systems." in candidate.description
    assert candidate.description_truncated is False
    assert coverage.limitations == []


def test_enrich_skips_candidates_that_already_have_description(monkeypatch):
    def boom(url: str, timeout_seconds: int) -> str:
        raise AssertionError("fetch_text should not be called")

    monkeypatch.setattr(http, "fetch_text", boom)

    candidate = Candidate(
        employer="Example",
        title="Security Engineer",
        url="https://example.com/jobs/security-engineer",
        source_url="https://example.com/jobs",
        description="Already fetched JD body.",
    )
    coverage = _coverage([candidate])

    enrich_candidate_descriptions(coverage, timeout_seconds=5)

    assert candidate.description == "Already fetched JD body."


def test_enrich_records_failures_in_limitations(monkeypatch):
    def fail(url: str, timeout_seconds: int) -> str:
        raise RuntimeError("network down")

    monkeypatch.setattr(http, "fetch_text", fail)

    candidate = Candidate(
        employer="Example",
        title="Security Engineer",
        url="https://example.com/jobs/security-engineer",
        source_url="https://example.com/jobs",
    )
    coverage = _coverage([candidate])

    enrich_candidate_descriptions(coverage, timeout_seconds=5)

    assert candidate.description == ""
    assert coverage.limitations == ["JD fetch failed for 1 candidate(s)"]


def test_enrich_caps_fetches_at_hard_ceiling(monkeypatch):
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        fetched_urls.append(url)
        return f"<p>JD for {url}</p>"

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    candidates = [
        Candidate(
            employer="Example",
            title=f"Role {idx}",
            url=f"https://example.com/jobs/{idx}",
            source_url="https://example.com/jobs",
        )
        for idx in range(5)
    ]
    coverage = _coverage(candidates)

    enrich_candidate_descriptions(coverage, timeout_seconds=5, max_fetches=2)

    assert len(fetched_urls) == 2
    assert candidates[0].description != ""
    assert candidates[1].description != ""
    assert candidates[2].description == ""
    assert candidates[3].description == ""
    assert candidates[4].description == ""
    assert any("budget exhausted" in lim for lim in coverage.limitations)


def test_enrich_stops_when_wall_clock_budget_exhausted(monkeypatch):
    fetched_urls: list[str] = []
    fake_now = [0.0]

    def fake_monotonic() -> float:
        return fake_now[0]

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        fetched_urls.append(url)
        # Each fetch advances the wall clock by 0.4 seconds.
        fake_now[0] += 0.4
        return f"<p>JD for {url}</p>"

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)
    monkeypatch.setattr("time.monotonic", fake_monotonic)

    candidates = [
        Candidate(
            employer="Example",
            title=f"Role {idx}",
            url=f"https://example.com/jobs/{idx}",
            source_url="https://example.com/jobs",
        )
        for idx in range(20)
    ]
    coverage = _coverage(candidates)

    enrich_candidate_descriptions(coverage, timeout_seconds=5, max_seconds=1.0)

    # Budget = 1.0s, each fetch advances 0.4s. The loop checks the clock BEFORE
    # the fetch, so fetches happen at t=0.0, 0.4, 0.8; the next check at t=1.2
    # exits the loop. Expect exactly 3 fetches before exhaustion.
    assert len(fetched_urls) == 3
    assert any("budget exhausted" in lim for lim in coverage.limitations)
    unfilled = sum(1 for c in candidates if not c.description)
    assert unfilled == len(candidates) - 3


def test_enrich_truncates_to_char_budget_and_sets_flag(monkeypatch):
    long_paragraph = "lorem " * 2000

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        return f"<p>{long_paragraph}</p>"

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    candidate = Candidate(
        employer="Example",
        title="Long JD",
        url="https://example.com/jobs/long",
        source_url="https://example.com/jobs",
    )
    coverage = _coverage([candidate])

    enrich_candidate_descriptions(coverage, timeout_seconds=5, char_budget=200)

    assert candidate.description != ""
    assert len(candidate.description) <= 200
    assert candidate.description_truncated is True


def test_enrich_skips_candidates_with_no_url(monkeypatch):
    def boom(url: str, timeout_seconds: int) -> str:
        raise AssertionError("fetch_text should not be called")

    monkeypatch.setattr(http, "fetch_text", boom)

    candidate = Candidate(
        employer="Example",
        title="No URL",
        url="",
        source_url="https://example.com/jobs",
    )
    coverage = _coverage([candidate])

    enrich_candidate_descriptions(coverage, timeout_seconds=5)

    assert candidate.description == ""
    assert coverage.limitations == []


def test_enrich_counts_failed_fetches_toward_hard_ceiling(monkeypatch):
    attempted_urls: list[str] = []

    def failing_fetch_text(url: str, timeout_seconds: int) -> str:
        attempted_urls.append(url)
        raise RuntimeError("dead link")

    monkeypatch.setattr(http, "fetch_text", failing_fetch_text)

    candidates = [
        Candidate(
            employer="Example",
            title=f"Role {idx}",
            url=f"https://example.com/jobs/{idx}",
            source_url="https://example.com/jobs",
        )
        for idx in range(5)
    ]
    coverage = _coverage(candidates)

    enrich_candidate_descriptions(coverage, timeout_seconds=5, max_fetches=2)

    # Failures consume the ceiling too; a source full of dead links cannot
    # spin through unbounded fetch attempts.
    assert len(attempted_urls) == 2
    assert any("JD fetch failed for 2 candidate(s)" in lim for lim in coverage.limitations)
    assert any("budget exhausted" in lim for lim in coverage.limitations)


def test_runner_enriches_descriptions_only_after_track_filtering(tmp_path, monkeypatch):
    import json

    from discover import runner
    from discover.core import SourceConfig

    source = SourceConfig(
        source="Example",
        url="https://example.com/jobs",
        discovery_mode="html",
        last_checked=None,
        cadence_group="every_run",
    )
    kept = Candidate(
        employer="Example",
        title="Security Engineer",
        url="https://example.com/jobs/keep",
        source_url="https://example.com/jobs",
        matched_terms=["security"],
    )
    dropped = Candidate(
        employer="Example",
        title="Security Engineer, Filtered Team",
        url="https://example.com/jobs/drop",
        source_url="https://example.com/jobs",
        matched_terms=["security"],
    )

    def fake_load(track):
        return [source], ["security"], {}

    def fake_discover(src, terms, timeout_seconds):
        return _coverage([dropped, kept])

    def fake_filter(track, coverage):
        coverage.candidates = [c for c in coverage.candidates if c.url.endswith("/keep")]
        coverage.matched_jobs = len(coverage.candidates)
        return coverage

    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        fetched_urls.append(url)
        return "<p>JD body for the kept security engineer role.</p>"

    monkeypatch.setattr(http, "fetch_text", fake_fetch_text)

    output = tmp_path / "artifact.json"
    rc = runner.main(
        ["--track", "demo", "--today", "2026-07-06", "--output", str(output)],
        load_track_config_func=fake_load,
        discover_source_func=fake_discover,
        filter_coverage_func=fake_filter,
    )

    assert rc == 0
    # The filtered-out candidate's URL is never fetched: enrichment runs after
    # track filtering, not inside discover_source.
    assert fetched_urls == ["https://example.com/jobs/keep"]
    payload = json.loads(output.read_text())
    candidates = payload["sources"][0]["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["url"] == "https://example.com/jobs/keep"
    assert "JD body for the kept security engineer role." in candidates[0]["description"]
