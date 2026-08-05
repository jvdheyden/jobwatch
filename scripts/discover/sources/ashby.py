"""Ashby job board provider.

Supported discovery modes:
- `ashby_api`
- `ashby_html` (compatibility alias for the same API extraction)

Expected source URL shape:
- `https://jobs.ashbyhq.com/<board-slug>`
"""

from __future__ import annotations

from urllib.parse import unquote, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


ASHBY_JOB_BOARD_QUERY = """query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
  jobBoard: jobBoardWithTeams(
    organizationHostedJobsPageName: $organizationHostedJobsPageName
  ) {
    teams {
      id
      name
      externalName
      parentTeamId
      __typename
    }
    jobPostings {
      id
      title
      teamId
      locationId
      locationName
      workplaceType
      employmentType
      secondaryLocations {
        ...JobPostingSecondaryLocationParts
        __typename
      }
      compensationTierSummary
      __typename
    }
    __typename
  }
}

fragment JobPostingSecondaryLocationParts on JobPostingSecondaryLocation {
  locationId
  locationName
  __typename
}"""


ASHBY_JOB_POSTING_QUERY = """query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {
  jobPosting(
    organizationHostedJobsPageName: $organizationHostedJobsPageName
    jobPostingId: $jobPostingId
  ) {
    id
    title
    descriptionHtml
    compensationTierSummary
    __typename
  }
}"""


ASHBY_TASK_HEADINGS = (
    "Responsibilities",
    "Key Responsibilities",
    "Your Responsibilities",
    "What You'll Do",
    "What You Will Do",
    "What Youll Do",
    "What You'll Be Doing",
    "Job Description",
    "Position Summary",
    "Position Overview",
    "Role Summary",
    "The Role",
    "About the Role",
    "Your Role",
    "Your Mission",
)
ASHBY_QUALIFICATION_HEADINGS = (
    "Qualifications",
    "Requirements",
    "Required Qualifications",
    "Required Skills",
    "Minimum Qualifications",
    "Preferred Qualifications",
    "Basic Qualifications",
    "What You Bring",
    "What You'll Bring",
    "What You Will Bring",
    "What We're Looking For",
    "What We Are Looking For",
    "Who You Are",
    "You Have",
    "You'll Need",
    "What You'll Need",
)
ASHBY_COMPENSATION_HEADINGS = (
    "Compensation",
    "Pay Range",
    "Salary Range",
    "Total Rewards",
)
ASHBY_DETAIL_STOP_HEADINGS = (
    *ASHBY_TASK_HEADINGS,
    *ASHBY_QUALIFICATION_HEADINGS,
    *ASHBY_COMPENSATION_HEADINGS,
    "About Us",
    "About the Company",
    "About Suno",
    "Benefits",
    "Perks & Benefits",
    "Perks and Benefits",
    "Perks & Benefits for Full-Time Employees",
    "Additional Notes",
    "Equal Opportunity",
    "Equal Opportunity Employer",
    "Equal Employment Opportunity",
    "EEO Statement",
    "Apply",
)
ASHBY_COMPENSATION_MARKERS = (
    "salary range",
    "pay range",
    "compensation",
    "base pay",
    "base salary",
    "hourly rate",
)


def ashby_board_slug(source_url: str) -> str:
    path_bits = [bit for bit in urlparse(source_url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Ashby board slug from {source_url}")
    return unquote(path_bits[0])


def extract_ashby_detail_sections(description_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(description_html))
    tasks = helpers.extract_visible_text_section(
        detail_text,
        ASHBY_TASK_HEADINGS,
        ASHBY_DETAIL_STOP_HEADINGS,
    )
    qualifications = helpers.extract_visible_text_section(
        detail_text,
        ASHBY_QUALIFICATION_HEADINGS,
        ASHBY_DETAIL_STOP_HEADINGS,
    )
    compensation_section = helpers.extract_visible_text_section(
        detail_text,
        ASHBY_COMPENSATION_HEADINGS,
        ASHBY_DETAIL_STOP_HEADINGS,
    )
    compensation = compensation_section or helpers.extract_visible_text_marker_snippet(
        detail_text,
        ASHBY_COMPENSATION_MARKERS,
        ASHBY_DETAIL_STOP_HEADINGS,
    )
    return {
        "tasks": tasks,
        "qualifications": qualifications,
        "compensation": compensation,
    }


def build_ashby_detail_note_parts(sections: dict[str, str], compensation_tier_summary: str = "") -> list[str]:
    parts: list[str] = []
    if sections.get("tasks"):
        parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections.get("qualifications"):
        parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    compensation = sections.get("compensation") or compensation_tier_summary
    if compensation:
        parts.append(f"Compensation: {helpers.truncate_text(compensation, 200)}")
    return parts


def fetch_ashby_job_detail(board_slug: str, job_posting_id: str, source_url: str, timeout_seconds: int) -> dict:
    endpoint = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting"
    payload = {
        "operationName": "ApiJobPosting",
        "variables": {
            "organizationHostedJobsPageName": board_slug,
            "jobPostingId": job_posting_id,
        },
        "query": ASHBY_JOB_POSTING_QUERY,
    }
    response = http.post_json(endpoint, payload, timeout_seconds, headers={"Referer": source_url})
    if not isinstance(response, dict):
        return {}
    posting = response.get("data", {}).get("jobPosting")
    return posting if isinstance(posting, dict) else {}


def discover_ashby_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    board_slug = ashby_board_slug(source.url)
    endpoint = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
    payload = {
        "operationName": "ApiJobBoardWithTeams",
        "variables": {"organizationHostedJobsPageName": board_slug},
        "query": ASHBY_JOB_BOARD_QUERY,
    }
    response = http.post_json(endpoint, payload, timeout_seconds, headers={"Referer": source.url})
    job_board = response.get("data", {}).get("jobBoard", {}) if isinstance(response, dict) else {}
    postings = job_board.get("jobPostings", [])
    teams = {
        team.get("id"): team.get("externalName") or team.get("name") or ""
        for team in job_board.get("teams", [])
        if team.get("id")
    }
    candidates_by_url: dict[str, Candidate] = {}
    posting_ids_by_url: dict[str, str] = {}
    compensation_summary_by_url: dict[str, str] = {}
    for posting in postings:
        title = posting.get("title") or "unknown"
        primary_location = posting.get("locationName") or "unknown"
        secondary_locations = [item.get("locationName") or "" for item in posting.get("secondaryLocations") or []]
        location = "; ".join(part for part in [primary_location, *secondary_locations] if part) or "unknown"
        team_name = teams.get(posting.get("teamId"), "")
        compensation_summary = posting.get("compensationTierSummary") or ""
        searchable_text = " ".join(
            part
            for part in [
                title,
                team_name,
                location,
                posting.get("workplaceType") or "",
                posting.get("employmentType") or "",
                compensation_summary,
            ]
            if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not matched_terms:
            continue
        posting_id = posting.get("id") or ""
        candidate_url = f"{source.url.rstrip('/')}/{posting_id}"
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=candidate_url,
                source_url=source.url,
                location=location,
                remote=posting.get("workplaceType") or "unknown",
                matched_terms=matched_terms,
                notes="Enumerated through Ashby non-user GraphQL API",
            ),
        )
        if posting_id and candidate_url not in posting_ids_by_url:
            posting_ids_by_url[candidate_url] = posting_id
        if compensation_summary:
            compensation_summary_by_url[candidate_url] = compensation_summary

    limitations: list[str] = []
    direct_job_pages_opened = 0
    for candidate_url, posting_id in posting_ids_by_url.items():
        candidate = candidates_by_url.get(candidate_url)
        if candidate is None:
            continue
        try:
            posting_detail = fetch_ashby_job_detail(board_slug, posting_id, source.url, timeout_seconds)
        except Exception:
            limitations.append(f"Detail fetch failed for {candidate_url}")
            continue
        direct_job_pages_opened += 1
        description_html = posting_detail.get("descriptionHtml") or ""
        sections = extract_ashby_detail_sections(description_html)
        detail_compensation_summary = (
            posting_detail.get("compensationTierSummary")
            or compensation_summary_by_url.get(candidate_url, "")
        )
        detail_parts = build_ashby_detail_note_parts(sections, detail_compensation_summary)
        if detail_parts:
            candidate.notes = "; ".join(part for part in [candidate.notes, *detail_parts] if part)
        helpers.set_candidate_description(candidate, helpers.visible_text_from_html(description_html))

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("ashby_api", "ashby_html"), discover=discover_ashby_api)
