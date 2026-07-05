from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import discover_jobs
from discover import http as discover_http
from discover.sources import alphatheta as alphatheta_provider
from discover.sources import bamboohr as bamboohr_provider
from discover.sources import dover as dover_provider
from discover.sources import eightfold as eightfold_provider
from discover.sources import getro as getro_provider
from discover.sources import harman as harman_provider
from discover.sources import ibm as ibm_provider
from discover.sources import jobvite as jobvite_provider
from discover.sources import krisp as krisp_provider
from discover.sources import lifeatspotify as lifeatspotify_provider
from discover.sources import successfactors as successfactors_provider
from discover.sources import teamtailor as teamtailor_provider
from discover.sources import ultipro as ultipro_provider


def test_discover_greenhouse_api_filters_and_builds_urls(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Greenhouse",
        url="https://job-boards.greenhouse.io/example",
        discovery_mode="greenhouse_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    matching_content = """
    <h2>About the Role</h2>
    <p>Build applied cryptography systems for privacy products.</p>
    <h2>Requirements</h2>
    <ul>
      <li>Security engineering experience with production cryptography.</li>
    </ul>
    <h2>Benefits</h2>
    <p>This complete benefits catalogue should not be copied into candidate notes.</p>
    """

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert url == "https://boards-api.greenhouse.io/v1/boards/example/jobs?content=true"
        assert timeout_seconds == 5
        return {
            "jobs": [
                {
                    "title": "Security Engineer",
                    "absolute_url": "https://job-boards.greenhouse.io/example/jobs/1",
                    "location": {"name": "Remote"},
                    "content": matching_content,
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
    assert candidate.notes.startswith("Enumerated through Greenhouse board API; ")
    assert "Tasks: Build applied cryptography systems for privacy products." in candidate.notes
    assert "Qualifications: Security engineering experience with production cryptography." in candidate.notes
    assert "complete benefits catalogue" not in candidate.notes


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

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert url == "https://example.wd1.myworkdayjobs.com/wday/cxs/example/Example/job/123"
        return {
            "jobPostingInfo": {
                "jobDescription": (
                    "<h2>Responsibilities</h2>"
                    "<ul><li>Design and ship security-critical services.</li></ul>"
                    "<h2>Qualifications</h2>"
                    "<ul><li>5+ years in production security engineering.</li></ul>"
                    "<h2>Pay Range</h2>"
                    "<p>$180,000 - $220,000 USD annually.</p>"
                )
            }
        }

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)
    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = discover_jobs.discover_workday_api(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://example.wd1.myworkdayjobs.com/Example/job/123"
    assert candidate.location == "Remote"
    assert candidate.matched_terms == ["security"]
    assert "Tasks: Design and ship security-critical services." in candidate.notes
    assert "Qualifications: 5+ years in production security engineering." in candidate.notes
    assert "Compensation: $180,000 - $220,000 USD annually." in candidate.notes


def test_discover_workday_api_keeps_candidate_when_detail_fetch_fails(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Workday",
        url="https://example.wd1.myworkdayjobs.com/Example",
        discovery_mode="workday_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
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

    def failing_fetch_json(url: str, timeout_seconds: int):
        raise RuntimeError("detail endpoint unavailable")

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)
    monkeypatch.setattr(discover_http, "fetch_json", failing_fetch_json)

    coverage = discover_jobs.discover_workday_api(source, ["security"], timeout_seconds=5)

    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 0
    assert coverage.status == "partial"
    assert any("Detail fetch failed" in limitation for limitation in coverage.limitations)


def test_discover_ashby_api_uses_non_user_graphql_payload(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Ashby",
        url="https://jobs.ashbyhq.com/example",
        discovery_mode="ashby_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert headers == {"Referer": source.url}
        if payload["operationName"] == "ApiJobBoardWithTeams":
            assert url == "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
            assert payload["variables"] == {"organizationHostedJobsPageName": "example"}
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
        assert payload["operationName"] == "ApiJobPosting"
        assert url == "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
        assert payload["variables"] == {
            "organizationHostedJobsPageName": "example",
            "jobPostingId": "job-1",
        }
        return {"data": {"jobPosting": {"descriptionHtml": "", "compensationTierSummary": ""}}}

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = discover_jobs.discover_ashby_api(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://jobs.ashbyhq.com/example/job-1"
    assert candidate.location == "Remote"
    assert candidate.remote == "Remote"


def test_discover_ashby_api_decodes_percent_encoded_board_slug(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Tools for Humanity / World",
        url="https://jobs.ashbyhq.com/Tools%20for%20Humanity",
        discovery_mode="ashby_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert headers == {"Referer": source.url}
        if payload["operationName"] == "ApiJobBoardWithTeams":
            assert url == "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
            assert payload["variables"] == {"organizationHostedJobsPageName": "Tools for Humanity"}
            return {
                "data": {
                    "jobBoard": {
                        "teams": [{"id": "eng", "externalName": "Engineering"}],
                        "jobPostings": [
                            {
                                "id": "privacy-engineer",
                                "title": "Privacy Engineer",
                                "teamId": "eng",
                                "locationName": "San Francisco, CA",
                                "secondaryLocations": [{"locationName": "Munich, Germany"}],
                                "workplaceType": "Hybrid",
                                "employmentType": "Full-time",
                                "compensationTierSummary": "",
                            }
                        ],
                    }
                }
            }
        assert payload["operationName"] == "ApiJobPosting"
        assert payload["variables"] == {
            "organizationHostedJobsPageName": "Tools for Humanity",
            "jobPostingId": "privacy-engineer",
        }
        return {"data": {"jobPosting": {"descriptionHtml": "", "compensationTierSummary": ""}}}

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = discover_jobs.discover_ashby_api(source, ["privacy"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://jobs.ashbyhq.com/Tools%20for%20Humanity/privacy-engineer"
    assert candidate.location == "San Francisco, CA; Munich, Germany"


def test_eightfold_domain_for_source_supports_existing_infineon_mode():
    source = discover_jobs.SourceConfig(
        source="Infineon",
        url="https://jobs.infineon.com/careers",
        discovery_mode="infineon_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    assert discover_jobs.eightfold_domain_for_source(source) == "infineon.com"


def test_discover_infineon_api_enriches_kept_candidates_from_detail_pages(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Infineon",
        url="https://jobs.infineon.com/careers",
        discovery_mode="infineon_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        query = parse_qs(urlparse(url).query)
        assert query["domain"] == ["infineon.com"]
        if query["query"] != ["security"]:
            return {"data": {"count": 0, "positions": []}}
        return {
            "data": {
                "count": 1,
                "positions": [
                    {
                        "id": 563808969188654,
                        "displayJobId": "HRC1234567",
                        "name": "Principal Security Architect",
                        "locations": ["Munich (Germany)"],
                        "department": "Information Technology",
                        "workLocationOption": "Hybrid",
                        "positionUrl": "/careers/job/563808969188654",
                    }
                ],
            }
        }

    def fake_fetch_text(url: str, timeout_seconds: int):
        assert url == "https://jobs.infineon.com/careers/job/563808969188654"
        assert timeout_seconds == 5
        return """
        <html><body>
          <h2>In your new role you will</h2>
          <ul>
            <li>Design identity security architecture for zero trust authentication.</li>
          </ul>
          <h2>You are best equipped for this task if you have</h2>
          <p>Experience with cryptography, secure hardware, and protocol design.</p>
          <h2>Contact</h2>
          <p>This contact copy should not be included.</p>
        </body></html>
        """

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_infineon_api(source, ["security", "cryptography"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.direct_job_pages_opened == 1
    candidate = coverage.candidates[0]
    assert candidate.matched_terms == ["cryptography", "security"]
    assert "Enumerated through Eightfold PCSx search for 'security'" in candidate.notes
    assert "Tasks: Design identity security architecture for zero trust authentication." in candidate.notes
    assert "Qualifications: Experience with cryptography, secure hardware, and protocol design." in candidate.notes
    assert "contact copy" not in candidate.notes


def test_extract_eightfold_detail_sections_prefers_jobposting_json_ld():
    html = """
    <html><head>
      <script type="application/ld+json">
        {
          "@context": "http://schema.org",
          "@type": "JobPosting",
          "description": "<p>Lead security architecture for zero trust authentication.</p>"
        }
      </script>
      <script>
        {"themeOptions": {"compensationColor": "#000000"}}
      </script>
    </head><body></body></html>
    """

    sections = eightfold_provider.extract_eightfold_detail_sections(html)

    assert sections["tasks"] == "Lead security architecture for zero trust authentication."
    assert sections["qualifications"] == ""
    assert sections["compensation"] == ""


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
        assert url == ibm_provider.IBM_SEARCH_API_URL
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

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)
    monkeypatch.setattr(ibm_provider, "IBM_RESULTS_PAGE_SIZE", 25)

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


def test_discover_jobvite_enriches_candidates_with_detail_sections(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Jobvite",
        url="https://jobs.jobvite.com/example/jobs",
        discovery_mode="jobvite_html",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    listing_html = (
        '<a href="/example/job/abc123" class="jv-job-list-link">'
        '<div class="jv-job-list-name">Senior Security Engineer</div>'
        '<div class="jv-job-id">REQ-42</div>'
        '<div class="jv-job-list-location">Remote, USA</div>'
        '</a>'
        '<a href="/example/job/def456" class="jv-job-list-link">'
        '<div class="jv-job-list-name">Marketing Coordinator</div>'
        '<div class="jv-job-id">REQ-99</div>'
        '<div class="jv-job-list-location">Remote, USA</div>'
        '</a>'
    )
    detail_html = (
        "<h2>Responsibilities</h2>"
        "<ul><li>Own the music discovery product roadmap.</li></ul>"
        "<h2>Qualifications</h2>"
        "<ul><li>7+ years of product management experience.</li></ul>"
        "<h2>Pay Range</h2>"
        "<p>$190,000 - $230,000 USD annually.</p>"
    )

    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        fetched_urls.append(url)
        if url == source.url:
            return listing_html
        return detail_html

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = jobvite_provider.discover_jobvite_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 1
    assert coverage.status == "complete"
    candidate = coverage.candidates[0]
    assert candidate.url == "https://jobs.jobvite.com/example/job/abc123"
    assert candidate.location == "Remote, USA"
    assert "REQ-42" in candidate.notes
    assert "Tasks: Own the music discovery product roadmap." in candidate.notes
    assert "Qualifications: 7+ years of product management experience." in candidate.notes
    assert "Compensation: $190,000 - $230,000 USD annually." in candidate.notes
    assert fetched_urls == [source.url, candidate.url]


def test_discover_jobvite_marks_partial_when_detail_fetch_fails(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Jobvite",
        url="https://jobs.jobvite.com/example/jobs",
        discovery_mode="jobvite_html",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    listing_html = (
        '<a href="/example/job/abc123" class="jv-job-list-link">'
        '<div class="jv-job-list-name">Senior Security Engineer</div>'
        '<div class="jv-job-id">REQ-42</div>'
        '<div class="jv-job-list-location">Remote, USA</div>'
        '</a>'
    )

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if url == source.url:
            return listing_html
        raise RuntimeError("detail endpoint unavailable")

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = jobvite_provider.discover_jobvite_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 0
    assert coverage.status == "partial"
    assert any("Detail fetch failed" in limitation for limitation in coverage.limitations)


def test_discover_krisp_jobs_extracts_role_detail_sections_from_detail_pages(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Krisp",
        url="https://krisp.ai/careers/",
        discovery_mode="krisp_html",
        last_checked=None,
        cadence_group="every_month",
    )

    careers_html = """
    <html><body>
      <a href="https://krisp.ai/jobs/senior-security-engineer-cx/">Senior Security Engineer, CX Armenia Hybrid</a>
      <a href="https://krisp.ai/jobs/senior-security-engineer-growth/">Senior Security Engineer, Growth US Remote</a>
      <a href="https://krisp.ai/security">Security</a>
      <a href="https://krisp.ai/careers/">Back to Careers</a>
    </body></html>
    """
    detail_pages = {
        "https://krisp.ai/jobs/senior-security-engineer-cx": """
        <html><head><title>Senior Security Engineer, CX | Krisp</title></head><body>
          <h1>Senior Security Engineer, CX</h1>
          <p>Armenia</p>
          <p>Hybrid</p>
          <p>About Krisp’s CX portfolio.</p>
          <h2>What you'll do</h2>
          <ul>
            <li>Define product strategy for Krisp’s CX portfolio.</li>
            <li>Collaborate with engineering, design, and data teams.</li>
          </ul>
          <h2>What we are looking for</h2>
          <ul>
            <li>5+ years of product management experience in B2B SaaS.</li>
            <li>Strong analytical skills and data-driven decision-making.</li>
          </ul>
          <h2>How to apply</h2>
          <p>Submit through this form.</p>
          <h2>Benefits</h2>
          <p>These benefits should not appear in tasks or qualifications notes.</p>
        </body></html>
        """,
        "https://krisp.ai/jobs/senior-security-engineer-growth": """
        <html><head><title>Senior Security Engineer, Growth | Krisp</title></head><body>
          <h1>Senior Security Engineer, Growth</h1>
          <p>US</p>
          <p>Remote</p>
          <h2>Responsibilities</h2>
          <ul><li>Own the growth funnel for Krisp’s self-serve plans.</li></ul>
          <h2>Requirements</h2>
          <ul><li>5+ years of growth product management experience.</li></ul>
        </body></html>
        """,
    }

    def fake_fetch_text(url, timeout_seconds):
        if url == source.url:
            return careers_html
        if url in detail_pages:
            return detail_pages[url]
        raise AssertionError(f"unexpected fetch_text({url})")

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = krisp_provider.discover_krisp_jobs(
        source,
        ["security", "security engineer"],
        timeout_seconds=5,
    )

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 2
    assert coverage.direct_job_pages_opened == 2

    by_url = {c.url: c for c in coverage.candidates}
    pm = by_url["https://krisp.ai/jobs/senior-security-engineer-cx"]
    assert pm.title == "Senior Security Engineer, CX"
    assert pm.location == "Armenia"
    assert pm.remote == "Hybrid"
    assert pm.matched_terms == ["security", "security engineer"]
    assert "Tasks: Define product strategy" in pm.notes
    assert "Qualifications: 5+ years of product management experience" in pm.notes
    assert "Benefits" not in pm.notes
    assert "should not appear" not in pm.notes

    growth = by_url["https://krisp.ai/jobs/senior-security-engineer-growth"]
    assert growth.title == "Senior Security Engineer, Growth"
    assert growth.location == "US"
    assert growth.remote == "Remote"
    assert growth.matched_terms == ["security", "security engineer"]
    assert "Tasks: Own the growth funnel for Krisp’s self-serve plans." in growth.notes
    assert "Qualifications: 5+ years of growth product management experience." in growth.notes

    assert "https://krisp.ai/security" not in by_url


def test_discover_dover_jobs_filters_unpublished_and_builds_detail_urls(monkeypatch):
    careers_id = "123e4567-e89b-12d3-a456-426614174000"
    source = discover_jobs.SourceConfig(
        source="Example Dover",
        url=f"https://app.dover.com/acme/careers/{careers_id}",
        discovery_mode="dover_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert url == f"https://app.dover.com/api/v1/careers-page/{careers_id}/jobs"
        return {
            "results": [
                {
                    "id": "job-1",
                    "title": "Senior Security Engineer",
                    "is_published": True,
                    "locations": [{"name": "Remote"}],
                },
                {
                    "id": "job-2",
                    "title": "Security Engineer",
                    "is_published": False,
                    "locations": [{"name": "Remote"}],
                },
                {
                    "id": "job-3",
                    "title": "Security Engineer (Sample)",
                    "is_published": True,
                    "is_sample": True,
                },
                {
                    "id": "job-4",
                    "title": "Marketing Manager",
                    "is_published": True,
                    "locations": [{"name": "Remote"}],
                },
            ]
        }

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = dover_provider.discover_dover_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 4
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Senior Security Engineer"
    assert candidate.url == f"https://app.dover.com/dover/careers/{careers_id}/job-1"
    assert candidate.location == "Remote"
    assert candidate.notes == "Enumerated through Dover careers-page API"


def test_discover_dover_jobs_fails_without_careers_id():
    source = discover_jobs.SourceConfig(
        source="Example Dover",
        url="https://app.dover.com/acme/jobs",
        discovery_mode="dover_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    coverage = dover_provider.discover_dover_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "failed"
    assert any("Dover careers id" in limitation for limitation in coverage.limitations)


def test_discover_teamtailor_jobs_reads_feed_and_locations(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Teamtailor",
        url="https://www.rolandcareers.com/",
        discovery_mode="teamtailor_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        assert url == "https://www.rolandcareers.com/jobs.json"
        return {
            "items": [
                {
                    "url": "https://www.rolandcareers.com/jobs/123-senior-security-engineer",
                    "title": "Senior Security Engineer",
                    "content_html": "<p>Own the device security roadmap.</p>",
                    "_jobposting": {
                        "jobLocation": {
                            "address": {
                                "addressLocality": "Hamamatsu",
                                "addressCountry": "JP",
                            }
                        }
                    },
                },
                {
                    "url": "https://www.rolandcareers.com/jobs/456-sales-lead",
                    "title": "Sales Lead",
                    "content_html": "<p>Grow retail partnerships.</p>",
                },
            ]
        }

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = teamtailor_provider.discover_teamtailor_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://www.rolandcareers.com/jobs/123-senior-security-engineer"
    assert candidate.location == "Hamamatsu, JP"
    assert "Description: Own the device security roadmap." in candidate.notes


def test_discover_ultipro_jobs_pages_search_results_and_builds_detail_urls(monkeypatch):
    tenant = "STA1000SWHM"
    board = "d439f0a5-6c1e-4f81-b0c8-85f0f0bb0e10"
    source = discover_jobs.SourceConfig(
        source="Example UltiPro",
        url=f"https://recruiting2.ultipro.com/{tenant}/JobBoard/{board}/?q=&o=postedDateDesc",
        discovery_mode="ultipro_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    posted_payloads: list[object] = []

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        assert url == f"https://recruiting2.ultipro.com/{tenant}/JobBoard/{board}/JobBoardView/LoadSearchResults"
        posted_payloads.append(payload)
        return {
            "totalCount": 2,
            "opportunities": [
                {
                    "Id": "op-1",
                    "Title": "Senior Security Engineer",
                    "RequisitionNumber": "R-100",
                    "JobCategoryName": "Engineering",
                    "FullTime": True,
                    "PostedDate": "2026-06-30",
                    "BriefDescription": "Lead embedded security work.",
                    "Locations": [
                        {
                            "LocalizedName": "Headquarters",
                            "Address": {
                                "City": "Eden Prairie",
                                "State": {"Code": "MN"},
                                "Country": {"Code": "US"},
                            },
                        }
                    ],
                },
                {
                    "Id": "op-2",
                    "Title": "Regional Sales Representative",
                    "BriefDescription": "Own the retail channel.",
                },
            ],
        }

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = ultipro_provider.discover_ultipro_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert len(posted_payloads) == 1
    assert posted_payloads[0]["opportunitySearch"]["Skip"] == 0
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == (
        f"https://recruiting2.ultipro.com/{tenant}/JobBoard/{board}/OpportunityDetail?opportunityId=op-1"
    )
    assert candidate.location == "Headquarters (Eden Prairie, MN, US)"
    assert "Requisition: R-100" in candidate.notes
    assert "Category: Engineering" in candidate.notes
    assert "Employment type: Full-time" in candidate.notes
    assert "Description: Lead embedded security work." in candidate.notes


def test_discover_bamboohr_jobs_enriches_from_detail_endpoint(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example BambooHR",
        url="https://moises.bamboohr.com/careers",
        discovery_mode="bamboohr_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    description_html = (
        "<h2>Responsibilities</h2>"
        "<ul><li>Harden the audio pipeline security.</li></ul>"
        "<h2>Requirements</h2>"
        "<ul><li>5+ years of security engineering experience.</li></ul>"
    )

    def fake_fetch_json(url: str, timeout_seconds: int):
        if url == "https://moises.bamboohr.com/careers/list":
            return {
                "result": [
                    {
                        "id": 42,
                        "jobOpeningName": "Senior Security Engineer",
                        "departmentLabel": "Engineering",
                        "employmentStatusLabel": "Full-Time",
                        "atsLocation": {"city": "Remote", "country": "Brazil"},
                    },
                    {
                        "id": 43,
                        "jobOpeningName": "Sales Lead",
                        "departmentLabel": "Sales",
                    },
                ]
            }
        if url == "https://moises.bamboohr.com/careers/42/detail":
            return {"result": {"jobOpening": {"description": description_html}}}
        if url == "https://moises.bamboohr.com/careers/43/detail":
            return {"result": {"jobOpening": {"description": "<p>Sell more.</p>"}}}
        raise AssertionError(f"unexpected fetch_json({url})")

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = bamboohr_provider.discover_bamboohr_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.direct_job_pages_opened == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://moises.bamboohr.com/careers/42"
    assert candidate.location == "Remote, Brazil"
    assert "Department: Engineering" in candidate.notes
    assert "Employment: Full-Time" in candidate.notes
    assert "Tasks: Harden the audio pipeline security." in candidate.notes
    assert "Qualifications: 5+ years of security engineering experience." in candidate.notes


def test_discover_lifeatspotify_jobs_enriches_matched_candidates_only(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Spotify",
        url="https://www.lifeatspotify.com/jobs",
        discovery_mode="lifeatspotify_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    fetched_urls: list[str] = []

    def fake_fetch_json(url: str, timeout_seconds: int):
        fetched_urls.append(url)
        if url == "https://api.lifeatspotify.com/wp-json/animal/v1/job/search":
            return {
                "result": [
                    {
                        "id": "sec-eng",
                        "text": "Senior Security Engineer",
                        "main_category": {"name": "Engineering"},
                        "locations": [{"location": "Stockholm"}],
                    },
                    {
                        "id": "sales-lead",
                        "text": "Sales Lead",
                        "main_category": {"name": "Sales"},
                        "locations": [{"location": "New York"}],
                    },
                ]
            }
        if url == "https://api.lifeatspotify.com/wp-json/animal/v1/job/single/sec-eng":
            return {
                "data": {
                    "content": {
                        "descriptionHtml": "<p>Protect the creator platform.</p>",
                        "lists": [
                            {
                                "text": "What you'll do",
                                "content": "<ul><li>Ship security features.</li></ul>",
                            }
                        ],
                    }
                }
            }
        raise AssertionError(f"unexpected fetch_json({url})")

    monkeypatch.setattr(discover_http, "fetch_json", fake_fetch_json)

    coverage = lifeatspotify_provider.discover_lifeatspotify_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 1
    candidate = coverage.candidates[0]
    assert candidate.url == "https://www.lifeatspotify.com/jobs/sec-eng"
    assert candidate.location == "Stockholm"
    assert "Description: Protect the creator platform." in candidate.notes
    assert "What you'll do: Ship security features." in candidate.notes
    assert "sales-lead" not in " ".join(fetched_urls)


def test_discover_demant_rss_searches_terms_and_splits_title_location(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Demant",
        url="https://www.demant.com/careers",
        discovery_mode="demant_rss",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>Senior Security Engineer (Copenhagen, DK)</title>
        <link>https://careers.demant.com/job/copenhagen/senior-security-engineer/1</link>
        <description>&lt;p&gt;Embedded security for hearing aids.&lt;/p&gt;</description>
      </item>
      <item>
        <title>Sales Consultant (Berlin, DE)</title>
        <link>https://careers.demant.com/job/berlin/sales-consultant/2</link>
        <description>&lt;p&gt;Retail sales.&lt;/p&gt;</description>
      </item>
    </channel></rss>
    """
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        fetched_urls.append(url)
        return rss_xml

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = successfactors_provider.discover_demant_successfactors(source, ["security"], timeout_seconds=5)

    assert len(fetched_urls) == 1
    query = parse_qs(urlparse(fetched_urls[0]).query)
    assert query["locale"] == ["en_GB"]
    assert query["keywords"] == ["security"]
    assert coverage.status == "complete"
    assert coverage.result_pages_scanned == "rss_search=1"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Senior Security Engineer"
    assert candidate.location == "Copenhagen, DK"
    assert candidate.notes == "Enumerated through Demant SAP SuccessFactors RSS search"


def test_discover_sennheiser_rss_reads_full_feed(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Sennheiser",
        url="https://jobs.sennheiser.com/",
        discovery_mode="sennheiser_rss",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0"><channel>
      <item>
        <title>Security Engineer, Audio Products (Wedemark, DE)</title>
        <link>https://jobs.sennheiser.com/job/wedemark/security-engineer/9</link>
        <description>&lt;p&gt;Secure connected audio devices.&lt;/p&gt;</description>
      </item>
    </channel></rss>
    """
    fetched_urls: list[str] = []

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        fetched_urls.append(url)
        return rss_xml

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = successfactors_provider.discover_sennheiser_jobs(source, ["security"], timeout_seconds=5)

    assert len(fetched_urls) == 1
    assert fetched_urls[0].startswith("https://jobs.sennheiser.com/services/rss/job/")
    assert parse_qs(urlparse(fetched_urls[0]).query)["locale"] == ["en_US"]
    assert coverage.status == "complete"
    assert coverage.result_pages_scanned == "rss_feed=1"
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Security Engineer, Audio Products"
    assert candidate.location == "Wedemark, DE"
    assert candidate.notes == "Enumerated through Sennheiser SAP/Jobs2Web RSS feed"


def test_discover_harman_jobsearch_keeps_only_jobdetail_links(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Harman",
        url="https://jobsearch.harman.com/en_US/careers/SearchJobs",
        discovery_mode="harman_html",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    listing_html = """
    <html><body>
      <a href="https://jobsearch.harman.com/en_US/careers/JobDetail/Senior-Security-Engineer/12345">Senior Security Engineer</a>
      <a href="https://jobsearch.harman.com/en_US/careers/SearchJobs?page=2">Next page</a>
      <a href="https://www.harman.com/about">About Harman</a>
    </body></html>
    """

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: listing_html)

    coverage = harman_provider.discover_harman_jobsearch_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 1
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Senior Security Engineer"
    assert candidate.url == "https://jobsearch.harman.com/en_US/careers/JobDetail/Senior-Security-Engineer/12345"
    assert candidate.notes == "Enumerated through direct Harman careers (Avature) JobDetail links"


def test_discover_alphatheta_recognizes_no_openings_marker(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="AlphaTheta",
        url="https://alphatheta.com/careers/",
        discovery_mode="alphatheta_html",
        last_checked=None,
        cadence_group="every_month",
    )
    empty_page = """
    <html><body>
      <p>There are currently no open positions available.</p>
      <a href="https://alphatheta.com/">Home</a>
    </body></html>
    """

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: empty_page)

    coverage = alphatheta_provider.discover_alphatheta_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.matched_jobs == 0
    assert coverage.candidates == []
    assert coverage.limitations == ["AlphaTheta career page reports no open positions"]


def test_discover_alphatheta_falls_back_to_generic_enumeration(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="AlphaTheta",
        url="https://alphatheta.com/careers/",
        discovery_mode="alphatheta_html",
        last_checked=None,
        cadence_group="every_month",
    )
    listing_page = """
    <html><body>
      <a href="/careers/security-engineer/">Security Engineer</a>
      <a href="/company/">Company</a>
    </body></html>
    """

    monkeypatch.setattr(discover_http, "fetch_text", lambda url, timeout_seconds: listing_page)

    coverage = alphatheta_provider.discover_alphatheta_jobs(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert candidate.title == "Security Engineer"
    assert candidate.url == "https://alphatheta.com/careers/security-engineer"


def test_discover_ashby_api_enriches_candidates_with_detail_sections(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Ashby",
        url="https://jobs.ashbyhq.com/example",
        discovery_mode="ashby_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    description_html = (
        "<h2>What You'll Do</h2>"
        "<ul><li>Own the platform security roadmap.</li></ul>"
        "<h2>Who You Are</h2>"
        "<ul><li>7+ years of security engineering experience.</li></ul>"
        "<h2>Compensation:</h2>"
        "<p>$280,000 to $340,000 base salary (before equity)</p>"
        "<h2>Perks &amp; Benefits</h2>"
        "<p>Catalogue of benefits that should not appear in tasks or qualifications.</p>"
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        if payload["operationName"] == "ApiJobBoardWithTeams":
            return {
                "data": {
                    "jobBoard": {
                        "teams": [{"id": "sec", "externalName": "Security"}],
                        "jobPostings": [
                            {
                                "id": "staff-security-engineer",
                                "title": "Staff Security Engineer",
                                "teamId": "sec",
                                "locationName": "New York, NY",
                                "secondaryLocations": [],
                                "workplaceType": "On-site",
                                "employmentType": "Full-time",
                                "compensationTierSummary": "$280K – $340K",
                            }
                        ],
                    }
                }
            }
        assert payload["operationName"] == "ApiJobPosting"
        assert payload["variables"]["jobPostingId"] == "staff-security-engineer"
        return {
            "data": {
                "jobPosting": {
                    "descriptionHtml": description_html,
                    "compensationTierSummary": "$280K – $340K",
                }
            }
        }

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = discover_jobs.discover_ashby_api(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 1
    candidate = coverage.candidates[0]
    assert "Tasks: Own the platform security roadmap." in candidate.notes
    assert "Qualifications: 7+ years of security engineering experience." in candidate.notes
    assert "Compensation: $280,000 to $340,000 base salary (before equity)" in candidate.notes
    assert "Catalogue of benefits" not in candidate.notes


def test_discover_ashby_api_falls_back_to_compensation_summary_when_section_missing(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Ashby",
        url="https://jobs.ashbyhq.com/example",
        discovery_mode="ashby_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        if payload["operationName"] == "ApiJobBoardWithTeams":
            return {
                "data": {
                    "jobBoard": {
                        "teams": [{"id": "sec", "externalName": "Security"}],
                        "jobPostings": [
                            {
                                "id": "lead-security-engineer",
                                "title": "Lead Security Engineer",
                                "teamId": "sec",
                                "locationName": "Remote",
                                "secondaryLocations": [],
                                "workplaceType": "Remote",
                                "employmentType": "Full-time",
                                "compensationTierSummary": "$180K – $280K • Offers Equity",
                            }
                        ],
                    }
                }
            }
        return {
            "data": {
                "jobPosting": {
                    "descriptionHtml": (
                        "<h2>Who You Are</h2>"
                        "<ul><li>6+ years of security engineering experience.</li></ul>"
                    ),
                    "compensationTierSummary": "$180K – $280K • Offers Equity",
                }
            }
        }

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = discover_jobs.discover_ashby_api(source, ["security"], timeout_seconds=5)

    assert coverage.matched_jobs == 1
    candidate = coverage.candidates[0]
    assert "Qualifications: 6+ years of security engineering experience." in candidate.notes
    assert "Compensation: $180K – $280K" in candidate.notes


def test_discover_ashby_api_marks_partial_when_detail_fetch_fails(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Ashby",
        url="https://jobs.ashbyhq.com/example",
        discovery_mode="ashby_api",
        last_checked=None,
        cadence_group="every_3_runs",
    )

    def fake_post_json(url: str, payload: object, timeout_seconds: int, headers: dict[str, str] | None = None):
        if payload["operationName"] == "ApiJobBoardWithTeams":
            return {
                "data": {
                    "jobBoard": {
                        "teams": [{"id": "sec", "externalName": "Security"}],
                        "jobPostings": [
                            {
                                "id": "lead-security-engineer",
                                "title": "Lead Security Engineer",
                                "teamId": "sec",
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
        raise RuntimeError("detail endpoint unavailable")

    monkeypatch.setattr(discover_http, "post_json", fake_post_json)

    coverage = discover_jobs.discover_ashby_api(source, ["security"], timeout_seconds=5)

    assert coverage.matched_jobs == 1
    assert coverage.direct_job_pages_opened == 0
    assert coverage.status == "partial"
    assert any("Detail fetch failed" in limitation for limitation in coverage.limitations)


def test_discover_personio_page_falls_back_to_xml_feed(monkeypatch):
    source = discover_jobs.SourceConfig(
        source="Example Personio",
        url="https://example.jobs.personio.de/",
        discovery_mode="personio_page",
        last_checked=None,
        cadence_group="every_3_runs",
    )
    xml_feed = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position>
    <id>4242</id>
    <name>Senior Security Engineer</name>
    <office>Berlin</office>
    <department>Engineering</department>
    <employmentType>permanent</employmentType>
    <jobDescriptions><jobDescription><name>About</name><value>ignored</value></jobDescription></jobDescriptions>
  </position>
  <position>
    <id>4243</id>
    <name>Sales Lead</name>
    <office>Berlin</office>
  </position>
</workzag-jobs>
"""

    def fake_fetch_text(url: str, timeout_seconds: int) -> str:
        if url == source.url:
            return "<html><body><p>Careers page rendered without an embedded jobs payload.</p></body></html>"
        if url == "https://example.jobs.personio.de/xml":
            return xml_feed
        raise AssertionError(f"unexpected fetch_text({url})")

    monkeypatch.setattr(discover_http, "fetch_text", fake_fetch_text)

    coverage = discover_jobs.discover_personio_page(source, ["security"], timeout_seconds=5)

    assert coverage.status == "complete"
    assert coverage.enumerated_jobs == 2
    assert coverage.matched_jobs == 1
    assert any("used XML feed" in limitation for limitation in coverage.limitations)
    candidate = coverage.candidates[0]
    assert candidate.title == "Senior Security Engineer"
    assert candidate.url == "https://example.jobs.personio.de/job/4242"
    assert candidate.location == "Berlin"
