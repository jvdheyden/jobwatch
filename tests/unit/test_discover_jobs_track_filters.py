from __future__ import annotations

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


def test_filter_coverage_for_alignment_tech_prunes_generic_broad_source_roles():
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

    filtered = discover_jobs.filter_coverage_for_track("alignment_tech", coverage)

    assert filtered.matched_jobs == 2
    assert [candidate.employer for candidate in filtered.candidates] == ["Enveritas", "SPADE Agriculture"]
    assert filtered.limitations == [
        "Alignment Tech filter removed 1 candidate(s) from this broad source without explicit sector evidence."
    ]


def test_filter_coverage_for_alignment_tech_keeps_priority_employer_for_spirit_board():
    coverage = make_coverage(
        "Spirit Tech Collective Jobs",
        [
            discover_jobs.Candidate(
                employer="Gaia Inc.",
                title="Senior Software Engineer - Javascript Stack - Full Stack",
                url="https://example.com/gaia",
                source_url="https://jobs.spirit-tech-collective.com/jobs",
                location="Louisville, CO, USA",
                notes="Enumerated through Getro collection search API; Work mode: on_site; Seniority: senior",
            ),
            discover_jobs.Candidate(
                employer="Thatgamecompany",
                title="Senior Software Engineer (Fullstack)",
                url="https://example.com/thatgamecompany",
                source_url="https://jobs.spirit-tech-collective.com/jobs",
                location="United States; Remote",
                notes="Enumerated through Getro collection search API; Work mode: remote; Topics: Media; Industries: Entertainment",
            ),
        ],
    )

    filtered = discover_jobs.filter_coverage_for_track("alignment_tech", coverage)

    assert filtered.matched_jobs == 1
    assert [candidate.employer for candidate in filtered.candidates] == ["Gaia Inc."]


def test_filter_coverage_for_track_is_noop_for_other_tracks():
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

    filtered = discover_jobs.filter_coverage_for_track("core_crypto", coverage)

    assert filtered.matched_jobs == 1
    assert [candidate.employer for candidate in filtered.candidates] == ["Plain"]
    assert filtered.limitations == []
