"""Workday jobs API provider.

Supported discovery modes:
- `workday_api`

Expected source URL shape:
- `https://<tenant>.wd*.myworkdayjobs.com/<site>`
"""

from __future__ import annotations

from urllib.parse import urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


WORKDAY_RESULTS_PAGE_SIZE = 20


def build_workday_job_url(source_url: str, external_path: str) -> str:
    if not external_path:
        return source_url
    parsed = urlparse(external_path)
    if parsed.scheme and parsed.netloc:
        return helpers.normalize_url_without_fragment(external_path)
    return helpers.normalize_url_without_fragment(source_url.rstrip("/") + "/" + external_path.lstrip("/"))


def discover_workday_api(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    parsed_source = urlparse(source.url)
    if "myworkdayjobs.com" not in parsed_source.netloc:
        raise ValueError(f"Workday discovery requires a Workday board URL, got {source.url}")
    path_bits = [bit for bit in parsed_source.path.split("/") if bit]
    if not path_bits:
        raise ValueError(f"Could not derive Workday site token from {source.url}")
    tenant = parsed_source.netloc.split(".")[0]
    site = path_bits[0]
    endpoint = f"{parsed_source.scheme}://{parsed_source.netloc}/wday/cxs/{tenant}/{site}/jobs"
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    errored_terms: list[str] = []
    total_pages_scanned = 0

    for term in terms:
        term_pages_scanned = 0
        term_total = 0
        offset = 0
        page_signatures: set[str] = set()
        while True:
            payload = {"limit": WORKDAY_RESULTS_PAGE_SIZE, "offset": offset, "searchText": term}
            try:
                response = http.post_json(endpoint, payload, timeout_seconds, headers={"Referer": source.url})
            except Exception:
                errored_terms.append(term)
                break

            postings = response.get("jobPostings", []) if isinstance(response, dict) else []
            if term_total == 0:
                term_total = int(response.get("total", 0) or 0) if isinstance(response, dict) else 0
            if not postings:
                break

            page_signature = ",".join(
                str(posting.get("externalPath") or posting.get("title") or "") for posting in postings[:10]
            )
            if not page_signature or page_signature in page_signatures:
                break
            page_signatures.add(page_signature)

            term_pages_scanned += 1
            total_pages_scanned += 1
            for posting in postings:
                external_path = posting.get("externalPath") or ""
                title = posting.get("title") or "unknown"
                absolute_url = build_workday_job_url(source.url, external_path)
                raw_id = external_path or title
                raw_seen_ids.add(raw_id)
                location = posting.get("locationsText") or "unknown"
                searchable_text = " ".join(
                    part
                    for part in [
                        title,
                        location,
                        posting.get("postedOn") or "",
                        helpers.join_text(posting.get("bulletFields")),
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
                        url=absolute_url,
                        source_url=source.url,
                        location=location,
                        matched_terms=matched_terms,
                        notes=f"Enumerated through Workday jobs API for '{term}'",
                    ),
                )

            offset += len(postings)
            if len(postings) < WORKDAY_RESULTS_PAGE_SIZE:
                break
            if term_total and offset >= term_total:
                break

        term_summaries.append(f"{term}={term_pages_scanned}p/{term_total}")

    if errored_terms:
        limitations.append("Errored terms: " + ", ".join(sorted(set(errored_terms))))

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=total_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(term_summaries) if term_summaries else "none",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("workday_api",), discover=discover_workday_api)
