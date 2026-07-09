from __future__ import annotations

import json
from pathlib import Path

import discover_jobs


def make_coverage(source_name: str, candidates: list[discover_jobs.Candidate]) -> discover_jobs.Coverage:
    return discover_jobs.Coverage(
        source=source_name,
        source_url="https://example.com/jobs",
        discovery_mode="html",
        cadence_group="every_month",
        last_checked=None,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=["software engineer"],
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(candidates),
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def write_match_rules(tracks_root: Path, track: str, rules: list[dict]) -> None:
    track_dir = tracks_root / track
    track_dir.mkdir(parents=True, exist_ok=True)
    (track_dir / "match_rules.json").write_text(
        json.dumps({"schema_version": 1, "track": track, "rules": rules}) + "\n"
    )


SECTOR_RULE = {
    "id": "broad_sources_require_sector_evidence",
    "source_names": ["Hacker News Who Is Hiring", "Curated Collective Jobs"],
    "keep_if_any_text_term": ["sustainability", "farm", "gaia"],
    "limitation": (
        "Track filter removed {removed} candidate(s) from this broad source "
        "without explicit sector evidence."
    ),
}


def test_filter_coverage_prunes_broad_source_roles_without_sector_evidence(tmp_path):
    write_match_rules(tmp_path, "demo", [SECTOR_RULE])
    coverage = make_coverage(
        "Hacker News Who Is Hiring",
        [
            discover_jobs.Candidate(
                employer="Enveritas",
                title="Backend Software Engineer",
                url="https://example.com/enveritas",
                source_url="https://news.ycombinator.com/user?id=whoishiring",
                location="Remote (Global)",
                notes="Excerpt: Enveritas is a nonprofit working on sustainability issues facing smallholder coffee farmers.",
            ),
            discover_jobs.Candidate(
                employer="SPADE Agriculture",
                title="Full Stack Engineer",
                url="https://example.com/spade",
                source_url="https://news.ycombinator.com/user?id=whoishiring",
                location="Remote (US Timezones)",
                notes="Excerpt: We build farm data and animal health systems for the dairy industry.",
            ),
            discover_jobs.Candidate(
                employer="Plain",
                title="Software Engineer",
                url="https://example.com/plain",
                source_url="https://news.ycombinator.com/user?id=whoishiring",
                location="Remote",
                notes="Excerpt: General software infrastructure for business operations.",
            ),
        ],
    )

    filtered = discover_jobs.filter_coverage_for_track("demo", coverage, tracks_root=tmp_path)

    assert filtered.matched_jobs == 2
    assert [candidate.employer for candidate in filtered.candidates] == ["Enveritas", "SPADE Agriculture"]
    assert filtered.limitations == [
        "Track filter removed 1 candidate(s) from this broad source without explicit sector evidence."
    ]


def test_filter_coverage_keeps_priority_employer_named_in_rule_terms(tmp_path):
    write_match_rules(tmp_path, "demo", [SECTOR_RULE])
    coverage = make_coverage(
        "Curated Collective Jobs",
        [
            discover_jobs.Candidate(
                employer="Gaia Inc.",
                title="Senior Software Engineer - Javascript Stack - Full Stack",
                url="https://example.com/gaia",
                source_url="https://jobs.curated-collective.com/jobs",
                location="Louisville, CO, USA",
                notes="Enumerated through Getro collection search API; Work mode: on_site; Seniority: senior",
            ),
            discover_jobs.Candidate(
                employer="Thatgamecompany",
                title="Senior Software Engineer (Fullstack)",
                url="https://example.com/thatgamecompany",
                source_url="https://jobs.curated-collective.com/jobs",
                location="United States; Remote",
                notes="Enumerated through Getro collection search API; Work mode: remote; Topics: Media; Industries: Entertainment",
            ),
        ],
    )

    filtered = discover_jobs.filter_coverage_for_track("demo", coverage, tracks_root=tmp_path)

    assert filtered.matched_jobs == 1
    assert [candidate.employer for candidate in filtered.candidates] == ["Gaia Inc."]


def test_filter_coverage_ignores_sources_not_named_by_any_rule(tmp_path):
    write_match_rules(tmp_path, "demo", [SECTOR_RULE])
    coverage = make_coverage(
        "Example Careers",
        [
            discover_jobs.Candidate(
                employer="Plain",
                title="Software Engineer",
                url="https://example.com/plain",
                source_url="https://example.com/jobs",
                location="Remote",
                notes="Excerpt: General software infrastructure for business operations.",
            )
        ],
    )

    filtered = discover_jobs.filter_coverage_for_track("demo", coverage, tracks_root=tmp_path)

    assert filtered.matched_jobs == 1
    assert [candidate.employer for candidate in filtered.candidates] == ["Plain"]
    assert filtered.limitations == []


def test_filter_coverage_is_noop_for_tracks_without_match_rules(tmp_path):
    coverage = make_coverage(
        "Hacker News Who Is Hiring",
        [
            discover_jobs.Candidate(
                employer="Plain",
                title="Software Engineer",
                url="https://example.com/plain",
                source_url="https://news.ycombinator.com/user?id=whoishiring",
                location="Remote",
                notes="Excerpt: General software infrastructure for business operations.",
            )
        ],
    )

    filtered = discover_jobs.filter_coverage_for_track("demo", coverage, tracks_root=tmp_path)

    assert filtered.matched_jobs == 1
    assert [candidate.employer for candidate in filtered.candidates] == ["Plain"]
    assert filtered.limitations == []
