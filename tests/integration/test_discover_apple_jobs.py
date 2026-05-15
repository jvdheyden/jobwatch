from __future__ import annotations

import discover_jobs
from discover import http as discover_http


def test_discover_apple_jobs_extracts_search_result_details(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Apple",
        url="https://jobs.apple.com/en-us/search?search=cryptography",
        discovery_mode="apple_jobs",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    html = """
    <a href="https://www.apple.com/careers/us">Careers at Apple</a>
    <section>
      <h2>
        <a href="/en-us/details/200662871-0836/software-engineer-secure-enclave-core-os?team=SFTWR">Software Engineer - Secure Enclave, Core OS</a>
      </h2>
      <p>Software and Services May 12, 2026</p>
      <p>Location Cupertino</p>
      <p>Actions</p>
      <a href="/en-us/details/200662871-0836/software-engineer-secure-enclave-core-os?team=SFTWR">See full role description</a>
      <p>Share Software Engineer - Secure Enclave, Core OS 200662871-0836</p>
      <p>Role Number: 200662871-0836</p>
      <p>Weekly Hours: 40 Hours</p>
      <p>Design Secure Enclave services and production cryptography for platform security.</p>
      <p>Submit Resume</p>
    </section>
    <section>
      <h2>
        <a href="/en-us/details/200663495-0321/corporate-security-partner?team=CORSV">Corporate Security Partner</a>
      </h2>
      <p>Corporate Functions May 12, 2026</p>
      <p>Location Cupertino</p>
      <p>Share Corporate Security Partner 200663495-0321</p>
      <p>Role Number: 200663495-0321</p>
      <p>Weekly Hours: 40 Hours</p>
      <p>Coordinate physical security partner programs.</p>
      <p>Submit Resume</p>
    </section>
    """

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_apple_jobs(source, ["cryptography", "security", "secure hardware"], 5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Software Engineer - Secure Enclave, Core OS"
    assert candidate.url == "https://jobs.apple.com/en-us/details/200662871-0836/software-engineer-secure-enclave-core-os?team=SFTWR"
    assert candidate.location == "Cupertino"
    assert candidate.matched_terms == ["cryptography", "secure hardware", "security"]
    assert "Responsibilities: Design Secure Enclave services" in candidate.notes
    assert "Careers at Apple" not in {item.title for item in coverage.candidates}
