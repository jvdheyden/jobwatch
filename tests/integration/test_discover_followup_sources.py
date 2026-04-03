from __future__ import annotations

import json

import discover_jobs


def test_discover_workable_api_filters_and_builds_job_urls(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Waking Up",
        url="https://apply.workable.com/waking-up-1/",
        discovery_mode="workable_api",
        last_checked=None,
        cadence_group="every_month",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert url == "https://apply.workable.com/api/v3/accounts/waking-up-1/jobs"
        assert payload == {"query": ""}
        assert headers == {"Referer": source.url, "X-Requested-With": "XMLHttpRequest"}
        return {
            "total": 2,
            "results": [
                {
                    "shortcode": "SEC123",
                    "title": "Security Engineer",
                    "location": "Remote",
                    "remote": True,
                    "department": "Engineering",
                    "workplace": "remote",
                    "type": "Full time",
                    "state": "published",
                },
                {
                    "shortcode": "DES456",
                    "title": "Product Designer",
                    "location": "Remote",
                    "remote": True,
                    "department": "Design",
                    "workplace": "remote",
                    "type": "Full time",
                    "state": "published",
                },
            ],
        }

    monkeypatch.setattr(discover_jobs, "post_json", fake_post_json)

    coverage = discover_jobs.discover_workable_api(
        source,
        ["security engineer", "software engineer", "programmer"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Security Engineer"
    assert candidate.url == "https://apply.workable.com/waking-up-1/j/SEC123"
    assert candidate.location == "Remote"
    assert candidate.remote == "remote"
    assert candidate.matched_terms == ["security engineer"]


def test_discover_getro_api_paginates_collection_results(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Spirit Tech Collective Jobs",
        url="https://jobs.spirit-tech-collective.com/jobs",
        discovery_mode="getro_api",
        last_checked=None,
        cadence_group="every_month",
    )

    html = """
    <html><body>
    <script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"network":{"id":"32465"}}}}
    </script>
    </body></html>
    """

    responses = {
        0: {
            "results": {
                "count": 3,
                "jobs": [
                    {
                        "id": 1,
                        "title": "Senior Software Engineer",
                        "url": "https://example.com/jobs/1",
                        "workMode": "remote",
                        "locations": ["Remote"],
                        "skills": ["Python", "Systems Design"],
                        "seniority": "senior",
                        "organization": {"name": "YouVersion", "topics": ["Learning"], "industryTags": ["Software"]},
                    },
                    {
                        "id": 2,
                        "title": "Security Engineer",
                        "url": "https://example.com/jobs/2",
                        "workMode": "on_site",
                        "locations": ["Chicago, IL, USA"],
                        "skills": ["Security", "Threat Modeling"],
                        "seniority": "mid_senior",
                        "organization": {"name": "Headspace", "topics": ["Wellness"], "industryTags": ["Software"]},
                    },
                ],
            }
        },
        1: {
            "results": {
                "count": 3,
                "jobs": [
                    {
                        "id": 3,
                        "title": "Brand Marketing Manager",
                        "url": "https://example.com/jobs/3",
                        "workMode": "remote",
                        "locations": ["Remote"],
                        "skills": ["Campaigns"],
                        "seniority": "mid_senior",
                        "organization": {"name": "Thatgamecompany", "topics": ["Media"], "industryTags": ["Entertainment"]},
                    }
                ],
            }
        },
    }

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert url == "https://api.getro.com/api/v2/collections/32465/search/jobs"
        assert headers == {"Referer": source.url}
        assert isinstance(payload, dict)
        return responses[payload["page"]]

    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: html)
    monkeypatch.setattr(discover_jobs, "post_json", fake_post_json)
    monkeypatch.setattr(discover_jobs, "GETRO_RESULTS_PAGE_SIZE", 2)
    monkeypatch.setattr(discover_jobs, "MAX_GETRO_PAGES", 5)

    coverage = discover_jobs.discover_getro_api(
        source,
        ["software engineer", "security engineer", "programmer"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.listing_pages_scanned == 2
    assert coverage.enumerated_jobs == 3
    assert coverage.matched_jobs == 2
    employers = {candidate.employer for candidate in coverage.candidates}
    titles = {candidate.title for candidate in coverage.candidates}
    assert employers == {"YouVersion", "Headspace"}
    assert titles == {"Senior Software Engineer", "Security Engineer"}


def test_discover_personio_page_parses_embedded_jobs_payload(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Albert Schweitzer Stiftung",
        url="https://albert-schweitzer-stiftung.jobs.personio.de/",
        discovery_mode="personio_page",
        last_checked=None,
        cadence_group="every_month",
    )

    decoded_chunk = (
        '[["$","$L13"],{"jobs":[{"title":"Software Engineer","location":"Berlin, Germany",'
        '"url":"https://albert.example/jobs/software-engineer","department":"Engineering"}],'
        '"subdomain":"albert-schweitzer-stiftung"}]'
    )
    html = f"<html><body><script>self.__next_f.push([1,{json.dumps(decoded_chunk)}])</script></body></html>"

    monkeypatch.setattr(discover_jobs, "fetch_text", lambda url, timeout_seconds: html)

    coverage = discover_jobs.discover_personio_page(
        source,
        ["software engineer", "security engineer"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Software Engineer"
    assert candidate.url == "https://albert.example/jobs/software-engineer"
    assert candidate.location == "Berlin, Germany"
    assert candidate.matched_terms == ["software engineer"]
