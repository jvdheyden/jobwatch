"""Generic Phenom-hosted careers search provider.

Supported ``discovery_mode`` values: ``phenom_html``.

Expected source URL shape: a Phenom search-results page such as
``https://careers.bcg.com/global/en/search-results?keywords=BCG%20X``. The
path prefix before ``/search-results`` is reused as the locale path for job
detail URLs (``<origin>/<locale-path>/job/<id>/<slug>``), and every query
parameter on the source URL is preserved on the search requests.

Behaviour:

- Runs one keyword search per configured term and pages through the results
  with ``from=<offset>`` (without ``s=1``, which makes Phenom drop the keyword
  query) up to ``PHENOM_MAX_PAGES_PER_TERM`` pages per term.
- When the source URL carries ``keywords=``, those keywords are prepended to
  every term query and a posting is only kept when its searchable payload also
  contains them. Phenom keyword search ranks fuzzily instead of filtering, so
  the URL keywords act as the configured scope of the source.
- Parses the ``phApp.ddo`` / ``eagerLoadRefineSearch`` payload embedded in the
  static HTML; no JavaScript is executed.
- Opens matched job detail pages and stores the embedded ``jobDetail``
  description, bounded through ``helpers.set_candidate_description``.

Supported source ``filters``: none; encode native Phenom parameters in the
source URL.

Known limitations: queries whose results exceed the per-term page cap are
reported as a coverage limitation. Tenants with bespoke URL layouts keep their
dedicated providers (``thales_html``, ``enbw_phenom``).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


PHENOM_RESULTS_PAGE_SIZE = 10
PHENOM_MAX_PAGES_PER_TERM = 5
PHENOM_DDO_MARKER = "phApp.ddo = "
PHENOM_SEARCH_MARKER = '"eagerLoadRefineSearch":'
PHENOM_SEARCH_PATH = "/search-results"
PHENOM_SEARCH_QUERY_KEYS = {"keywords", "from", "s"}


def extract_phenom_search_payload(html: str) -> dict[str, Any] | None:
    """Return the embedded ``eagerLoadRefineSearch`` payload when the page has one."""
    ddo = helpers.extract_json_object_after_marker(html or "", PHENOM_DDO_MARKER)
    payload = ddo.get("eagerLoadRefineSearch") if isinstance(ddo, dict) else None
    if not isinstance(payload, dict):
        payload = helpers.extract_json_object_after_marker(html or "", PHENOM_SEARCH_MARKER)
    return payload if isinstance(payload, dict) else None


def phenom_url_keywords(source_url: str) -> str:
    query = parse_qsl(urlparse(source_url).query, keep_blank_values=True)
    return helpers.normalize_whitespace(" ".join(value for key, value in query if key == "keywords"))


def build_phenom_search_url(source_url: str, keywords: str, offset: int) -> str:
    parsed = urlparse(source_url)
    params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key not in PHENOM_SEARCH_QUERY_KEYS
    ]
    params.append(("keywords", keywords))
    if offset:
        # Phenom drops the keyword query when the `s=1` flag accompanies `from=`,
        # so paging sends the offset alone.
        params.append(("from", str(offset)))
    return parsed._replace(query=urlencode(params), fragment="").geturl()


def phenom_locale_base(source_url: str) -> str:
    parsed = urlparse(source_url)
    index = parsed.path.find(PHENOM_SEARCH_PATH)
    prefix = parsed.path[:index] if index != -1 else parsed.path
    return f"{parsed.scheme}://{parsed.netloc}{prefix.rstrip('/')}"


def build_phenom_job_url(source_url: str, job_id: str, title: str) -> str:
    slug = helpers.slugify_title(title)
    url = f"{phenom_locale_base(source_url)}/job/{job_id}"
    if slug:
        url = f"{url}/{slug}"
    return helpers.normalize_url_without_fragment(url)


def phenom_job_location(job: dict[str, Any]) -> str:
    location = helpers.normalize_whitespace(helpers.join_text(job.get("cityStateCountry") or job.get("location")))
    if not location:
        parts = (helpers.normalize_whitespace(helpers.join_text(job.get(key))) for key in ("city", "state", "country"))
        location = ", ".join(part for part in parts if part)
    return location or "unknown"


def phenom_job_searchable_text(job: dict[str, Any], title: str, location: str) -> str:
    parts = [
        title,
        helpers.strip_html_fragment(helpers.join_text(job.get("descriptionTeaser"))),
        helpers.join_text(job.get("ml_skills")),
        helpers.join_text(job.get("category")),
        helpers.join_text(job.get("subCategory")),
        location,
        helpers.join_text(job.get("multi_location")),
    ]
    return " ".join(part for part in parts if part)


def phenom_detail_description(html: str) -> str:
    """Prefer the embedded ``jobDetail`` description; fall back to visible page text."""
    ddo = helpers.extract_json_object_after_marker(html or "", PHENOM_DDO_MARKER)
    job = None
    if isinstance(ddo, dict):
        job = ((ddo.get("jobDetail") or {}).get("data") or {}).get("job")
    description = helpers.join_text(job.get("description")) if isinstance(job, dict) else ""
    if description.strip():
        return helpers.strip_html_fragment(description)
    return helpers.visible_text_from_html(html or "")


def enrich_phenom_candidate_details(
    candidates_by_url: dict[str, Candidate],
    timeout_seconds: int,
    limitations: list[str],
) -> int:
    direct_job_pages_opened = 0
    failed = 0
    for candidate in candidates_by_url.values():
        try:
            detail_html = http.fetch_text(candidate.url, timeout_seconds)
        except Exception:
            failed += 1
            continue
        direct_job_pages_opened += 1
        helpers.set_candidate_description(candidate, phenom_detail_description(detail_html))
    if failed:
        limitations.append(f"Phenom detail page fetch errored for {failed} of {len(candidates_by_url)} matched roles")
    return direct_job_pages_opened


def discover_phenom_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    result_summaries: list[str] = []
    errored_queries: list[str] = []
    capped_queries: list[str] = []
    listing_pages_scanned = 0
    scope_keywords = phenom_url_keywords(source.url)

    for term in terms:
        keywords = helpers.normalize_whitespace(f"{scope_keywords} {term}")
        offset = 0
        pages = 0
        seen = 0
        total: int | None = None
        page_signatures: set[str] = set()
        while pages < PHENOM_MAX_PAGES_PER_TERM:
            search_url = build_phenom_search_url(source.url, keywords, offset)
            try:
                html = http.fetch_text(search_url, timeout_seconds)
            except Exception:
                errored_queries.append(keywords)
                break
            payload = extract_phenom_search_payload(html)
            if payload is None:
                limitations.append(f"Phenom search payload for '{keywords}' was not found in the page HTML")
                break
            jobs = [job for job in (payload.get("data") or {}).get("jobs") or [] if isinstance(job, dict)]
            hits = int(payload.get("hits") or len(jobs))
            total = int(payload.get("totalHits") or len(jobs))
            pages += 1
            listing_pages_scanned += 1
            if not jobs:
                break
            signature = ",".join(
                str(job.get("jobSeqNo") or job.get("jobId") or job.get("reqId") or "") for job in jobs
            )
            if signature in page_signatures:
                break
            page_signatures.add(signature)
            seen += len(jobs)

            for job in jobs:
                job_id = helpers.normalize_whitespace(
                    helpers.join_text(job.get("jobId") or job.get("reqId") or job.get("jobSeqNo"))
                )
                if not job_id:
                    continue
                raw_seen_ids.add(job_id)
                title = helpers.normalize_whitespace(helpers.join_text(job.get("title"))) or "unknown"
                location = phenom_job_location(job)
                searchable_text = phenom_job_searchable_text(job, title, location)
                if scope_keywords and not helpers.match_terms(searchable_text, [scope_keywords]):
                    continue
                matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
                if not matched_terms:
                    continue
                helpers.merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=build_phenom_job_url(source.url, job_id, title),
                        source_url=source.url,
                        location=location,
                        matched_terms=matched_terms,
                        notes=f"Enumerated through Phenom search-results HTML for '{keywords}'",
                    ),
                )

            if seen >= total:
                break
            offset += hits or PHENOM_RESULTS_PAGE_SIZE

        total_label = total if total is not None else seen
        result_summaries.append(f"{keywords}={pages}p/{seen}of{total_label}")
        if total is not None and seen < total and pages >= PHENOM_MAX_PAGES_PER_TERM:
            capped_queries.append(keywords)

    if errored_queries:
        limitations.append("Errored Phenom searches: " + ", ".join(sorted(set(errored_queries))))
    if capped_queries:
        limitations.append(
            f"Phenom page cap of {PHENOM_MAX_PAGES_PER_TERM} pages per term reached for "
            f"{len(capped_queries)} of {len(terms)} searches"
        )
    direct_job_pages_opened = enrich_phenom_candidate_details(candidates_by_url, timeout_seconds, limitations)

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if limitations else "complete",
        listing_pages_scanned=listing_pages_scanned,
        search_terms_tried=terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("phenom_html",), discover=discover_phenom_html)
