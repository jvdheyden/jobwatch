from __future__ import annotations

import json

import pytest

import discover_jobs
from discover import http
from discover.constants import JD_DESCRIPTION_CHAR_BUDGET
from discover.core import Coverage, enrich_candidate_descriptions


class FakeScriptLocator:
    def __init__(self, scripts: list[str]) -> None:
        self._scripts = scripts

    def all_inner_texts(self) -> list[str]:
        return self._scripts


class FakeGooglePage:
    def __init__(self, payload: list[object]) -> None:
        self._scripts = [
            "AF_initDataCallback({"
            "key: 'ds:1', "
            f"data:{json.dumps(payload)}, "
            "sideChannel: {}"
            "});"
        ]

    def locator(self, selector: str) -> FakeScriptLocator:
        assert selector == "script"
        return FakeScriptLocator(self._scripts)


def _coverage(source, candidates):
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=None,
        due_today=True,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=["cryptography"],
        result_pages_scanned="cryptography=1p/1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(candidates),
        matched_jobs=len(candidates),
        candidates=candidates,
    )


@pytest.mark.parametrize("long_summary", [False, True])
def test_extract_google_jobs_preserves_description_and_concise_notes(monkeypatch, long_summary):
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    responsibilities = (
        "Build Rust verification tools using formal verification and Lean. "
        "Lead applied cryptography architecture for privacy-preserving products. "
        "Coordinate design reviews for secure distributed systems. "
        "Own implementation roadmaps for trusted systems. "
        "Own implementation roadmaps for trusted systems. "
        "Own implementation roadmaps for trusted systems. "
        "UNTRUNCATED RESPONSIBILITY TAIL"
    )
    summary = "Protect users by building privacy-preserving security systems."
    if long_summary:
        summary += " Generic company introduction." * 200
    requirements = (
        "<h3>Minimum qualifications:</h3>"
        "<p>Experience with security engineering and applied cryptography.</p>"
        "<h3>Preferred qualifications:</h3><p>Two years of formal verification.</p>"
    )
    payload = [
        [
            [
                "123456",
                "Software Engineer, Proof and Verification Engineer",
                "https://careers.google.com/jobs/results/123456-security-engineer/",
                ["Responsibilities", f"<p>{responsibilities}</p>"],
                ["Qualifications", requirements],
                None,
                None,
                "Google",
                None,
                [["Munich, Germany"], ["Zurich, Switzerland"]],
                ["Summary", f"<p>{summary}</p>"],
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                ["Working location", "Hybrid role in Munich or Zurich."],
            ]
        ]
    ]

    result = discover_jobs.extract_google_jobs(
        FakeGooglePage(payload),
        source,
        term="cryptography",
        terms=["cryptography", "privacy", "security"],
        page_num=1,
    )

    assert result.visible_results == 1
    assert result.raw_ids == ["123456"]
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.title == "Software Engineer, Proof and Verification Engineer"
    assert candidate.matched_terms == ["cryptography", "privacy", "security"]
    assert "Google browser search q='cryptography'" in candidate.notes
    assert "Summary: Protect users by building privacy-preserving security systems." in candidate.notes
    assert "Tasks: Build Rust verification tools" in candidate.notes
    assert "Qualifications: Minimum qualifications:" in candidate.notes
    assert "UNTRUNCATED RESPONSIBILITY TAIL" not in candidate.notes
    assert candidate.description.startswith(f"Responsibilities: {responsibilities}")
    assert "Minimum qualifications: Experience with security engineering and applied cryptography." in candidate.description
    assert "Preferred qualifications: Two years of formal verification." in candidate.description
    assert "Working location: Hybrid role in Munich or Zurich." in candidate.description
    assert "About the job: Protect users" in candidate.description
    assert "<p>" not in candidate.description
    assert len(candidate.description) <= JD_DESCRIPTION_CHAR_BUDGET
    assert candidate.description_truncated is long_summary

    fetched_urls = []

    def unexpected_fetch(url, timeout_seconds):
        fetched_urls.append(url)
        return "<script>Irrelevant page configuration</script>"

    monkeypatch.setattr(http, "fetch_text", unexpected_fetch)
    original_description = candidate.description
    coverage = _coverage(source, result.candidates)
    enrich_candidate_descriptions(coverage, timeout_seconds=5)

    assert fetched_urls == []
    assert candidate.description == original_description
    assert candidate.description_truncated is long_summary
    assert coverage.limitations == []


def test_google_candidate_without_job_sections_uses_description_fallback(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Google",
        url="https://www.google.com/about/careers/applications/jobs/results",
        discovery_mode="browser",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    job = [None] * 19
    job[0] = "123456"
    job[1] = "Cryptography Engineer"
    job[7] = "Google"
    job[9] = [["Munich, Germany"]]
    job[18] = ["Working location", "Munich, Germany"]
    result = discover_jobs.extract_google_jobs(
        FakeGooglePage([[job]]), source, term="cryptography", terms=["cryptography"], page_num=1
    )
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.description == ""
    fetched_urls = []

    def fetch_detail(url, timeout_seconds):
        fetched_urls.append(url)
        return "<script>Page configuration</script><p>Build cryptography libraries.</p>"

    monkeypatch.setattr(http, "fetch_text", fetch_detail)
    enrich_candidate_descriptions(_coverage(source, result.candidates), timeout_seconds=5)

    assert fetched_urls == [candidate.url]
    assert candidate.description == "Build cryptography libraries."
    assert candidate.description_truncated is False
