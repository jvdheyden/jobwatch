from __future__ import annotations

import discover_jobs
from discover import http as discover_http


def test_discover_iacr_jobs_extracts_real_postings_from_fixture(read_text_fixture, monkeypatch):
    html = read_text_fixture("iacr/iacr_jobs_sample.html")
    source = discover_jobs.SourceConfig(
        source="IACR Jobs",
        url="https://www.iacr.org/jobs/",
        discovery_mode="iacr_jobs",
        last_checked=None,
        cadence_group="every_run",
    )

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_iacr_jobs(source, ["cryptography", "zero-knowledge"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.employer == "LayerZero Labs"
    assert candidate.title == "Cryptographer"
    assert candidate.url == "https://www.iacr.org/jobs/item/4189"
    assert candidate.alternate_url == "https://layerzero.network/zero"
    assert candidate.location == "Vancouver, BC Canada"
    assert candidate.remote == "remote"
