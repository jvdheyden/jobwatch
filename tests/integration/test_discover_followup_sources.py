from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import discover_jobs
from discover import http as discover_http
from discover.sources import eightfold as eightfold_provider
from discover.sources import getro as getro_provider


def test_discover_greenhouse_api_filters_and_builds_urls(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Greenhouse",
        url="https://job-boards.greenhouse.io/example",
        discovery_mode="greenhouse_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert url == "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
        assert timeout_seconds == 5
        return {
            "jobs": [
                {
                    "title": "Security Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1",
                    "location": {"name": "Remote"},
                    "content": "Applied cryptography and security engineering.",
                },
                {
                    "title": "Marketing Manager",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/2",
                    "location": {"name": "Remote"},
                    "content": "Campaign planning.",
                },
            ]
        }

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_greenhouse_api(source, ["security", "cryptography"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Security Engineer"
    assert candidate.url == "https://job-boards.greenhouse.io/example/jobs/1"
    assert candidate.location == "Remote"
    assert candidate.matched_terms == ["security", "cryptography"]


def test_discover_workday_api_posts_search_terms_and_builds_detail_urls(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Workday",
        url="https://example.wd1.myworkdayjobs.com/Example",
        discovery_mode="workday_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert url == "https://example.wd1.myworkdayjobs.com/wday/cxs/example/Example/jobs"
        assert payload == {"limit": 20, "offset": 0, "searchText": "security"}
        assert headers == {"Referer": source.url}
        return {
            "total": 1,
            "jobPostings": [
                {
                    "title": "Security Engineer",
                    "externalPath": "/job/123",
                    "locationsText": "Remote",
                    "postedOn": "Posted Today",
                    "bulletFields": ["Security"],
                }
            ],
        }

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = discover_jobs.discover_workday_api(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://example.wd1.myworkdayjobs.com/Example/job/123"
    assert candidate.location == "Remote"
    assert candidate.matched_terms == ["security"]


def test_discover_ashby_api_uses_non_user_graphql_payload(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Ashby",
        url="https://jobs.ashbyhq.com/example",
        discovery_mode="ashby_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert url == "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
        assert payload["variables"] == {"organizationHostedJobsPageName": "example"}
        assert headers == {"Referer": source.url}
        return {
            "data": {
                "jobBoard": {
                    "teams": [{"id": "eng", "externalName": "Engineering"}],
                    "jobPostings": [
                        {
                            "id": "job-1",
                            "title": "Security Engineer",
                            "teamId": "eng",
                            "locationName": "Remote",
                            "secondaryLocations": [],
                            "workplaceType": "Remote",
                            "employmentType": "Full-time",
                            "compensationTierSummary": "",
                        }
                    ],
                }
            }
        }

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = discover_jobs.discover_ashby_api(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://jobs.ashbyhq.com/example/job-1"
    assert candidate.location == "Remote"
    assert candidate.remote == "Remote"


def test_eightfold_domain_for_source_supports_existing_infineon_mode():
    source = discover_jobs.SourceConfig(
        source="Infineon",
        url="https://jobs.infineon.com/careers",
        discovery_mode="infineon_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    assert discover_jobs.eightfold_domain_for_source(source) == "infineon.com"


def test_discover_eightfold_api_infers_microsoft_domain_and_filters_results(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Microsoft",
        url="https://apply.careers.microsoft.com/careers",
        discovery_mode="eightfold_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        query = parse_qs(urlparse(url).query)
        assert query["domain"] == ["microsoft.com"]
        assert query["query"] == ["cryptography"]
        assert query["start"] == ["0"]
        return {
            "data": {
                "count": 2,
                "positions": [
                    {
                        "id": 1970393556857301,
                        "displayJobId": "200034351",
                        "name": "Cryptography Engineer",
                        "locations": ["Ireland, Dublin, Dublin"],
                        "standardizedLocations": ["Dublin, D, IE"],
                        "department": "Software Engineering",
                        "workLocationOption": "onsite",
                        "positionUrl": "/careers/job/1970393556857301",
                    },
                    {
                        "id": 1970393556856300,
                        "displayJobId": "200034056",
                        "name": "Product Marketing Manager - Confidentiality & Encryption",
                        "locations": ["United States, Washington, Redmond"],
                        "department": "Product Marketing",
                        "workLocationOption": "onsite",
                        "positionUrl": "/careers/job/1970393556856300",
                    },
                ],
            }
        }

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_eightfold_api(source, ["cryptography"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Cryptography Engineer"
    assert candidate.url == "https://apply.careers.microsoft.com/careers/job/1970393556857301"
    assert candidate.location == "Ireland, Dublin, Dublin"
    assert candidate.matched_terms == ["cryptography"]


def test_discover_eightfold_api_reports_page_cap(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Microsoft",
        url="https://apply.careers.microsoft.com/careers",
        discovery_mode="eightfold_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        start = int(parse_qs(urlparse(url).query)["start"][0])
        return {
            "data": {
                "count": 99,
                "positions": [
                    {
                        "id": start + index + 1,
                        "displayJobId": f"job-{start + index + 1}",
                        "name": f"Cryptography Engineer {start + index + 1}",
                        "locations": ["Remote"],
                        "department": "Software Engineering",
                        "positionUrl": f"/careers/job/{start + index + 1}",
                    }
                    for index in range(10)
                ],
            }
        }

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(eightfold_provider, "EIGHTFOLD_MAX_PAGES", 2)

    coverage = discover_jobs.discover_eightfold_api(source, ["cryptography"], timeout_seconds=5)

    assert coverage.status == "partial"
    assert coverage.listing_pages_scanned == 2
    assert coverage.enumerated_jobs == 20
    assert coverage.matched_jobs == 20
    assert coverage.limitations == ["Eightfold PCSx search for 'cryptography' hit the page cap (2)"]


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

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

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

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)
    monkeypatch.setattr(discover_http, "post_json", fake_post_json)
    monkeypatch.setattr(getro_provider, "GETRO_RESULTS_PAGE_SIZE", 2)
    monkeypatch.setattr(getro_provider, "MAX_GETRO_PAGES", 5)

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
    notes_by_employer = {candidate.employer: candidate.notes for candidate in coverage.candidates}
    assert "Topics: Learning" in notes_by_employer["YouVersion"]
    assert "Industries: Software" in notes_by_employer["YouVersion"]
    assert "Topics: Wellness" in notes_by_employer["Headspace"]


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

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: html)

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


def test_discover_ibm_api_filters_ibm_research_generic_noise_and_keeps_canary_detail(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="IBM Research",
        url="https://www.ibm.com/careers/search",
        discovery_mode="ibm_api",
        last_checked=None,
        cadence_group="every_month",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert url == discover_jobs.IBM_SEARCH_API_URL
        assert headers == {"Referer": "https://www.ibm.com/"}
        return {
            "hits": {
                "total": {"value": 4},
                "hits": [
                    {
                        "_id": "107245",
                        "_source": {
                            "title": "Postdoctoral IT Research Scientist - IBM Research South Africa",
                            "url": "https://careers.ibm.com/careers/JobDetail?jobId=107245",
                            "description": (
                                "Join us for a unique 24-month paid internship at the IBM Research Africa lab "
                                "in Johannesburg, South Africa."
                            ),
                            "field_keyword_19": "JOHANNESBURG, ZA",
                            "field_keyword_17": "Hybrid",
                            "field_keyword_08": "Cloud",
                            "field_keyword_18": "Internship",
                        },
                    },
                    {
                        "_id": "88976",
                        "_source": {
                            "title": "Quantum Hardware Research Scientist",
                            "url": "https://careers.ibm.com/careers/JobDetail?jobId=88976",
                            "description": "Quantum hardware role for scalable fault tolerant systems.",
                            "field_keyword_19": "Yorktown Heights, US",
                            "field_keyword_17": "",
                            "field_keyword_08": "Research",
                            "field_keyword_18": "Professional",
                        },
                    },
                    {
                        "_id": "60324",
                        "_source": {
                            "title": "Research Scientist—AI & Algorithmic Innovations Intern: 2026",
                            "url": "https://careers.ibm.com/careers/JobDetail?jobId=60324",
                            "description": "Research internship in AI systems.",
                            "field_keyword_19": "Warrington, GB",
                            "field_keyword_17": "Hybrid",
                            "field_keyword_08": "Research",
                            "field_keyword_18": "Internship",
                        },
                    },
                    {
                        "_id": "85519",
                        "_source": {
                            "title": "Backend Engineer (Cryptography Team) - Hashicorp Vault",
                            "url": "https://careers.ibm.com/careers/JobDetail?jobId=85519",
                            "description": "Backend engineer on the cryptography team.",
                            "field_keyword_19": "Multiple Cities",
                            "field_keyword_17": "Hybrid",
                            "field_keyword_08": "Software Engineering",
                            "field_keyword_18": "Professional",
                        },
                    },
                ],
            }
        }

    monkeypatch.setattr(discover_jobs, "post_json", fake_post_json)
    monkeypatch.setattr(discover_jobs, "IBM_RESULTS_PAGE_SIZE", 25)

    coverage = discover_jobs.discover_ibm_api(
        source,
        [
            "multi-party computation",
            "MPC",
            "garbled circuits",
            "isogenies",
            "isogeny-based cryptography",
            "real-world cryptography",
            "real-world protocols",
            "privacy-enhancing applications",
            "privacy-preserving applications",
            "research scientist",
            "postdoctoral",
            "postdoc",
            "cryptography",
        ],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 4
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Postdoctoral IT Research Scientist - IBM Research South Africa"
    assert candidate.matched_terms == ["postdoc", "postdoctoral", "research scientist"]
    assert "Summary: Join us for a unique 24-month paid internship" in candidate.notes
