"""Greenhouse board provider.

Supported discovery modes:
- `greenhouse_api`

Expected source URL shape:
- `https://job-boards.greenhouse.io/<board-token>`
- `https://boards.greenhouse.io/<board-token>`
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


def greenhouse_board_token(source_url: str) -> str:
    path_bits = [bit for bit in urlparse(source_url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Greenhouse board token from {source_url}")
    return path_bits[0]


def discover_greenhouse_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    token = greenhouse_board_token(source.url)
    api_url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true"
    payload = http.fetch_json(api_url, timeout_seconds)
    jobs = payload.get("jobs", []) if isinstance(payload, dict) else []
    candidates_by_url: dict[str, Candidate] = {}

    for job in jobs:
        if not isinstance(job, dict):
            continue
        title = job.get("title", "unknown")
        location_payload = job.get("location", {})
        if not isinstance(location_payload, dict):
            location_payload = {}
        location = location_payload.get("name") or "unknown"
        content = job.get("content", "")
        searchable_text = f"{title} {location} {content}"
        matched = helpers.match_terms(searchable_text, terms)
        if not helpers.should_keep_candidate(title, matched, searchable_text):
            continue
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=helpers.normalize_url_without_fragment(job.get("absolute_url") or source.url),
                source_url=source.url,
                location=location,
                matched_terms=matched,
                notes="Enumerated through Greenhouse board API",
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
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=[],
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("greenhouse_api",), discover=discover_greenhouse_api)
