"""Lever Jobs provider.

Supported discovery modes:
- `lever_json`

Expected source URL shape:
- `https://jobs.lever.co/<board-token>`
- `https://jobs.<custom-domain>.lever.co/<board-token>`
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


def lever_api_url(source_url: str) -> str:
    path_bits = [bit for bit in urlparse(source_url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Lever board token from {source_url}")
    token = path_bits[0]
    parsed = urlparse(source_url)
    if parsed.netloc == "jobs.lever.co":
        api_host = "api.lever.co"
    elif parsed.netloc.startswith("jobs.") and parsed.netloc.endswith(".lever.co"):
        api_host = "api." + parsed.netloc[len("jobs.") :]
    else:
        api_host = "api.lever.co"
    return f"{parsed.scheme or 'https'}://{api_host}/v0/postings/{token}?mode=json"


def discover_lever_json(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    postings = http.fetch_json(lever_api_url(source.url), timeout_seconds)
    if not isinstance(postings, list):
        postings = []

    candidates_by_url: dict[str, Candidate] = {}
    for posting in postings:
        if not isinstance(posting, dict):
            continue
        title = posting.get("text", "unknown")
        categories = posting.get("categories", {})
        if not isinstance(categories, dict):
            categories = {}
        location = categories.get("location") or "unknown"
        payload = " ".join(
            filter(
                None,
                [
                    title,
                    posting.get("descriptionPlain", ""),
                    categories.get("team", ""),
                    location,
                ],
            )
        )
        matched = helpers.match_terms(payload, terms)
        if not helpers.should_keep_candidate(title, matched, payload):
            continue
        raw_url = posting.get("hostedUrl") or posting.get("applyUrl") or source.url
        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=helpers.normalize_url_without_fragment(raw_url),
                source_url=source.url,
                location=location,
                matched_terms=matched,
                notes="Enumerated through Lever JSON",
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


SOURCE = SourceAdapter(modes=("lever_json",), discover=discover_lever_json)
