"""Workable jobs API provider.

Supported discovery modes:
- `workable_api`

Expected source URL shape:
- `https://apply.workable.com/<account-slug>/`
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


def build_workable_job_url(source_url: str, board_slug: str, shortcode: str) -> str:
    if not shortcode:
        return source_url
    parsed = urlparse(source_url)
    base_url = f"{parsed.scheme or 'https'}://{parsed.netloc}"
    return helpers.normalize_url_without_fragment(f"{base_url}/{board_slug}/j/{shortcode}")


def discover_workable_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    path_bits = [bit for bit in urlparse(source.url).path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Workable board slug from {source.url}")
    board_slug = path_bits[0]
    parsed = urlparse(source.url)
    endpoint = f"{parsed.scheme or 'https'}://{parsed.netloc}/api/v3/accounts/{board_slug}/jobs"
    response = http.post_json(
        endpoint,
        {"query": ""},
        timeout_seconds,
        headers={"Referer": source.url, "X-Requested-With": "XMLHttpRequest"},
    )
    jobs = response.get("results") if isinstance(response, dict) else []
    jobs = jobs or []
    reported_total = int(response.get("total", len(jobs)) or 0) if isinstance(response, dict) else len(jobs)
    candidates_by_url: dict[str, Candidate] = {}

    for job in jobs:
        title = helpers.normalize_whitespace(helpers.join_text(job.get("title"))) or "unknown"
        location = helpers.normalize_whitespace(helpers.join_text(job.get("location"))) or helpers.normalize_whitespace(
            helpers.join_text(job.get("locations"))
        )
        location = location or "unknown"
        workplace = helpers.normalize_whitespace(helpers.join_text(job.get("workplace")))
        department = helpers.normalize_whitespace(helpers.join_text(job.get("department")))
        employment_type = helpers.normalize_whitespace(helpers.join_text(job.get("type")))
        shortcode = helpers.normalize_whitespace(helpers.join_text(job.get("shortcode")))
        remote_flag = job.get("remote")
        if remote_flag is True:
            remote = "remote"
        elif remote_flag is False:
            remote = helpers.infer_remote_status(location, workplace)
        else:
            remote = helpers.infer_remote_status(location, workplace, helpers.join_text(remote_flag))

        searchable_text = " ".join(
            part
            for part in [
                title,
                location,
                workplace,
                department,
                employment_type,
                helpers.join_text(job.get("state")),
                helpers.join_text(job.get("published")),
            ]
            if part
        )
        matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
        if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note_parts = ["Enumerated through Workable jobs API"]
        if department:
            note_parts.append(f"Department: {department}")
        if workplace:
            note_parts.append(f"Workplace: {workplace}")
        if employment_type:
            note_parts.append(f"Type: {employment_type}")

        helpers.merge_candidate(
            candidates_by_url,
            Candidate(
                employer=source.source,
                title=title,
                url=build_workable_job_url(source.url, board_slug, shortcode),
                source_url=source.url,
                location=location,
                remote=remote,
                matched_terms=matched_terms,
                notes="; ".join(note_parts),
            ),
        )

    limitations: list[str] = []
    status = "complete"
    if reported_total > len(jobs):
        status = "partial"
        limitations.append(
            f"Workable reported {reported_total} openings but returned {len(jobs)} records in the board payload."
        )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="local_filter=1",
        direct_job_pages_opened=0,
        enumerated_jobs=reported_total or len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("workable_api",), discover=discover_workable_api)
