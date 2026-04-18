"""Ashby job board provider.

Supported discovery modes:
- `ashby_api`
- `ashby_html` (compatibility alias for the same API extraction)

Expected source URL shape:
- `https://jobs.ashbyhq.com/<board-slug>`
"""

from __future__ import annotations

from urllib.parse import urlparse

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


def discover_ashby_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    path_bits = [bit for bit in urlparse(source.url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Ashby board slug from {source.url}")
    board_slug = path_bits[0]
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
    for posting in postings:
        title = posting.get("title") or "unknown"
        primary_location = posting.get("locationName") or "unknown"
        secondary_locations = [item.get("locationName") or "" for item in posting.get("secondaryLocations") or []]
        location = "; ".join(part for part in [primary_location, *secondary_locations] if part) or "unknown"
        team_name = teams.get(posting.get("teamId"), "")
        searchable_text = " ".join(
            part
            for part in [
                title,
                team_name,
                location,
                posting.get("workplaceType") or "",
                posting.get("employmentType") or "",
                posting.get("compensationTierSummary") or "",
            ]
            if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=f"{source.url.rstrip('/')}/{posting.get('id')}",
                source_url=source.url,
                location=location,
                remote=posting.get("workplaceType") or "unknown",
                matched_terms=matched_terms,
                notes="Enumerated through Ashby non-user GraphQL API",
            ),
        )
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(postings),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("ashby_api", "ashby_html"), discover=discover_ashby_api)
