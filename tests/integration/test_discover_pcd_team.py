from __future__ import annotations

import discover_jobs


def test_discover_pcd_team_extracts_job_description_candidate(monkeypatch):
    html = """
    <html><body>
      <h1>Software Engineer JD · <a href="https://airtable.com/shr0T7U6ZtQgH83Gq">Apply Here</a></h1>
      <p>We are building programmable cryptography, privacy-preserving applications, and real-world protocols.</p>
    </body></html>
    """
    source = discover_jobs.SourceConfig(
        source="0xPARC / PCD Team",
        url="https://pcd.team/jd",
        discovery_mode="pcd_team",
        last_checked=None,
        cadence_group="every_run",
    )

    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_pcd_team(
        source,
        ["cryptography", "privacy-preserving", "protocol"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.employer == "0xPARC / PCD Team"
    assert candidate.title == "Software Engineer"
    assert candidate.url == "https://pcd.team/jd"
    assert candidate.alternate_url == "https://airtable.com/shr0T7U6ZtQgH83Gq"
    assert candidate.matched_terms == ["cryptography", "privacy-preserving", "protocol"]
    assert candidate.notes == "PCD Team job description page"
