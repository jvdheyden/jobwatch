"""Rheinmetall SSR jobs page provider."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter
from discover.sources.service_bund import should_keep_service_bund_candidate


MAX_RHEINMETALL_PAGES = 20
RHEINMETALL_CARD_START_RE = re.compile(r'<div class="flex gap-0\.5 group">', flags=re.IGNORECASE)
RHEINMETALL_CARD_URL_RE = re.compile(
    r'<a href="(?P<href>/de/job/[^"]+)"[^>]*class="print-avoid-page-break flex-grow pr-8"',
    flags=re.IGNORECASE,
)
RHEINMETALL_CARD_TITLE_RE = re.compile(
    r'<div class="text-sm font-bold md:text-xl mb-2">(?P<title>.*?)</div>',
    flags=re.DOTALL | re.IGNORECASE,
)
RHEINMETALL_CARD_META_RE = re.compile(
    r'<div class="flex flex-wrap mr-6">\s*(?P<meta>.*?)\s*</div>',
    flags=re.DOTALL | re.IGNORECASE,
)
RHEINMETALL_PAGE_NUMBER_RE = re.compile(
    r'<a class="[^"]*cursor-pointer[^"]*inline-flex[^"]*"[^>]*>\s*(?P<page>\d+)\s*</a>',
    flags=re.DOTALL | re.IGNORECASE,
)


def build_rheinmetall_page_url(source_url: str, page_num: int) -> str:
    parsed = urlparse(source_url)
    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if page_num > 1:
        params["page"] = str(page_num)
    else:
        params.pop("page", None)
    return parsed._replace(query=urlencode(params)).geturl()


def discover_rheinmetall_html(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    first_page_html = http.fetch_text(source.url, timeout_seconds)
    page_numbers = [int(match.group("page")) for match in RHEINMETALL_PAGE_NUMBER_RE.finditer(first_page_html)]
    total_pages = max(page_numbers) if page_numbers else 1
    pages_to_scan = min(total_pages, MAX_RHEINMETALL_PAGES)
    candidates_by_url: dict[str, Candidate] = {}
    raw_urls: set[str] = set()
    listing_pages_scanned = 0
    result_summaries: list[str] = []
    limitations: list[str] = []

    if total_pages > pages_to_scan:
        limitations.append(
            f"Rheinmetall exposes {total_pages} paginated result pages; scanned the first {pages_to_scan} pages."
        )

    for page_num in range(1, pages_to_scan + 1):
        try:
            html = (
                first_page_html
                if page_num == 1
                else http.fetch_text(build_rheinmetall_page_url(source.url, page_num), timeout_seconds)
            )
        except Exception as exc:
            limitations.append(f"page {page_num}: {exc}")
            continue
        listing_pages_scanned += 1
        card_starts = [match.start() for match in RHEINMETALL_CARD_START_RE.finditer(html)]
        result_summaries.append(f"{page_num}:{len(card_starts)}")
        if not card_starts:
            continue

        for index, start in enumerate(card_starts):
            end = card_starts[index + 1] if index + 1 < len(card_starts) else len(html)
            chunk = html[start:end]
            href_match = RHEINMETALL_CARD_URL_RE.search(chunk)
            title_match = RHEINMETALL_CARD_TITLE_RE.search(chunk)
            if not href_match or not title_match:
                continue

            absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, unescape(href_match.group("href"))))
            raw_urls.add(absolute_url)
            title = helpers.strip_html_fragment(title_match.group("title")) or "unknown"
            meta_match = RHEINMETALL_CARD_META_RE.search(chunk)
            meta = helpers.strip_html_fragment(meta_match.group("meta")) if meta_match else ""

            employer = source.source
            location = "unknown"
            if "|" in meta:
                employer_text, location_text = [helpers.normalize_whitespace(part) for part in meta.split("|", 1)]
                employer = employer_text or employer
                location = location_text or location
            elif meta:
                employer = meta

            searchable_text = " ".join(part for part in [title, employer, location] if part)
            matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))
            if not should_keep_service_bund_candidate(title, matched_terms, searchable_text):
                continue

            helpers.merge_candidate(
                candidates_by_url,
                Candidate(
                    employer=employer,
                    title=title,
                    url=absolute_url,
                    source_url=source.url,
                    location=location,
                    matched_terms=matched_terms,
                    notes=f"Rheinmetall SSR jobs page {page_num}/{total_pages}",
                ),
            )

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
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCE = SourceAdapter(modes=("rheinmetall_html",), discover=discover_rheinmetall_html)
