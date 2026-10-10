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


MAX_PAGES = 30


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
    headers = {"Referer": source.url, "X-Requested-With": "XMLHttpRequest"}
    jobs: list[dict] = []
    seen_shortcodes: set[str] = set()
    reported_total = 0
    pages_scanned = 0
    payload: dict[str, str] = {"query": ""}
    # The board returns 10 jobs per page plus a `nextPage` token. The token is
    # still present after the last page, so stop on the reported total, on a
    # page that adds nothing new, or at the page cap.
    while pages_scanned < MAX_PAGES:
        response = http.post_json(endpoint, payload, timeout_seconds, headers=headers)
        pages_scanned += 1
        if not isinstance(response, dict):
            break
        page_jobs = [job for job in response.get("results") or [] if isinstance(job, dict)]
        reported_total = int(response.get("total", 0) or 0)
        new_jobs = []
        for job in page_jobs:
            shortcode = helpers.normalize_whitespace(helpers.join_text(job.get("shortcode")))
            if shortcode and shortcode in seen_shortcodes:
                continue
            if shortcode:
                seen_shortcodes.add(shortcode)
            new_jobs.append(job)
        jobs.extend(new_jobs)
        next_page = response.get("nextPage")
        if not new_jobs or not next_page or len(jobs) >= reported_total:
            break
        payload = {"query": "", "token": str(next_page)}
    reported_total = reported_total or len(jobs)
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
        if not matched_terms:
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
            f"Workable reported {reported_total} openings but {len(jobs)} were enumerated within {pages_scanned} page(s)."
        )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=f"api_pages={pages_scanned}",
        direct_job_pages_opened=0,
        enumerated_jobs=len(jobs),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("workable_api",), discover=discover_workable_api)
