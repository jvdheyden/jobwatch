"""EnBW Phenom embedded-search provider."""

from __future__ import annotations

from urllib.parse import urlencode, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


ENBW_RESULTS_PAGE_SIZE = 10


def build_enbw_search_url(source_url: str, term: str, offset: int) -> str:
    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    params = {"keywords": term}
    if offset:
        params["from"] = str(offset)
    return f"{base}/de/de/search-results?{urlencode(params)}"


def build_enbw_job_url(source_url: str, job_id: str, title: str) -> str:
    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    slug = helpers.slugify_title(title)
    if slug:
        return helpers.normalize_url_without_fragment(f"{base}/de/de/job/{job_id}/{slug}")
    return helpers.normalize_url_without_fragment(f"{base}/de/de/job/{job_id}")


def build_enbw_apply_url(source_url: str, job_seq_no: str) -> str:
    parsed = urlparse(source_url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    return helpers.normalize_url_without_fragment(f"{base}/de/de/apply?{urlencode({'jobSeqNo': job_seq_no})}")


def discover_enbw_phenom(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    result_summaries: list[str] = []
    listing_pages_scanned = 0
    max_pages_per_term = 5

    for term in terms:
        offset = 0
        term_pages = 0
        term_seen = 0
        term_total: int | None = None
        while term_pages < max_pages_per_term:
            html = http.fetch_text(build_enbw_search_url(source.url, term, offset), timeout_seconds)
            ddo = helpers.extract_json_object_after_marker(html, "phApp.ddo = ")
            if not isinstance(ddo, dict):
                limitations.append(f"EnBW search payload for '{term}' was not found in the page HTML.")
                break
            payload = ddo.get("eagerLoadRefineSearch") or {}
            jobs = payload.get("data", {}).get("jobs") or []
            hits = int(payload.get("hits") or len(jobs))
            term_total = int(payload.get("totalHits") or len(jobs))
            term_pages += 1
            listing_pages_scanned += 1
            term_seen += len(jobs)

            for job in jobs:
                if not isinstance(job, dict):
                    continue
                job_id = helpers.normalize_whitespace(helpers.join_text(job.get("jobId") or job.get("reqId") or job.get("jobSeqNo")))
                if not job_id:
                    continue
                raw_seen_ids.add(job_id)
                title = helpers.normalize_whitespace(helpers.join_text(job.get("title"))) or "unknown"
                employer = helpers.normalize_whitespace(helpers.join_text(job.get("company"))) or source.source
                location = helpers.normalize_whitespace(
                    helpers.join_text(job.get("cityStateCountry") or job.get("location") or job.get("city"))
                ) or "unknown"
                description = helpers.strip_html_fragment(helpers.join_text(job.get("descriptionTeaser")))
                category = helpers.normalize_whitespace(helpers.join_text(job.get("category")))
                remote = helpers.normalize_whitespace(helpers.join_text(job.get("remote"))) or "unknown"
                job_seq_no = helpers.normalize_whitespace(helpers.join_text(job.get("jobSeqNo")))
                job_url = build_enbw_job_url(source.url, job_id, title)
                apply_url = build_enbw_apply_url(source.url, job_seq_no) if job_seq_no else ""
                searchable_text = " ".join(
                    part for part in [title, employer, location, category, remote, description] if part
                )
                matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
                if not helpers.should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                helpers.merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=employer,
                        title=title,
                        url=job_url,
                        source_url=source.url,
                        alternate_url=apply_url if apply_url and apply_url != job_url else "",
                        location=location,
                        remote=remote,
                        matched_terms=matched_terms,
                        notes=f"EnBW Phenom search keyword='{term}'",
                    ),
                )

            if not jobs or term_total is None or term_seen >= term_total:
                break
            offset += hits or ENBW_RESULTS_PAGE_SIZE

        total_label = term_total if term_total is not None else term_seen
        result_summaries.append(f"{term}:{term_pages}p/{term_seen}of{total_label}")
        if term_total is not None and term_seen < term_total:
            limitations.append(f"EnBW search for '{term}' surfaced {term_seen} of {term_total} results")

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
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("enbw_phenom",), discover=discover_enbw_phenom)
