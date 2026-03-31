from __future__ import annotations

import json
from html import escape

import discover_jobs


def test_discover_yc_jobs_board_extracts_filtered_candidates(monkeypatch):
    payload = {
        "component": "WaasJobListingsPage",
        "props": {
            "jobPostings": [
                {
                    "title": "Cryptography Engineer",
                    "url": "/companies/cipher/jobs/abc123-cryptography-engineer",
                    "applyUrl": "https://account.ycombinator.com/authenticate?continue=/application?signup_job_id=1",
                    "location": "Remote",
                    "type": "Full-time",
                    "roleSpecificType": "Security",
                    "prettyRole": "Engineering",
                    "salaryRange": "$150K - $220K",
                    "equityRange": "0.1% - 0.5%",
                    "minExperience": "3+ years",
                    "visa": "Will sponsor",
                    "companyName": "Cipher",
                    "companyBatchName": "S24",
                    "companyOneLiner": "Building applied cryptography for wallet security",
                    "createdAt": "5 days",
                    "lastActive": "1 day",
                },
                {
                    "title": "Product Designer",
                    "url": "/companies/plain/jobs/plain-product-designer",
                    "location": "New York, NY, US",
                    "type": "Full-time",
                    "companyName": "Plain",
                    "companyBatchName": "W26",
                    "companyOneLiner": "Team communication software",
                },
            ]
        },
    }
    html = f'<div data-page="{escape(json.dumps(payload))}"></div>'
    source = discover_jobs.SourceConfig(
        source="YC Startups",
        url="https://www.ycombinator.com/jobs/role/software-engineer",
        discovery_mode="yc_jobs_board",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_yc_jobs_board(source, ["cryptography", "security", "privacy"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.employer == "Cipher"
    assert candidate.title == "Cryptography Engineer"
    assert candidate.location == "Remote"
    assert candidate.remote == "remote"
    assert candidate.url == "https://www.ycombinator.com/companies/cipher/jobs/abc123-cryptography-engineer"
    assert candidate.alternate_url.startswith("https://account.ycombinator.com/authenticate")


def test_discover_hackernews_jobs_extracts_submission_rows_across_pages(monkeypatch):
    page_one = """
    <html><body><table>
    <tr class="athing submission" id="1">
      <td class="title"><span class="titleline"><a href="https://example.com/jobs/security-engineer">Cipher (YC S24) is hiring a Security Engineer</a></span></td>
    </tr>
    <tr><td colspan="2"></td><td class="subtext"><span class="age" title="2026-03-31T07:00:00"><a href="item?id=1">1 hour ago</a></span></td></tr>
    <tr class="athing submission" id="2">
      <td class="title"><span class="titleline"><a href="https://example.com/jobs/generalist">Plain (YC W26) is hiring</a></span></td>
    </tr>
    <tr><td colspan="2"></td><td class="subtext"><span class="age" title="2026-03-30T07:00:00"><a href="item?id=2">1 day ago</a></span></td></tr>
    <a href='jobs?next=2&amp;n=31' class='morelink' rel='next'>More</a>
    </table></body></html>
    """
    page_two = """
    <html><body><table>
    <tr class="athing submission" id="3">
      <td class="title"><span class="titleline"><a href="https://example.com/jobs/cryptography-engineer">Orbit (YC W25) is hiring a Cryptography Engineer</a></span></td>
    </tr>
    <tr><td colspan="2"></td><td class="subtext"><span class="age" title="2026-03-29T07:00:00"><a href="item?id=3">2 days ago</a></span></td></tr>
    </table></body></html>
    """
    source = discover_jobs.SourceConfig(
        source="Hackernews Jobs",
        url="https://news.ycombinator.com/jobs",
        discovery_mode="hackernews_jobs",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if "next=2" in url:
            return page_two
        return page_one

    monkeypatch.setattr(discover_jobs, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_hackernews_jobs(source, ["cryptography", "security", "privacy"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 2
    assert coverage.enumerated_jobs == 3
    assert coverage.matched_jobs == 2
    employers = {candidate.employer for candidate in coverage.candidates}
    titles = {candidate.title for candidate in coverage.candidates}
    assert employers == {"Cipher", "Orbit"}
    assert titles == {
        "Cipher (YC S24) is hiring a Security Engineer",
        "Orbit (YC W25) is hiring a Cryptography Engineer",
    }
