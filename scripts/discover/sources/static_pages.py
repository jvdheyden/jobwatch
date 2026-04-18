"""Bespoke static-page providers for small official career pages."""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from discover import helpers, http
from discover.core import Candidate, Coverage, SourceConfig
from discover.registry import SourceAdapter


PCD_TEAM_TASK_HEADINGS = (
    "The perks of this job are that the candidate would",
    "What you'll do",
    "What you will do",
    "What youll do",
    "Responsibilities",
)
PCD_TEAM_QUALIFICATION_HEADINGS = (
    "The platonic ideal candidate",
    "Qualifications",
    "Requirements",
    "Who you are",
    "What you'll need",
    "What you will need",
    "What you need",
    "What youll need",
)
PCD_TEAM_DETAIL_STOP_HEADINGS = (
    *PCD_TEAM_TASK_HEADINGS,
    *PCD_TEAM_QUALIFICATION_HEADINGS,
    "Compensation",
    "Benefits",
    "Apply",
    "Apply Here",
    "About PCD",
)


def extract_pcd_team_detail_sections(detail_html: str) -> dict[str, str]:
    detail_text = "\n".join(helpers.extract_visible_text_lines_from_html(detail_html))
    return {
        "tasks": helpers.extract_visible_text_section(
            detail_text,
            PCD_TEAM_TASK_HEADINGS,
            PCD_TEAM_DETAIL_STOP_HEADINGS,
        ),
        "qualifications": helpers.extract_visible_text_section(
            detail_text,
            PCD_TEAM_QUALIFICATION_HEADINGS,
            PCD_TEAM_DETAIL_STOP_HEADINGS,
        ),
    }


def apply_pcd_team_detail_text(candidate: Candidate, detail_html: str, terms: list[str]) -> bool:
    sections = extract_pcd_team_detail_sections(detail_html)
    detail_text_for_matching = " ".join(part for part in sections.values() if part)
    original_terms = list(candidate.matched_terms)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + helpers.match_terms(detail_text_for_matching, terms)))

    original_notes = candidate.notes
    note_parts = [candidate.notes] if candidate.notes else []
    if sections["tasks"]:
        note_parts.append(f"Tasks: {helpers.truncate_text(sections['tasks'], 260)}")
    if sections["qualifications"]:
        note_parts.append(f"Qualifications: {helpers.truncate_text(sections['qualifications'], 260)}")
    candidate.notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def discover_pcd_team(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    searchable_text = helpers.strip_html_fragment(html)

    title_match = re.search(r"<h1>(?P<title>.*?)</h1>", html, flags=re.DOTALL | re.IGNORECASE)
    title = helpers.strip_html_fragment(title_match.group("title")) if title_match else "Software Engineer"
    if "·" in title:
        title = helpers.normalize_whitespace(title.split("·", 1)[0])
    title = re.sub(r"\s+JD$", "", title).strip() or "Software Engineer"

    apply_match = re.search(
        r'<a href="(?P<href>[^"]+)"[^>]*>\s*Apply Here\s*</a>',
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    apply_url = helpers.normalize_url_without_fragment(apply_match.group("href")) if apply_match else ""
    matched_terms = sorted(set(helpers.match_terms(searchable_text, terms)))

    candidates: list[Candidate] = []
    if helpers.should_keep_candidate(title, matched_terms, searchable_text):
        candidate = Candidate(
            employer=source.source,
            title=title,
            url=source.url,
            source_url=source.url,
            alternate_url=apply_url,
            matched_terms=matched_terms,
            notes="PCD Team job description page",
        )
        apply_pcd_team_detail_text(candidate, html, terms)
        candidates.append(candidate)

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
        enumerated_jobs=1,
        matched_jobs=len(candidates),
        limitations=[],
        candidates=candidates,
    )


def discover_qedit_inline(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    body = helpers.strip_html_fragment(html)
    title = "Cryptography Engineer"
    candidates: list[Candidate] = []
    limitations: list[str] = []
    enumerated_jobs = 0

    match = re.search(r"Open Positions\s+Cryptography Engineer\s+\+\s+(.*?)(?:Please contact|QEDIT Office Life|$)", body)
    if match:
        enumerated_jobs = 1
        snippet = helpers.normalize_whitespace(f"{title} {match.group(1)}")
        matched_terms = sorted(set(helpers.match_terms(snippet, terms)))
        if helpers.should_keep_candidate(title, matched_terms, snippet):
            candidates.append(
                Candidate(
                    employer=source.source,
                    title=title,
                    url=source.url,
                    source_url=source.url,
                    matched_terms=matched_terms,
                    notes="Inline careers page posting",
                )
            )
    else:
        limitations.append("Expected inline 'Cryptography Engineer' role was not found on the careers page.")

    if "Cryptography Interns" in body:
        limitations.append("Page mentions biannual cryptography interns, but not as a direct current opening.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete" if enumerated_jobs else "partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="inline_roles=1",
        direct_job_pages_opened=0,
        enumerated_jobs=enumerated_jobs,
        matched_jobs=len(candidates),
        limitations=limitations,
        candidates=candidates,
    )


def _discover_filtered_html_links(
    source: SourceConfig,
    terms: list[str],
    timeout_seconds: int,
    url_filter,
    notes: str,
    limitation_if_empty: str | None = None,
) -> Coverage:
    html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(html)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if urlparse(absolute_url).scheme not in {"http", "https"}:
            continue
        if not url_filter(absolute_url):
            continue
        raw_urls.add(absolute_url)
        text = helpers.normalize_whitespace(link["text"]) or "unknown"
        visible_lines = helpers.split_visible_lines(link["text"])
        title = visible_lines[0] if visible_lines else text
        searchable_text = f"{title} {text} {absolute_url}"
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
                matched_terms=matched_terms,
                notes=notes,
            ),
        )

    limitations = [limitation_if_empty] if not raw_urls and limitation_if_empty else []
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
        result_pages_scanned="filtered_links=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_neclab_jobs(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    return _discover_filtered_html_links(
        source,
        terms,
        timeout_seconds,
        lambda url: "jobs.neclab.eu/jobs/get" in url and "jid=" in url,
        notes="Enumerated through NEC Laboratories Europe job-detail links",
        limitation_if_empty="No NEC Laboratories Europe job-detail links were visible on the jobs page.",
    )


def _recognized_ats_url(url: str) -> bool:
    return any(host in url for host in ("boards.greenhouse.io", "jobs.lever.co", "apply.workable.com", "ashbyhq.com"))


def discover_leastauthority_careers(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    del terms
    html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(html)
    raw_urls: set[str] = set()
    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if _recognized_ats_url(absolute_url):
            raw_urls.add(absolute_url)
    limitations = []
    if not raw_urls:
        limitations.append("Careers page exposes category filters and company sections, but no direct current job links.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=[],
        result_pages_scanned="career_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=0,
        limitations=limitations,
        candidates=[],
    )


def discover_qusecure_careers(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    del terms
    html = http.fetch_text(source.url, timeout_seconds)
    parser = helpers.LinkCollector()
    parser.feed(html)
    body = helpers.strip_html_fragment(html)
    raw_urls: set[str] = set()
    for link in parser.links:
        absolute_url = helpers.normalize_url_without_fragment(urljoin(source.url, link["href"]))
        if _recognized_ats_url(absolute_url):
            raw_urls.add(absolute_url)
    limitations = []
    if "Please send cover letter and resume to Careers@qusecure.com." in body:
        limitations.append("Career page requests email applications and exposes no direct job listings.")
    elif not raw_urls:
        limitations.append("No direct job listings were visible on the QuSecure careers page.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete",
        listing_pages_scanned=1,
        search_terms_tried=[],
        result_pages_scanned="career_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=0,
        limitations=limitations,
        candidates=[],
    )


def discover_partisia_site(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    del terms
    checked_urls = [source.url]
    if source.url != "https://partisiafoundation.com/":
        checked_urls.append("https://partisiafoundation.com/")

    found_jobish_links: set[str] = set()
    limitations: list[str] = []
    fetch_failures = 0
    pages_scanned = 0
    for url in checked_urls:
        pages_scanned += 1
        try:
            html = http.fetch_text(url, timeout_seconds)
        except Exception as exc:
            fetch_failures += 1
            limitations.append(f"Could not read {url}: {type(exc).__name__}: {exc}")
            continue
        parser = helpers.LinkCollector()
        parser.feed(html)
        for link in parser.links:
            absolute_url = helpers.normalize_url_without_fragment(urljoin(url, link["href"]))
            combined = f"{link['text']} {absolute_url}".lower()
            if any(token in combined for token in ("career", "careers", "jobs", "join us", "work with us")):
                found_jobish_links.add(absolute_url)

    if not found_jobish_links:
        limitations.append("Official Partisia sites exposed no careers page or direct job listings.")

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial" if fetch_failures else "complete",
        listing_pages_scanned=pages_scanned,
        search_terms_tried=[],
        result_pages_scanned="homepage_scan=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(found_jobish_links),
        matched_jobs=0,
        limitations=limitations,
        candidates=[],
    )


SOURCES = [
    SourceAdapter(modes=("pcd_team",), discover=discover_pcd_team),
    SourceAdapter(modes=("qedit_inline",), discover=discover_qedit_inline),
    SourceAdapter(modes=("neclab_jobs",), discover=discover_neclab_jobs),
    SourceAdapter(modes=("leastauthority_careers",), discover=discover_leastauthority_careers, emits_candidates=False),
    SourceAdapter(modes=("qusecure_careers",), discover=discover_qusecure_careers, emits_candidates=False),
    SourceAdapter(modes=("partisia_site",), discover=discover_partisia_site, emits_candidates=False),
]
