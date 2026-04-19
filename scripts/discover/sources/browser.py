"""Playwright-backed browser discovery providers."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlencode, urljoin

from discover import helpers
from discover.constants import DEFAULT_BROWSER_TIMEOUT_MS, MAX_BROWSER_PAGES
from discover.core import (
    BrowserEnrichmentResult,
    BrowserPageResult,
    BrowserStrategy,
    Candidate,
    Coverage,
    SourceConfig,
    partial_browser_unavailable_coverage,
)
from discover.registry import SourceAdapter


GOOGLE_RESULTS_PAGE_SIZE = 20
GOOGLE_LOCATION_FILTERS = (
    "Munich, Germany",
    "Zurich, Switzerland",
    "London, UK",
    "New York, NY, USA",
)

META_TASK_HEADINGS = (
    "Responsibilities",
    "What You'll Do",
    "What You Will Do",
)
META_MINIMUM_QUALIFICATION_HEADINGS = (
    "Minimum Qualifications",
    "Qualifications",
    "Requirements",
)
META_PREFERRED_QUALIFICATION_HEADINGS = ("Preferred Qualifications",)
META_DETAIL_STOP_HEADINGS = (
    *META_TASK_HEADINGS,
    *META_MINIMUM_QUALIFICATION_HEADINGS,
    *META_PREFERRED_QUALIFICATION_HEADINGS,
    "Locations",
    "About Meta",
    "About Us",
    "Team",
    "Job Interviews",
    "Culture",
    "Benefits",
    "Compensation",
    "Equal Employment Opportunity",
)
META_DETAIL_IGNORED_LINES = {
    "Apply to Job",
    "Save Job",
    "Share Job",
    "See all jobs",
    "Show more",
    "Read more",
}


match_terms = helpers.match_terms
normalize_for_matching = helpers.normalize_for_matching
normalize_url_without_fragment = helpers.normalize_url_without_fragment
normalize_whitespace = helpers.normalize_whitespace
should_keep_candidate = helpers.should_keep_candidate
slugify_title = helpers.slugify_title
split_visible_lines = helpers.split_visible_lines
strip_html_fragment = helpers.strip_html_fragment
truncate_text = helpers.truncate_text
join_text = helpers.join_text
merge_candidate = helpers.merge_candidate


def load_sync_playwright() -> Any:
    from playwright.sync_api import sync_playwright  # type: ignore

    return sync_playwright


def playwright_import_missing_coverage(source: SourceConfig, terms: list[str], detail: str) -> Coverage:
    return partial_browser_unavailable_coverage(source, terms, f"Playwright is not installed; {detail}")


def playwright_browsers_missing_coverage(source: SourceConfig, terms: list[str], exc: BaseException) -> Coverage | None:
    message = normalize_whitespace(str(exc))
    lowered = message.lower()
    if "executable doesn't exist" not in lowered:
        return None
    if "playwright install" not in lowered and "chromium" not in lowered and "chrome-headless-shell" not in lowered:
        return None
    return partial_browser_unavailable_coverage(
        source,
        terms,
        "Playwright browser binaries are not installed; run ./.venv/bin/python -m playwright install chromium",
    )


def google_search_url(source: SourceConfig, term: str, page_num: int) -> str:
    params: list[tuple[str, str | int]] = [("q", term)]
    params.extend(("location", location) for location in google_location_filters(source))
    params.extend(("degree", normalize_google_degree_filter(degree)) for degree in google_degree_filters(source))
    if page_num > 1:
        params.append(("page", page_num))
    return f"{source.url}?{urlencode(params)}"


def google_location_filters(source: SourceConfig) -> list[str]:
    return source.filters.get("location") or list(GOOGLE_LOCATION_FILTERS)


def google_degree_filters(source: SourceConfig) -> list[str]:
    return source.filters.get("degree") or []


def normalize_google_degree_filter(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", value.lower())
    aliases = {
        "phd": "DOCTORATE",
        "doctorate": "DOCTORATE",
        "doctoral": "DOCTORATE",
    }
    return aliases.get(normalized, value)


def google_filter_note(source: SourceConfig) -> str:
    note_parts = [f"locations={', '.join(google_location_filters(source))}"]
    degree_filters = google_degree_filters(source)
    if degree_filters:
        note_parts.append(f"degree={', '.join(degree_filters)}")
    return " ".join(note_parts)


def meta_search_url(source: SourceConfig, term: str, page_num: int) -> str:
    del page_num
    base = urljoin(source.url.rstrip("/") + "/", "/jobsearch")
    return f"{base}?{urlencode({'q': term})}"


def extract_visible_text_section(text: str, headings: tuple[str, ...], stop_headings: tuple[str, ...]) -> str:
    return helpers.extract_visible_text_section(
        text,
        headings,
        stop_headings,
        ignored_lines=META_DETAIL_IGNORED_LINES,
    )


def extract_meta_detail_sections(detail_text: str) -> dict[str, str]:
    tasks = extract_visible_text_section(detail_text, META_TASK_HEADINGS, META_DETAIL_STOP_HEADINGS)
    minimum_qualifications = extract_visible_text_section(
        detail_text,
        META_MINIMUM_QUALIFICATION_HEADINGS,
        META_DETAIL_STOP_HEADINGS,
    )
    preferred_qualifications = extract_visible_text_section(
        detail_text,
        META_PREFERRED_QUALIFICATION_HEADINGS,
        META_DETAIL_STOP_HEADINGS,
    )
    qualifications = "; ".join(part for part in [minimum_qualifications, preferred_qualifications] if part)
    return {
        "tasks": tasks,
        "qualifications": qualifications,
    }


def apply_meta_detail_text(candidate: Candidate, detail_text: str, terms: list[str]) -> bool:
    sections = extract_meta_detail_sections(detail_text)
    detail_text_for_matching = " ".join(part for part in sections.values() if part)
    original_terms = list(candidate.matched_terms)
    if detail_text_for_matching:
        candidate.matched_terms = sorted(set(candidate.matched_terms + match_terms(detail_text_for_matching, terms)))

    original_notes = candidate.notes
    note_parts = [candidate.notes] if candidate.notes else []
    if sections["tasks"]:
        task_note = f"Tasks: {truncate_text(sections['tasks'], 260)}"
        if not candidate.notes or task_note not in candidate.notes:
            note_parts.append(task_note)
    if sections["qualifications"]:
        qualifications_note = f"Qualifications: {truncate_text(sections['qualifications'], 260)}"
        if not candidate.notes or qualifications_note not in candidate.notes:
            note_parts.append(qualifications_note)

    updated_notes = "; ".join(dict.fromkeys(part for part in note_parts if part))
    candidate.notes = updated_notes
    return candidate.notes != original_notes or candidate.matched_terms != original_terms


def enrich_meta_candidates(
    page: Any,
    candidates_by_url: dict[str, Candidate],
    terms: list[str],
    timeout_ms: int,
) -> BrowserEnrichmentResult:
    if not candidates_by_url:
        return BrowserEnrichmentResult()

    context = page.context
    browser_attr = getattr(context, "browser", None)
    browser = browser_attr() if callable(browser_attr) else browser_attr
    if browser is not None:
        detail_page = browser.new_page(viewport={"width": 1440, "height": 2200})
    else:
        detail_page = context.new_page()
    opened_pages = 0
    missing_detail_urls: list[str] = []

    try:
        for candidate in sorted(candidates_by_url.values(), key=lambda item: item.url):
            detail_page.goto(candidate.url, wait_until="domcontentloaded", timeout=timeout_ms)
            opened_pages += 1
            try:
                detail_page.wait_for_function(
                    """
                    () => {
                      const text = (document.body && document.body.innerText || '').toLowerCase();
                      return text.includes('responsibilities')
                        || text.includes('minimum qualifications')
                        || text.includes('preferred qualifications')
                        || text.includes('not logged in');
                    }
                    """,
                    timeout=5000,
                )
            except Exception:
                detail_page.wait_for_timeout(1000)
            detail_text = detail_page.locator("body").inner_text(timeout=5000)
            if not apply_meta_detail_text(candidate, detail_text, terms):
                missing_detail_urls.append(candidate.url)
    finally:
        detail_page.close()

    limitations: list[str] = []
    if missing_detail_urls:
        limitations.append(
            f"Meta detail page enrichment yielded no substantive role detail for {len(missing_detail_urls)} of {len(candidates_by_url)} matched roles"
        )

    return BrowserEnrichmentResult(
        direct_job_pages_opened=opened_pages,
        limitations=limitations,
    )


def google_public_job_url(source: SourceConfig, job_id: str, title: str) -> str:
    base = source.url.rstrip("/")
    if not job_id or job_id == "unknown":
        return base
    slug = slugify_title(title)
    if slug:
        return f"{base}/{job_id}-{slug}"
    return f"{base}/{job_id}"


def bosch_search_url(source: SourceConfig, term: str, page_num: int) -> str:
    del page_num
    return f"{source.url.rstrip('/')}/?{urlencode({'search': term})}"


def accept_bosch_cookies(page: Any) -> None:
    host = page.locator("dock-privacy-settings").first
    if not host.count():
        return
    host.evaluate(
        """
(el) => {
  const root = el.shadowRoot;
  const button = root && Array.from(root.querySelectorAll('button')).find(
    (candidate) => (candidate.innerText || '').includes('Alles akzeptieren')
  );
  if (button) button.click();
}
"""
    )
    page.wait_for_timeout(500)
    page.locator("dock-privacy-settings").evaluate_all(
        """
(elements) => {
  for (const element of elements) {
    element.remove();
  }
}
"""
    )
    page.wait_for_timeout(250)


def advance_bosch_results(page: Any, source: SourceConfig, term: str, page_num: int) -> bool:
    del source, term, page_num
    button = page.locator('button:has-text("Weitere Ergebnisse laden"), button:has-text("Load more results")').first
    if not button.count():
        return False
    before_count = page.locator('a[href*="/job/"][href*="searchTerm="]').count()
    button.scroll_into_view_if_needed(timeout=5000)
    button.evaluate("(element) => element.click()")
    for _ in range(12):
        page.wait_for_timeout(500)
        after_count = page.locator('a[href*="/job/"][href*="searchTerm="]').count()
        if after_count > before_count:
            return True
    return False


def accept_thales_cookies(page: Any) -> None:
    accept = page.get_by_role("button", name="Accept").first
    if accept.count():
        accept.click(timeout=5000)
        page.wait_for_timeout(500)
    page.locator('[ph-module="gdpr"]').evaluate_all(
        """
(elements) => {
  for (const element of elements) {
    element.remove();
  }
}
"""
    )
    page.wait_for_timeout(250)


def extract_google_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    scripts = page.locator("script").all_inner_texts()
    target = next((script for script in scripts if "key: 'ds:1'" in script and "data:" in script), None)
    if not target:
        return BrowserPageResult(
            candidates=[],
            raw_ids=[],
            visible_results=0,
            declared_total=None,
            page_signature=f"{term}:{page_num}:missing-ds1",
            limitations=["Google ds:1 payload not found in rendered page"],
        )
    match = re.search(r"data:(\[.*\]),\s*sideChannel:", target, re.DOTALL)
    if not match:
        return BrowserPageResult(
            candidates=[],
            raw_ids=[],
            visible_results=0,
            declared_total=None,
            page_signature=f"{term}:{page_num}:unparseable-ds1",
            limitations=["Google ds:1 payload could not be parsed"],
        )

    payload = json.loads(match.group(1))
    jobs = payload[0] if payload and isinstance(payload[0], list) else []
    candidates: list[Candidate] = []
    raw_ids: list[str] = []
    for job in jobs:
        if not isinstance(job, list) or len(job) < 10:
            continue
        job_id = join_text(job[0]) or join_text(job[2]) or "unknown"
        title = join_text(job[1]) or "unknown"
        apply_url = join_text(job[2]) or ""
        url = google_public_job_url(source, job_id, title) or apply_url or source.url
        responsibilities = strip_html_fragment(
            join_text(job[3][1] if len(job) > 3 and isinstance(job[3], list) and len(job[3]) > 1 else "")
        )
        requirements = strip_html_fragment(
            join_text(job[4][1] if len(job) > 4 and isinstance(job[4], list) and len(job[4]) > 1 else "")
        )
        employer = join_text(job[7] if len(job) > 7 else "") or source.source
        location_entries = job[9] if len(job) > 9 and isinstance(job[9], list) else []
        location = "; ".join(
            join_text(entry[0]) for entry in location_entries if isinstance(entry, list) and entry and join_text(entry[0])
        ) or "unknown"
        summary = strip_html_fragment(
            join_text(job[10][1] if len(job) > 10 and isinstance(job[10], list) and len(job[10]) > 1 else "")
        )
        working_location = strip_html_fragment(
            join_text(job[18][1] if len(job) > 18 and isinstance(job[18], list) and len(job[18]) > 1 else "")
        )
        searchable_text = " ".join(
            part for part in [title, employer, location, summary, responsibilities, requirements, working_location] if part
        )
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        raw_ids.append(job_id)
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue
        candidates.append(
            Candidate(
                employer=employer,
                title=title,
                url=url,
                source_url=source.url,
                alternate_url=apply_url if apply_url and apply_url != url else "",
                location=location,
                matched_terms=matched_terms,
                notes=(
                    f"Google browser search q='{term}' {google_filter_note(source)} "
                    f"page={page_num}; public overview URL synthesized from Google ds:1 payload"
                ),
            )
        )
    page_signature = ",".join(raw_ids[:10]) if raw_ids else f"{term}:{page_num}:empty"
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
    )


def extract_meta_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    links = page.locator('a[href^="/profile/job_details/"]')
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = urljoin(source.url, href)
        if not href or absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)

        lines = [line for line in split_visible_lines(element.inner_text()) if line != "⋅"]
        title = lines[0] if lines else "unknown"
        location = next((line for line in lines[1:] if "," in line or "Multiple Locations" in line), "unknown")
        searchable_text = " ".join(lines)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=f"Meta browser search q='{term}' page={page_num}",
            )
        )

    page_signature = f"{term}:{page_num}:{len(raw_ids)}:{','.join(raw_ids[:10])}" if raw_ids else f"{term}:{page_num}:empty"
    limitations: list[str] = []
    if not raw_ids:
        limitations.append(f"Meta browser search for '{term}' showed no visible job cards")
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
        limitations=limitations,
    )


def extract_helsing_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    del term
    links = page.locator('a[href^="/jobs/"]')
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = normalize_url_without_fragment(urljoin(source.url, href))
        if not href or absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)

        lines = split_visible_lines(element.inner_text())
        title = lines[0] if lines else "unknown"
        team = lines[1] if len(lines) > 1 else ""
        employment_type = lines[2] if len(lines) > 2 else ""
        location = lines[3] if len(lines) > 3 else "unknown"
        searchable_text = " ".join(part for part in [title, team, employment_type, location] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note = f"Helsing jobs page browser enumeration page={page_num}"
        if team:
            note = f"{note}; team={team}"
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=note,
            )
        )

    page_signature = ",".join(raw_ids[:10]) if raw_ids else f"helsing:{page_num}:empty"
    limitations: list[str] = []
    if not raw_ids:
        limitations.append("Helsing jobs page showed no visible job cards")
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
        limitations=limitations,
    )


def extract_asml_jobs(page: Any, source: SourceConfig, terms: list[str], page_num: int) -> BrowserPageResult:
    links = page.locator("a.search-results__item")
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = normalize_url_without_fragment(urljoin(source.url, href))
        if not href or absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)

        try:
            title = element.locator("h2").first.inner_text().strip() or "unknown"
            field_items = element.locator("ul.search-results__fields li")
            location = field_items.nth(0).inner_text().strip() if field_items.count() > 0 else "unknown"
            team = field_items.nth(1).inner_text().strip() if field_items.count() > 1 else ""
        except Exception:
            lines = [line for line in split_visible_lines(element.inner_text()) if line]
            while lines and lines[0].upper() == "NEW":
                lines.pop(0)
            title = lines[0] if lines else "unknown"
            location = lines[1] if len(lines) > 1 else "unknown"
            team = lines[2] if len(lines) > 2 else ""
        searchable_text = " ".join(part for part in [title, location, team] if part)
        matched_terms = sorted(set(match_terms(searchable_text, terms)))
        if not should_keep_candidate(title, matched_terms, searchable_text):
            continue

        note = f"ASML browser enumeration page={page_num}"
        if team:
            note = f"{note}; team={team}"
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=note,
            )
        )

    page_signature = ",".join(raw_ids[:10]) if raw_ids else f"asml:{page_num}:empty"
    limitations: list[str] = []
    if not raw_ids:
        limitations.append(f"ASML browser page {page_num} showed no visible job cards")
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=None,
        page_signature=page_signature,
        limitations=limitations,
    )


def dismiss_onetrust_banner(page: Any) -> None:
    def wait_for_results() -> None:
        try:
            page.wait_for_function(
                "() => document.querySelectorAll('a.search-results__item').length > 0",
                timeout=5000,
            )
        except Exception:
            page.wait_for_timeout(1000)

    reject_button = page.locator("#onetrust-reject-all-handler").first
    if reject_button.count():
        try:
            reject_button.click(timeout=3000)
            wait_for_results()
            return
        except Exception:
            pass
    accept_button = page.locator("#onetrust-accept-btn-handler").first
    if accept_button.count():
        try:
            accept_button.click(timeout=3000)
            wait_for_results()
            return
        except Exception:
            pass
    try:
        page.evaluate(
            """
            () => {
              const root = document.querySelector('#onetrust-consent-sdk');
              if (root) root.remove();
              document.querySelectorAll('.onetrust-pc-dark-filter').forEach((node) => node.remove());
            }
            """
        )
    except Exception:
        pass


def advance_meta_results(page: Any, source: SourceConfig, term: str, page_num: int) -> bool:
    del source, term, page_num
    button = page.get_by_role("button", name="Show more").first
    if not button.count():
        return False
    before_count = page.locator('a[href^="/profile/job_details/"]').count()
    button.scroll_into_view_if_needed(timeout=5000)
    button.click(timeout=5000)
    for _ in range(16):
        page.wait_for_timeout(500)
        after_count = page.locator('a[href^="/profile/job_details/"]').count()
        if after_count > before_count:
            return True
    return False


def advance_asml_results(page: Any, source: SourceConfig, page_num: int) -> bool:
    del source
    dismiss_onetrust_banner(page)
    next_button = page.locator('nav[aria-label="Pagination"] li.pagination-next button[role="link"]').first
    if not next_button.count():
        return False
    try:
        disabled = next_button.evaluate("(element) => Boolean(element.disabled)")
    except Exception:
        disabled = False
    if disabled:
        return False
    active_page = page.locator('nav[aria-label="Pagination"] li.pagination-link.active button[role="link"]').first
    current_page = active_page.inner_text().strip() if active_page.count() else ""
    current_first = ""
    first_card = page.locator("a.search-results__item").first
    if first_card.count():
        current_first = first_card.get_attribute("href") or ""
    next_button.click(timeout=5000)
    for _ in range(20):
        page.wait_for_timeout(500)
        active_page = page.locator('nav[aria-label="Pagination"] li.pagination-link.active button[role="link"]').first
        active_label = active_page.inner_text().strip() if active_page.count() else ""
        first_card = page.locator("a.search-results__item").first
        next_first = first_card.get_attribute("href") if first_card.count() else ""
        if active_label == str(page_num) and next_first != current_first:
            return True
        if current_page != active_label and active_label == str(page_num):
            return True
    return False


def discover_asml_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        sync_playwright = load_sync_playwright()
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "ASML browser discovery is scaffolded but inactive")

    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    pages_scanned = 0
    declared_total: int | None = None
    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    max_pages = 30

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="networkidle", timeout=timeout_ms)
            page.wait_for_timeout(1000)
            dismiss_onetrust_banner(page)
            count_label = page.locator(".pagination-results strong").first
            if count_label.count():
                count_text = re.sub(r"[^0-9]", "", count_label.inner_text())
                if count_text:
                    declared_total = int(count_text)

            page_num = 1
            while page_num <= max_pages:
                result = extract_asml_jobs(page, source, terms, page_num)
                pages_scanned += 1
                limitations.extend(result.limitations)
                for raw_id in result.raw_ids:
                    raw_seen_ids.add(raw_id)
                for candidate in result.candidates:
                    merge_candidate(candidates_by_url, candidate)
                if result.visible_results == 0:
                    break
                next_page_num = page_num + 1
                if next_page_num > max_pages:
                    limitations.append(f"ASML browser enumeration hit the page cap ({max_pages})")
                    break
                if not advance_asml_results(page, source, next_page_num):
                    break
                page_num = next_page_num
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned="unknown",
            search_terms_tried=terms,
            result_pages_scanned="unknown",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=[f"ASML browser discovery failed: {exc}"],
            candidates=[],
        )

    result_summary = (
        f"all_jobs={pages_scanned}p/{len(raw_seen_ids)}of{declared_total}"
        if declared_total is not None
        else f"all_jobs={pages_scanned}p/{len(raw_seen_ids)}"
    )
    status = "complete"
    if declared_total is not None and len(raw_seen_ids) < declared_total:
        status = "partial"
        limitations.append(f"ASML browser enumeration surfaced {len(raw_seen_ids)} of {declared_total} jobs")
    elif any("page cap" in limitation.lower() for limitation in limitations):
        status = "partial"

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
        result_pages_scanned=result_summary,
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def extract_bosch_jobs(page: Any, source: SourceConfig, term: str, terms: list[str], page_num: int) -> BrowserPageResult:
    del page_num
    body_text = page.locator("body").inner_text()
    count_match = re.search(r"(\d+)\s+passende Jobs gefunden", body_text)
    declared_total = int(count_match.group(1)) if count_match else None
    links = page.locator('a[href*="/job/"][href*="searchTerm="]')
    visible_count = links.count()
    raw_ids: list[str] = []
    candidates: list[Candidate] = []
    seen_urls: set[str] = set()

    for index in range(visible_count):
        element = links.nth(index)
        href = element.get_attribute("href") or ""
        absolute_url = urljoin(source.url, href)
        if absolute_url in seen_urls:
            continue
        seen_urls.add(absolute_url)
        raw_ids.append(absolute_url)
        text = element.inner_text().strip()
        title = re.split(r"\s+(?:Standort|Location):", text, maxsplit=1)[0].strip() or "unknown"
        location_match = re.search(r"(?:Standort|Location):\s*(.*?)(?:\s+Arbeitsbereich:|\s+Job veröffentlicht|\s+Job posted|$)", text)
        location = location_match.group(1).strip() if location_match else "unknown"
        matched_terms = sorted(set(match_terms(text, terms)))
        if not should_keep_candidate(title, matched_terms, text):
            continue
        candidates.append(
            Candidate(
                employer=source.source,
                title=title,
                url=absolute_url,
                source_url=source.url,
                location=location,
                matched_terms=matched_terms,
                notes=f"Bosch browser search q='{term}'",
            )
        )

    page_signature = f"{len(raw_ids)}:{','.join(raw_ids[-10:])}" if raw_ids else f"{term}:empty"
    return BrowserPageResult(
        candidates=candidates,
        raw_ids=raw_ids,
        visible_results=len(raw_ids),
        declared_total=declared_total,
        page_signature=page_signature,
    )


def discover_trailofbits_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        sync_playwright = load_sync_playwright()
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Trail of Bits browser discovery is unavailable")

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2000)
            links = page.locator('a[href*="apply.workable.com"]')
            count = links.count()
            for index in range(count):
                element = links.nth(index)
                href = normalize_url_without_fragment(element.get_attribute("href") or "")
                if not href or href in raw_urls:
                    continue
                raw_urls.add(href)
                lines = split_visible_lines(element.inner_text())
                title = lines[0] if lines else "unknown"
                searchable_text = " ".join(lines) or title
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=href,
                        source_url=source.url,
                        matched_terms=matched_terms,
                        notes="Enumerated through Trail of Bits career-page Workable links",
                    ),
                )
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

    limitations = []
    if not raw_urls:
        limitations.append("No Workable job links were visible on the Trail of Bits careers page.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete" if raw_urls else "partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="career_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_automattic_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        sync_playwright = load_sync_playwright()
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Automattic browser discovery is unavailable")

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    raw_urls: set[str] = set()
    candidates_by_url: dict[str, Candidate] = {}

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(2000)
            links = page.locator('a[href*="/work-with-us/job/"]')
            count = links.count()
            for index in range(count):
                element = links.nth(index)
                href = normalize_url_without_fragment(element.get_attribute("href") or "")
                if not href or href in raw_urls:
                    continue
                raw_urls.add(href)
                lines = split_visible_lines(element.inner_text())
                title = lines[0] if lines else "unknown"
                searchable_text = " ".join(lines) or title
                matched_terms = sorted(set(match_terms(searchable_text, terms)))
                if not should_keep_candidate(title, matched_terms, searchable_text):
                    continue
                merge_candidate(
                    candidates_by_url,
                    Candidate(
                        employer=source.source,
                        title=title,
                        url=href,
                        source_url=source.url,
                        matched_terms=matched_terms,
                        notes="Enumerated through Automattic jobs-page cards",
                    ),
                )
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

    limitations = []
    if not raw_urls:
        limitations.append("No Automattic job-detail links were visible on the jobs page.")
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="complete" if raw_urls else "partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="jobs_page=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(raw_urls),
        matched_jobs=len(candidates_by_url),
        limitations=limitations,
        candidates=list(candidates_by_url.values()),
    )


def discover_coinbase_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        sync_playwright = load_sync_playwright()
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Coinbase browser discovery is unavailable")

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_timeout(10000)
            title = page.title()
            body_text = normalize_whitespace(page.locator("body").inner_text())
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

    if "performing security verification" in body_text.lower() or title.lower() == "just a moment...":
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned=1,
            search_terms_tried=terms,
            result_pages_scanned="challenge_page=1",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=["Cloudflare challenge blocked automated access to Coinbase careers listings."],
            candidates=[],
        )

    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status="partial",
        listing_pages_scanned=1,
        search_terms_tried=terms,
        result_pages_scanned="browser_probe=1",
        direct_job_pages_opened=0,
        enumerated_jobs=0,
        matched_jobs=0,
        limitations=["Coinbase careers loaded, but no deterministic job-listing extraction path is implemented yet."],
        candidates=[],
    )


def discover_thales_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        sync_playwright = load_sync_playwright()
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Thales browser discovery is unavailable")

    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    term_summaries: list[str] = []
    total_pages_scanned = 0

    def extract_page(page: Any, term: str) -> BrowserPageResult:
        body_text = page.locator("body").inner_text()
        count_match = re.search(r"Showing\s+\d+\s*-\s*\d+\s+of\s+(\d+)\s+results?", body_text)
        declared_total = int(count_match.group(1)) if count_match else None
        links = page.locator('a[href*="/global/en/job/"]')
        visible_count = links.count()
        raw_ids: list[str] = []
        candidates: list[Candidate] = []
        seen_urls: set[str] = set()

        for index in range(visible_count):
            element = links.nth(index)
            href = element.get_attribute("href") or ""
            absolute_url = urljoin(source.url, href)
            if absolute_url in seen_urls:
                continue
            seen_urls.add(absolute_url)
            raw_ids.append(absolute_url)
            title = element.inner_text().strip() or "unknown"
            card_text = element.evaluate(
                """
(el) => {
  let node = el;
  while (node && node.parentElement && (!node.innerText || node.innerText.length < 220)) {
    node = node.parentElement;
  }
  return (node && node.innerText) ? node.innerText : (el.innerText || '');
}
"""
            )
            matched_terms = sorted(set(match_terms(card_text, terms)))
            if not should_keep_candidate(title, matched_terms, card_text):
                continue
            location_match = re.search(r"Work Location\\s+(.+?)(?:\\s+Join our team|\\s+Save|$)", card_text, flags=re.DOTALL)
            location = re.sub(r"\\s+", " ", location_match.group(1)).strip() if location_match else "unknown"
            candidates.append(
                Candidate(
                    employer=source.source,
                    title=title,
                    url=absolute_url,
                    source_url=source.url,
                    location=location,
                    matched_terms=matched_terms,
                    notes=f"Enumerated through Thales browser pagination for '{term}'",
                )
            )

        page_signature = ",".join(raw_ids[:10]) if raw_ids else f"{term}:empty"
        return BrowserPageResult(
            candidates=candidates,
            raw_ids=raw_ids,
            visible_results=len(raw_ids),
            declared_total=declared_total,
            page_signature=page_signature,
        )

    timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            for term in terms:
                search_url = f"{source.url}?{urlencode({'keywords': term})}"
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
                accept_thales_cookies(page)
                page.wait_for_timeout(1000)

                term_pages_scanned = 0
                term_visible_total = 0
                term_declared_total: int | None = None
                term_page_signatures: set[str] = set()

                while True:
                    result = extract_page(page, term)
                    if not result.page_signature or result.page_signature in term_page_signatures:
                        break
                    term_page_signatures.add(result.page_signature)
                    total_pages_scanned += 1
                    term_pages_scanned += 1
                    term_visible_total += result.visible_results
                    if term_declared_total is None and result.declared_total is not None:
                        term_declared_total = result.declared_total
                    for raw_id in result.raw_ids:
                        raw_seen_ids.add(raw_id)
                    for candidate in result.candidates:
                        merge_candidate(candidates_by_url, candidate)
                    if result.visible_results == 0:
                        break
                    if term_declared_total is not None and term_visible_total >= term_declared_total:
                        break
                    next_link = page.locator('a[data-ph-at-id="pagination-next-link"]').first
                    if not next_link.count():
                        break
                    next_href = next_link.get_attribute("href")
                    if not next_href:
                        break
                    page.goto(next_href, wait_until="domcontentloaded", timeout=timeout_ms)
                    accept_thales_cookies(page)
                    page.wait_for_timeout(1000)

                term_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}of{term_declared_total or 0}")
                if term_declared_total is not None and term_visible_total < term_declared_total:
                    limitations.append(
                        f"Thales browser search for '{term}' surfaced {term_visible_total} of {term_declared_total} results"
                    )

            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        raise

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


def discover_helsing_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        sync_playwright = load_sync_playwright()
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "Helsing browser discovery is unavailable")

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            page.goto(source.url, wait_until="domcontentloaded", timeout=max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS))
            page.wait_for_timeout(3000)
            result = extract_helsing_jobs(page, source, "catalog", terms, 1)
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, terms, exc)
        if setup_issue is not None:
            return setup_issue
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned="unknown",
            search_terms_tried=terms,
            result_pages_scanned="unknown",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=[f"Helsing browser discovery failed: {type(exc).__name__}: {exc}"],
            candidates=[],
        )

    status = "complete" if result.raw_ids else "partial"
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
        result_pages_scanned="catalog=1",
        direct_job_pages_opened=0,
        enumerated_jobs=len(result.raw_ids),
        matched_jobs=len(result.candidates),
        limitations=result.limitations,
        candidates=result.candidates,
    )


BROWSER_STRATEGIES = {
    "Bosch": BrowserStrategy(
        search_url_builder=bosch_search_url,
        extract_page=extract_bosch_jobs,
        prepare_page=accept_bosch_cookies,
        advance_page=advance_bosch_results,
        supports_pagination=True,
        cumulative_results=True,
        max_pages=30,
    ),
    "Google": BrowserStrategy(
        search_url_builder=google_search_url,
        extract_page=extract_google_jobs,
        override_terms=("cryptography",),
        supports_pagination=True,
        page_size=GOOGLE_RESULTS_PAGE_SIZE,
        max_pages=MAX_BROWSER_PAGES,
    ),
    "Meta": BrowserStrategy(
        search_url_builder=meta_search_url,
        extract_page=extract_meta_jobs,
        advance_page=advance_meta_results,
        enrich_candidates=enrich_meta_candidates,
        supports_pagination=True,
        cumulative_results=True,
        max_pages=10,
    ),
}


def discover_browser(source: SourceConfig, terms: list[str], timeout_seconds: int) -> Coverage:
    try:
        sync_playwright = load_sync_playwright()
    except ImportError:
        return playwright_import_missing_coverage(source, terms, "browser-mode discovery is scaffolded but inactive")
    strategy = BROWSER_STRATEGIES.get(source.source)
    if not strategy:
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned="unknown",
            search_terms_tried=terms,
            result_pages_scanned="unknown",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=[f"No browser strategy is implemented yet for {source.source}"],
            candidates=[],
        )

    candidates_by_url: dict[str, Candidate] = {}
    raw_seen_ids: set[str] = set()
    limitations: list[str] = []
    result_summaries: list[str] = []
    pages_scanned = 0
    status = "complete"
    effective_terms = list(strategy.override_terms) if strategy.override_terms else terms
    direct_job_pages_opened = 0

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 2200})
            timeout_ms = max(timeout_seconds * 1000, DEFAULT_BROWSER_TIMEOUT_MS)
            for term in effective_terms:
                search_url = strategy.search_url_builder(source, term, 1)
                page.goto(search_url, wait_until="domcontentloaded", timeout=timeout_ms)
                if strategy.prepare_page:
                    strategy.prepare_page(page)
                page.wait_for_timeout(1000)
                term_page_signatures: set[str] = set()
                term_pages_scanned = 0
                term_visible_total = 0
                term_declared_total: int | None = None
                term_hit_page_cap = False
                page_num = 1
                while page_num <= strategy.max_pages:
                    result = strategy.extract_page(page, source, term, terms, page_num)
                    if not result.page_signature or result.page_signature in term_page_signatures:
                        break
                    term_pages_scanned += 1
                    pages_scanned += 1
                    if strategy.cumulative_results:
                        term_visible_total = max(term_visible_total, result.visible_results)
                    else:
                        term_visible_total += result.visible_results
                    if term_declared_total is None and result.declared_total is not None:
                        term_declared_total = result.declared_total
                    limitations.extend(result.limitations)
                    for raw_id in result.raw_ids:
                        raw_seen_ids.add(raw_id)
                    for candidate in result.candidates:
                        merge_candidate(candidates_by_url, candidate)
                    term_page_signatures.add(result.page_signature)
                    if result.visible_results == 0:
                        break
                    if term_declared_total is not None and term_visible_total >= term_declared_total:
                        break
                    if not strategy.supports_pagination:
                        break
                    if strategy.page_size is not None and not strategy.cumulative_results and result.visible_results < strategy.page_size:
                        break
                    next_page_num = page_num + 1
                    if next_page_num > strategy.max_pages:
                        term_hit_page_cap = True
                        break
                    if strategy.advance_page:
                        if not strategy.advance_page(page, source, term, next_page_num):
                            break
                    else:
                        next_url = strategy.search_url_builder(source, term, next_page_num)
                        page.goto(next_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        if strategy.prepare_page:
                            strategy.prepare_page(page)
                        page.wait_for_timeout(1000)
                    page_num = next_page_num
                if term_declared_total is not None:
                    result_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}of{term_declared_total}")
                    if term_visible_total < term_declared_total:
                        status = "partial"
                        limitations.append(
                            f"{source.source} browser search for '{term}' surfaced {term_visible_total} of {term_declared_total} results"
                        )
                else:
                    result_summaries.append(f"{term}={term_pages_scanned}p/{term_visible_total}")
                if term_hit_page_cap and (term_declared_total is None or term_visible_total < term_declared_total):
                    status = "partial"
                    limitations.append(f"{source.source} browser search for '{term}' hit the page cap ({strategy.max_pages})")
            if strategy.enrich_candidates:
                enrichment = strategy.enrich_candidates(page, candidates_by_url, terms, timeout_ms)
                direct_job_pages_opened += enrichment.direct_job_pages_opened
                if enrichment.limitations:
                    limitations.extend(enrichment.limitations)
            browser.close()
    except Exception as exc:  # pragma: no cover - defensive output for live runs
        setup_issue = playwright_browsers_missing_coverage(source, effective_terms, exc)
        if setup_issue is not None:
            return setup_issue
        return Coverage(
            source=source.source,
            source_url=source.url,
            discovery_mode=source.discovery_mode,
            cadence_group=source.cadence_group,
            last_checked=source.last_checked,
            due_today=False,
            status="partial",
            listing_pages_scanned="unknown",
            search_terms_tried=effective_terms,
            result_pages_scanned="unknown",
            direct_job_pages_opened=0,
            enumerated_jobs=0,
            matched_jobs=0,
            limitations=[f"Browser discovery failed: {type(exc).__name__}: {exc}"],
            candidates=[],
        )

    deduped_limitations = list(dict.fromkeys(limitations))
    return Coverage(
        source=source.source,
        source_url=source.url,
        discovery_mode=source.discovery_mode,
        cadence_group=source.cadence_group,
        last_checked=source.last_checked,
        due_today=False,
        status=status,
        listing_pages_scanned=pages_scanned,
        search_terms_tried=effective_terms,
        result_pages_scanned=", ".join(result_summaries) if result_summaries else "none",
        direct_job_pages_opened=direct_job_pages_opened,
        enumerated_jobs=len(raw_seen_ids),
        matched_jobs=len(candidates_by_url),
        limitations=deduped_limitations,
        candidates=list(candidates_by_url.values()),
    )


SOURCES = [
    SourceAdapter(modes=("asml_browser",), discover=discover_asml_browser, requires=("playwright.sync_api",)),
    SourceAdapter(modes=("automattic_browser",), discover=discover_automattic_browser, requires=("playwright.sync_api",)),
    SourceAdapter(modes=("browser",), discover=discover_browser, requires=("playwright.sync_api",)),
    SourceAdapter(modes=("coinbase_browser",), discover=discover_coinbase_browser, requires=("playwright.sync_api",)),
    SourceAdapter(modes=("helsing_browser",), discover=discover_helsing_browser, requires=("playwright.sync_api",)),
    SourceAdapter(modes=("thales_browser",), discover=discover_thales_browser, requires=("playwright.sync_api",)),
    SourceAdapter(modes=("trailofbits_browser",), discover=discover_trailofbits_browser, requires=("playwright.sync_api",)),
]
